from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class SourceOfTruth(str, Enum):
    SANOCEA = "sanocea"
    CHANNEL = "channel"
    CONNECTOR = "connector"
    CUSTOMER = "customer"
    SUPPLIER = "supplier"
    DERIVED = "derived"
    UNKNOWN = "unknown"


class SyncMetadata(BaseModel):
    source_version: str | None = None
    source_updated_at: datetime | None = None
    observed_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)
    event_sequence: int | None = None
    raw_payload_ref: str | None = None


class ExternalRef(BaseModel):
    system: str
    external_id: str
    entity_type: str
    channel_id: str | None = None
    version: str | None = None


class IdempotencyInfo(BaseModel):
    key: str
    scope: str
    first_seen_at: datetime = Field(default_factory=now_utc)


class CanonicalEntity(BaseModel):
    id: str
    merchant_id: str
    external_refs: list[ExternalRef] = Field(default_factory=list)
    source_of_truth: SourceOfTruth = SourceOfTruth.UNKNOWN
    sync: SyncMetadata = Field(default_factory=SyncMetadata)
    idempotency: IdempotencyInfo | None = None


class Merchant(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("mer"))
    legal_name: str
    display_name: str
    default_currency: str = "INR"
    timezone: str = "Asia/Kolkata"
    config: dict[str, Any] = Field(default_factory=dict)
    source_of_truth: SourceOfTruth = SourceOfTruth.SANOCEA


class Channel(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("chn"))
    type: str
    name: str
    enabled: bool = True
    api_version: str | None = None
    capabilities: dict[str, bool] = Field(default_factory=dict)
    credential_ref: str | None = None
    rate_limit_profile: str | None = None
    source_of_truth: SourceOfTruth = SourceOfTruth.SANOCEA


class Product(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("prd"))
    title: str
    brand: str | None = None
    taxonomy: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    status: Literal["draft", "approved", "published", "archived"] = "draft"


class ProvenanceClassification(str, Enum):
    SOURCE_FACT = "SOURCE_FACT"
    DERIVED_DETERMINISTIC = "DERIVED_DETERMINISTIC"
    AI_ENRICHED = "AI_ENRICHED"
    AI_SUGGESTED = "AI_SUGGESTED"
    MISSING = "MISSING"
    HUMAN_APPROVED = "HUMAN_APPROVED"
    EXTERNALLY_VERIFIED = "EXTERNALLY_VERIFIED"


class CommercialFact(BaseModel):
    name: str
    value: Any = None
    source: str = ""
    locator: dict[str, Any] = Field(default_factory=dict)
    evidence_ref: str = ""
    classification: str = "SOURCE_FACT"
    confidence: float = 1.0
    approved: bool = False
    approved_by: str | None = None
    approved_at: datetime | None = None
    verified: bool = False
    verified_by: str | None = None
    verified_at: datetime | None = None
    conflicted: bool = False
    conflict_sources: list[dict[str, Any]] = Field(default_factory=list)
    resolution_note: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExtractedAttribute(BaseModel):
    name: str
    value: Any
    source_file: str
    source_locator: dict[str, Any]
    evidence_ref: str
    confidence: float = 1.0
    extractor: str = "structured"
    verified: bool = False
    approved: bool = False
    rejected: bool = False


class VariantDraft(BaseModel):
    id: str = Field(default_factory=lambda: new_id("vdf"))
    sku: str | None = None
    barcode: str | None = None
    option_values: dict[str, str] = Field(default_factory=dict)
    price: int | None = None
    compare_at_price: int | None = None
    cost_price: int | None = None
    weight: float | None = None
    dimensions: dict[str, Any] = Field(default_factory=dict)
    inventory_quantity: int | None = None
    commercial_facts: dict[str, CommercialFact] = Field(default_factory=dict)
    conflicts: list[str] = Field(default_factory=list)
    status: Literal["ACTIVE", "STALE", "REMOVED"] = "ACTIVE"
    source_locators: list[dict[str, Any]] = Field(default_factory=list)


