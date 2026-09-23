from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, TypeVar

import psycopg2
from psycopg2.extras import Json, RealDictCursor
from pydantic import BaseModel

from .credentials import CredentialProvider, EnvCredentialProvider
from .models import (
    Approval,
    AuditEvent,
    Cancellation,
    CanonicalEntity,
    Channel,
    ChannelOperation,
    ConnectorCommand,
    DemoSessionContact,
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
    IdentityDecision,
    InboundShipment,
    InboundShipmentLine,
    Inventory,
    InventoryObservation,
    InventoryReservation,
    ListingVerification,
    Location,
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
    WhatsAppConversationState,
    WorkflowExecution,
    now_utc,
)
from .store import NotFoundError, TenantAccessError, generate_api_key, hash_api_key


T = TypeVar("T", bound=BaseModel)


MODEL_TABLES: dict[str, str] = {
    "Merchant": "merchants",
    "Channel": "channels",
    "Location": "locations",
    "Product": "products",
    "ProductDraft": "product_drafts",
    "Variant": "variants",
    "MediaAsset": "media_assets",
    "Inventory": "inventory",
    "InventoryReservation": "inventory_reservations",
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
    "IdentityDecision": "identity_decisions",
    "ChannelOperation": "channel_operations",
    "DemoSessionContact": "demo_session_contacts",
    "WhatsAppConversationState": "whatsapp_conversation_states",
}


TABLE_MODELS: dict[str, type[BaseModel]] = {
    "Merchant": Merchant,
    "Channel": Channel,
    "Product": Product,
    "ProductDraft": ProductDraft,
    "Variant": Variant,
    "IdentityDecision": IdentityDecision,
    "Inventory": Inventory,
    "InventoryReservation": InventoryReservation,
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
    "ChannelOperation": ChannelOperation,
    "DemoSessionContact": DemoSessionContact,
    "WhatsAppConversationState": WhatsAppConversationState,
}


