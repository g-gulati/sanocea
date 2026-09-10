from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, TypeVar

import psycopg2
from psycopg2.extras import Json, RealDictCursor
from pydantic import BaseModel

from .models import (
    Approval,
    AuditEvent,
    Cancellation,
    CanonicalEntity,
    Channel,
    ConnectorCommand,
    Customer,
    CustomerSupportAction,
    ExceptionRecord,
    Exchange,
    ExternalIdMapping,
    FinanceReconciliation,
    FulfilmentObservation,
    Fulfilment,
    GoodsReceipt,
    GoodsReceiptLine,
    InboundShipment,
    InboundShipmentLine,
    Inventory,
    InventoryObservation,
    ListingVerification,
    MediaAsset,
    Merchant,
    Order,
    OrderLine,
    Payment,
    PaymentObservation,
    Product,
    ProductDraft,
    Publication,
    PublicationAttempt,
    PurchaseOrder,
    PurchaseOrderLine,
    RawPayload,
    ReconciliationResult,
    Refund,
    ReplenishmentRecommendation,
    Return,
    SettlementBatch,
    SettlementEntry,
    Shipment,
    ShipmentObservation,
    Supplier,
    SupplierAcknowledgement,
    SupplierSku,
    SupportConversation,
    SupportIntent,
    TrackingEvent,
    Variant,
    WorkflowExecution,
    now_utc,
)
from .store import NotFoundError, TenantAccessError, generate_api_key, hash_api_key


T = TypeVar("T", bound=BaseModel)


MODEL_TABLES: dict[str, str] = {
    "Merchant": "merchants",
    "Channel": "channels",
    "Product": "products",
    "ProductDraft": "product_drafts",
    "Variant": "variants",
    "MediaAsset": "media_assets",
    "Inventory": "inventory",
    "Publication": "publications",
    "PublicationAttempt": "publication_attempts",
    "ListingVerification": "listing_verifications",
    "Customer": "customers",
    "Order": "orders",
    "OrderLine": "order_lines",
    "Payment": "payments",
    "PaymentObservation": "payment_observations",
    "SettlementBatch": "settlement_batches",
    "SettlementEntry": "settlement_entries",
    "FinanceReconciliation": "finance_reconciliations",
    "Fulfilment": "fulfilments",
    "Shipment": "shipments",
    "TrackingEvent": "tracking_events",
    "Return": "returns",
    "Refund": "refunds",
    "Cancellation": "cancellations",
    "Exchange": "exchanges",
    "InventoryObservation": "inventory_observations",
    "FulfilmentObservation": "fulfilment_observations",
    "ShipmentObservation": "shipment_observations",
    "SupportConversation": "support_conversations",
    "SupportIntent": "support_intents",
    "CustomerSupportAction": "customer_support_actions",
    "Approval": "approvals",
    "ExceptionRecord": "exceptions",
    "WorkflowExecution": "workflow_executions",
    "ConnectorCommand": "connector_commands",
    "Supplier": "suppliers",
    "SupplierSku": "supplier_skus",
    "ReplenishmentRecommendation": "replenishment_recommendations",
    "PurchaseOrder": "purchase_orders",
    "PurchaseOrderLine": "purchase_order_lines",
    "SupplierAcknowledgement": "supplier_acknowledgements",
    "InboundShipment": "inbound_shipments",
    "InboundShipmentLine": "inbound_shipment_lines",
    "GoodsReceipt": "goods_receipts",
    "GoodsReceiptLine": "goods_receipt_lines",
}


TABLE_MODELS: dict[str, type[BaseModel]] = {
    "Merchant": Merchant,
    "Channel": Channel,
    "Product": Product,
    "ProductDraft": ProductDraft,
    "Variant": Variant,
    "Inventory": Inventory,
    "MediaAsset": MediaAsset,
    "Publication": Publication,
    "PublicationAttempt": PublicationAttempt,
    "ListingVerification": ListingVerification,
    "Customer": Customer,
    "Order": Order,
    "OrderLine": OrderLine,
    "Payment": Payment,
    "PaymentObservation": PaymentObservation,
    "SettlementBatch": SettlementBatch,
    "SettlementEntry": SettlementEntry,
    "FinanceReconciliation": FinanceReconciliation,
    "Fulfilment": Fulfilment,
    "Shipment": Shipment,
    "TrackingEvent": TrackingEvent,
    "Return": Return,
    "Refund": Refund,
    "Cancellation": Cancellation,
    "Exchange": Exchange,
    "InventoryObservation": InventoryObservation,
    "FulfilmentObservation": FulfilmentObservation,
    "ShipmentObservation": ShipmentObservation,
    "SupportConversation": SupportConversation,
    "SupportIntent": SupportIntent,
    "CustomerSupportAction": CustomerSupportAction,
    "Approval": Approval,
    "ExceptionRecord": ExceptionRecord,
    "WorkflowExecution": WorkflowExecution,
    "ConnectorCommand": ConnectorCommand,
    "Supplier": Supplier,
    "SupplierSku": SupplierSku,
    "ReplenishmentRecommendation": ReplenishmentRecommendation,
    "PurchaseOrder": PurchaseOrder,
    "PurchaseOrderLine": PurchaseOrderLine,
    "SupplierAcknowledgement": SupplierAcknowledgement,
    "InboundShipment": InboundShipment,
    "InboundShipmentLine": InboundShipmentLine,
    "GoodsReceipt": GoodsReceipt,
    "GoodsReceiptLine": GoodsReceiptLine,
}