class IdentityDecision(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("idd"))
    source_identifier_a: str
    source_identifier_b: str
    decision: Literal["SAME", "DIFFERENT"]
    decided_by: str
    decided_at: datetime = Field(default_factory=now_utc)
    canonical_id: str | None = None
    notes: str | None = None


class ProductDraft(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("pdr"))
    product_id: str | None = None
    sku: str | None = None
    title: str | None = None
    price: int | None = None
    currency: str | None = None
    product_type: str | None = None
    category: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    commercial_facts: dict[str, CommercialFact] = Field(default_factory=dict)
    extracted_attributes: list[ExtractedAttribute] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    conflict_details: dict[str, Any] = Field(default_factory=dict)

    # Orthogonal Identity Status (Stage 4 Amendment 2)
    identity_status: Literal["RESOLVED", "AMBIGUOUS", "UNRESOLVED", "CONFLICT"] = "UNRESOLVED"
    identity_key: str | None = None
    identity_candidates: list[dict[str, Any]] = Field(default_factory=list)
    identity_conflict_reason: str | None = None

    # Variants & Options Modeling (Stage 4 Amendment 6)
    options: list[str] = Field(default_factory=list)
    variants: list[VariantDraft] = Field(default_factory=list)
    stale_revision: bool = False
    source_revision: str | None = None

    state: Literal[
        "READY",
        "NEEDS_APPROVAL",
        "INCOMPLETE",
        "CONFLICTED",
        "INVALID",
        "NEEDS_INFORMATION",
        "CONFLICT",
        "BLOCKED",
    ] = "INCOMPLETE"
    approved_for_publication: bool = False
    approved_by: str | None = None
    approved_at: datetime | None = None


class Variant(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("var"))
    product_id: str
    sku: str | None = None
    option_values: dict[str, str] = Field(default_factory=dict)
    barcode: str | None = None
    dimensions: dict[str, Any] = Field(default_factory=dict)
    price_hint: dict[str, Any] = Field(default_factory=dict)


class MediaAsset(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("med"))
    object_uri: str
    checksum: str
    mime_type: str
    transforms: dict[str, str] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)


class Inventory(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("inv"))
    sku: str
    location_ref: str
    quantity: int
    reserved: int = 0
    status: str = "observed"
    # `available` is a STRICT DERIVED/CACHE value, never independently mutated - authoritative formula
    # is always `quantity - reserved` (2026-09 reservation-lifecycle fix; see InventoryReservation).
    # Kept as a real persisted field rather than a computed property for backward compatibility with
    # every existing caller/fixture that constructs Inventory(..., available=X) directly - but every
    # WRITE path this fix touches (reserve/release/consume/restock/observe_inventory) now derives it
    # from quantity-reserved instead of applying an independent delta or overwrite, closing the exact
    # bug this fix found: an external inventory sync used to reset `available` to the raw synced
    # quantity, silently discarding whatever was currently reserved.
    available: int | None = None
    committed: int = 0
    # Phase 4: quantity a supplier has CONFIRMED (via SupplierAcknowledgement) but that has not yet
    # passed goods receipt. Deliberately separate from `quantity`/`available` - confirmed inbound
    # informs replenishment planning (see ProcurementService.inventory_position) but must NEVER be
    # added to sellable stock automatically. Only an explicit goods-receipt action moves it there.
    confirmed_inbound: int = 0
    observed_at: datetime = Field(default_factory=now_utc)