class PostgresStore:
    def __init__(self, dsn: str, credential_provider: "CredentialProvider | None" = None) -> None:
        self.dsn = dsn
        # Step P0.1: EnvCredentialProvider is a DEVELOPMENT-ONLY default, kept here purely for backward
        # compatibility with every existing direct `PostgresStore(dsn)` construction across this
        # codebase's test suite (none of which need durable/encrypted storage). Production code must
        # NEVER rely on this default - apps/api/app.py's _build_store() always passes an explicit
        # DurableEncryptedCredentialProvider, built via build_production_credential_provider(), which
        # fails closed at startup if a master key is not configured, rather than silently falling back
        # to this class. See packages/domain_contract/credentials.py.
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

    def clear_catalogue_drafts(self, merchant_id: str) -> dict[str, int]:
        """Narrow "clean slate" for the catalogue/product-onboarding test data ONLY - deletes every
        ProductDraft for this merchant plus every ExceptionRecord whose object_id points at one of
        them. Deliberately does NOT touch orders/approvals/credentials/channels/audit - unlike
        reset_prospect_tenant (packages/prospect_demo/reset.py), which wipes the entire tenant
        including real Shopify credentials and channel config. Real gap this closes: rehearsal/test
        product drafts (including image-only junk drafts from a WhatsApp attachment test) had no way
        to be cleared without either living with the clutter or risking the full tenant wipe."""
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM product_drafts WHERE merchant_id = %s", (merchant_id,))
            draft_ids = [row[0] for row in cur.fetchall()]
            deleted_exceptions = 0
            if draft_ids:
                cur.execute(
                    "DELETE FROM exceptions WHERE merchant_id = %s AND data->>'object_id' = ANY(%s)",
                    (merchant_id, draft_ids),
                )
                deleted_exceptions = cur.rowcount
            cur.execute("DELETE FROM product_drafts WHERE merchant_id = %s", (merchant_id,))
            deleted_drafts = cur.rowcount
        return {"product_drafts": deleted_drafts, "exceptions": deleted_exceptions}

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
            elif isinstance(entity, Refund):
                # Step 7B: mirrors PurchaseOrder's exact pattern above - Refund has a genuine multi-step
                # lifecycle (permitted -> mutation_submitted -> external_confirmed -> reconciled ->
                # completed) that re-persists the SAME row many times, so id-based upsert must remain the
                # PRIMARY path (correct for both create and every later status update). The
                # uq_refund_return_id partial unique index is a pure safety net against a genuinely NEW
                # row (different id) duplicating an existing return-owned refund under concurrency -
                # handled via a savepoint so we can recover within the same transaction, exactly like
                # PurchaseOrder's idempotency_key does.
                cur.execute("SAVEPOINT refund_upsert")
                try:
                    cur.execute(
                        """
                        INSERT INTO refunds (id, merchant_id, data, updated_at)
                        VALUES (%s, %s, %s, now())
                        ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, updated_at = now()
                        """,
                        (entity.id, entity.merchant_id, Json(data)),
                    )
                except psycopg2.errors.UniqueViolation:
                    cur.execute("ROLLBACK TO SAVEPOINT refund_upsert")
                    cur.execute(
                        "SELECT data FROM refunds WHERE merchant_id = %s AND data->>'return_id' = %s ORDER BY created_at ASC LIMIT 1",
                        (entity.merchant_id, entity.return_id),
                    )
                    row = cur.fetchone()
                    return Refund.model_validate(row[0])
                else:
                    cur.execute("RELEASE SAVEPOINT refund_upsert")
            elif isinstance(entity, Inventory):
                cur.execute("SAVEPOINT inv_upsert")
                try:
                    cur.execute(
                        """
                        INSERT INTO inventory (id, merchant_id, data, updated_at)
                        VALUES (%s, %s, %s, now())
                        ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, updated_at = now()
                        """,
                        (entity.id, entity.merchant_id, Json(data)),
                    )
                except psycopg2.errors.UniqueViolation:
                    cur.execute("ROLLBACK TO SAVEPOINT inv_upsert")
                    cur.execute(
                        """
                        UPDATE inventory SET id = %s, data = %s, updated_at = now()
                        WHERE merchant_id = %s AND data->>'sku' = %s AND data->>'location_ref' = %s
                        RETURNING data
                        """,
                        (entity.id, Json(data), entity.merchant_id, entity.sku, entity.location_ref),
                    )
                    row = cur.fetchone()
                    if row:
                        return Inventory.model_validate(row[0])
                else:
                    cur.execute("RELEASE SAVEPOINT inv_upsert")
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
        """Step P0.1 - delegates the ACTUAL secret storage to self.credential_provider.store(), which
        returns an opaque locator; this method's own job is only to record WHICH provider produced that
        locator (`credential_references.provider`), for observability/health purposes - never the secret
        itself, and never provider-specific parsing of the locator's shape."""
        provider_name = self.credential_provider.health().get("provider", "unknown")
        locator = self.credential_provider.store(merchant_id, ref, secret)
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO credential_references (merchant_id, ref, provider, locator)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (merchant_id, ref) DO UPDATE SET provider = EXCLUDED.provider, locator = EXCLUDED.locator
                """,
                (merchant_id, ref, provider_name, locator),
            )

    def get_credential_ref(self, merchant_id: str, ref: str) -> str:
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT locator FROM credential_references WHERE merchant_id = %s AND ref = %s", (merchant_id, ref))
            row = cur.fetchone()
        if not row:
            raise TenantAccessError(f"{merchant_id} cannot access credential {ref}")
        try:
            return self.credential_provider.resolve(row[0])
        except KeyError as exc:
            # "not found" and "revoked" both surface as KeyError from the provider - both mean the SAME
            # thing to a caller as "no credential row exists at all": this tenant cannot currently use
            # this credential. A decryption failure (ValueError, wrong/missing master key) is a distinct,
            # operator-facing configuration problem and is deliberately NOT caught here - it should not
            # be mistaken for an ordinary tenant-access refusal.
            raise TenantAccessError(f"{merchant_id} cannot access credential {ref}") from exc

    def delete_credential_ref(self, merchant_id: str, ref: str) -> None:
        """Revokes a credential - after this call, get_credential_ref for the same (merchant_id, ref)
        raises TenantAccessError, and any connector already holding a cached auth_headers()/token from
        before the call is unaffected only until its own natural refresh/next resolve - consistent with
        the disclosed limitation already documented for Meesho's static, non-refreshing credentials."""
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT locator FROM credential_references WHERE merchant_id = %s AND ref = %s", (merchant_id, ref))
            row = cur.fetchone()
        if not row:
            raise TenantAccessError(f"{merchant_id} cannot access credential {ref}")
        self.credential_provider.delete(row[0])

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

    def atomic_claim_refund_capacity(self, merchant_id: str, order_id: str, return_id: str, currency: str) -> dict[str, Any] | None:
        """Step 7B.1 - closes a real, reproduced cross-Return refund-cap race (19/20 trials over-refunded
        in the bounded reproduction that preceded this fix): `evaluate_return_refund`'s "remaining
        refundable amount" computation was a plain, unlocked read - two DISTINCT Returns on the SAME
        order, evaluated concurrently, could both read the same pre-refund remaining balance and both
        create a full-amount Refund, together exceeding the order's authoritative refundable amount.

        SELECT ... FOR UPDATE on the Order row is the per-order serialization point (the natural,
        already-canonical authority every Refund traces back to via order_id) - the SAME idiom as every
        other atomic primitive in this codebase, not a new locking mechanism. Inside that lock: re-read
        the order's authoritative total, re-read EVERY Refund already committed against it (financially
        committed = every status except "denied" - see this method's caller for the full state-machine
        reasoning, in particular that "mutation_uncertain" and "permitted"/"approval_required" MUST
        continue reserving capacity, since a status other than "denied" always represents money that has
        moved or might still move), compute the remaining capacity, and - if any remains - claim it by
        inserting the new Refund row for THIS return atomically, in the SAME transaction. A concurrent
        claim for a DIFFERENT return on the same order blocks on this SAME lock and, once unblocked,
        correctly sees the first claim's already-committed row reducing its own remaining capacity.

        The Refund is created with a NEUTRAL, capacity-consuming placeholder status ("permitted") - the
        caller is responsible for correcting it to "approval_required"/"denied" immediately afterward
        using the merchant's actual policy threshold (which, for a return-triggered refund, can only
        move a NON-DENIED decision between ALLOW and REQUIRE_APPROVAL once capacity has genuinely been
        claimed - see evaluate_return_refund's docstring for why DENY is resolved BEFORE ever attempting
        a claim, so it never contends for this lock at all). This keeps policy/approval business logic
        out of the storage layer, while the SAFETY-CRITICAL capacity claim itself stays atomic.

        Same-return replay protection (uq_refund_return_id, Step 7B) remains fully in effect and is
        explicitly handled here too, via the same SAVEPOINT-based UniqueViolation recovery used
        elsewhere in this file: cross-return serialization is an ADDITIONAL guarantee on top of it, not
        a replacement.

        Returns the newly-claimed Refund's data dict, or None if no capacity remained.
        """
        with self.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT data FROM orders WHERE id = %(id)s AND merchant_id = %(mid)s FOR UPDATE", {"id": order_id, "mid": merchant_id})
            order_row = cur.fetchone()
            if not order_row:
                raise NotFoundError(order_id)
            total_amount = int(order_row["data"]["total_amount"])

            cur.execute("SELECT data FROM refunds WHERE merchant_id = %(mid)s AND data->>'order_id' = %(oid)s", {"mid": merchant_id, "oid": order_id})
            committed = sum(int(row["data"]["amount"]) for row in cur.fetchall() if row["data"].get("status") != "denied")
            remaining = max(total_amount - committed, 0)
            if remaining <= 0:
                return None

            refund = Refund(merchant_id=merchant_id, order_id=order_id, return_id=return_id, amount=remaining, currency=currency, status="permitted")
            cur.execute("SAVEPOINT refund_capacity_claim")
            try:
                cur.execute(
                    "INSERT INTO refunds (id, merchant_id, data) VALUES (%(id)s, %(mid)s, %(data)s)",
                    {"id": refund.id, "mid": merchant_id, "data": Json(refund.model_dump(mode="json"))},
                )
            except psycopg2.errors.UniqueViolation:
                cur.execute("ROLLBACK TO SAVEPOINT refund_capacity_claim")
                cur.execute(
                    "SELECT data FROM refunds WHERE merchant_id = %(mid)s AND data->>'return_id' = %(rid)s ORDER BY created_at ASC LIMIT 1",
                    {"mid": merchant_id, "rid": return_id},
                )
                row = cur.fetchone()
                return row["data"]
            else:
                cur.execute("RELEASE SAVEPOINT refund_capacity_claim")
            return refund.model_dump(mode="json")

    def mark_acknowledgement_applied(self, merchant_id: str, acknowledgement_id: str, applied: bool) -> None:
        """Step 7A.1 - a direct, targeted UPDATE for SupplierAcknowledgement.applied. `store.put()` for
        this model is INSERT-only (ON CONFLICT ... DO NOTHING, keyed on (merchant_id, purchase_order_id,
        external_ref) - see put()'s SupplierAcknowledgement branch): a second put() call for a row that
        already exists is SILENTLY DISCARDED, never updating existing fields. That is exactly correct
        for the model's own external_ref-replay-dedup purpose, but it means `applied` (which
        record_supplier_acknowledgement can only determine authoritatively AFTER the row has already
        been inserted, to preserve the existing external_ref dedup ordering) can never be corrected via
        put() - a genuine, found bug where the persisted `applied` value silently stayed at its initial
        placeholder forever, defeating the whole sequence-staleness check downstream. No row lock is
        needed here: exactly one call (the one that created/resolved this specific ack.id) ever writes
        this field, so there is no concurrent writer to serialize against."""
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE supplier_acknowledgements SET data = jsonb_set(data, '{applied}', %s), updated_at = now() WHERE id = %s AND merchant_id = %s",
                (Json(applied), acknowledgement_id, merchant_id),
            )

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

    def atomic_apply_acknowledgement(
        self, merchant_id: str, po_id: str, po_line_id: str, sku: str, location_ref: str, sequence: int, raw_delta: int,
    ) -> dict[str, Any]:
        """Step 7A.1 - ONE atomic transaction coupling three consequences that were previously three
        separate, under-synchronized operations: (1) the per-PO acknowledgement-sequence staleness
        claim, (2) the PurchaseOrderLine.quantity_confirmed increment, and (3) the location-scoped
        Inventory.confirmed_inbound increment (capped to the legitimate/ordered portion). A failure
        anywhere in this transaction rolls back ALL THREE together - the PO line can never end up
        confirmed while the matching inbound increment is lost, or vice versa.

        ROOT CAUSE this closes (found via a real, reproduced Postgres race - see the Step 7A.1
        investigation, not a theoretical concern): `record_supplier_acknowledgement` used to compute
        "is this sequence stale" via a PLAIN, UNLOCKED read of the highest already-APPLIED sequence,
        THEN separately call the (individually correct) `atomic_apply_po_line_confirmation`. Two
        genuinely concurrent acknowledgement events for DIFFERENT, legitimate sequence numbers (e.g.
        sequence=1 confirming +60, sequence=2 confirming +40, arriving with no real ordering between
        them) could have their staleness DECIDED in an order that doesn't match their sequence numbers
        purely due to processing/scheduling - and the OLD rule ("reject if sequence <= highest already
        applied") then incorrectly discarded the lower-numbered one as "stale", losing 60 real, confirmed
        units. This is not solvable by locking alone: even under perfect serialization, whichever of the
        two is processed first still makes the other look "stale" under that rule.

        STALENESS RULE (corrected): an acknowledgement event is stale/rejected if and only if this EXACT
        `sequence` number has ALREADY been applied for this PO before - never merely because some OTHER,
        numerically higher sequence was already applied. This is what makes genuinely concurrent,
        DISTINCT acknowledgement deltas both apply regardless of processing order, while an EXACT
        sequence being resent (a real replay/duplicate-with-a-different-external_ref risk, distinct from
        an identical external_ref replay - which is already deduped upstream by a DB-unique constraint
        and never reaches this method at all) is still correctly rejected, evidence-kept, state
        unaltered.

        Deterministic lock order, every caller, always: PurchaseOrder -> PurchaseOrderLine -> Inventory
        (the Inventory step is itself a single-statement atomic UPSERT via
        uq_inventory_merchant_sku_location's own ON CONFLICT handling, reusing atomic_adjust_inventory's
        exact SQL pattern rather than a fourth locking primitive).

        Returns {"applied": bool, "new_true_total": int | None, "legitimate_delta": int, "over_confirmed": bool}.
        `new_true_total`/`legitimate_delta`/`over_confirmed` are only meaningful when `applied` is True.
        """
        with self.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id FROM purchase_orders WHERE id = %(po_id)s AND merchant_id = %(mid)s FOR UPDATE", {"po_id": po_id, "mid": merchant_id})
            if not cur.fetchone():
                raise NotFoundError(po_id)

            cur.execute(
                "SELECT DISTINCT (data->>'sequence')::int AS sequence FROM supplier_acknowledgements "
                "WHERE merchant_id = %(mid)s AND data->>'purchase_order_id' = %(po_id)s AND (data->>'applied')::boolean = true",
                {"mid": merchant_id, "po_id": po_id},
            )
            applied_sequences = {row["sequence"] for row in cur.fetchall()}
            if sequence in applied_sequences:
                return {"applied": False, "new_true_total": None, "legitimate_delta": 0, "over_confirmed": False}

            cur.execute("SELECT data FROM purchase_order_lines WHERE id = %(id)s AND merchant_id = %(mid)s FOR UPDATE", {"id": po_line_id, "mid": merchant_id})
            line_row = cur.fetchone()
            if not line_row:
                raise NotFoundError(po_line_id)
            line_data = line_row["data"]
            previous_true_total = int(line_data.get("quantity_confirmed", 0))
            new_true_total = previous_true_total + raw_delta
            quantity_ordered = int(line_data["quantity_ordered"])
            line_data["quantity_confirmed"] = new_true_total
            cur.execute("UPDATE purchase_order_lines SET data = %(data)s, updated_at = now() WHERE id = %(id)s", {"data": Json(line_data), "id": po_line_id})

            legitimate_before = min(previous_true_total, quantity_ordered)
            legitimate_after = min(new_true_total, quantity_ordered)
            legitimate_delta = max(legitimate_after - legitimate_before, 0)

            if legitimate_delta:
                seed = Inventory(merchant_id=merchant_id, sku=sku, location_ref=location_ref, quantity=0, available=0, confirmed_inbound=max(legitimate_delta, 0))
                cur.execute(
                    """
                    INSERT INTO inventory (id, merchant_id, data, updated_at)
                    VALUES (%(id)s, %(merchant_id)s, %(data)s, now())
                    ON CONFLICT (merchant_id, (data->>'sku'), (data->>'location_ref'))
                    DO UPDATE SET
                      data = jsonb_set(
                        inventory.data, '{confirmed_inbound}',
                        to_jsonb(GREATEST(COALESCE((inventory.data->>'confirmed_inbound')::int, 0) + %(ci)s, 0))
                      ),
                      updated_at = now()
                    """,
                    {"id": seed.id, "merchant_id": merchant_id, "data": Json(seed.model_dump(mode="json")), "ci": legitimate_delta},
                )

            return {
                "applied": True, "new_true_total": new_true_total, "legitimate_delta": legitimate_delta,
                "over_confirmed": new_true_total > quantity_ordered,
            }

    def atomic_transition_cancellation_status(self, merchant_id: str, cancellation_id: str, from_statuses: set[str], to_status: str) -> bool:
        """Step 7A - the SAME SELECT ... FOR UPDATE idiom as atomic_apply_po_line_confirmation, applied
        as a general compare-and-swap for Cancellation.status rather than a new subsystem.

        The REAL race this closes (found by a genuine, reproduced concurrency failure, not
        theoretical): a plain read-then-write status transition (e.g. approve_cancellation's old
        "approval_required" -> "approved" write) can silently REGRESS a row that a concurrent
        execute_cancellation call has already advanced further (e.g. all the way to "completed") back
        to an earlier state, because the plain write never re-checks the CURRENT persisted value under
        a lock before overwriting it. Every Cancellation status transition (approve, reject, the
        stale-execution check, and the completion claim) must go through this ONE compare-and-swap.

        Returns True ONLY for the caller whose transition actually applied (status was still one of
        `from_statuses` at lock-acquisition time); every other concurrent caller gets False and must not
        proceed with the mutation/audit its own transition would have authorized.
        """
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT data FROM cancellations WHERE id = %s AND merchant_id = %s FOR UPDATE", (cancellation_id, merchant_id))
            row = cur.fetchone()
            if not row:
                raise NotFoundError(cancellation_id)
            data = row[0]
            if data.get("status") not in from_statuses:
                return False
            data["status"] = to_status
            cur.execute("UPDATE cancellations SET data = %s, updated_at = now() WHERE id = %s", (Json(data), cancellation_id))
            return True

    def atomic_transition_refund_status(self, merchant_id: str, refund_id: str, from_statuses: set[str], to_status: str) -> bool:
        """Step 9 - the SAME SELECT ... FOR UPDATE compare-and-swap idiom as
        atomic_transition_cancellation_status, applied to Refund.status for mutation-uncertainty
        recovery. Returns True ONLY for the caller whose transition actually applied."""
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT data FROM refunds WHERE id = %s AND merchant_id = %s FOR UPDATE", (refund_id, merchant_id))
            row = cur.fetchone()
            if not row:
                raise NotFoundError(refund_id)
            data = row[0]
            if data.get("status") not in from_statuses:
                return False
            data["status"] = to_status
            cur.execute("UPDATE refunds SET data = %s, updated_at = now() WHERE id = %s", (Json(data), refund_id))
            return True

    def atomic_adjust_inventory(
        self, merchant_id: str, sku: str, location_ref: str, *,
        confirmed_inbound_delta: int = 0, quantity_delta: int = 0, available_delta: int = 0,
        reserved_delta: int = 0,
    ) -> Inventory:
        """Atomically creates-or-adjusts the Inventory row for (merchant_id, sku, location_ref) in one
        statement, using uq_inventory_merchant_sku_location's own ON CONFLICT atomicity - no
        application-level lock needed. Phase 4.6 fix for a genuine, reproducible race found while
        hardening this phase: two concurrent supplier acknowledgements (or an acknowledgement racing a
        goods receipt) for a SKU with no prior Inventory row both read "does not exist yet" under the
        old read-modify-write and each INSERT a competing new row - the second INSERT raised
        uq_inventory_merchant_sku_location's UniqueViolation uncaught, and even had it been caught
        naively, discarding the losing caller's delta would have been a silent lost update, not merely
        a crash. All counters are adjusted in the SAME atomic UPSERT regardless of whether the row
        already existed.

        `reserved_delta` (2026-09 reservation-lifecycle fix): used ONLY for CONSUME (paired with
        `quantity_delta`, same sign) and RESTOCK-adjacent bookkeeping where ownership/quantity is
        already deterministically established by the caller (see `adjust_reservation_atomic` for the
        general release/consume path, which locks the owning InventoryReservation row first). This
        method's own upsert has no availability ceiling to check, so it must NEVER be used to CREATE a
        reservation from a requested quantity - that is exactly the check-then-update race
        `reserve_inventory_atomic` exists to close. Floored at 0 via GREATEST exactly like
        `confirmed_inbound`, so `reserved < 0` is structurally impossible regardless of call order.

        `available` remains a strict DERIVED/CACHE value (see Inventory model docstring): every caller
        in this codebase must pass an `available_delta` that keeps it equal to `quantity - reserved`
        (e.g. reserve: -N/+0; release: +N/-N on available/reserved; consume: 0/-N paired with
        quantity_delta=-N; restock: +N/+0 paired with quantity_delta=+N) - this method does not derive
        it automatically, to avoid silently changing existing callers' (e.g. procurement's goods-receipt)
        established, already-correct delta pairs.
        """
        seed = Inventory(
            merchant_id=merchant_id, sku=sku, location_ref=location_ref,
            quantity=max(quantity_delta, 0), available=max(available_delta, 0), confirmed_inbound=max(confirmed_inbound_delta, 0),
            reserved=max(reserved_delta, 0),
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
                        jsonb_set(
                          inventory.data, '{confirmed_inbound}',
                          to_jsonb(GREATEST(COALESCE((inventory.data->>'confirmed_inbound')::int, 0) + %(ci)s, 0))
                        ),
                        '{quantity}', to_jsonb(COALESCE((inventory.data->>'quantity')::int, 0) + %(q)s)
                      ),
                      '{available}', to_jsonb(COALESCE((inventory.data->>'available')::int, 0) + %(av)s)
                    ),
                    '{reserved}', to_jsonb(GREATEST(COALESCE((inventory.data->>'reserved')::int, 0) + %(rv)s, 0))
                  ),
                  updated_at = now()
                RETURNING data
                """,
                {
                    "id": seed.id, "merchant_id": merchant_id, "data": Json(seed.model_dump(mode="json")),
                    "ci": confirmed_inbound_delta, "q": quantity_delta, "av": available_delta, "rv": reserved_delta,
                },
            )
            row = cur.fetchone()
        return Inventory.model_validate(row["data"])

    def reserve_inventory_atomic(
        self, merchant_id: str, sku: str, location_ref: str, *,
        quantity_requested: int, source_type: str, source_id: str, idempotency_key: str,
        order_line_id: str | None = None,
    ) -> InventoryReservation:
        """THE one database-atomic reservation-CREATION operation (2026-09 concurrency correction).
        Plain additive deltas cannot safely create a reservation, because creation must both CHECK
        available stock and INCREMENT `reserved` under the same concurrency boundary - two concurrent
        callers each reading available=1 and each incrementing reserved is the exact oversell Saleor's
        own issue #543 documents (checkout-time stock allocation with no locking). This closes it with
        `SELECT ... FOR UPDATE` row-locking the specific Inventory row for the rest of the transaction,
        mirroring the already-established `atomic_apply_po_line_confirmation` pattern in this same file.
        A concurrent reservation attempt against the SAME (merchant, sku, location) blocks here until
        this transaction commits, then sees the updated `reserved` and correctly computes reduced (or
        zero) remaining availability - never both granting the last unit.

        Idempotent replay: a second call with the same (merchant_id, idempotency_key) returns the
        original InventoryReservation unchanged, enforced by uq_inventory_reservations_idempotency at
        the DB level (not just an app-level check), so even a genuine concurrent duplicate call is safe.

        Partial fill: reserves min(available, quantity_requested); the shortfall (if any) is visible as
        quantity_requested - quantity_reserved on the returned record - callers decide what a shortfall
        means (existing ExceptionRecord flow, unchanged). No Inventory row for this (sku, location) is
        treated as zero availability, matching existing pre-fix behavior.
        """
        with self.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT data FROM inventory_reservations WHERE merchant_id = %(mid)s AND data->>'idempotency_key' = %(key)s",
                {"mid": merchant_id, "key": idempotency_key},
            )
            existing = cur.fetchone()
            if existing:
                return InventoryReservation.model_validate(existing["data"])
            cur.execute(
                "SELECT data FROM inventory WHERE merchant_id = %(mid)s AND data->>'sku' = %(sku)s AND data->>'location_ref' = %(loc)s FOR UPDATE",
                {"mid": merchant_id, "sku": sku, "loc": location_ref},
            )
            row = cur.fetchone()
            reserve_qty = 0
            if row is not None:
                inv = Inventory.model_validate(row["data"])
                reserve_qty = max(min(inv.quantity - inv.reserved, quantity_requested), 0)
                if reserve_qty > 0:
                    cur.execute(
                        """
                        UPDATE inventory SET
                          data = jsonb_set(
                            jsonb_set(data, '{reserved}', to_jsonb(GREATEST(COALESCE((data->>'reserved')::int, 0) + %(rq)s, 0))),
                            '{available}', to_jsonb(GREATEST(COALESCE((data->>'available')::int, (data->>'quantity')::int) - %(rq)s, 0))
                          ),
                          updated_at = now()
                        WHERE id = %(id)s
                        """,
                        {"rq": reserve_qty, "id": inv.id},
                    )
            reservation = InventoryReservation(
                merchant_id=merchant_id, sku=sku, location_ref=location_ref,
                source_type=source_type, source_id=source_id, order_line_id=order_line_id, idempotency_key=idempotency_key,
                quantity_requested=quantity_requested, quantity_reserved=reserve_qty,
            )
            cur.execute(
                "INSERT INTO inventory_reservations (id, merchant_id, data) VALUES (%(id)s, %(mid)s, %(data)s)",
                {"id": reservation.id, "mid": merchant_id, "data": Json(reservation.model_dump(mode="json"))},
            )
            return reservation

    def adjust_reservation_atomic(self, merchant_id: str, reservation_id: str, *, mode: str, amount: int) -> InventoryReservation:
        """The one database-atomic reservation RELEASE/CONSUME operation. Ownership and quantity are
        already deterministically established here (this reservation's own `quantity_reserved`, set once
        at creation and never changed) - per the accepted design, additive deltas are safe for this half
        of the lifecycle. `SELECT ... FOR UPDATE` on the reservation row still guards against two
        concurrent release/consume attempts on the SAME reservation double-applying; `amount` is clamped
        to whatever is actually still outstanding (`quantity_reserved - quantity_released -
        quantity_consumed`), so this method is naturally idempotent - calling it twice with the same or
        larger `amount` applies the remainder once, then 0 on any further call. Both the reservation row
        and its owning Inventory row are updated in this SAME transaction.

        mode="release": reserved -N, available +N (quantity unchanged - stock returns to the sellable pool).
        mode="consume": reserved -N, quantity -N (available unchanged - the stock permanently left; it
        was already excluded from `available` since the moment it was reserved).
        """
        with self.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT data FROM inventory_reservations WHERE id = %(id)s AND merchant_id = %(mid)s FOR UPDATE", {"id": reservation_id, "mid": merchant_id})
            row = cur.fetchone()
            if row is None:
                raise NotFoundError(reservation_id)
            reservation = InventoryReservation.model_validate(row["data"])
            remaining = reservation.quantity_reserved - reservation.quantity_released - reservation.quantity_consumed
            apply_amount = max(min(amount, remaining), 0)
            if apply_amount > 0:
                if mode == "release":
                    reservation.quantity_released += apply_amount
                else:
                    reservation.quantity_consumed += apply_amount
                if reservation.quantity_released + reservation.quantity_consumed >= reservation.quantity_reserved:
                    reservation.status = "closed"
                cur.execute(
                    "UPDATE inventory_reservations SET data = %(data)s, updated_at = now() WHERE id = %(id)s",
                    {"data": Json(reservation.model_dump(mode="json")), "id": reservation.id},
                )
                if mode == "release":
                    cur.execute(
                        """
                        UPDATE inventory SET
                          data = jsonb_set(
                            jsonb_set(data, '{reserved}', to_jsonb(GREATEST(COALESCE((data->>'reserved')::int, 0) - %(amt)s, 0))),
                            '{available}', to_jsonb(GREATEST(COALESCE((data->>'available')::int, 0) + %(amt)s, 0))
                          ),
                          updated_at = now()
                        WHERE merchant_id = %(mid)s AND data->>'sku' = %(sku)s AND data->>'location_ref' = %(loc)s
                        """,
                        {"amt": apply_amount, "mid": merchant_id, "sku": reservation.sku, "loc": reservation.location_ref},
                    )
                else:
                    cur.execute(
                        """
                        UPDATE inventory SET
                          data = jsonb_set(
                            jsonb_set(data, '{reserved}', to_jsonb(GREATEST(COALESCE((data->>'reserved')::int, 0) - %(amt)s, 0))),
                            '{quantity}', to_jsonb(GREATEST(COALESCE((data->>'quantity')::int, 0) - %(amt)s, 0))
                          ),
                          updated_at = now()
                        WHERE merchant_id = %(mid)s AND data->>'sku' = %(sku)s AND data->>'location_ref' = %(loc)s
                        """,
                        {"amt": apply_amount, "mid": merchant_id, "sku": reservation.sku, "loc": reservation.location_ref},
                    )
            return reservation

    def quarantine_inventory_atomic(
        self, merchant_id: str, sku: str, location_ref: str, *, quantity: int, reason: str = "inspection"
    ) -> Inventory:
        with self.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT data FROM inventory WHERE merchant_id = %(mid)s AND data->>'sku' = %(sku)s AND data->>'location_ref' = %(loc)s FOR UPDATE",
                {"mid": merchant_id, "sku": sku, "loc": location_ref},
            )
            row = cur.fetchone()
            if row is None:
                raise NotFoundError(f"Inventory({sku}@{location_ref})")
            inv = Inventory.model_validate(row["data"])
            current_sellable = inv.sellable if inv.sellable is not None else max(inv.quantity - inv.quarantine - inv.in_transit, 0)
            ats = max(current_sellable - inv.reserved, 0)
            if ats < quantity:
                raise ValueError(f"Insufficient available stock to quarantine: ats={ats}, requested={quantity}")
            new_sellable = max(current_sellable - quantity, 0)
            new_quarantine = inv.quarantine + quantity
            new_available = max(new_sellable - inv.reserved, 0)
            cur.execute(
                """
                UPDATE inventory SET
                  data = jsonb_set(
                    jsonb_set(
                      jsonb_set(data, '{sellable}', to_jsonb(%(sellable)s::int)),
                      '{quarantine}', to_jsonb(%(quarantine)s::int)
                    ),
                    '{available}', to_jsonb(%(available)s::int)
                  ),
                  updated_at = now()
                WHERE merchant_id = %(mid)s AND data->>'sku' = %(sku)s AND data->>'location_ref' = %(loc)s
                RETURNING data
                """,
                {
                    "sellable": new_sellable,
                    "quarantine": new_quarantine,
                    "available": new_available,
                    "mid": merchant_id,
                    "sku": sku,
                    "loc": location_ref,
                },
            )
            updated_row = cur.fetchone()
            return Inventory.model_validate(updated_row["data"])

    def release_quarantine_atomic(
        self, merchant_id: str, sku: str, location_ref: str, *, quantity: int
    ) -> Inventory:
        with self.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT data FROM inventory WHERE merchant_id = %(mid)s AND data->>'sku' = %(sku)s AND data->>'location_ref' = %(loc)s FOR UPDATE",
                {"mid": merchant_id, "sku": sku, "loc": location_ref},
            )
            row = cur.fetchone()
            if row is None:
                raise NotFoundError(f"Inventory({sku}@{location_ref})")
            inv = Inventory.model_validate(row["data"])
            if inv.quarantine < quantity:
                raise ValueError(f"Cannot release {quantity} from quarantine; current quarantine is {inv.quarantine}")
            new_quarantine = inv.quarantine - quantity
            current_sellable = inv.sellable if inv.sellable is not None else max(inv.quantity - inv.quarantine - inv.in_transit, 0)
            new_sellable = current_sellable + quantity
            new_available = max(new_sellable - inv.reserved, 0)
            cur.execute(
                """
                UPDATE inventory SET
                  data = jsonb_set(
                    jsonb_set(
                      jsonb_set(data, '{sellable}', to_jsonb(%(sellable)s::int)),
                      '{quarantine}', to_jsonb(%(quarantine)s::int)
                    ),
                    '{available}', to_jsonb(%(available)s::int)
                  ),
                  updated_at = now()
                WHERE merchant_id = %(mid)s AND data->>'sku' = %(sku)s AND data->>'location_ref' = %(loc)s
                RETURNING data
                """,
                {
                    "sellable": new_sellable,
                    "quarantine": new_quarantine,
                    "available": new_available,
                    "mid": merchant_id,
                    "sku": sku,
                    "loc": location_ref,
                },
            )
            updated_row = cur.fetchone()
            return Inventory.model_validate(updated_row["data"])

    def reserve_order_lines_atomic(
        self, merchant_id: str, source_type: str, source_id: str, location_ref: str, lines: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Step 4 Part A/B/C/F - TRUE whole-order atomicity for one candidate-location attempt. Every
        line is checked and reserved together in ONE database transaction: either ALL commit together, or
        NOTHING is ever mutated or externally visible. This closes the exact gap Step 3's
        sequential-per-line-with-Python-level-compensating-release design left open - a concurrent
        transaction COULD observe an earlier line's committed reservation before a later line's failure
        triggered the compensating release, because each line was its OWN separate transaction. Here,
        `SELECT ... FOR UPDATE` locks are held across the WHOLE decision, and nothing is written until
        every line is confirmed sufficient.

        Part B - deterministic lock order: every required Inventory row at this location is locked in
        SKU-ascending order (a stable, canonical, input-order-independent key) BEFORE any check or
        mutation - the standard, well-established deadlock-avoidance technique (this step's OSS-adjacent
        check: "sort resources by a stable key before locking, to avoid cyclic waiting" is generic
        database practice, not specific to any one commerce system, and directly confirms this design).
        Two concurrent multi-line orders whose SKU line order happens to be reversed lock in the SAME
        physical order regardless, so neither can hold what the other needs while waiting for what the
        other holds.

        Part C/F - idempotency conflict as a real signal, not silently absorbed: each line's
        `idempotency_key` is enforced by `inventory_reservations`' own uq_inventory_reservations_idempotency
        unique index (Step 1). If a concurrent attempt for the SAME order-line already committed elsewhere
        (e.g. a racing allocator reached a different candidate location first, or this is a genuine
        replay), THIS transaction's own INSERT conflicts and the whole attempt aborts cleanly - nothing
        mutated, `conflict=True` returned. The caller must then re-check the order's now-existing
        reservations (the idempotent-replay / ALREADY_ALLOCATED case), never invent a second decision.

        Returns `{"success": bool, "conflict": bool, "line_results": [{"sku","requested","reserved",
        "shortfall"}, ...]}`. `lines` is `[{"sku", "quantity_requested", "order_line_id", "idempotency_key"}, ...]`.
        """
        if not lines:
            return {"success": True, "conflict": False, "line_results": []}
        skus_needed = sorted({line["sku"] for line in lines})
        with self.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            try:
                cur.execute(
                    """
                    SELECT id, data FROM inventory
                    WHERE merchant_id = %(mid)s AND data->>'location_ref' = %(loc)s AND data->>'sku' = ANY(%(skus)s)
                    ORDER BY data->>'sku' ASC
                    FOR UPDATE
                    """,
                    {"mid": merchant_id, "loc": location_ref, "skus": skus_needed},
                )
                locked_by_sku = {row["data"]["sku"]: (row["id"], Inventory.model_validate(row["data"])) for row in cur.fetchall()}

                shortfalls = []
                for line in lines:
                    inv_tuple = locked_by_sku.get(line["sku"])
                    available = inv_tuple[1].ats if inv_tuple else 0
                    if available < line["quantity_requested"]:
                        shortfalls.append(line)

                if shortfalls:
                    conn.rollback()
                    return {
                        "success": False, "conflict": False,
                        "line_results": [
                            {"sku": line["sku"], "requested": line["quantity_requested"], "reserved": 0, "shortfall": line["quantity_requested"]}
                            for line in lines
                        ],
                    }

                for line in sorted(lines, key=lambda l: l["sku"]):
                    reservation = InventoryReservation(
                        merchant_id=merchant_id, sku=line["sku"], location_ref=location_ref,
                        source_type=source_type, source_id=source_id, order_line_id=line.get("order_line_id"),
                        idempotency_key=line["idempotency_key"],
                        quantity_requested=line["quantity_requested"], quantity_reserved=line["quantity_requested"],
                    )
                    cur.execute(
                        "INSERT INTO inventory_reservations (id, merchant_id, data) VALUES (%(id)s, %(mid)s, %(data)s)",
                        {"id": reservation.id, "mid": merchant_id, "data": Json(reservation.model_dump(mode="json"))},
                    )
                    inv_id, inv = locked_by_sku[line["sku"]]
                    cur.execute(
                        """
                        UPDATE inventory SET
                          data = jsonb_set(
                            jsonb_set(data, '{reserved}', to_jsonb(GREATEST(COALESCE((data->>'reserved')::int, 0) + %(q)s, 0))),
                            '{available}', to_jsonb(GREATEST(COALESCE((data->>'available')::int, 0) - %(q)s, 0))
                          ),
                          updated_at = now()
                        WHERE id = %(id)s
                        """,
                        {"q": line["quantity_requested"], "id": inv_id},
                    )
                conn.commit()
                return {
                    "success": True, "conflict": False,
                    "line_results": [
                        {"sku": line["sku"], "requested": line["quantity_requested"], "reserved": line["quantity_requested"], "shortfall": 0}
                        for line in lines
                    ],
                }
            except psycopg2.errors.UniqueViolation:
                conn.rollback()
                return {"success": False, "conflict": True, "line_results": []}

    def create_api_key(
        self, *, merchant_id: str | None, role: str, label: str | None = None,
        allowed_merchants: list[str] | None = None,
    ) -> tuple[str, str]:
        """`allowed_merchants`, when given, mints an internal-operator key explicitly authorized for
        exactly that set of merchants (api_keys.merchant_id is left NULL - this key is not scoped to one
        merchant, it is scoped to the set in api_key_merchants). Every existing caller that never passes
        this keeps creating single-merchant keys exactly as before - purely additive. Only meaningful for
        role='operator'; a 'service' key is already unrestricted and never needs this."""
        raw_key = generate_api_key()
        key_id = f"key_{os.urandom(12).hex()}"
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO api_keys (id, merchant_id, key_hash, role, label) VALUES (%s, %s, %s, %s, %s)",
                (key_id, None if allowed_merchants else merchant_id, hash_api_key(raw_key), role, label),
            )
            if allowed_merchants:
                cur.executemany(
                    "INSERT INTO api_key_merchants (api_key_id, merchant_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    [(key_id, m) for m in allowed_merchants],
                )
        return key_id, raw_key

    def resolve_api_key(self, raw_key: str) -> dict[str, Any] | None:
        with self.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, merchant_id, role, label FROM api_keys WHERE key_hash = %s AND revoked_at IS NULL",
                (hash_api_key(raw_key),),
            )
            row = cur.fetchone()
            if row is None:
                return None
            record = dict(row)
            cur.execute("SELECT merchant_id FROM api_key_merchants WHERE api_key_id = %s", (record["id"],))
            allowed = [r["merchant_id"] for r in cur.fetchall()]
            record["allowed_merchants"] = allowed or None
        return record

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