class EnvCredentialProvider:
    """Local Phase 0.5 credential boundary.

    Database rows store a locator such as `SANOCEA_CRED_MER_A_SHOPIFY`.
    The secret value stays in the process environment. Production should swap
    this provider for KMS/Vault without changing canonical entities.
    """

    def resolve(self, locator: str) -> str:
        value = os.environ.get(locator)
        if value is None:
            raise KeyError(f"credential locator not available: {locator}")
        return value


class PostgresStore:
    def __init__(self, dsn: str, credential_provider: EnvCredentialProvider | None = None) -> None:
        self.dsn = dsn
        self.credential_provider = credential_provider or EnvCredentialProvider()
        self._reuse_connection = os.environ.get("SANOCEA_PG_REUSE_CONNECTION") == "1"
        self._connection = None

    def connect(self):
        if self._reuse_connection:
            if self._connection is None or self._connection.closed:
                self._connection = psycopg2.connect(self.dsn)
            return self._connection
        return psycopg2.connect(self.dsn)

    def migrate(self) -> None:
        migration = Path(__file__).parent / "migrations" / "0001_phase05.sql"
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(migration.read_text(encoding="utf-8"))

    def delete_merchant(self, merchant_id: str) -> None:
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM merchants WHERE id = %s", (merchant_id,))

    def put(self, entity: CanonicalEntity) -> CanonicalEntity:
        entity.sync.updated_at = now_utc()
        table = MODEL_TABLES[type(entity).__name__]
        data = entity.model_dump(mode="json")
        with self.connect() as conn, conn.cursor() as cur:
            if isinstance(entity, Merchant):
                cur.execute(
                    """
                    INSERT INTO merchants (id, merchant_id, data, updated_at)
                    VALUES (%s, %s, %s, now())
                    ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, updated_at = now()
                    """,
                    (entity.id, entity.merchant_id, Json(data)),
                )
            elif isinstance(entity, OrderLine):
                cur.execute(
                    f"""
                    INSERT INTO {table} (id, merchant_id, order_id, data, updated_at)
                    VALUES (%s, %s, %s, %s, now())
                    ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, updated_at = now()
                    """,
                    (entity.id, entity.merchant_id, entity.order_id, Json(data)),
                )
            elif isinstance(entity, InventoryObservation):
                cur.execute(
                    """
                    INSERT INTO inventory_observations (id, merchant_id, order_id, sku, status, data)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status, data = EXCLUDED.data
                    """,
                    (entity.id, entity.merchant_id, entity.order_id, entity.sku, entity.status, Json(data)),
                )
            elif isinstance(entity, FulfilmentObservation):
                cur.execute(
                    """
                    INSERT INTO fulfilment_observations (id, merchant_id, order_id, status, data)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status, data = EXCLUDED.data
                    """,
                    (entity.id, entity.merchant_id, entity.order_id, entity.status, Json(data)),
                )
            elif isinstance(entity, ShipmentObservation):
                cur.execute(
                    """
                    INSERT INTO shipment_observations (id, merchant_id, order_id, status, data)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status, data = EXCLUDED.data
                    """,
                    (entity.id, entity.merchant_id, entity.order_id, entity.status, Json(data)),
                )
            elif isinstance(entity, SupportIntent):
                cur.execute(
                    """
                    INSERT INTO support_intents (id, merchant_id, conversation_id, data, updated_at)
                    VALUES (%s, %s, %s, %s, now())
                    ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, updated_at = now()
                    """,
                    (entity.id, entity.merchant_id, entity.conversation_id, Json(data)),
                )
            elif isinstance(entity, CustomerSupportAction):
                cur.execute(
                    """
                    INSERT INTO customer_support_actions (id, merchant_id, conversation_id, handling_mode, status, data, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, now())
                    ON CONFLICT (id) DO UPDATE SET handling_mode = EXCLUDED.handling_mode, status = EXCLUDED.status, data = EXCLUDED.data, updated_at = now()
                    """,
                    (entity.id, entity.merchant_id, entity.conversation_id, entity.handling_mode, entity.status, Json(data)),
                )
            elif isinstance(entity, ProductDraft):
                cur.execute(
                    """
                    INSERT INTO product_drafts (id, merchant_id, sku, state, data, updated_at)
                    VALUES (%s, %s, %s, %s, %s, now())
                    ON CONFLICT (id) DO UPDATE SET sku = EXCLUDED.sku, state = EXCLUDED.state, data = EXCLUDED.data, updated_at = now()
                    """,
                    (entity.id, entity.merchant_id, entity.sku, entity.state, Json(data)),
                )
            elif isinstance(entity, Publication):
                # Phase 4.6: id-based upsert is the primary path (a Publication's status is updated
                # repeatedly across its lifecycle, same reasoning as PurchaseOrder above).
                # uq_publication_draft_channel is a DB-enforced safety net against a genuine concurrent
                # race minting two DIFFERENT Publication rows for the same (draft, channel) - not merely
                # a SELECT-before-INSERT check (packages/product_onboarding/publication.py's own
                # find_one() pre-check is only the fast path).
                cur.execute("SAVEPOINT publication_upsert")
                try:
                    cur.execute(
                        """
                        INSERT INTO publications (id, merchant_id, product_draft_id, channel_id, status, data, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, now())
                        ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status, data = EXCLUDED.data, updated_at = now()
                        """,
                        (entity.id, entity.merchant_id, entity.product_draft_id, entity.channel_id, entity.status, Json(data)),
                    )
                except psycopg2.errors.UniqueViolation:
                    cur.execute("ROLLBACK TO SAVEPOINT publication_upsert")
                    cur.execute(
                        """
                        SELECT data FROM publications
                        WHERE merchant_id = %s AND product_draft_id = %s AND channel_id = %s
                          AND status IN ('approved', 'publishing', 'published')
                        ORDER BY created_at ASC LIMIT 1
                        """,
                        (entity.merchant_id, entity.product_draft_id, entity.channel_id),
                    )
                    row = cur.fetchone()
                    return Publication.model_validate(row[0])
                else:
                    cur.execute("RELEASE SAVEPOINT publication_upsert")
            elif isinstance(entity, PublicationAttempt):
                cur.execute(
                    """
                    INSERT INTO publication_attempts (id, merchant_id, publication_id, connector_command_id, status, data)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status, data = EXCLUDED.data
                    """,
                    (entity.id, entity.merchant_id, entity.publication_id, entity.connector_command_id, entity.status, Json(data)),
                )
            elif isinstance(entity, ListingVerification):
                cur.execute(
                    """
                    INSERT INTO listing_verifications (id, merchant_id, publication_id, outcome, data)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET outcome = EXCLUDED.outcome, data = EXCLUDED.data
                    """,
                    (entity.id, entity.merchant_id, entity.publication_id, entity.outcome, Json(data)),
                )
            elif isinstance(entity, ConnectorCommand):
                cur.execute(
                    """
                    INSERT INTO connector_commands (id, merchant_id, connector, action, object_type, idempotency_key, status, data, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
                    ON CONFLICT (merchant_id, connector, action, idempotency_key)
                    DO UPDATE SET status = EXCLUDED.status, data = EXCLUDED.data, updated_at = now()
                    RETURNING id
                    """,
                    (entity.id, entity.merchant_id, entity.connector, entity.action, entity.object_type, entity.idempotency_key, entity.status, Json(data)),
                )
                returned = cur.fetchone()
                if returned:
                    entity.id = returned[0]
            elif isinstance(entity, WorkflowExecution):
                cur.execute(
                    """
                    INSERT INTO workflow_executions
                      (id, merchant_id, workflow_type, business_key, temporal_workflow_id, temporal_run_id, data, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, now())
                    ON CONFLICT (merchant_id, workflow_type, business_key)
                    DO UPDATE SET data = EXCLUDED.data, temporal_run_id = EXCLUDED.temporal_run_id, updated_at = now()
                    RETURNING id
                    """,
                    (
                        entity.id,
                        entity.merchant_id,
                        entity.workflow_type,
                        entity.business_key,
                        entity.temporal_workflow_id,
                        entity.temporal_run_id,
                        Json(data),
                    ),
                )
                returned = cur.fetchone()
                if returned:
                    entity.id = returned[0]
            elif isinstance(entity, PaymentObservation):
                if entity.external_payment_id is not None:
                    cur.execute(
                        """
                        INSERT INTO payment_observations (id, merchant_id, data, updated_at)
                        VALUES (%s, %s, %s, now())
                        ON CONFLICT (merchant_id, (data->>'provider'), (data->>'external_payment_id'))
                        WHERE (data->>'external_payment_id') IS NOT NULL
                        DO NOTHING
                        """,
                        (entity.id, entity.merchant_id, Json(data)),
                    )
                    if cur.rowcount == 0:
                        # Database-enforced uniqueness is the final authority: a row with this
                        # (merchant_id, provider, external_payment_id) already exists - this delivery
                        # is a duplicate (retry/replay/race), not a new business observation. Return the
                        # pre-existing canonical row instead of pretending the new one was persisted.
                        cur.execute(
                            """
                            SELECT data FROM payment_observations
                            WHERE merchant_id = %s AND data->>'provider' = %s AND data->>'external_payment_id' = %s
                            ORDER BY created_at ASC LIMIT 1
                            """,
                            (entity.merchant_id, entity.provider, entity.external_payment_id),
                        )
                        row = cur.fetchone()
                        return PaymentObservation.model_validate(row[0])
                else:
                    cur.execute(
                        """
                        INSERT INTO payment_observations (id, merchant_id, data, updated_at)
                        VALUES (%s, %s, %s, now())
                        ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, updated_at = now()
                        """,
                        (entity.id, entity.merchant_id, Json(data)),
                    )
            elif isinstance(entity, SettlementBatch):
                cur.execute(
                    """
                    INSERT INTO settlement_batches (id, merchant_id, data, updated_at)
                    VALUES (%s, %s, %s, now())
                    ON CONFLICT (merchant_id, (data->>'provider'), (data->>'external_batch_id'))
                    DO NOTHING
                    """,
                    (entity.id, entity.merchant_id, Json(data)),
                )
                if cur.rowcount == 0:
                    cur.execute(
                        """
                        SELECT data FROM settlement_batches
                        WHERE merchant_id = %s AND data->>'provider' = %s AND data->>'external_batch_id' = %s
                        ORDER BY created_at ASC LIMIT 1
                        """,
                        (entity.merchant_id, entity.provider, entity.external_batch_id),
                    )
                    row = cur.fetchone()
                    return SettlementBatch.model_validate(row[0])
            elif isinstance(entity, SettlementEntry):
                cur.execute(
                    """
                    INSERT INTO settlement_entries (id, merchant_id, data, updated_at)
                    VALUES (%s, %s, %s, now())
                    ON CONFLICT (merchant_id, (data->>'provider'), (data->>'external_entry_id'))
                    DO NOTHING
                    """,
                    (entity.id, entity.merchant_id, Json(data)),
                )
                if cur.rowcount == 0:
                    # A race let two concurrent ingestions past the application-level pre-check; the
                    # unique index is the final authority here too. Surface the pre-existing row rather
                    # than raising an unhandled UniqueViolation into the caller.
                    cur.execute(
                        """
                        SELECT data FROM settlement_entries
                        WHERE merchant_id = %s AND data->>'provider' = %s AND data->>'external_entry_id' = %s
                        ORDER BY created_at ASC LIMIT 1
                        """,
                        (entity.merchant_id, entity.provider, entity.external_entry_id),
                    )
                    row = cur.fetchone()
                    return SettlementEntry.model_validate(row[0])
            elif isinstance(entity, SupplierSku):
                cur.execute(
                    """
                    INSERT INTO supplier_skus (id, merchant_id, data, updated_at)
                    VALUES (%s, %s, %s, now())
                    ON CONFLICT (merchant_id, (data->>'supplier_id'), (data->>'sku'))
                    DO UPDATE SET data = EXCLUDED.data, updated_at = now()
                    RETURNING id
                    """,
                    (entity.id, entity.merchant_id, Json(data)),
                )
                returned = cur.fetchone()
                if returned and returned[0] != entity.id:
                    entity.id = returned[0]
            elif isinstance(entity, PurchaseOrder):
                # Unlike Phase 3's write-once entities, a PurchaseOrder has a genuine multi-step
                # lifecycle (DRAFT -> ... -> CLOSED) that re-persists the SAME row many times while its
                # idempotency_key stays set. An ON-CONFLICT(idempotency_key)-DO-NOTHING upsert would
                # treat every one of those legitimate status updates as "already exists, skip" and
                # silently discard them. id-based upsert is the primary path (correct for both create
                # and every later lifecycle update); the idempotency_key unique index is a pure safety
                # net against a genuinely NEW row (different id) duplicating an existing draft, handled
                # via a savepoint so we can recover within the same transaction.
                cur.execute("SAVEPOINT po_upsert")
                try:
                    cur.execute(
                        """
                        INSERT INTO purchase_orders (id, merchant_id, data, updated_at)
                        VALUES (%s, %s, %s, now())
                        ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, updated_at = now()
                        """,
                        (entity.id, entity.merchant_id, Json(data)),
                    )
                except psycopg2.errors.UniqueViolation:
                    cur.execute("ROLLBACK TO SAVEPOINT po_upsert")
                    cur.execute(
                        "SELECT data FROM purchase_orders WHERE merchant_id = %s AND data->>'idempotency_key' = %s ORDER BY created_at ASC LIMIT 1",
                        (entity.merchant_id, entity.idempotency_key),
                    )
                    row = cur.fetchone()
                    return PurchaseOrder.model_validate(row[0])
                else:
                    cur.execute("RELEASE SAVEPOINT po_upsert")
            elif isinstance(entity, SupplierAcknowledgement):
                if entity.external_ref is not None:
                    cur.execute(
                        """
                        INSERT INTO supplier_acknowledgements (id, merchant_id, data, updated_at)
                        VALUES (%s, %s, %s, now())
                        ON CONFLICT (merchant_id, (data->>'purchase_order_id'), (data->>'external_ref'))
                        WHERE (data->>'external_ref') IS NOT NULL
                        DO NOTHING
                        """,
                        (entity.id, entity.merchant_id, Json(data)),
                    )
                    if cur.rowcount == 0:
                        # Duplicate/stale/out-of-order acknowledgement event for a PO already
                        # acknowledged under this external_ref - final authority is the DB, not the
                        # caller's own dedup logic.
                        cur.execute(
                            "SELECT data FROM supplier_acknowledgements WHERE merchant_id = %s AND data->>'purchase_order_id' = %s AND data->>'external_ref' = %s ORDER BY created_at ASC LIMIT 1",
                            (entity.merchant_id, entity.purchase_order_id, entity.external_ref),
                        )
                        row = cur.fetchone()
                        return SupplierAcknowledgement.model_validate(row[0])
                else:
                    cur.execute(
                        """
                        INSERT INTO supplier_acknowledgements (id, merchant_id, data, updated_at)
                        VALUES (%s, %s, %s, now())
                        ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, updated_at = now()
                        """,
                        (entity.id, entity.merchant_id, Json(data)),
                    )
            elif isinstance(entity, InboundShipment):
                if entity.external_shipment_ref is not None:
                    cur.execute(
                        """
                        INSERT INTO inbound_shipments (id, merchant_id, data, updated_at)
                        VALUES (%s, %s, %s, now())
                        ON CONFLICT (merchant_id, (data->>'supplier_id'), (data->>'external_shipment_ref'))
                        WHERE (data->>'external_shipment_ref') IS NOT NULL
                        DO NOTHING
                        """,
                        (entity.id, entity.merchant_id, Json(data)),
                    )
                    if cur.rowcount == 0:
                        cur.execute(
                            "SELECT data FROM inbound_shipments WHERE merchant_id = %s AND data->>'supplier_id' = %s AND data->>'external_shipment_ref' = %s ORDER BY created_at ASC LIMIT 1",
                            (entity.merchant_id, entity.supplier_id, entity.external_shipment_ref),
                        )
                        row = cur.fetchone()
                        return InboundShipment.model_validate(row[0])
                else:
                    cur.execute(
                        """
                        INSERT INTO inbound_shipments (id, merchant_id, data, updated_at)
                        VALUES (%s, %s, %s, now())
                        ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, updated_at = now()
                        """,
                        (entity.id, entity.merchant_id, Json(data)),
                    )
            elif isinstance(entity, GoodsReceipt):
                # Same reasoning as PurchaseOrder above: record_goods_receipt() re-fetches and re-puts
                # the SAME receipt (to set its final status) after the initial insert, while
                # external_receipt_ref stays set - id-based upsert primary, business-key uniqueness as
                # a savepoint-guarded safety net against a genuinely new duplicate row.
                cur.execute("SAVEPOINT gr_upsert")
                try:
                    cur.execute(
                        """
                        INSERT INTO goods_receipts (id, merchant_id, data, updated_at)
                        VALUES (%s, %s, %s, now())
                        ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, updated_at = now()
                        """,
                        (entity.id, entity.merchant_id, Json(data)),
                    )
                except psycopg2.errors.UniqueViolation:
                    cur.execute("ROLLBACK TO SAVEPOINT gr_upsert")
                    cur.execute(
                        "SELECT data FROM goods_receipts WHERE merchant_id = %s AND data->>'external_receipt_ref' = %s ORDER BY created_at ASC LIMIT 1",
                        (entity.merchant_id, entity.external_receipt_ref),
                    )
                    row = cur.fetchone()
                    return GoodsReceipt.model_validate(row[0])
                else:
                    cur.execute("RELEASE SAVEPOINT gr_upsert")
            elif isinstance(entity, Order):
                cur.execute(
                    """
                    INSERT INTO orders (id, merchant_id, data, event_sequence, updated_at)
                    VALUES (%s, %s, %s, %s, now())
                    ON CONFLICT (id) DO UPDATE
                    SET data = EXCLUDED.data, event_sequence = EXCLUDED.event_sequence, updated_at = now()
                    WHERE orders.event_sequence IS NULL
                       OR EXCLUDED.event_sequence IS NULL
                       OR EXCLUDED.event_sequence >= orders.event_sequence
                    """,
                    (entity.id, entity.merchant_id, Json(data), entity.sync.event_sequence),
                )
            else:
                cur.execute(
                    f"""
                    INSERT INTO {table} (id, merchant_id, data, updated_at)
                    VALUES (%s, %s, %s, now())
                    ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, updated_at = now()
                    """,
                    (entity.id, entity.merchant_id, Json(data)),
                )
        return entity.model_copy(deep=True)

    def get(self, model: type[T], merchant_id: str, entity_id: str) -> T:
        table = MODEL_TABLES[model.__name__]
        with self.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(f"SELECT merchant_id, data FROM {table} WHERE id = %s", (entity_id,))
            row = cur.fetchone()
        if not row:
            raise NotFoundError(entity_id)
        if row["merchant_id"] != merchant_id:
            raise TenantAccessError(f"{merchant_id} cannot access {entity_id}")
        return model.model_validate(row["data"])

    def list(self, model: type[T], merchant_id: str) -> list[T]:
        table = MODEL_TABLES[model.__name__]
        with self.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(f"SELECT data FROM {table} WHERE merchant_id = %s ORDER BY created_at", (merchant_id,))
            return [model.model_validate(row["data"]) for row in cur.fetchall()]

    def list_all_merchants(self) -> list[Merchant]:
        """Phase 4.6: a deliberate, narrow escape hatch from per-tenant scoping - merchant enumeration
        is inherently a system/service-level operation (a tenant cannot enumerate other tenants;
        something operating ACROSS all tenants - the recovery runner, an admin listing - must). Every
        Merchant row's own merchant_id field equals its own id (see MerchantOnboardingService.onboard),
        so a plain list(Merchant, some_id) can never return more than one row; this is the only correct
        way to enumerate all merchants. Callers must gate access themselves (require_service, never a
        tenant-authenticated route)."""
        with self.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT data FROM merchants ORDER BY created_at")
            return [Merchant.model_validate(row["data"]) for row in cur.fetchall()]

    def list_where(self, model: type[T], merchant_id: str, **field_equals: str) -> list[T]:
        """Phase 4.5: for operational control-plane queries (open exceptions, uncertain connector
        commands, pending approvals) - filters in SQL against the JSONB expression indexes already
        created for exactly these fields (idx_exceptions_merchant_status, idx_connector_commands_status,
        idx_approvals_merchant_status, ...), instead of `list()` + a Python filter that scans every row
        for the merchant. Field NAMES are always hardcoded by the calling query function, never taken
        from a request - only VALUES are parameterized.
        """
        table = MODEL_TABLES[model.__name__]
        clauses = ["merchant_id = %s"]
        params: list[Any] = [merchant_id]
        for field, value in field_equals.items():
            assert field.isidentifier(), f"unsafe field name for list_where: {field!r}"
            clauses.append(f"data->>'{field}' = %s")
            params.append(str(value))
        query = f"SELECT data FROM {table} WHERE {' AND '.join(clauses)} ORDER BY created_at DESC"  # noqa: S608
        with self.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return [model.model_validate(row["data"]) for row in cur.fetchall()]

    def find_one(self, model: type[T], merchant_id: str, **attrs: Any) -> T | None:
        for entity in self.list(model, merchant_id):
            if all(getattr(entity, key) == value for key, value in attrs.items()):
                return entity
        return None

    def append_audit(self, event: AuditEvent) -> AuditEvent:
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audit_events
                  (id, merchant_id, actor, source, action, object_type, object_id, timestamp,
                   workflow_id, evidence_ref, requested_mutation, result, external_ref, error, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    event.id,
                    event.merchant_id,
                    event.actor,
                    event.source,
                    event.action,
                    event.object_type,
                    event.object_id,
                    event.timestamp,
                    event.workflow_id,
                    event.evidence_ref,
                    Json(event.requested_mutation) if event.requested_mutation is not None else None,
                    event.result,
                    Json(event.external_ref.model_dump(mode="json")) if event.external_ref else None,
                    event.error,
                    event.correlation_id,
                ),
            )
        return event.model_copy(deep=True)

    def list_audit(self, merchant_id: str) -> list[AuditEvent]:
        with self.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM audit_events WHERE merchant_id = %s ORDER BY timestamp, id", (merchant_id,))
            rows = cur.fetchall()
        events = []
        for row in rows:
            events.append(
                AuditEvent(
                    id=row["id"],
                    merchant_id=row["merchant_id"],
                    actor=row["actor"],
                    source=row["source"],
                    action=row["action"],
                    object_type=row["object_type"],
                    object_id=row["object_id"],
                    timestamp=row["timestamp"],
                    workflow_id=row["workflow_id"],
                    evidence_ref=row["evidence_ref"],
                    requested_mutation=row["requested_mutation"],
                    result=row["result"],
                    external_ref=row["external_ref"],
                    error=row["error"],
                    correlation_id=row.get("correlation_id"),
                )
            )
        return events

    def store_raw_payload(self, payload: RawPayload) -> RawPayload:
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO raw_external_events (id, merchant_id, source, payload, headers, received_at, checksum)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    payload.id,
                    payload.merchant_id,
                    payload.source,
                    Json(payload.payload),
                    Json(payload.headers),
                    payload.received_at,
                    payload.checksum,
                ),
            )
        return payload.model_copy(deep=True)

    def get_raw_payload(self, merchant_id: str, payload_id: str) -> RawPayload:
        with self.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM raw_external_events WHERE id = %s", (payload_id,))
            row = cur.fetchone()
        if not row:
            raise NotFoundError(payload_id)
        if row["merchant_id"] != merchant_id:
            raise TenantAccessError(f"{merchant_id} cannot access {payload_id}")
        return RawPayload(
            id=row["id"],
            merchant_id=row["merchant_id"],
            source=row["source"],
            payload=row["payload"],
            headers=row["headers"],
            received_at=row["received_at"],
            checksum=row["checksum"],
        )

    def put_external_mapping(self, mapping: ExternalIdMapping) -> ExternalIdMapping:
        with self.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO external_id_mappings
                  (id, merchant_id, sanocea_entity_type, sanocea_id, external_system,
                   external_entity_type, external_id, channel_id, first_seen_at, last_seen_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (merchant_id, external_system, external_entity_type, external_id)
                DO UPDATE SET sanocea_id = EXCLUDED.sanocea_id, last_seen_at = EXCLUDED.last_seen_at
                RETURNING *
                """,
                (
                    mapping.id,
                    mapping.merchant_id,
                    mapping.sanocea_entity_type,
                    mapping.sanocea_id,
                    mapping.external_system,
                    mapping.external_entity_type,
                    mapping.external_id,
                    mapping.channel_id,
                    mapping.first_seen_at,
                    now_utc(),
                ),
            )
            row = cur.fetchone()
        return ExternalIdMapping(**row)

    def get_external_mapping(self, merchant_id: str, external_system: str, external_entity_type: str, external_id: str) -> ExternalIdMapping | None:
        with self.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT * FROM external_id_mappings
                WHERE merchant_id = %s AND external_system = %s AND external_entity_type = %s AND external_id = %s
                """,
                (merchant_id, external_system, external_entity_type, external_id),
            )
            row = cur.fetchone()
        return ExternalIdMapping(**row) if row else None

    def set_config(self, merchant_id: str, config: dict[str, Any]) -> None:
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO merchant_configurations (merchant_id, config, updated_at)
                VALUES (%s, %s, now())
                ON CONFLICT (merchant_id) DO UPDATE SET config = EXCLUDED.config, updated_at = now()
                """,
                (merchant_id, Json(config)),
            )

    def get_config(self, merchant_id: str) -> dict[str, Any]:
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT config FROM merchant_configurations WHERE merchant_id = %s", (merchant_id,))
            row = cur.fetchone()
        return row[0] if row else {}

    def set_credential_ref(self, merchant_id: str, ref: str, secret: str) -> None:
        locator = f"SANOCEA_CRED_{merchant_id.upper()}_{ref.upper()}".replace("-", "_")
        os.environ[locator] = secret
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO credential_references (merchant_id, ref, provider, locator)
                VALUES (%s, %s, 'env', %s)
                ON CONFLICT (merchant_id, ref) DO UPDATE SET provider = 'env', locator = EXCLUDED.locator
                """,
                (merchant_id, ref, locator),
            )

    def get_credential_ref(self, merchant_id: str, ref: str) -> str:
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT locator FROM credential_references WHERE merchant_id = %s AND ref = %s", (merchant_id, ref))
            row = cur.fetchone()
        if not row:
            raise TenantAccessError(f"{merchant_id} cannot access credential {ref}")
        return self.credential_provider.resolve(row[0])

    def list_credential_refs(self, merchant_id: str) -> list[str]:
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT ref FROM credential_references WHERE merchant_id = %s ORDER BY ref", (merchant_id,))
            return [row[0] for row in cur.fetchall()]

    def reserve_idempotency(self, scope: str, key: str, result: Any = None) -> bool:
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO idempotency_records (scope, key, result, status)
                VALUES (%s, %s, %s, 'reserved')
                ON CONFLICT DO NOTHING
                """,
                (scope, key, Json(result)),
            )
            return cur.rowcount == 1

    def complete_idempotency(self, scope: str, key: str, result: Any) -> None:
        payload = result.model_dump(mode="json") if isinstance(result, BaseModel) else result
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE idempotency_records
                SET result = %s, status = 'completed', completed_at = now()
                WHERE scope = %s AND key = %s
                """,
                (Json(payload), scope, key),
            )

    def get_idempotency_result(self, scope: str, key: str) -> Any:
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT result FROM idempotency_records WHERE scope = %s AND key = %s AND status = 'completed'", (scope, key))
            row = cur.fetchone()
        return row[0] if row else None

    def release_idempotency(self, scope: str, key: str) -> None:
        # Releases a reservation whose operation raised before completing, so a genuine retry can
        # actually re-attempt the mutation instead of polling forever for a result that will never
        # arrive (see IdempotencyService.run_once). Never releases an already-completed reservation.
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM idempotency_records WHERE scope = %s AND key = %s AND status = 'reserved'", (scope, key))

    def append_reconciliation_result(self, result: ReconciliationResult) -> ReconciliationResult:
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO reconciliation_results
                  (id, merchant_id, scope, canonical_ref, external_ref, result, exception_id, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    result.id,
                    result.merchant_id,
                    Json(result.model_dump(mode="json")["scope"]),
                    Json(result.model_dump(mode="json")["canonical_ref"]) if result.canonical_ref else None,
                    Json(result.model_dump(mode="json")["external_ref"]) if result.external_ref else None,
                    result.result,
                    result.exception_id,
                    result.created_at,
                ),
            )
        return result

    def atomic_apply_po_line_confirmation(self, merchant_id: str, line_id: str, delta: int) -> int:
        """Atomically increments PurchaseOrderLine.quantity_confirmed by `delta` inside a single
        transaction using SELECT ... FOR UPDATE, returning the resulting TRUE cumulative total (which
        may exceed quantity_ordered - the caller decides what an over-confirmation means). Without the
        row lock, two genuinely concurrent acknowledgement events for the same line would both read the
        same base value and race on the write, silently losing one event's contribution (a classic
        lost-update bug) - this is the real fix, not a re-check after the fact.
        """
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT data FROM purchase_order_lines WHERE id = %s AND merchant_id = %s FOR UPDATE", (line_id, merchant_id))
            row = cur.fetchone()
            if not row:
                raise NotFoundError(line_id)
            data = row[0]
            new_total = int(data.get("quantity_confirmed", 0)) + delta
            data["quantity_confirmed"] = new_total
            cur.execute("UPDATE purchase_order_lines SET data = %s, updated_at = now() WHERE id = %s", (Json(data), line_id))
            return new_total

    def atomic_adjust_inventory(
        self, merchant_id: str, sku: str, location_ref: str, *,
        confirmed_inbound_delta: int = 0, quantity_delta: int = 0, available_delta: int = 0,
    ) -> Inventory:
        """Atomically creates-or-adjusts the Inventory row for (merchant_id, sku, location_ref) in one
        statement, using uq_inventory_merchant_sku_location's own ON CONFLICT atomicity - no
        application-level lock needed. Phase 4.6 fix for a genuine, reproducible race found while
        hardening this phase: two concurrent supplier acknowledgements (or an acknowledgement racing a
        goods receipt) for a SKU with no prior Inventory row both read "does not exist yet" under the
        old read-modify-write and each INSERT a competing new row - the second INSERT raised
        uq_inventory_merchant_sku_location's UniqueViolation uncaught, and even had it been caught
        naively, discarding the losing caller's delta would have been a silent lost update, not merely
        a crash. All three counters are adjusted in the SAME atomic UPSERT regardless of whether the row
        already existed.
        """
        seed = Inventory(
            merchant_id=merchant_id, sku=sku, location_ref=location_ref,
            quantity=max(quantity_delta, 0), available=max(available_delta, 0), confirmed_inbound=max(confirmed_inbound_delta, 0),
        )
        with self.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO inventory (id, merchant_id, data, updated_at)
                VALUES (%(id)s, %(merchant_id)s, %(data)s, now())
                ON CONFLICT (merchant_id, (data->>'sku'), (data->>'location_ref'))
                DO UPDATE SET
                  data = jsonb_set(
                    jsonb_set(
                      jsonb_set(
                        inventory.data, '{confirmed_inbound}',
                        to_jsonb(GREATEST(COALESCE((inventory.data->>'confirmed_inbound')::int, 0) + %(ci)s, 0))
                      ),
                      '{quantity}', to_jsonb(COALESCE((inventory.data->>'quantity')::int, 0) + %(q)s)
                    ),
                    '{available}', to_jsonb(COALESCE((inventory.data->>'available')::int, 0) + %(av)s)
                  ),
                  updated_at = now()
                RETURNING data
                """,
                {"id": seed.id, "merchant_id": merchant_id, "data": Json(seed.model_dump(mode="json")), "ci": confirmed_inbound_delta, "q": quantity_delta, "av": available_delta},
            )
            row = cur.fetchone()
        return Inventory.model_validate(row["data"])

    def create_api_key(self, *, merchant_id: str | None, role: str, label: str | None = None) -> tuple[str, str]:
        raw_key = generate_api_key()
        key_id = f"key_{os.urandom(12).hex()}"
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO api_keys (id, merchant_id, key_hash, role, label) VALUES (%s, %s, %s, %s, %s)",
                (key_id, merchant_id, hash_api_key(raw_key), role, label),
            )
        return key_id, raw_key

    def resolve_api_key(self, raw_key: str) -> dict[str, Any] | None:
        with self.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, merchant_id, role, label FROM api_keys WHERE key_hash = %s AND revoked_at IS NULL",
                (hash_api_key(raw_key),),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def revoke_api_key(self, key_id: str) -> None:
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("UPDATE api_keys SET revoked_at = now() WHERE id = %s", (key_id,))

    def health(self) -> dict[str, str]:
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return {"postgres": "ok"}

    @contextmanager
    def advisory_lock(self, name: str) -> Iterator[bool]:
        """Phase 4.6: a non-blocking, DB-enforced, cross-process mutex - the production-shaped recovery
        runner (scripts/run_recovery_worker.py) uses this so two overlapping invocations (a systemd
        timer firing again before the previous run finished, or a stray cron entry alongside a running
        systemd service) can never process the same work concurrently. pg_try_advisory_lock returns
        immediately (never blocks) and is scoped to the SESSION (this method's own dedicated
        connection, held open for the `with` block's lifetime, never the pooled/per-call default) -
        yields True if acquired, False if another holder already has it (caller must skip its work,
        never proceed assuming success). Released automatically (pg_advisory_unlock, then the
        connection is closed) even if the caller's block raises.
        """
        conn = psycopg2.connect(self.dsn)
        conn.autocommit = True
        try:
            cur = conn.cursor()
            cur.execute("SELECT pg_try_advisory_lock(hashtext(%s))", (name,))
            acquired = bool(cur.fetchone()[0])
            try:
                yield acquired
            finally:
                if acquired:
                    cur.execute("SELECT pg_advisory_unlock(hashtext(%s))", (name,))
        finally:
            conn.close()