class InventoryReservation(CanonicalEntity):
    """The reservation OWNERSHIP ledger (2026-09 reservation-lifecycle fix). `Inventory.reserved` is
    the aggregate counter; this is the per-reservation record that makes release/consume correct under
    partial fulfilment and concurrency - proven necessary by direct inspection (not assumed) before
    adding it: `ConnectorCommand`/idempotency history is an immutable, append-only AUDIT trail of
    individual events, not a live record with a mutable "how much of this reservation is still
    outstanding" counter, so it cannot alone answer "release exactly what THIS order actually owns,
    even after a partial release/consume already happened" without unsafely re-deriving state by
    scanning history. Modeled after the reservation-ledger pattern found in mature OSS commerce systems
    (Medusa's ReservationItem, Saleor's Allocation, ERPNext's Stock Reservation Entries) - the SEMANTIC
    is adopted, not their code or schema.
    """
    id: str = Field(default_factory=lambda: new_id("rsv"))
    sku: str
    location_ref: str
    source_type: str  # "order" | "exchange" - what created this reservation
    source_id: str  # Order.id or Exchange.id
    # Disambiguates two OrderLines sharing the same SKU within the same order (a real ambiguity found
    # during Step 1A review, not hypothetical: the reservation idempotency_key alone used to be keyed by
    # (order_id, sku), so a second same-SKU line would collide with the first line's key and silently
    # reserve nothing for itself). None for exchange reservations, which have no OrderLine.
    order_line_id: str | None = None
    idempotency_key: str  # unique per (merchant_id, idempotency_key) - DB-enforced, not just app-checked
    quantity_requested: int  # what was asked for (may exceed quantity_reserved - a real shortfall)
    quantity_reserved: int  # immutable: the exact amount actually reserved at creation time
    quantity_released: int = 0  # cumulative, never exceeds quantity_reserved
    quantity_consumed: int = 0  # cumulative, never exceeds quantity_reserved - quantity_released
    status: str = "active"  # active | closed (released+consumed together reached quantity_reserved)


class Customer(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("cus"))
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    consent: dict[str, bool] = Field(default_factory=dict)


class Address(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("adr"))
    customer_id: str | None = None
    line1: str
    line2: str | None = None
    city: str | None = None
    region: str | None = None
    postal_code: str | None = None
    country_code: str
    verification_status: Literal["unverified", "verified", "failed"] = "unverified"


class Order(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("ord"))
    channel_id: str
    customer_id: str | None = None
    order_number: str
    status: str
    payment_status: str | None = None
    fulfillment_status: str | None = None
    total_amount: int
    currency: str
    placed_at: datetime | None = None


class OrderLine(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("lin"))
    order_id: str
    product_id: str | None = None
    variant_id: str | None = None
    sku: str | None = None
    title: str
    quantity: int
    unit_amount: int
    tax_amount: int = 0
    discount_amount: int = 0
    fulfillment_state: str = "pending"


class Payment(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("pay"))
    order_id: str
    provider: str
    amount: int
    currency: str
    status: str
    verified: bool = False


class PaymentObservation(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("pob"))
    order_id: str | None = None
    payment_id: str | None = None
    provider: str
    external_payment_id: str | None = None
    amount: int
    currency: str
    status: str
    observed_at: datetime = Field(default_factory=now_utc)
    evidence_ref: str | None = None


class SettlementBatch(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("stb"))
    provider: str
    external_batch_id: str
    settlement_date: datetime
    currency: str
    gross_amount: int = 0
    net_amount: int = 0
    status: str = "observed"


class SettlementEntry(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("ste"))
    batch_id: str
    provider: str
    external_entry_id: str
    entry_type: Literal["payment", "refund", "fee", "courier_charge", "marketplace_deduction", "cod_collection", "adjustment"]
    # The provider's OWN order/transaction reference, exactly as it arrived on the settlement feed -
    # immutable evidence, kept even when resolution fails. Phase 3.1: settlement entries no longer carry
    # Sanocea's internal order.id directly for payment/cod_collection entries; order_id below is filled
    # in by FinanceOperationsService by resolving provider_order_reference through external_id_mappings.
    provider_order_reference: str | None = None
    order_id: str | None = None
    # Phase 4.6: the same treatment as provider_order_reference, applied to refund entries - the
    # provider's own refund reference, exactly as it arrived; refund_id below is filled in by
    # FinanceOperationsService by resolving this through external_id_mappings, never trusted directly
    # off the incoming payload.
    provider_refund_reference: str | None = None
    refund_id: str | None = None
    amount: int
    currency: str
    description: str | None = None
    evidence_ref: str | None = None


