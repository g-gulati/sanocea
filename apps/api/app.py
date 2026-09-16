from __future__ import annotations

import os
import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi import Body, Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from sanocea.packages.audit.context import reset_correlation_id, set_correlation_id
from sanocea.packages.authn import AuthContext, require_operator, require_service
from sanocea.packages.domain_contract.credentials import build_production_credential_provider
from sanocea.packages.domain_contract.postgres_store import PostgresStore
from sanocea.packages.domain_contract.store import Phase0Store
from sanocea.packages.object_storage import S3ObjectStorage
from sanocea.packages.onboarding.merchant import ConfigValidationError, MerchantOnboardingService
from sanocea.packages.runtime import ChannelMismatchError, Services, UnknownStorefrontChannelError, build_service_graph, commands, queries
from sanocea.workers.workflow.temporal_runtime import TemporalRuntime


class CorrelationMiddleware(BaseHTTPMiddleware):
    """Phase 4.5: the correlation id is not just an HTTP response header - it is set into a contextvar
    (packages.audit.context) for the lifetime of the request, so every AuditEvent/ExceptionRecord
    written by any domain service called during this request automatically carries it, with zero
    changes to those services' own code."""

    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get("x-correlation-id", f"corr_{uuid4().hex}")
        request.state.correlation_id = correlation_id
        token = set_correlation_id(correlation_id)
        try:
            response = await call_next(request)
        finally:
            reset_correlation_id(token)
        response.headers["x-correlation-id"] = correlation_id
        return response


def _build_store() -> Phase0Store | PostgresStore:
    if os.environ.get("SANOCEA_USE_IN_MEMORY_STORE") == "1":
        return Phase0Store()
    dsn = os.environ.get("SANOCEA_PG_DSN")
    if not dsn:
        raise RuntimeError("SANOCEA_PG_DSN is required. Set SANOCEA_USE_IN_MEMORY_STORE=1 only for unit harnesses.")
    # Step P0.1 - the real (non-in-memory) path ALWAYS uses durable, encrypted-at-rest credential
    # storage; there is no configuration flag to opt back into the development EnvCredentialProvider
    # here. This raises MissingMasterKeyError immediately, before the process ever accepts a request, if
    # SANOCEA_CRED_MASTER_KEY_CURRENT/SANOCEA_CRED_MASTER_KEY_<VERSION> are not configured - a silent
    # fallback to non-durable, unencrypted credential storage in production is exactly what this must
    # never do.
    credential_provider = build_production_credential_provider(dsn)
    store = PostgresStore(dsn, credential_provider=credential_provider)
    store.migrate()
    return store


