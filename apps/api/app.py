from __future__ import annotations

import os
import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi import Body, Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
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

    # Self-service demo browser (Slice 1): the public /demo/sessions endpoint is rate-limited per
    # client IP, in-process (no Redis - see infra/systemd/sanocea-api.service.example, one uvicorn
    # worker). Every other route is unaffected - only endpoints explicitly decorated with
    # @limiter.limit(...) below are governed by this.
    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # CORS: narrow by design - no origins allowed unless explicitly configured, never credentialed
    # (every route here authenticates via Bearer token, not cookies), and only the methods/headers the
    # demo browser and Command Center actually use. Unset SANOCEA_DEMO_CORS_ORIGINS (the default)
    # leaves this middleware entirely out, i.e. no behavior change for same-origin deployments.
    _demo_cors_origins = [o.strip() for o in os.environ.get("SANOCEA_DEMO_CORS_ORIGINS", "").split(",") if o.strip()]
    if _demo_cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=_demo_cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type"],
        )

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

    # ================================================================================================
    # Self-service prospect demo sessions (public, unauthenticated by design - this IS the entry point
    # that mints a merchant-scoped credential; see packages/prospect_demo/sessions.py). It only ever
    # leases an already-isolated prospect_* tenant, reset to its canonical baseline before being handed
    # out - never real merchant data, never ref_anchal_heritage. Every other route's auth is unchanged.
    # ================================================================================================

    @app.post("/demo/sessions")
    @limiter.limit("5/minute")
    def create_demo_session(request: Request, payload: dict = Body(default={})) -> dict:
        from sanocea.packages.prospect_demo import NoDemoTenantAvailable, lease_demo_session

        try:
            return lease_demo_session(
                store, dsn=os.environ.get("SANOCEA_PG_DSN"), whatsapp_number=payload.get("whatsapp_number"),
            )
        except NoDemoTenantAvailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/merchants/{merchant_id}/demo/attach-whatsapp")
    @limiter.limit("10/minute")
    def attach_demo_whatsapp(request: Request, merchant_id: str, payload: dict = Body(...), ctx: AuthContext = Depends(require_operator)) -> dict:
        """Lets the interactive walkthrough (real findings, real approve action, real audit record - all
        BEFORE a phone number is ever asked for) hand off into the WhatsApp-style chat on the SAME
        already-leased, already-interacted-with tenant - never re-leases or resets it, which would wipe
        the very state the visitor just built. Reuses DemoApprovalNotificationService.set_session_contact
        exactly as lease_demo_session's own whatsapp_number path already does (packages/prospect_demo/
        sessions.py) - this is just that same call exposed for an already-scoped session instead of a
        brand new one. TTL matches the tenant lease's own window so this can't keep a tenant reserved
        past when the underlying lease itself would naturally free it for the next visitor."""
        from sanocea.packages.notifications.phone import PhoneValidationError
        from sanocea.packages.notifications.resolution import DemoApprovalNotificationService
        from sanocea.packages.notifications.transport import WebChatTransport
        from sanocea.packages.prospect_demo.sessions import DEFAULT_SESSION_TTL, touch_lease

        whatsapp_number = payload.get("whatsapp_number")
        if not whatsapp_number:
            raise HTTPException(status_code=400, detail="whatsapp_number is required")
        try:
            contact = DemoApprovalNotificationService(store, WebChatTransport()).set_session_contact(
                merchant_id, phone_e164=whatsapp_number, session_label="web_chat_demo", consented=True,
                ttl=DEFAULT_SESSION_TTL,
            )
        except PhoneValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        new_expiry = touch_lease(store, merchant_id, ttl=DEFAULT_SESSION_TTL)
        return {
            "status": "attached", "contact_id": contact.id,
            "expires_at": (new_expiry or contact.expires_at).isoformat(),
        }

    @app.post("/merchants/{merchant_id}/chat")
    @limiter.limit("30/minute")
    def demo_chat(request: Request, merchant_id: str, payload: dict = Body(...), ctx: AuthContext = Depends(require_operator)) -> dict:
        """The live conversational demo endpoint: a free-text message in, a real reply out, generated by
        the SAME conversation engine (menu navigation, approval decisions, AI-explain fallback) that would
        run a real WhatsApp session - see packages/notifications/resolution.py::handle_web_chat_message
        and packages/notifications/transport.py::WebChatTransport. No message is ever sent anywhere
        outside this HTTP response - no WAHA/WhatsApp transport is provisioned (see
        docs/architecture/integrations/WHATSAPP_DEMO_TRANSPORT_COMPARISON.md)."""
        from sanocea.packages.domain_contract.models import DemoSessionContact, now_utc
        from sanocea.packages.notifications.resolution import DemoApprovalNotificationService, InboundResolutionError
        from sanocea.packages.notifications.transport import InboundApprovalMessage, WebChatTransport

        text = (payload.get("text") or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="text is required")

        now = now_utc()
        contacts = [c for c in store.list(DemoSessionContact, merchant_id) if c.cleared_at is None and c.expires_at > now]
        if not contacts:
            raise HTTPException(status_code=409, detail="no active chat session for this tenant - start a new demo session with a WhatsApp number")
        contact = max(contacts, key=lambda c: c.consented_at)

        transport = WebChatTransport()
        svc = DemoApprovalNotificationService(store, transport)
        msg = InboundApprovalMessage(
            provider="web_chat", provider_message_id=f"web_{uuid4().hex}",
            from_identifier=contact.phone_e164, raw_text=text, received_at=now,
        )
        try:
            svc.handle_web_chat_message(merchant_id, msg)
        except InboundResolutionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        # Sliding expiry: real activity extends the session rather than letting a fixed one-shot timer
        # cut off an actively-engaged visitor - see packages/prospect_demo/sessions.py::touch_lease.
        from sanocea.packages.prospect_demo.sessions import touch_lease
        new_expiry = touch_lease(store, merchant_id)
        return {"replies": transport.sent, "expires_at": new_expiry.isoformat() if new_expiry else None}

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
            result = connector.ingest_webhook(merchant_id, dict(request.headers), body)

            # ── Tally ERP live sync (demo) ────────────────────────────────────────
            # Fire-and-forget: post to the mock Tally server (localhost:9000) when a
            # paid/created Shopify order arrives. Runs in a daemon thread so it never
            # blocks Shopify's required 200 ACK and never raises if Tally is down.
            topic = request.headers.get("x-shopify-topic", "")
            if channel_type == "shopify_live" and topic in ("orders/paid", "orders/create", "orders/updated"):
                import json as _json
                import threading as _threading
                def _post_to_tally():
                    try:
                        import sys as _sys, os as _os
                        _root = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", ".."))
                        if _root not in _sys.path:
                            _sys.path.insert(0, _root)
                        from sanocea.packages.tally_integration.connector import TallyConnector
                        payload = _json.loads(body.decode("utf-8"))
                        # Only post when payment is confirmed
                        financial = payload.get("financial_status", "")
                        if financial not in ("paid", "partially_paid"):
                            return
                        customer = payload.get("customer") or {}
                        customer_name = " ".join(filter(None, [
                            customer.get("first_name"), customer.get("last_name")
                        ])) or payload.get("email") or "Shopify Customer"
                        order = {
                            "order_number": str(payload.get("order_number") or payload.get("name") or payload.get("id")),
                            "total_amount": int(float(payload.get("total_price", 0)) * 100),  # to paise
                            "currency": payload.get("currency", "INR"),
                            "channel_id": "shopify_live",
                            "status": "confirmed",
                            "payment_status": "paid",
                            "customer_name": customer_name,
                        }
                        order_lines = []
                        for item in payload.get("line_items", []):
                            unit_paise = int(float(item.get("price", 0)) * 100)
                            tax_paise = int(sum(float(t.get("price", 0)) for t in item.get("tax_lines", [])) * 100)
                            order_lines.append({
                                "sku": item.get("sku") or item.get("variant_id") or "SHOPIFY-SKU",
                                "title": item.get("title") or item.get("name") or "Product",
                                "quantity": int(item.get("quantity", 1)),
                                "unit_amount": unit_paise,
                                "tax_amount": tax_paise,
                            })
                        tc = TallyConnector()
                        tc.post_sales_voucher(order, order_lines)
                    except Exception:
                        pass  # Tally sync is best-effort — never surface to caller
                _threading.Thread(target=_post_to_tally, daemon=True).start()
            # ─────────────────────────────────────────────────────────────────────

            return result
        except (ChannelMismatchError, UnknownStorefrontChannelError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # ================================================================================================
    # DEMO TRANSPORT — UNOFFICIAL WHATSAPP WEB (WAHA). See
    # docs/architecture/integrations/WHATSAPP_DEMO_TRANSPORT_COMPARISON.md - never a production
    # integration. Not merchant-scoped in its URL (WAHA has no notion of SANOCEA tenants) - the sender
    # phone is matched against an active DemoSessionContact INSIDE handle_inbound(), which is exactly
    # where merchant/session binding and every other security check happens.
    # ================================================================================================

    @app.post("/webhooks/whatsapp-demo")
    async def whatsapp_demo_webhook(request: Request) -> dict:
        from sanocea.packages.notifications import DemoApprovalNotificationService, InboundResolutionError
        from sanocea.packages.notifications.transport import WhatsAppDemoTransport

        raw_event = await request.json()
        # TEMPORARY diagnostic (certification debugging, Sept 2026) - real WAHA payload shape differs
        # from what parse_inbound assumed; capturing the actual event to fix it against ground truth
        # instead of guessing again. Remove once parse_inbound is confirmed correct against real events.
        import json as _json
        with open(os.path.join(tempfile.gettempdir(), "waha_raw_events.jsonl"), "a", encoding="utf-8") as _f:
            _f.write(_json.dumps(raw_event) + "\n")
        transport = WhatsAppDemoTransport(waha_base_url=os.environ.get("SANOCEA_WAHA_BASE_URL", "http://127.0.0.1:3000"), api_key=os.environ.get("SANOCEA_WAHA_API_KEY"))
        try:
            msg = transport.parse_inbound(raw_event)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if msg is None:
            return {"status": "ignored", "reason": "not an inbound message event"}
        svc = DemoApprovalNotificationService(store, transport)
        # A CSV/XLSX/image attachment (missing-field WhatsApp reply, or "send us the file on
        # WhatsApp") is routed to file ingestion instead of the APPROVE/REJECT text path - detected
        # from the real payload shape WAHA reports (hasMedia + media.mimetype/filename), never guessed.
        payload = (raw_event.get("payload") or {})
        media = payload.get("media") or {}
        filename = media.get("filename") or ""
        mimetype = media.get("mimetype") or ""
        _INGESTIBLE_EXT = (".csv", ".xlsx", ".xlsm", ".pdf", ".png", ".jpg", ".jpeg", ".webp")
        is_ingestible = payload.get("hasMedia") and (
            filename.lower().endswith(_INGESTIBLE_EXT)
            or any(t in mimetype for t in ("csv", "spreadsheet", "excel", "pdf", "image"))
        )
        try:
            if is_ingestible and media.get("url"):
                import mimetypes as _mimetypes

                if not filename:
                    filename = "attachment" + (_mimetypes.guess_extension(mimetype) or ".bin")
                result = svc.handle_inbound_media(msg, filename=filename, content_type=mimetype or "application/octet-stream")
            else:
                result = svc.handle_inbound(msg)
        except InboundResolutionError as exc:
            # Fail closed, but never a 4xx that would make WAHA retry-storm a message it correctly
            # could not resolve (e.g. a wrong number) - 200 + a rejected status is the correct shape
            # for "we received this, we deliberately did nothing".
            return {"status": "rejected", "reason": str(exc)}
        return {"status": "resolved", **result}

    @app.post("/merchants/{merchant_id}/demo/whatsapp-contact")
    def set_demo_whatsapp_contact(merchant_id: str, payload: dict = Body(...), ctx: AuthContext = Depends(require_operator)) -> dict:
        from sanocea.packages.notifications import DemoApprovalNotificationService, PhoneValidationError
        from sanocea.packages.notifications.transport import WhatsAppDemoTransport

        phone = (payload.get("phone_e164") or "").strip()
        consented = bool(payload.get("consented"))
        if not phone or not consented:
            raise HTTPException(status_code=400, detail="phone_e164 and explicit consented=true are both required")
        transport = WhatsAppDemoTransport(waha_base_url=os.environ.get("SANOCEA_WAHA_BASE_URL", "http://127.0.0.1:3000"), api_key=os.environ.get("SANOCEA_WAHA_API_KEY"))
        svc = DemoApprovalNotificationService(store, transport)
        try:
            contact = svc.set_session_contact(merchant_id, phone_e164=phone, session_label=payload.get("session_label") or "live meeting", consented=consented)
        except PhoneValidationError as exc:
            # Clear, operator-facing reason - never a generic 400, and no WAHA request has happened or
            # ever will for this attempt (validation runs before any DemoSessionContact is persisted).
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        from sanocea.packages.notifications.transport import mask_phone
        return {"id": contact.id, "masked_phone": mask_phone(contact.phone_e164), "expires_at": contact.expires_at.isoformat()}

    @app.get("/merchants/{merchant_id}/demo/whatsapp-contact")
    def get_demo_whatsapp_contact(merchant_id: str, ctx: AuthContext = Depends(require_operator)) -> dict:
        """Read-only counterpart to the POST above - reports whichever DemoSessionContact every
        automatic owner-approval / missing-field WhatsApp send will actually use right now (same "most
        recent non-expired" selection as PostOrderOperations._auto_notify_whatsapp_if_no_queue), so
        Command Center's universal owner-number control can show real current state on page load /
        merchant switch instead of only what this one browser tab remembers having set."""
        from sanocea.packages.domain_contract.models import DemoSessionContact, now_utc
        from sanocea.packages.notifications.transport import mask_phone

        contacts = [c for c in store.list(DemoSessionContact, merchant_id) if c.cleared_at is None and c.expires_at > now_utc()]
        if not contacts:
            return {"active": False}
        contact = max(contacts, key=lambda c: c.consented_at)
        return {"active": True, "id": contact.id, "masked_phone": mask_phone(contact.phone_e164), "expires_at": contact.expires_at.isoformat()}

    @app.delete("/merchants/{merchant_id}/demo/whatsapp-contact/{contact_id}")
    def clear_demo_whatsapp_contact(merchant_id: str, contact_id: str, ctx: AuthContext = Depends(require_operator)) -> dict:
        from sanocea.packages.notifications import DemoApprovalNotificationService
        from sanocea.packages.notifications.transport import WhatsAppDemoTransport

        transport = WhatsAppDemoTransport(waha_base_url=os.environ.get("SANOCEA_WAHA_BASE_URL", "http://127.0.0.1:3000"), api_key=os.environ.get("SANOCEA_WAHA_API_KEY"))
        DemoApprovalNotificationService(store, transport).clear_session_contact(merchant_id, contact_id)
        return {"status": "cleared"}

    @app.post("/merchants/{merchant_id}/approvals/{approval_id}/send-whatsapp")
    def send_approval_whatsapp(merchant_id: str, approval_id: str, payload: dict = Body(...), ctx: AuthContext = Depends(require_operator)) -> dict:
        from sanocea.packages.domain_contract.models import Approval, ChannelOperation, DemoSessionContact, Merchant, Order
        from sanocea.packages.notifications import DemoApprovalNotificationService
        from sanocea.packages.notifications.transport import WhatsAppDemoTransport, mask_phone

        contact_id = payload.get("contact_id")
        if not contact_id:
            raise HTTPException(status_code=400, detail="contact_id is required - set a demo WhatsApp contact first")
        transport = WhatsAppDemoTransport(waha_base_url=os.environ.get("SANOCEA_WAHA_BASE_URL", "http://127.0.0.1:3000"), api_key=os.environ.get("SANOCEA_WAHA_API_KEY"))
        svc = DemoApprovalNotificationService(store, transport)
        contact = store.get(DemoSessionContact, merchant_id, contact_id)
        approval = store.get(Approval, merchant_id, approval_id)
        # approval.object_id's MEANING depends on approval.action - a channel_operation_correction's
        # object_id is a ChannelOperation id, but every order-flow action (resolve_inventory_shortage,
        # cancel_order, create_return, refund) has object_id set to the ORDER id instead (same
        # distinction ApprovalService.resolve() already has to make on the approve/reject side - see
        # its own object_id-resolution comment). Real bug found live: this route always assumed
        # ChannelOperation, so approving a real inventory-shortage approval's WhatsApp send 500'd with
        # NotFoundError on a real order id.
        if approval.action == "channel_operation_correction":
            channel = store.get(ChannelOperation, merchant_id, approval.object_id).channel
        else:
            channel = store.get(Order, merchant_id, approval.object_id).channel_id
        merchant = store.get(Merchant, merchant_id, merchant_id)
        try:
            result = svc.send_approval(merchant_id, approval_id, contact, merchant.display_name, channel)
        except NotImplementedError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {"delivered": result.delivered, "error": result.error, "sent_to_masked": mask_phone(contact.phone_e164)}

    @app.post("/merchants/{merchant_id}/daily-briefing")
    def send_merchant_daily_briefing(merchant_id: str, payload: dict = Body(default={}), ctx: AuthContext = Depends(require_operator)) -> dict:
        """Dispatches an executive daily operational briefing to the merchant's active WhatsApp contact."""
        from sanocea.packages.notifications import DemoApprovalNotificationService
        from sanocea.packages.notifications.transport import WhatsAppDemoTransport

        recipient = payload.get("recipient")
        transport = WhatsAppDemoTransport(
            waha_base_url=os.environ.get("SANOCEA_WAHA_BASE_URL", "http://127.0.0.1:3000"),
            api_key=os.environ.get("SANOCEA_WAHA_API_KEY"),
        )
        svc = DemoApprovalNotificationService(store, transport)
        try:
            res = svc.send_daily_briefing(merchant_id, recipient=recipient)
            return {"delivered": res.delivered, "provider_message_id": res.provider_message_id, "error": res.error}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/merchants/{merchant_id}/demo-preflight")
    def get_demo_preflight_check(merchant_id: str, ctx: AuthContext = Depends(require_operator)) -> dict:
        """Executes a fast preflight health and baseline check across all Sanocea demo systems."""
        import json as _json
        import urllib.request as _urllib_req
        from sanocea.packages.domain_contract.models import DemoSessionContact, Inventory, Product, Variant, now_utc

        checks = {}
        failed = []

        # 1. API & Postgres
        checks["api"] = {"status": "ok"}
        try:
            pg_health = store.health() if hasattr(store, "health") else {"status": "ok"}
            checks["postgres"] = {"status": "ok", **pg_health}
        except Exception as exc:
            checks["postgres"] = {"status": "error", "error": str(exc)}
            failed.append("postgres")

        # 2. Storefront live connector
        try:
            connector = graph.storefronts.resolve(merchant_id)
            connector_name = getattr(connector, "name", "storefront_live")
            shop_domain = getattr(connector, "shop_domain", None)
            checks[connector_name] = {"status": "ok", "shop_domain": shop_domain}
        except Exception as exc:
            connector_name = "storefront_live"
            checks[connector_name] = {"status": "error", "error": str(exc)}
            failed.append(connector_name)

        # 3. WhatsApp WAHA container & session
        waha_url = os.environ.get("SANOCEA_WAHA_BASE_URL", "http://127.0.0.1:3000")
        waha_key = os.environ.get("SANOCEA_WAHA_API_KEY")
        try:
            headers = {"X-Api-Key": waha_key} if waha_key else {}
            req = _urllib_req.Request(f"{waha_url}/api/sessions", headers=headers)
            with _urllib_req.urlopen(req, timeout=3) as resp:
                sessions = _json.loads(resp.read())
            working_session = next((s for s in sessions if s.get("status") == "WORKING"), None)
            if working_session:
                checks["whatsapp_waha"] = {
                    "status": "ok",
                    "session": working_session.get("name"),
                    "working": True,
                    "me": (working_session.get("me") or {}).get("id"),
                }
            else:
                checks["whatsapp_waha"] = {"status": "error", "working": False, "error": "No working session"}
                failed.append("whatsapp_waha")
        except Exception as exc:
            checks["whatsapp_waha"] = {"status": "error", "working": False, "error": str(exc)}
            failed.append("whatsapp_waha")

        # 4. Demo contact
        contacts = [c for c in store.list(DemoSessionContact, merchant_id) if c.cleared_at is None and c.expires_at > now_utc()]
        if contacts:
            active_contact = max(contacts, key=lambda c: c.consented_at)
            checks["demo_contact"] = {"status": "ok", "phone": active_contact.phone_e164, "label": active_contact.session_label}
        else:
            checks["demo_contact"] = {"status": "warning", "note": "No active contact, will use session default"}

        # 5. Baseline anomaly present
        prods = store.list(Product, merchant_id)
        invs = store.list(Inventory, merchant_id)
        bbq_inv = next((i for i in invs if "BBQ" in (i.sku or "") or "2P" in (i.sku or "")), None)
        checks["demo_baseline"] = {
            "products_count": len(prods),
            "inventory_lines_count": len(invs),
            "bbq_sku_found": bbq_inv is not None,
            "bbq_sku": bbq_inv.sku if bbq_inv else None,
        }
        if len(prods) == 0 or not bbq_inv:
            failed.append("demo_baseline")

        return {
            "ready": len(failed) == 0,
            "merchant_id": merchant_id,
            "checks": checks,
            "failed_checks": failed,
        }

    @app.post("/merchants/{merchant_id}/demo-reset")
    def reset_demo_baseline(merchant_id: str, ctx: AuthContext = Depends(require_operator)) -> dict:
        """Resets the demo baseline: restores Smoky Hickory BBQ Almonds 2-pack price anomaly on Shopify,
        ensures active demo WhatsApp contact session, and resets pending approval state."""
        from datetime import timedelta
        from sanocea.packages.domain_contract.models import Approval, DemoSessionContact, ExceptionRecord, Inventory, Location, Product, Variant, now_utc
        from sanocea.packages.exceptions import ExceptionCategory, ExceptionService

        # 1. Reset Shopify price back to anomaly (Price: 998.00, Compare-at: 499.00)
        connector = graph.storefronts.resolve(merchant_id)
        sku = "DEMO-PB-BBQ-100G-2P"
        variant_gid = "gid://shopify/ProductVariant/46832702455887"
        if hasattr(connector, "update_variant_price"):
            connector.update_variant_price(
                merchant_id,
                variant_gid=variant_gid,
                sku=sku,
                price="998.00",
                compare_at_price="499.00",
            )

        # 1b. Two more seeded price errors (demo store only), each with its own approval below.
        # variant_gid is explicit: the two Goan Cashews variants share one SKU, so a SKU lookup is ambiguous.
        extra_findings = [
            {"reference": "PB-PRICE-002", "sku": "DEMO-PB-GC-DG-MCC-600G", "variant_gid": "gid://shopify/ProductVariant/46832702718031",
             "object_id": "prd_9089095041103", "bad_price": "179.00", "bad_compare": "1799.00", "new_price": "1799.00", "new_compare": "1799.00",
             "summary": "Restore Stuffed Dates Gift Box price - decimal slip (₹179 instead of ₹1,799)",
             "recommendation": "Approve price correction to ₹1,799.00",
             "unit_economics": "12 Medjool dates listed at ₹179 against a ₹1,799 compare-at (90% off) - a decimal-place slip that sells the gift box far below cost."},
            {"reference": "PB-PRICE-003", "sku": "DEMO-PB-ND-CA-GOP-0250G", "variant_gid": "gid://shopify/ProductVariant/46832703111247",
             "object_id": "prd_9089095434319", "bad_price": "649.00", "bad_compare": None, "new_price": "499.00", "new_compare": None,
             "summary": "Fix Goan Cashews 250g Pouch priced above the identical 250g Jar",
             "recommendation": "Approve price correction to ₹499.00",
             "unit_economics": "The 250g Pouch is listed at ₹649 while the same-weight 250g Jar is ₹549 - the cheaper-to-pack variant costs the customer more."},
        ]
        if hasattr(connector, "update_variant_price"):
            for f in extra_findings:
                connector.update_variant_price(merchant_id, variant_gid=f["variant_gid"], sku=f["sku"], price=f["bad_price"], compare_at_price=f["bad_compare"])

        # 2. Ensure active WhatsApp demo contact
        demo_phone = os.environ.get("SANOCEA_DEMO_PHONE", "+919825133222")
        contact = DemoSessionContact(
            merchant_id=merchant_id,
            id=f"cnt_{merchant_id}_demo",
            phone_e164=demo_phone,
            session_label="The Premium Basket Executive Demo",
            consented=True,
            expires_at=now_utc() + timedelta(days=30),
        )
        store.put(contact)

        # 3. Clean up existing demo approvals and create fresh pending approval
        existing_approvals = store.list(Approval, merchant_id)
        for app_item in existing_approvals:
            if app_item.reference in ("PB-PRICE-001", "DEMO-PRICE-001", *(f["reference"] for f in extra_findings)) or (app_item.evidence and app_item.evidence.get("sku") == sku):
                app_item.status = "expired"
                store.put(app_item)

        new_approval = Approval(
            merchant_id=merchant_id,
            id=f"app_pb_price_{uuid4().hex[:6]}",
            action="price_change",
            object_id="prd_9089094778959",
            channel=getattr(connector, "name", "storefront_live"),
            requested_by="policy_engine:pricing_audit",
            summary="Adjust Smoky Hickory BBQ Almonds 2-pack price to fix unit pricing inversion",
            reference="PB-PRICE-001",
            evidence={
                "sku": sku,
                "variant_gid": variant_gid,
                "current_price": "998.00",
                "new_price": "449.00",
                "compare_at_price": "498.00",
                "single_pack_price": "249.00",
                "likely_impact": "+28% conversion lift on bundle SKU, eliminates 100% customer penalty",
                "unit_economics": "Two single packs sell at ₹498. 2-pack at ₹998 is an inverted penalty. Recommended price ₹449 provides a 10% bundle discount while retaining 42% contribution margin.",
            },
            recommendation="Approve price correction to ₹449.00 (compare-at ₹498.00)",
            status="pending",
        )
        store.put(new_approval)
        for f in extra_findings:
            store.put(Approval(
                merchant_id=merchant_id, id=f"app_pb_{f['reference'].lower().replace('-', '_')}_{uuid4().hex[:6]}",
                action="price_change", object_id=f["object_id"], channel=getattr(connector, "name", "storefront_live"),
                requested_by="policy_engine:pricing_audit", summary=f["summary"], reference=f["reference"],
                evidence={"sku": f["sku"], "variant_gid": f["variant_gid"], "current_price": f["bad_price"], "new_price": f["new_price"],
                          "compare_at_price": f["new_compare"], "unit_economics": f["unit_economics"]},
                recommendation=f["recommendation"], status="pending",
            ))

        # 3b. Blinkit out-of-stock demo scenario: a real demo SKU (Smoky Hickory BBQ Almonds 2-pack,
        # same one the price-approval flow above governs) with 0 ATS on the Blinkit quick-commerce
        # channel, plus a corresponding open inventory exception for the Command Center. Same pattern
        # as the premium-basket catalogue scenario seeder (packages/prospect_demo/scenarios.py TPB-001)
        # - an Inventory row at a Blinkit dark-store location with sellable=0 (so ats=0), and an
        # ExceptionRecord through the production ExceptionService. The WhatsApp daily briefing derives
        # its OOS line from ats==0 inventory, so this is picked up with no extra work. Idempotent: a
        # repeated reset resolves any prior open Blinkit exception and upserts the same inventory row.
        blinkit_oos_sku = "DEMO-PB-BBQ-100G-2P"
        blinkit_product_id = "prd_9089094778959"  # canonical product this SKU's variant belongs to - the same demo product PB-PRICE-001 governs
        blinkit_location_ref = "loc_blinkit_hub"
        blinkit_loc = next((l for l in store.list(Location, merchant_id) if l.code == "BLINKIT_DELHI"), None)
        if blinkit_loc is None:
            blinkit_loc = Location(
                merchant_id=merchant_id,
                name="Blinkit Dark Store — Delhi NCR",
                code="BLINKIT_DELHI",
                is_active=True,
                fulfillment_types=["q_commerce"],
                metadata={"channel": "blinkit", "location_ref": blinkit_location_ref},
            )
            store.put(blinkit_loc)
        blinkit_inv = Inventory(
            merchant_id=merchant_id,
            id=f"{merchant_id}:{blinkit_location_ref}:{blinkit_oos_sku}",
            sku=blinkit_oos_sku,
            location_ref=blinkit_location_ref,
            quantity=50,  # historically stocked
            sellable=0,   # -> ats=0: fully depleted on Blinkit
            reserved=0,
            quarantine=0,
            in_transit=0,
            available=0,
            status="active",
        )
        store.put(blinkit_inv)
        # The variant row (sku -> canonical product) is what lets the generic WhatsApp briefing resolve
        # this product's real title; variants survive the reset wipe, so this mapping persists.
        store.put(Variant(
            merchant_id=merchant_id,
            id=f"{merchant_id}:variant:{blinkit_oos_sku}",
            product_id=blinkit_product_id,
            sku=blinkit_oos_sku,
        ))
        # ONE canonical human-readable title for both the exception and the briefing: the Product the
        # SKU's Variant points at. Same source the WhatsApp briefing resolves, so the demo never shows
        # two different product names. "An item" is the same neutral fallback the briefing uses.
        blinkit_product = store.get(Product, merchant_id, blinkit_product_id)
        blinkit_oos_title = blinkit_product.title if blinkit_product else "An item"
        exceptions_svc = ExceptionService(store)
        for exc in store.list(ExceptionRecord, merchant_id):
            if exc.status == "open" and exc.category == ExceptionCategory.INVENTORY_CONFLICT.value and "blinkit" in exc.message.lower():
                exc.status = "resolved"
                store.put(exc)
        blinkit_oos_exc = exceptions_svc.create(
            merchant_id=merchant_id,
            category=ExceptionCategory.INVENTORY_CONFLICT,
            message=(
                f"{blinkit_oos_title} is currently showing as out of stock on Blinkit. "
                f"{blinkit_inv.quantity} units are available in inventory, but none are currently available for customers. Please investigate."
            ),
            object_id=blinkit_inv.id,
            severity="critical",
            remediation_options=["replenish_blinkit_stock", "suspend_blinkit_listing", "review"],
        )

        # 4. Clean up existing demo supplier drafts so the ingestion scene can be rehearsed fresh
        dsn = os.environ.get("SANOCEA_PG_DSN")
        if dsn:
            try:
                import psycopg2
                with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
                    demo_skus = ["GC-MK-BLK-0050G-2P", "GC-NT-ALM-0250G", "GC-NT-CCC-0200G", "GC-NT-BBQ-0250G"]
                    cur.execute(
                        "DELETE FROM publications WHERE merchant_id = %s AND (data->>'product_draft_id' IN (SELECT id FROM product_drafts WHERE merchant_id = %s AND (data->>'sku' = ANY(%s) OR id = ANY(%s))))",
                        (merchant_id, merchant_id, demo_skus, demo_skus),
                    )
                    cur.execute(
                        "DELETE FROM product_drafts WHERE merchant_id = %s AND (data->>'sku' = ANY(%s) OR id = ANY(%s))",
                        (merchant_id, demo_skus, demo_skus),
                    )
                    cur.execute(
                        "DELETE FROM whatsapp_conversation_states WHERE merchant_id = %s",
                        (merchant_id,),
                    )
            except Exception:
                pass

        return {
            "status": "ok",
            "reset": True,
            "sku": sku,
            "price": "998.00",
            "compare_at_price": "499.00",
            "approval_id": new_approval.id,
            "approval_reference": new_approval.reference,
            "contact_phone": contact.phone_e164,
            "blinkit_oos": {
                "sku": blinkit_oos_sku,
                "location_ref": blinkit_location_ref,
                "ats": blinkit_inv.ats,
                "inventory_id": blinkit_inv.id,
                "exception_id": blinkit_oos_exc.id,
            },
        }

    @app.post("/merchants/{merchant_id}/orders/{order_id}/resync-from-source")
    def resync_order_from_source(merchant_id: str, order_id: str, ctx: AuthContext = Depends(require_operator)) -> dict:
        """Recovery path for a missed/dropped webhook - real, reusable infrastructure (any merchant,
        any order), not a one-off. See ShopifyLiveConnector.resync_order's docstring for why this is
        needed even with the underlying staleness-check bug fixed: Shopify does not redeliver a past
        webhook event on request, so an order already stuck on stale data needs one real re-pull."""
        from sanocea.packages.domain_contract.models import Order

        order = store.get(Order, merchant_id, order_id)
        channel_type = graph.storefronts.channel_type_for(merchant_id)
        external_order_id = next((r.external_id for r in order.external_refs if r.entity_type == "order" and r.system == channel_type), None)
        if not external_order_id:
            raise HTTPException(status_code=400, detail=f"order {order_id} has no external order reference for channel {channel_type}")
        connector = graph.storefronts.resolve(merchant_id)
        if not hasattr(connector, "resync_order"):
            raise HTTPException(status_code=501, detail=f"connector {channel_type} does not support resync_order")
        return connector.resync_order(merchant_id, external_order_id)

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

    @app.post("/merchants/{merchant_id}/inventory/{sku}/observe")
    def observe_inventory_from_source(merchant_id: str, sku: str, payload: dict = Body(...), ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> dict:
        """Real, reusable sync-from-connector action (any merchant/sku/connector implementing `fetch`
        for entity_type='inventory') - reuses PostOrderOperationsService.observe_inventory unchanged.
        Real gap this closes: connector mutations against Shopify (e.g. inventorySetQuantities) never
        automatically push back into SANOCEA's own canonical Inventory.quantity - only an explicit
        observe/sync does, and no route previously existed to trigger one on demand."""
        from sanocea.packages.domain_contract.location import resolve_location_ref
        from sanocea.packages.domain_contract.models import Inventory

        external_product_id = payload.get("external_product_id")
        if not external_product_id:
            raise HTTPException(status_code=400, detail="external_product_id is required")
        connector = graph.storefronts.resolve(merchant_id)
        fetched = connector.fetch(merchant_id, "inventory", external_product_id)
        location = payload.get("location")
        resolved_location = resolve_location_ref(store, merchant_id, location)
        existing = [i for i in store.list(Inventory, merchant_id) if i.sku == sku and i.location_ref == resolved_location]
        canonical_qty = existing[-1].quantity if existing else 0
        services.post_order.observe_inventory(merchant_id, sku, canonical_qty, fetched["available"], location=location)
        return {"sku": sku, "canonical_qty_before": canonical_qty, "external_qty": fetched["available"]}

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

    @app.get("/merchants/{merchant_id}/channel-operations")
    def list_channel_operations(merchant_id: str, run_id: str | None = None, channel: str | None = None, ctx: AuthContext = Depends(require_operator)) -> list[dict]:
        return [c.model_dump(mode="json") for c in queries.list_channel_operations(store, merchant_id, run_id=run_id, channel=channel)]

    @app.post("/merchants/{merchant_id}/approvals/{approval_id}/resolve")
    def resolve_approval_route(merchant_id: str, approval_id: str, payload: dict = Body(...), ctx: AuthContext = Depends(require_operator)) -> dict:
        from sanocea.packages.approvals import ApprovalError, ApprovalService

        decision = payload.get("decision")
        if decision not in ("approved", "denied"):
            raise HTTPException(status_code=400, detail="decision must be 'approved' or 'denied'")
        try:
            result = ApprovalService(store).resolve(
                merchant_id, approval_id, decision=decision,
                resolved_via="command_center", decided_by=ctx.principal_id,
            )
        except ApprovalError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return result

    @app.post("/merchants/{merchant_id}/propose-action")
    def propose_action_route(
        merchant_id: str, payload: dict = Body(...), ctx: AuthContext = Depends(require_operator)
    ) -> dict:
        """Control-plane endpoint for proposing sensitive actions (refunds, price changes, catalog unpublishing).
        Evaluates the action against the merchant's deterministic policy:
        - If ALLOW: returns permitted.
        - If REQUIRE_APPROVAL: creates a pending Approval with structured evidence and reason.
        - If DENY: rejects with reason.
        """
        from sanocea.packages.approvals import ApprovalService
        from sanocea.packages.policy_engine import Decision, PolicyEngine

        action = payload.get("action")
        object_id = payload.get("object_id")
        context = payload.get("context", {})
        summary = payload.get("summary") or f"Proposed {action} on {object_id or 'resource'}"

        if not action:
            raise HTTPException(status_code=400, detail="action is required")

        config = store.get_config(merchant_id)
        policy = config.get("policy", {})

        engine = PolicyEngine()
        decision, reason, evidence = engine.evaluate_with_reason(policy, action, context)

        if decision == Decision.DENY:
            return {
                "decision": "DENY",
                "reason": reason,
                "evidence": evidence,
                "action": action,
                "status": "denied",
            }

        if decision == Decision.REQUIRE_APPROVAL:
            svc = ApprovalService(store)
            approval = svc.request_approval(
                merchant_id,
                action=action,
                object_id=object_id,
                requested_by=ctx.principal_id,
                summary=summary,
                evidence=evidence,
                recommendation=payload.get("recommendation") or f"Review proposed {action}",
            )
            return {
                "decision": "REQUIRE_APPROVAL",
                "approval_id": approval.id,
                "reference": approval.reference,
                "reason": reason,
                "evidence": evidence,
                "action": action,
                "status": "approval_required",
            }

        return {
            "decision": "ALLOW",
            "reason": reason,
            "evidence": evidence,
            "action": action,
            "status": "permitted",
        }

    @app.get("/merchants/{merchant_id}/locations")
    def list_locations_route(merchant_id: str, ctx: AuthContext = Depends(require_operator)) -> list[dict]:
        from sanocea.packages.domain_contract.models import Location
        return [loc.model_dump(mode="json") for loc in store.list(Location, merchant_id)]

    @app.post("/merchants/{merchant_id}/inventory/quarantine")
    def quarantine_inventory_route(
        merchant_id: str, payload: dict = Body(...), ctx: AuthContext = Depends(require_operator)
    ) -> dict:
        sku = payload.get("sku")
        location_ref = payload.get("location_ref", "default")
        quantity = int(payload.get("quantity", 0))
        reason = payload.get("reason", "inspection")
        if not sku or quantity <= 0:
            raise HTTPException(status_code=400, detail="sku and positive quantity required")
        try:
            inv = store.quarantine_inventory_atomic(merchant_id, sku, location_ref, quantity=quantity, reason=reason)
            return inv.model_dump(mode="json")
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/merchants/{merchant_id}/inventory/release-quarantine")
    def release_quarantine_inventory_route(
        merchant_id: str, payload: dict = Body(...), ctx: AuthContext = Depends(require_operator)
    ) -> dict:
        sku = payload.get("sku")
        location_ref = payload.get("location_ref", "default")
        quantity = int(payload.get("quantity", 0))
        if not sku or quantity <= 0:
            raise HTTPException(status_code=400, detail="sku and positive quantity required")
        try:
            inv = store.release_quarantine_atomic(merchant_id, sku, location_ref, quantity=quantity)
            return inv.model_dump(mode="json")
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc


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

    # ================================================================================================
    # Email-driven demo ingress (service auth only - a mailbox watcher/n8n is an internal job, exactly
    # what the 'service' role already exists for; see packages/authn/deps.py::require_service). This
    # endpoint is inbox-level (no merchant_id in the URL) because ROUTING TO A MERCHANT IS ITSELF PART
    # OF WHAT THIS ENDPOINT AUTHORITATIVELY DECIDES (packages/email_ingress/service.py -
    # resolve_merchant_from_routing) - a transport (n8n, a raw script) delivers raw email metadata and
    # bytes; it never gets to assert which merchant those belong to.
    # ================================================================================================

    @app.post("/demo/email-ingest")
    async def email_ingest(payload: dict = Body(...), ctx: AuthContext = Depends(require_service)) -> dict:
        import base64 as _b64

        from sanocea.packages.email_ingress import EmailIngestionError, EmailIngestionService, EmailRoutingError
        from sanocea.packages.email_ingress.service import resolve_merchant_from_routing
        from sanocea.packages.idempotency import IdempotencyService

        trusted_senders = {s.strip().lower() for s in os.environ.get("SANOCEA_DEMO_TRUSTED_SENDERS", "").split(",") if s.strip()}
        try:
            merchant_id = resolve_merchant_from_routing(
                to_addresses=payload.get("to_addresses") or [], sender=payload.get("sender", ""),
                trusted_senders=trusted_senders,
            )
        except EmailRoutingError as exc:
            raise HTTPException(status_code=422, detail=f"routing refused (fail-closed): {exc}") from exc

        try:
            content = _b64.b64decode(payload["content_base64"])
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"content_base64 is not valid base64: {exc}") from exc

        email_svc = EmailIngestionService(store, services, IdempotencyService(store))
        try:
            result = email_svc.ingest_email_attachment(
                merchant_id=merchant_id,
                message_id=payload["message_id"],
                filename=payload["filename"],
                content=content,
                sender=payload.get("sender", ""),
                subject=payload.get("subject", ""),
            )
        except EmailIngestionError as exc:
            raise HTTPException(status_code=422, detail=f"attachment rejected: {exc}") from exc
        return result.as_dict()

    @app.post("/merchants/{merchant_id}/demo/reset")
    def reset_demo_tenant(merchant_id: str, ctx: AuthContext = Depends(require_operator)) -> dict:
        """Lets an operator rehearse a prospect demo as many times as they need before a real client call
        - require_operator already enforces the caller's key is actually authorized for THIS merchant_id
        (packages/authn/deps.py), so a single-tenant key can only ever reset its own tenant. Deliberately
        refuses ref_anchal_heritage (reset_prospect_tenant's own guard) - the certification/reference
        tenant is never reset from the Command Center."""
        from sanocea.packages.prospect_demo import reset_prospect_tenant

        try:
            result = reset_prospect_tenant(merchant_id, dsn=os.environ.get("SANOCEA_PG_DSN"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if merchant_id == "prospect_premium_basket":
            try:
                reset_demo_baseline(merchant_id, ctx)
            except Exception:
                pass

        # Never return the freshly-minted operator_api_key over HTTP - the caller's OWN session key
        # (internal-operator keys, unaffected by this reset - see the module docstring in
        # packages/prospect_demo/reset.py) remains what the browser keeps using.
        return {k: v for k, v in result.items() if k != "operator_api_key"}

    @app.post("/merchants/{merchant_id}/demo/ingest-csv")
    def ingest_demo_csv(
        merchant_id: str,
        payload: dict = Body(default={}),
        ctx: AuthContext = Depends(require_operator),
        services: Services = Depends(get_services),
    ) -> dict:
        """Demo CSV product ingestion workflow (The Premium Basket live dataset):
        Ingests the 4-product supplier catalog with photos, detects missing required publishing fields
        (e.g. price, product_type), stages them as drafts without rejecting, and kicks off sequential
        WhatsApp owner resolution while preserving existing approval state."""
        custom_path = payload.get("file_path")
        if custom_path:
            csv_path = Path(custom_path)
        else:
            default_path = Path("C:/Users/gagan/Downloads/premium_basket_4_products_with_photos.csv")
            fallback_path = Path(__file__).resolve().parent.parent.parent / "packages/prospect_demo/premium_basket_4_products_with_photos.csv"
            csv_path = default_path if default_path.exists() else fallback_path

        if not csv_path.exists():
            raise HTTPException(status_code=404, detail=f"demo CSV file not found: {csv_path}")

        drafts = services.catalogue.ingest_file(merchant_id, csv_path, "text/csv")
        return {
            "status": "ok",
            "file_path": str(csv_path),
            "drafts_count": len(drafts),
            "drafts": [
                {
                    "id": d.id,
                    "sku": d.sku,
                    "title": d.title,
                    "state": d.state,
                    "validation_errors": d.validation_errors,
                }
                for d in drafts
            ],
        }

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

    @app.post("/merchants/{merchant_id}/catalogue/drafts/{draft_id}/provide-missing-fact")
    def provide_missing_draft_fact(merchant_id: str, draft_id: str, payload: dict = Body(...), ctx: AuthContext = Depends(require_operator), services: Services = Depends(get_services)) -> dict:
        draft = commands.provide_missing_draft_fact(
            services,
            merchant_id=merchant_id,
            draft_id=draft_id,
            fact_name=payload["fact_name"],
            value=payload["value"],
            actor=ctx.principal_id,
            source=payload.get("source", "owner_reply"),
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

    @app.post("/merchants/{merchant_id}/config/product-rules/required")
    def add_required_product_fields(merchant_id: str, payload: dict = Body(...), ctx: AuthContext = Depends(require_operator)) -> dict:
        """Narrow, additive config update - merges new field names into config.product_rules.required
        (deduplicated), never touches any other config section. Real gap this closes: description/
        tags/vendor/SEO were never in the required-fields list at all, so a draft missing them never
        triggered the missing-field WhatsApp workflow the way a missing price or SKU does."""
        fields = payload.get("fields")
        if not fields or not isinstance(fields, list):
            raise HTTPException(status_code=400, detail="fields must be a non-empty list of field names")
        config = store.get_config(merchant_id)
        product_rules = config.setdefault("product_rules", {})
        required = list(product_rules.get("required") or ["sku", "title", "price", "currency", "product_type"])
        for f in fields:
            if f not in required:
                required.append(f)
        product_rules["required"] = required
        store.set_config(merchant_id, config)
        return {"required": required}

    @app.post("/merchants/{merchant_id}/catalogue/drafts/clear")
    def clear_catalogue_drafts(merchant_id: str, ctx: AuthContext = Depends(require_operator)) -> dict:
        """Narrow rehearsal-cleanup action - see PostgresStore.clear_catalogue_drafts's own docstring
        for exactly what this does and, just as importantly, does not touch (orders, approvals,
        credentials, channels, audit)."""
        return store.clear_catalogue_drafts(merchant_id)

    @app.post("/merchants/{merchant_id}/catalogue/products/{sku}/publish-to-online-store")
    def publish_product_to_online_store(merchant_id: str, sku: str, ctx: AuthContext = Depends(require_operator)) -> dict:
        """Distinct from the existing catalogue-draft publish flow above, which only writes the product
        into the connected store (Sanocea's own Publication concept) - it does NOT touch storefront
        (sales-channel) visibility. Real gap found during the Mariyal/Premium Basket rehearsal: a
        product can be ACTIVE, in stock, and fully synced, yet still 404 on the storefront because
        nothing ever published it to Shopify's "Online Store" channel. Kept as a generic, reusable
        admin action (any merchant/sku, any connector supporting `publish_to_online_store`) rather than
        a one-off script, per the "do this once for all future clients" decision - one call fixes this
        class of gap for every future prospect demo, not just this one."""
        from sanocea.packages.connector_sdk import MutationRequest

        connector = graph.storefronts.resolve(merchant_id)
        try:
            result = connector.execute_mutation(MutationRequest(
                merchant_id=merchant_id, action="publish_to_online_store", object_type="Product",
                payload={"sku": sku}, idempotency_key=f"publish_to_online_store:{merchant_id}:{sku}",
            ))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return result.model_dump(mode="json")

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