class FinanceReconciliation(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("fin"))
    scope: str
    object_type: str
    object_id: str | None = None
    expected_amount: int | None = None
    observed_amount: int | None = None
    currency: str | None = None
    result: Literal[
        "MATCH", "EXPECTED_LAG", "DIVERGENCE", "UNKNOWN", "EXTERNAL_ONLY",
        "CANONICAL_ONLY", "DUPLICATE", "REQUIRES_CONFIGURATION",
        # Phase 3.1 - cumulative, cross-batch settlement accounting states:
        "PARTIAL_SETTLEMENT", "OVER_SETTLED", "UNDER_SETTLED", "UNRESOLVED_REFERENCE", "ADJUSTMENT_RECORDED",
    ]
    tolerance: int = 0
    exception_id: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)


class Fulfilment(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("ful"))
    order_id: str
    provider: str
    status: str
    sla_at: datetime | None = None


class Shipment(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("shp"))
    fulfilment_id: str | None = None
    order_id: str
    carrier: str
    tracking_number: str | None = None
    status: str
    promised_delivery_at: datetime | None = None


class TrackingEvent(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("trk"))
    shipment_id: str
    carrier_code: str
    description: str
    occurred_at: datetime
    location: str | None = None
    status: str = "unknown"
    external_sequence: int | None = None


class InventoryObservation(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("iob"))
    order_id: str | None = None
    sku: str
    observed_quantity: int | None = None
    source: str
    status: Literal["observed", "divergent", "unknown"] = "observed"
    evidence_ref: str | None = None


class FulfilmentObservation(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("fob"))
    order_id: str
    source: str
    status: str
    observed_at: datetime = Field(default_factory=now_utc)
    evidence_ref: str | None = None


class ShipmentObservation(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("sob"))
    order_id: str
    source: str
    status: str
    tracking_number: str | None = None
    last_tracking_at: datetime | None = None
    evidence_ref: str | None = None


class Return(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("ret"))
    order_id: str
    status: str
    reason: str | None = None
    requested_variant_sku: str | None = None
    eligibility: str | None = None
    approval_id: str | None = None
    # Set only when status becomes "accepted" (progress_return event "inspection_passed") - a DISTINCT
    # decision from acceptance itself: an accepted return is not automatically restockable (damaged/
    # tampered/non-resalable goods are accepted but never resold). None before that point; never
    # inferred, always the caller's explicit disposition. See PostOrderOperationsService.progress_return.
    restockable: bool | None = None


class Refund(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("ref"))
    order_id: str
    # Step 7B: durable ownership back to the Return that triggered this refund, when applicable - None
    # for a refund created directly (e.g. a support/API-driven request_refund, unrelated to any return).
    # DB-uniquely enforced per (merchant_id, return_id) where set (see migrations/0001_phase05.sql
    # uq_refund_return_id) - the actual concurrency-safety mechanism for "one Return -> at most one
    # Refund", not merely an application-level convention.
    return_id: str | None = None
    amount: int
    currency: str
    # OPERATIONAL EXECUTION lifecycle (Phase 2.1 - "did we tell the provider, did the provider confirm"):
    # permitted/approval_required -> mutation_submitted -> mutation_uncertain -> external_confirmed ->
    # reconciled -> completed. This describes whether the refund was actually carried out.
    status: str
    approval_id: str | None = None
    # FINANCIAL RECONCILIATION truth (Phase 3/3.1/4.5) - a DISTINCT, separately-tracked dimension: does
    # the settlement/statement evidence confirm this refund was correctly debited at the right amount.
    # A refund can be operationally "completed" while this stays "pending" (settlement hasn't arrived
    # yet) or flips to "discrepancy" (settlement disagrees) - that is a REAL, surfaced state, never
    # silently collapsed into `status` above. See packages/finance/operations.py
    # apply_refund_reconciliation_to_canonical() for the only code path that writes this field, and
    # packages/runtime/queries.py get_refund_full_state() for the only place both dimensions are read
    # together (what Support/the operator dashboard must use - never `status` alone).
    financial_reconciliation_status: Literal["pending", "matched", "discrepancy"] = "pending"
    financial_reconciliation_ref: str | None = None
    financial_reconciliation_updated_at: datetime | None = None


class Cancellation(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("can"))
    order_id: str
    status: str
    reason: str | None = None
    approval_id: str | None = None