def create_app(
    store: Phase0Store | PostgresStore | None = None,
    *,
    extra_storefront_factories=None,
) -> FastAPI:
    """`extra_storefront_factories` registers additional storefront channel types beyond the built-in
    "shopify"/"woocommerce" (see packages/runtime/service_graph.py::build_service_graph) - defaults to
    None, adding nothing, so every existing caller's behavior is unchanged. Which platform a given
    merchant actually uses is resolved per-request from that merchant's own Channel/credentials (see
    packages/runtime/storefront_registry.py) - never fixed at app-construction time - so ONE app
    instance can serve a Shopify merchant and a WooCommerce merchant simultaneously."""
    if store is None:
        store = _build_store()

    graph = build_service_graph(store, extra_storefront_factories=extra_storefront_factories)
    services = graph.services

    app = FastAPI(title="Sanocea Commerce OS")
    app.add_middleware(CorrelationMiddleware)
    app.state.store = store
    app.state.workflow = graph.order_orchestrator
    app.state.storefronts = graph.storefronts
    app.state.chatwoot = graph.chatwoot
    app.state.logistics = graph.logistics
    app.state.payments = graph.payments
    app.state.suppliers = graph.suppliers
    app.state.services = services

    def get_services(request: Request) -> Services:
        return request.app.state.services

    # ================================================================================================
    # Health / merchants (unauthenticated - operational, no tenant data exposed)
    # ================================================================================================

    @app.get("/health")
    async def health() -> dict[str, str]:
        status = {"api": "ok"}
        dsn = os.environ.get("SANOCEA_PG_DSN")
        if dsn:
            try:
                status.update(PostgresStore(dsn).health())
            except Exception as exc:
                status["postgres"] = f"error:{type(exc).__name__}"
        # Connectivity probe only (Phase 4.6 decision - see TemporalRuntime's docstring): no order,
        # support, finance, or procurement path routes through Temporal. Absence/failure here never
        # implies degraded business functionality.
        temporal_target = os.environ.get("SANOCEA_TEMPORAL_TARGET")
        if temporal_target:
            try:
                status.update(await TemporalRuntime(temporal_target).health())
            except Exception as exc:
                status["temporal"] = f"error:{type(exc).__name__}"
        if os.environ.get("SANOCEA_S3_BUCKET"):
            try:
                storage = S3ObjectStorage(
                    endpoint_url=os.environ.get("SANOCEA_S3_ENDPOINT"),
                    access_key_id=os.environ["SANOCEA_S3_ACCESS_KEY"],
                    secret_access_key=os.environ["SANOCEA_S3_SECRET_KEY"],
                    bucket=os.environ["SANOCEA_S3_BUCKET"],
                )
                status.update(storage.health())
            except Exception as exc:
                status["object_storage"] = f"error:{type(exc).__name__}"
        return status

    @app.get("/merchants")
    def merchants(ctx: AuthContext = Depends(require_service)) -> list[dict]:
        # Phase 4.6 fix: this used to call store.list(Merchant, "system"), which always returned an
        # empty list - every real Merchant row's own merchant_id equals its own id (see
        # MerchantOnboardingService.onboard), never the literal string "system", so this route was
        # silently dead code (no test exercised it either). list_all_merchants() is the correct,
        # deliberate cross-tenant enumeration - and, since it now returns real data across every
        # tenant, this route is gated behind require_service like every other cross-tenant surface.
        return [m.model_dump(mode="json") for m in store.list_all_merchants()]

    # ================================================================================================
    # Webhooks (events) - authenticated via per-merchant HMAC signature, not a bearer token. An invalid
    # signature is rejected (401) BEFORE any canonical mutation - ShopifyConnector._verify_hmac raises
    # PermissionError first thing inside ingest_webhook, before any raw payload is even persisted.
    # ================================================================================================

    # chatwoot MUST be registered BEFORE the generic storefront route below - both match the same
    # /webhooks/{segment}/{merchant_id} URL shape, and Starlette matches routes in registration order.
    # Chatwoot is the support channel, never a storefront platform, so it is intentionally NOT part of
    # the StorefrontConnectorRegistry.
    @app.post("/webhooks/chatwoot/{merchant_id}")
    async def chatwoot_webhook(merchant_id: str, request: Request) -> dict:
        body = await request.body()
        try:
            return graph.chatwoot.ingest_webhook(merchant_id, dict(request.headers), body)
        except PermissionError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/webhooks/{channel_type}/{merchant_id}")
    async def storefront_webhook(channel_type: str, merchant_id: str, request: Request) -> dict:
        body = await request.body()
        try:
            # resolve_expect enforces that THIS merchant is actually configured for THIS channel_type -
            # a webhook arriving at the wrong platform's URL for a given merchant (or a merchant with no
            # storefront channel configured at all) is refused outright, never silently routed to
            # whichever connector happens to be cached or falls back to a default.
            connector = graph.storefronts.resolve_expect(merchant_id, channel_type)
            return connector.ingest_webhook(merchant_id, dict(request.headers), body)
        except (ChannelMismatchError, UnknownStorefrontChannelError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # ================================================================================================
    # Admin (service auth only) - API key issuance. Bootstrapped from an env-configured master service
    # key so the very first key can be minted without a chicken-and-egg problem.
    # ================================================================================================

    @app.post("/admin/api-keys")
    def create_api_key(payload: dict = Body(...), ctx: AuthContext = Depends(require_service)) -> dict:
        merchant_id = payload.get("merchant_id")
        role = payload.get("role", "operator")
        if role not in {"operator", "service"}:
            raise HTTPException(status_code=400, detail="role must be 'operator' or 'service'")
        if role == "operator" and not merchant_id:
            raise HTTPException(status_code=400, detail="operator keys must be scoped to a merchant_id")
        key_id, raw_key = store.create_api_key(merchant_id=merchant_id, role=role, label=payload.get("label"))
        return {"key_id": key_id, "api_key": raw_key, "role": role, "merchant_id": merchant_id}

    @app.post("/admin/merchants")
    def onboard_merchant(payload: dict = Body(...), ctx: AuthContext = Depends(require_service)) -> dict:
        """Phase 4.5 onboarding v2, reachable through the running application (not a direct-service
        bypass) - config + credentials + supplier/SKU mappings, validated before activation."""
        onboarding = MerchantOnboardingService(store)
        try:
            result = onboarding.onboard(
                payload["merchant_id"], payload["display_name"],
                config=payload.get("config", {}), credentials=payload.get("credentials", {}),
                channels=payload.get("channels"), suppliers=payload.get("suppliers"),
                procurement_service=graph.procurement,
            )
        except ConfigValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "merchant_id": result.merchant_id,
            "config_sections_set": result.config_sections_set,
            "channels_created": result.channels_created,
            "credentials_set": result.credentials_set,
            "suppliers_created": result.suppliers_created,
            "supplier_offers_created": result.supplier_offers_created,
            "operator_api_key_id": result.operator_api_key_id,
            "operator_api_key": result.operator_api_key,
            "validation_warnings": result.validation_warnings,
        }

    # ================================================================================================
    # Queries (operator-scoped, read-only)
    # ================================================================================================

    @app.get("/merchants/{merchant_id}/operator/summary")
    def operator_summary(merchant_id: str, ctx: AuthContext = Depends(require_operator)) -> dict:
        return queries.operator_summary(store, merchant_id)

    @app.get("/merchants/{merchant_id}/orders")
    def list_orders(merchant_id: str, ctx: AuthContext = Depends(require_operator)) -> list[dict]:
        return [o.model_dump(mode="json") for o in queries.list_orders(store, merchant_id)]

    @app.get("/merchants/{merchant_id}/orders/{order_id}")
    def get_order(merchant_id: str, order_id: str, ctx: AuthContext = Depends(require_operator)) -> dict:
        return queries.get_order(store, merchant_id, order_id).model_dump(mode="json")

    @app.get("/merchants/{merchant_id}/inventory")
    def list_inventory(merchant_id: str, ctx: AuthContext = Depends(require_operator)) -> list[dict]:
        return [i.model_dump(mode="json") for i in queries.list_inventory(store, merchant_id)]

    @app.get("/merchants/{merchant_id}/shipments")
    def list_shipments(merchant_id: str, ctx: AuthContext = Depends(require_operator)) -> list[dict]:
        return [s.model_dump(mode="json") for s in queries.list_shipments(store, merchant_id)]

    @app.get("/merchants/{merchant_id}/returns")
    def list_returns(merchant_id: str, ctx: AuthContext = Depends(require_operator)) -> list[dict]:
        return [r.model_dump(mode="json") for r in queries.list_returns(store, merchant_id)]

    @app.get("/merchants/{merchant_id}/exchanges")
    def list_exchanges(merchant_id: str, ctx: AuthContext = Depends(require_operator)) -> list[dict]:
        return [e.model_dump(mode="json") for e in queries.list_exchanges(store, merchant_id)]

    @app.get("/merchants/{merchant_id}/refunds")
    def list_refunds(merchant_id: str, ctx: AuthContext = Depends(require_operator)) -> list[dict]:
        return queries.list_refunds_full_state(store, merchant_id)

    @app.get("/merchants/{merchant_id}/refunds/{refund_id}")
    def get_refund(merchant_id: str, refund_id: str, ctx: AuthContext = Depends(require_operator)) -> dict:
        return queries.get_refund_full_state(store, merchant_id, refund_id)

    @app.get("/merchants/{merchant_id}/payments")
    def list_payments(merchant_id: str, ctx: AuthContext = Depends(require_operator)) -> list[dict]:
        return [p.model_dump(mode="json") for p in queries.list_payments(store, merchant_id)]

    @app.get("/merchants/{merchant_id}/finance/reconciliations")
    def list_finance_reconciliations(merchant_id: str, ctx: AuthContext = Depends(require_operator)) -> list[dict]:
        return [r.model_dump(mode="json") for r in queries.list_finance_reconciliations(store, merchant_id)]

    @app.get("/merchants/{merchant_id}/suppliers")
    def list_suppliers(merchant_id: str, ctx: AuthContext = Depends(require_operator)) -> list[dict]:
        return [s.model_dump(mode="json") for s in queries.list_suppliers(store, merchant_id)]

    @app.get("/merchants/{merchant_id}/purchase-orders")
    def list_purchase_orders(merchant_id: str, ctx: AuthContext = Depends(require_operator)) -> list[dict]:
        return [p.model_dump(mode="json") for p in queries.list_purchase_orders(store, merchant_id)]

    @app.get("/merchants/{merchant_id}/goods-receipts")
    def list_goods_receipts(merchant_id: str, ctx: AuthContext = Depends(require_operator)) -> list[dict]:
        return [g.model_dump(mode="json") for g in queries.list_goods_receipts(store, merchant_id)]

    @app.get("/merchants/{merchant_id}/approvals")
    def list_approvals(merchant_id: str, ctx: AuthContext = Depends(require_operator)) -> list[dict]:
        return [a.model_dump(mode="json") for a in queries.list_open_approvals(store, merchant_id)]

    @app.get("/merchants/{merchant_id}/exceptions")
    def list_exceptions(merchant_id: str, ctx: AuthContext = Depends(require_operator)) -> list[dict]:
        return [e.model_dump(mode="json") for e in queries.list_open_exceptions(store, merchant_id)]

    @app.get("/merchants/{merchant_id}/audit")
    def list_audit_events(merchant_id: str, correlation_id: str | None = None, ctx: AuthContext = Depends(require_operator)) -> list[dict]:
        return [e.model_dump(mode="json") for e in queries.get_audit_trail(store, merchant_id, correlation_id=correlation_id)]

    @app.get("/merchants/{merchant_id}/profile")
    def get_merchant_profile(merchant_id: str, ctx: AuthContext = Depends(require_operator)) -> dict:
        from sanocea.packages.domain_contract.models import Merchant
        merchant = store.get(Merchant, merchant_id, merchant_id)
        config = store.get_config(merchant_id)
        return {
            "id": merchant.id if merchant else merchant_id,
            "legal_name": merchant.legal_name if merchant else None,
            "display_name": merchant.display_name if merchant else merchant_id,
            "config": config,
        }

    @app.get("/merchants/{merchant_id}/connector-commands/uncertain")
    def list_uncertain_commands(merchant_id: str, ctx: AuthContext = Depends(require_operator)) -> list[dict]:
        return [c.model_dump(mode="json") for c in queries.list_uncertain_connector_commands(store, merchant_id)]

    @app.get("/merchants/{merchant_id}/connector-commands/failed")
    def list_failed_commands(merchant_id: str, ctx: AuthContext = Depends(require_operator)) -> list[dict]:
        return [c.model_dump(mode="json") for c in queries.list_failed_connector_commands(store, merchant_id)]

    # ================================================================================================
    # Commands (operator-scoped, state-changing) - thin dispatch into packages.runtime.commands, which
    # dispatches into the existing domain services. No business logic here.
    # ================================================================================================

    @app.post("/merchants/{merchant_id}/refunds")
    def request_refund(merchant_id: str, payload: dict = Body(...), ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> dict:
        return commands.request_refund(services, merchant_id, payload["order_id"], int(payload["amount"])).model_dump(mode="json")

    @app.post("/merchants/{merchant_id}/refunds/{refund_id}/approve")
    def approve_refund(merchant_id: str, refund_id: str, ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> dict:
        return commands.approve_refund(services, merchant_id, refund_id, ctx.principal_id).model_dump(mode="json")

    @app.post("/merchants/{merchant_id}/refunds/{refund_id}/execute")
    def execute_refund(merchant_id: str, refund_id: str, payload: dict = Body(default={}), ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> dict:
        return commands.execute_refund(services, merchant_id, refund_id, reason=payload.get("reason", "customer_refund"), simulate=payload.get("simulate")).model_dump(mode="json")

    @app.post("/merchants/{merchant_id}/refunds/{refund_id}/recover")
    def recover_refund_mutation(merchant_id: str, refund_id: str, ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> dict:
        return commands.recover_refund_mutation(services, merchant_id, refund_id).model_dump(mode="json")

    @app.post("/merchants/{merchant_id}/returns")
    def request_return(merchant_id: str, payload: dict = Body(...), ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> dict:
        return commands.request_return(services, merchant_id, payload["order_id"], payload["reason"]).model_dump(mode="json")

    @app.post("/merchants/{merchant_id}/returns/{return_id}/progress")
    def progress_return(merchant_id: str, return_id: str, payload: dict = Body(...), ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> dict:
        return commands.progress_return(services, merchant_id, return_id, payload["event"]).model_dump(mode="json")

    @app.post("/merchants/{merchant_id}/exchanges")
    def request_exchange(merchant_id: str, payload: dict = Body(...), ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> dict:
        return commands.request_exchange(services, merchant_id, payload["order_id"], payload["requested_variant_sku"], simulate=payload.get("simulate")).model_dump(mode="json")

    @app.post("/merchants/{merchant_id}/exchanges/{exchange_id}/complete")
    def complete_exchange(merchant_id: str, exchange_id: str, ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> dict:
        return commands.complete_exchange(services, merchant_id, exchange_id).model_dump(mode="json")

    @app.post("/merchants/{merchant_id}/cancellations")
    def request_cancellation(merchant_id: str, payload: dict = Body(...), ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> dict:
        return commands.request_cancellation(services, merchant_id, payload["order_id"]).model_dump(mode="json")

    @app.post("/merchants/{merchant_id}/cancellations/{cancellation_id}/approve")
    def approve_cancellation(merchant_id: str, cancellation_id: str, ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> dict:
        return commands.approve_cancellation(services, merchant_id, cancellation_id, ctx.principal_id).model_dump(mode="json")

    @app.post("/merchants/{merchant_id}/cancellations/{cancellation_id}/reject")
    def reject_cancellation(merchant_id: str, cancellation_id: str, payload: dict = Body(default={}), ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> dict:
        return commands.reject_cancellation(services, merchant_id, cancellation_id, ctx.principal_id, reason=payload.get("reason")).model_dump(mode="json")

    @app.post("/merchants/{merchant_id}/cancellations/{cancellation_id}/execute")
    def execute_cancellation(merchant_id: str, cancellation_id: str, payload: dict = Body(default={}), ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> dict:
        return commands.execute_cancellation(services, merchant_id, cancellation_id, simulate=payload.get("simulate")).model_dump(mode="json")

    @app.post("/merchants/{merchant_id}/cancellations/{cancellation_id}/recover")
    def recover_cancellation_mutation(merchant_id: str, cancellation_id: str, ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> dict:
        return commands.recover_cancellation_mutation(services, merchant_id, cancellation_id).model_dump(mode="json")

    @app.post("/merchants/{merchant_id}/orders/{order_id}/fulfilment/monitor")
    def monitor_fulfilment(merchant_id: str, order_id: str, payload: dict = Body(...), ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> dict:
        return {"canonical_status": commands.monitor_fulfilment(services, merchant_id, order_id, payload["status"], int(payload.get("age_hours", 0)))}

    @app.post("/merchants/{merchant_id}/orders/{order_id}/shipments")
    def create_shipment(merchant_id: str, order_id: str, payload: dict = Body(default={}), ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> dict:
        return commands.create_or_observe_shipment(services, merchant_id, order_id, simulate=payload.get("simulate"))

    @app.post("/merchants/{merchant_id}/shipments/{shipment_ref}/tracking")
    def ingest_tracking(merchant_id: str, shipment_ref: str, ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> dict:
        return {"status": commands.ingest_tracking(services, merchant_id, shipment_ref)}

    @app.post("/merchants/{merchant_id}/shipments/{shipment_ref}/ndr-reattempt")
    def ndr_reattempt(merchant_id: str, shipment_ref: str, ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> dict:
        return {"status": commands.request_ndr_reattempt(services, merchant_id, shipment_ref)}

    @app.post("/merchants/{merchant_id}/finance/payment-observations")
    def observe_payment(merchant_id: str, payload: dict = Body(...), ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> dict:
        observation = commands.observe_payment(services, merchant_id, payload["order_id"], payload["provider"], int(payload["amount"]), payload["currency"], payload["status"], payload.get("external_payment_id"))
        return observation.model_dump(mode="json")

    @app.post("/merchants/{merchant_id}/finance/settlement-batches")
    def ingest_settlement_batch(merchant_id: str, payload: dict = Body(...), ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> dict:
        batch = commands.ingest_settlement_batch(services, merchant_id, payload["provider"], payload["batch"])
        return batch.model_dump(mode="json")

    @app.post("/merchants/{merchant_id}/finance/settlement-batches/{batch_id}/reconcile")
    def reconcile_settlement_batch(merchant_id: str, batch_id: str, ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> list[dict]:
        return [r.model_dump(mode="json") for r in commands.reconcile_settlement_batch(services, merchant_id, batch_id)]

    @app.post("/merchants/{merchant_id}/procurement/replenishment/{sku}")
    def recommend_replenishment(merchant_id: str, sku: str, ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> dict:
        return commands.recommend_replenishment(services, merchant_id, sku).model_dump(mode="json")

    @app.post("/merchants/{merchant_id}/procurement/purchase-orders")
    def create_purchase_order(merchant_id: str, payload: dict = Body(...), ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> dict:
        return commands.create_purchase_order(services, merchant_id, payload["supplier_id"], payload["lines"], idempotency_key=payload.get("idempotency_key")).model_dump(mode="json")

    @app.post("/merchants/{merchant_id}/procurement/purchase-orders/{po_id}/approve")
    def approve_purchase_order(merchant_id: str, po_id: str, ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> dict:
        return commands.approve_purchase_order(services, merchant_id, po_id, ctx.principal_id).model_dump(mode="json")

    @app.post("/merchants/{merchant_id}/procurement/purchase-orders/{po_id}/submit")
    def submit_purchase_order(merchant_id: str, po_id: str, payload: dict = Body(default={}), ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> dict:
        return commands.submit_purchase_order(services, merchant_id, po_id, simulate=payload.get("simulate")).model_dump(mode="json")

    @app.post("/merchants/{merchant_id}/procurement/purchase-orders/{po_id}/acknowledgements")
    def record_acknowledgement(merchant_id: str, po_id: str, payload: dict = Body(...), ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> dict:
        return commands.record_supplier_acknowledgement(services, merchant_id, po_id, payload["external_ref"], int(payload["sequence"]), payload["lines"], payload["status"]).model_dump(mode="json")

    @app.post("/merchants/{merchant_id}/procurement/purchase-orders/{po_id}/shipments")
    def record_shipment(merchant_id: str, po_id: str, payload: dict = Body(...), ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> dict:
        return commands.record_inbound_shipment(services, merchant_id, po_id, payload["external_shipment_ref"], int(payload["sequence"]), payload["lines"]).model_dump(mode="json")

    @app.post("/merchants/{merchant_id}/procurement/purchase-orders/{po_id}/goods-receipts")
    def record_goods_receipt(merchant_id: str, po_id: str, payload: dict = Body(...), ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> dict:
        return commands.record_goods_receipt(services, merchant_id, po_id, payload["external_receipt_ref"], payload["lines"], inbound_shipment_id=payload.get("inbound_shipment_id")).model_dump(mode="json")

    # ================================================================================================
    # Catalogue (Journey A, Phase 4.6) - supplier/product input -> ingestion -> ProductDraft ->
    # validation -> approval where required -> publication -> external/read-back verification. Never
    # exposes StructuredProductIngestor/ProductCompletenessValidator/ProductPublicationService's own
    # methods directly - only the safe, policy-gated commands in packages/runtime/commands.py.
    # ================================================================================================

    @app.post("/merchants/{merchant_id}/catalogue/ingest")
    def ingest_catalogue_file(merchant_id: str, file: UploadFile = File(...), ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> list[dict]:
        suffix = Path(file.filename or "upload.csv").suffix or ".csv"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file.file.read())
            tmp_path = Path(tmp.name)
        try:
            drafts = commands.ingest_product_file(services, merchant_id, tmp_path, file.content_type or "application/octet-stream")
        finally:
            tmp_path.unlink(missing_ok=True)
        return [d.model_dump(mode="json") for d in drafts]

    @app.post("/merchants/{merchant_id}/catalogue/ingest-package")
    def ingest_catalogue_package(merchant_id: str, files: list[UploadFile] = File(...), ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> list[dict]:
        tmp_paths: list[Path] = []
        try:
            for f in files:
                suffix = Path(f.filename or "upload.tmp").suffix or ".tmp"
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                    tmp.write(f.file.read())
                    tmp_paths.append(Path(tmp.name))
            drafts = commands.ingest_product_package(services, merchant_id, tmp_paths)
        finally:
            for p in tmp_paths:
                p.unlink(missing_ok=True)
        return [d.model_dump(mode="json") for d in drafts]

    @app.get("/merchants/{merchant_id}/catalogue/drafts")
    def list_catalogue_drafts(merchant_id: str, ctx: AuthContext = Depends(require_operator)) -> list[dict]:
        return [d.model_dump(mode="json") for d in queries.list_product_drafts(store, merchant_id)]

    @app.get("/merchants/{merchant_id}/catalogue/drafts/{draft_id}")
    def get_catalogue_draft(merchant_id: str, draft_id: str, ctx: AuthContext = Depends(require_operator)) -> dict:
        return queries.get_product_draft(store, merchant_id, draft_id).model_dump(mode="json")

    @app.post("/merchants/{merchant_id}/catalogue/drafts/{draft_id}/conflicts/resolve")
    def resolve_catalogue_conflict(merchant_id: str, draft_id: str, payload: dict = Body(...), ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> dict:
        draft = commands.resolve_draft_conflict(
            services,
            merchant_id=merchant_id,
            draft_id=draft_id,
            fact_name=payload["fact_name"],
            chosen_value=payload["chosen_value"],
            chosen_source=payload["chosen_source"],
            actor=ctx.principal_id,
            note=payload.get("note"),
        )
        return draft.model_dump(mode="json")

    @app.post("/merchants/{merchant_id}/catalogue/drafts/{draft_id}/approve-facts")
    def approve_catalogue_facts(merchant_id: str, draft_id: str, ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> dict:
        return commands.approve_product_facts(services, merchant_id, draft_id, ctx.principal_id).model_dump(mode="json")

    @app.post("/merchants/{merchant_id}/catalogue/drafts/{draft_id}/publish")
    def publish_catalogue_draft(merchant_id: str, draft_id: str, payload: dict = Body(...), ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> dict:
        return commands.request_publication(services, merchant_id, draft_id, payload["channel_id"], ctx.principal_id)

    @app.post("/merchants/{merchant_id}/catalogue/drafts/{draft_id}/publish/approve")
    def approve_catalogue_publication(merchant_id: str, draft_id: str, payload: dict = Body(...), ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> dict:
        return commands.approve_publication(services, merchant_id, draft_id, payload["channel_id"], ctx.principal_id)

    @app.get("/merchants/{merchant_id}/catalogue/publications")
    def list_catalogue_publications(merchant_id: str, ctx: AuthContext = Depends(require_operator)) -> list[dict]:
        return [p.model_dump(mode="json") for p in queries.list_publications(store, merchant_id)]

    @app.post("/merchants/{merchant_id}/catalogue/publications/{publication_id}/reverify")
    def reverify_catalogue_publication(merchant_id: str, publication_id: str, ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> dict:
        return commands.reverify_publication(services, merchant_id, publication_id).model_dump(mode="json")

    # ================================================================================================
    # Support (operator visibility) - the conversation/action trail SupportOrchestrator produces via
    # the Chatwoot webhook path above; no separate command surface (support is event-driven, not
    # operator-invoked, per this phase's scope).
    # ================================================================================================

    @app.get("/merchants/{merchant_id}/support/conversations")
    def list_support_conversations_route(merchant_id: str, ctx: AuthContext = Depends(require_operator)) -> list[dict]:
        return [c.model_dump(mode="json") for c in queries.list_support_conversations(store, merchant_id)]

    @app.get("/merchants/{merchant_id}/support/actions")
    def list_support_actions_route(merchant_id: str, ctx: AuthContext = Depends(require_operator)) -> list[dict]:
        return [a.model_dump(mode="json") for a in queries.list_support_actions(store, merchant_id)]

    # ================================================================================================
    # Operations Command Center (Phase 4.7 Demo Presentation Layer)
    # ================================================================================================
    ui_dir = Path(__file__).resolve().parent.parent / "command_center"
    if ui_dir.exists():
        app.mount("/static", StaticFiles(directory=str(ui_dir)), name="static")

        @app.get("/ui", include_in_schema=False)
        @app.get("/ui/{full_path:path}", include_in_schema=False)
        def serve_ui(full_path: str = ""):
            index_file = ui_dir / "index.html"
            if index_file.exists():
                return FileResponse(str(index_file))
            return {"error": "UI index.html not found"}

        @app.get("/", include_in_schema=False)
        def root_redirect():
            return RedirectResponse(url="/ui")

    return app


app = create_app()