class Exchange(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("exg"))
    order_id: str
    return_id: str | None = None
    requested_variant_sku: str
    status: str = "requested"
    price_delta: int = 0
    approval_id: str | None = None


class SupportConversation(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("sup"))
    channel_id: str
    customer_id: str | None = None
    order_id: str | None = None
    status: str = "open"
    last_message: str | None = None


class SupportIntent(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("int"))
    conversation_id: str
    intent: str
    confidence: float
    evidence_refs: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)


class CustomerSupportAction(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("csa"))
    conversation_id: str
    order_id: str | None = None
    intent: str
    handling_mode: Literal["AUTOMATIC", "APPROVAL-GATED", "EXCEPTION-ONLY", "MANUAL"]
    action: str
    # "requested": Phase 4.6 - a real canonical action-record (Refund/Return/Cancellation) was created
    # through the actual policy-gated engine, but support itself never executes it - execution/approval
    # follows the same operator flow as a directly-submitted API request. Distinct from "executed"
    # (support performed the mutation itself, e.g. an automatic informational reply).
    status: Literal["proposed", "executed", "blocked", "escalated", "requested"] = "proposed"
    response_text: str | None = None
    policy_decision: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)


class Approval(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("app"))
    workflow_id: str | None = None
    action: str
    object_id: str | None = None
    status: Literal["pending", "approved", "denied", "expired"] = "pending"
    requested_by: str
    decided_by: str | None = None
    decided_at: datetime | None = None


class ExceptionRecord(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("exc"))
    severity: Literal["info", "warning", "error", "critical"]
    category: str
    message: str
    object_id: str | None = None
    status: Literal["open", "acknowledged", "resolved"] = "open"
    remediation_options: list[str] = Field(default_factory=list)
    correlation_id: str | None = None


class WorkflowExecution(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("wfl"))
    workflow_type: str
    business_key: str
    temporal_workflow_id: str
    temporal_run_id: str | None = None
    status: Literal["running", "waiting_approval", "completed", "failed"] = "running"
    current_step: str | None = None
    correlation_id: str | None = None


class ConnectorCommand(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("cmd"))
    connector: str
    action: str
    object_type: str
    object_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str
    policy_decision: str = "REQUIRE_APPROVAL"
    approval_id: str | None = None
    status: Literal["pending", "approved", "executing", "succeeded", "failed", "uncertain", "blocked"] = "pending"
    external_ref: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)


class Publication(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("pub"))
    product_draft_id: str
    channel_id: str
    status: Literal["pending", "approved", "publishing", "published", "failed"] = "pending"
    connector_command_id: str | None = None
    external_product_id: str | None = None
    published_at: datetime | None = None


class PublicationAttempt(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("pat"))
    publication_id: str
    connector_command_id: str
    status: Literal["started", "succeeded", "failed", "uncertain"] = "started"
    request_payload: dict[str, Any] = Field(default_factory=dict)
    response_payload: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class ListingVerification(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("ver"))
    publication_id: str
    external_product_id: str | None = None
    outcome: Literal["VERIFIED", "MISMATCH", "FAILED", "UNKNOWN"]
    checked_fields: dict[str, Any] = Field(default_factory=dict)
    mismatches: list[str] = Field(default_factory=list)
    evidence_ref: str | None = None


class AuditEvent(BaseModel):
    id: str = Field(default_factory=lambda: new_id("aud"))
    merchant_id: str
    actor: str
    source: str
    action: str
    object_type: str
    object_id: str | None = None
    timestamp: datetime = Field(default_factory=now_utc)
    workflow_id: str | None = None
    evidence_ref: str | None = None
    requested_mutation: dict[str, Any] | None = None
    result: str
    external_ref: ExternalRef | None = None
    error: str | None = None
    correlation_id: str | None = None


class RawPayload(BaseModel):
    id: str = Field(default_factory=lambda: new_id("raw"))
    merchant_id: str
    source: str
    payload: dict[str, Any]
    headers: dict[str, str] = Field(default_factory=dict)
    received_at: datetime = Field(default_factory=now_utc)
    checksum: str


class ReconciliationResult(BaseModel):
    id: str = Field(default_factory=lambda: new_id("rec"))
    merchant_id: str
    scope: dict[str, Any]
    canonical_ref: dict[str, Any] | None = None
    external_ref: dict[str, Any] | None = None
    result: Literal["matched", "divergent", "failed", "unknown"]
    exception_id: str | None = None
    created_at: datetime = Field(default_factory=now_utc)


class ExternalIdMapping(BaseModel):
    id: str = Field(default_factory=lambda: new_id("map"))
    merchant_id: str
    sanocea_entity_type: str
    sanocea_id: str
    external_system: str
    external_entity_type: str
    external_id: str
    channel_id: str | None = None
    first_seen_at: datetime = Field(default_factory=now_utc)
    last_seen_at: datetime = Field(default_factory=now_utc)


# --- Phase 4: Inventory Planning, Procurement & Supplier Operations ----------------------------------
# DemandObservation is deliberately NOT a persisted entity: recent sales velocity/stock-outs are fully
# derivable from canonical Order/OrderLine/Inventory data Sanocea already owns. Persisting a parallel
# "demand" fact would violate "do not create parallel representations of facts Sanocea already owns."
# ProcurementPolicy is deliberately NOT a persisted entity either - like Phase 3 finance tolerances, it
# lives in merchant configuration (store.get_config(merchant_id)["procurement"]), the same pattern
# already used for finance.tolerances/expected_charges.


class Supplier(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("sup"))
    name: str
    status: Literal["active", "inactive"] = "active"
    default_lead_time_days: int = 7
    # Deterministically derived from historical on-time / short-shipment performance (see
    # ProcurementService._update_supplier_reliability) - never fabricated, never AI-estimated.
    reliability_score: float = 1.0
    contact_ref: str | None = None


class SupplierSku(CanonicalEntity):
    """The supplier <-> canonical SKU relationship: covers 'SupplierOffer', availability, cost, MOQ,
    pack quantity, lead time and preferred/alternate status in one reusable object rather than five."""

    id: str = Field(default_factory=lambda: new_id("ssk"))
    supplier_id: str
    sku: str
    supplier_sku: str
    cost: int
    currency: str
    moq: int = 1
    pack_quantity: int = 1
    lead_time_days: int
    preferred: bool = False
    status: Literal["active", "inactive"] = "active"
    evidence_ref: str | None = None
    observed_at: datetime = Field(default_factory=now_utc)


class ReplenishmentRecommendation(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("rep"))
    sku: str
    # Step 5: the destination this recommendation's inventory-position truth was read for - resolved
    # once (Step 2's resolve_location_ref) before this record is created, never re-resolved later.
    # Defaults to "default" for full backward compatibility with pre-Step-5 single-location merchants.
    location_ref: str = "default"
    recommended_quantity: int
    chosen_supplier_id: str | None = None
    # Every input and derived value that produced recommended_quantity - "explain exactly why".
    reasoning: dict[str, Any] = Field(default_factory=dict)
    status: Literal["proposed", "converted_to_po", "dismissed"] = "proposed"


class PurchaseOrder(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("po"))
    supplier_id: str
    status: Literal[
        "DRAFT", "VALIDATED", "APPROVED", "AUTO_APPROVED", "REQUIRES_APPROVAL", "BLOCKED", "REJECTED",
        "SUBMITTED", "ACKNOWLEDGED", "PARTIALLY_CONFIRMED", "CONFIRMED", "OVER_CONFIRMED",
        "INBOUND", "PARTIALLY_RECEIVED", "RECEIVED", "RECONCILED", "CLOSED",
    ] = "DRAFT"
    currency: str = "INR"
    policy_decision: str | None = None
    approval_id: str | None = None
    external_ref: str | None = None
    idempotency_key: str | None = None
    submitted_at: datetime | None = None


class PurchaseOrderLine(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("pol"))
    purchase_order_id: str
    sku: str
    supplier_sku: str | None = None
    # Step 5 (Part B): the ONE canonical destination location for this line, decided once at PO
    # creation (resolved via Step 2's resolve_location_ref if the caller did not supply one explicitly)
    # and never re-resolved or overridden afterward - acknowledgement, shipment, and goods receipt all
    # read this field rather than re-deriving a location. Defaults to "default" for full backward
    # compatibility with pre-Step-5 single-location merchants/fixtures.
    location_ref: str = "default"
    quantity_ordered: int
    unit_cost: int
    currency: str
    quantity_confirmed: int = 0
    quantity_shipped: int = 0
    quantity_received: int = 0


class SupplierAcknowledgement(CanonicalEntity):
    """The supplier's OWN observed truth about a submitted PO - independent of, and reconciled against,
    Sanocea's PurchaseOrderLine expectations. Mirrors PaymentObservation vs Order in Phase 3."""

    id: str = Field(default_factory=lambda: new_id("ack"))
    purchase_order_id: str
    external_ref: str | None = None
    # Supplier-side monotonic sequence for this PO's acknowledgement stream (independent of when
    # Sanocea happens to receive/process the event) - lets ProcurementService detect and refuse to let
    # a stale/out-of-order event regress authoritative PO state, even though the row itself is always
    # persisted as evidence.
    sequence: int = 0
    lines: list[dict[str, Any]] = Field(default_factory=list)  # [{sku, quantity_confirmed, unit_cost}]
    status: Literal["confirmed", "partially_confirmed", "rejected"] = "confirmed"
    applied: bool = True
    evidence_ref: str | None = None
    observed_at: datetime = Field(default_factory=now_utc)


class InboundShipment(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("isp"))
    purchase_order_id: str
    supplier_id: str
    external_shipment_ref: str | None = None
    sequence: int = 0
    status: Literal["dispatched", "in_transit", "delivered"] = "dispatched"
    applied: bool = True
    dispatched_at: datetime | None = None
    expected_delivery_at: datetime | None = None


class InboundShipmentLine(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("isl"))
    inbound_shipment_id: str
    sku: str
    quantity_shipped: int
    # Step 5B: the EXACT canonical PurchaseOrderLine this shipment line resolved to - set whenever
    # resolution succeeded (via echoed line_ref or an unambiguous legacy SKU match), None when it
    # failed closed (ambiguous_po_line/unknown_po_line/no matching line at all).
    purchase_order_line_id: str | None = None


class GoodsReceipt(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("grc"))
    purchase_order_id: str
    inbound_shipment_id: str | None = None
    external_receipt_ref: str | None = None
    received_at: datetime = Field(default_factory=now_utc)
    status: Literal["received", "received_with_exceptions"] = "received"


class GoodsReceiptLine(CanonicalEntity):
    id: str = Field(default_factory=lambda: new_id("grl"))
    goods_receipt_id: str
    sku: str | None = None
    raw_sku_reference: str | None = None
    quantity_received: int
    quantity_expected: int | None = None
    # Step 5A: `ambiguous_po_line` - a legacy SKU-only receipt matched MORE THAN ONE PurchaseOrderLine on
    # this PO (e.g. the same SKU ordered to two different locations, or twice to the same location) and
    # was refused rather than guessed. `unknown_po_line` - an explicit `po_line_id` was supplied but does
    # not resolve to any line on this PO.
    disposition: Literal["match", "shortage", "excess", "wrong_sku", "unexpected_item", "ambiguous_po_line", "unknown_po_line"] = "match"
    # Step 5 (Part F): the location inventory actually mutated for - always the resolved PO line's
    # canonical location_ref, never a caller-supplied override (see Part H). None for a line that never
    # resolved to exactly one known PO line (wrong_sku/unexpected_item/ambiguous_po_line/unknown_po_line)
    # - no inventory was touched for it.
    location_ref: str | None = None
    # Step 5A (PO-LINE RECEIPT IDENTITY): the EXACT canonical PurchaseOrderLine this receipt line
    # resolved to and mutated - the strongest identity available, always set whenever exactly one line
    # was resolved (whether via an explicit po_line_id or an unambiguous legacy SKU match). None when
    # resolution failed (wrong_sku/unexpected_item/ambiguous_po_line/unknown_po_line).
    purchase_order_line_id: str | None = None
