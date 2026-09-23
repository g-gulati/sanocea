from __future__ import annotations

import copy
import hashlib
import secrets
import threading
from collections import defaultdict
from contextlib import contextmanager
from typing import Any, Iterator, TypeVar

from pydantic import BaseModel

from .models import (
    Approval,
    AuditEvent,
    CanonicalEntity,
    ExternalIdMapping,
    RawPayload,
    now_utc,
)


def generate_api_key() -> str:
    return f"sk_{secrets.token_urlsafe(32)}"


def hash_api_key(raw_key: str) -> str:
    # A raw key is never stored - only its hash. Deliberately unsalted (like a webhook HMAC secret
    # lookup, not a user password): the key itself is high-entropy random, generated once, and the
    # threat model is "stolen DB dump", not "offline dictionary attack against a human-chosen secret".
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


class TenantAccessError(PermissionError):
    pass


class NotFoundError(KeyError):
    pass


T = TypeVar("T", bound=BaseModel)


class Phase0Store:
    """Tenant-aware in-memory repository.

    The interface intentionally mirrors a service/repository boundary that can
    be backed by Postgres without changing domain or connector code.
    """

    def __init__(self) -> None:
        self._entities: dict[str, dict[str, CanonicalEntity]] = defaultdict(dict)
        self._audit: list[AuditEvent] = []
        self._raw: dict[str, RawPayload] = {}
        self._external: dict[tuple[str, str, str, str], ExternalIdMapping] = {}
        self._config: dict[str, dict[str, Any]] = defaultdict(dict)
        self._credentials: dict[str, dict[str, str]] = defaultdict(dict)
        self._idempotency: dict[tuple[str, str], Any] = {}
        self._idempotency_completed: set[tuple[str, str]] = set()
        self._po_line_lock = threading.Lock()
        self._inventory_lock = threading.Lock()
        self._api_keys: dict[str, dict[str, Any]] = {}  # key_hash -> {id, merchant_id, role, label, revoked}
        self._advisory_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)

    @contextmanager
    def advisory_lock(self, name: str) -> Iterator[bool]:
        """In-memory equivalent of PostgresStore.advisory_lock - a non-blocking, process-local mutex
        keyed by name, for tests/harnesses that exercise the recovery runner without real Postgres."""
        lock = self._advisory_locks[name]
        acquired = lock.acquire(blocking=False)
        try:
            yield acquired
        finally:
            if acquired:
                lock.release()

    # Mirrors the Postgres unique indexes that are the FINAL authority against duplicates for these
    # entity types (see migrations/0001_phase05.sql) - keeps in-memory (unit test) and Postgres
    # (integration test) idempotency semantics identical. Each entry: attribute names whose combined,
    # non-None values must be unique within the entity type for a given merchant.
    _DEDUP_KEYS: dict[str, tuple[str, ...]] = {
        "PaymentObservation": ("provider", "external_payment_id"),
        "SettlementBatch": ("provider", "external_batch_id"),
        "SettlementEntry": ("provider", "external_entry_id"),
        "SupplierSku": ("supplier_id", "sku"),
        "PurchaseOrder": ("idempotency_key",),
        "SupplierAcknowledgement": ("purchase_order_id", "external_ref"),
        "InboundShipment": ("supplier_id", "external_shipment_ref"),
        "GoodsReceipt": ("external_receipt_ref",),
        "Publication": ("product_draft_id", "channel_id"),
        "Location": ("code",),
    }

    def put(self, entity: CanonicalEntity) -> CanonicalEntity:
        entity.sync.updated_at = now_utc()
        type_name = type(entity).__name__
        dedup_fields = self._DEDUP_KEYS.get(type_name)
        if dedup_fields:
            values = tuple(getattr(entity, field, None) for field in dedup_fields)
            if all(value is not None for value in values):
                for existing in self._entities[type_name].values():
                    if existing.id == entity.id:
                        # A legitimate update to the SAME row (e.g. a PurchaseOrder/GoodsReceipt moving
                        # through its lifecycle while its idempotency/business key stays set) - never
                        # short-circuit this, or every status transition after the first insert would
                        # silently discard itself and return the stale original.
                        continue
                    if existing.merchant_id == entity.merchant_id and tuple(getattr(existing, field, None) for field in dedup_fields) == values:
                        return copy.deepcopy(existing)
        self._entities[type_name][entity.id] = copy.deepcopy(entity)
        return copy.deepcopy(entity)

    def atomic_claim_refund_capacity(self, merchant_id: str, order_id: str, return_id: str, currency: str) -> dict[str, Any] | None:
        """In-memory equivalent of PostgresStore.atomic_claim_refund_capacity - `self._po_line_lock` held
        across the WHOLE re-read-committed + compute-remaining + claim sequence gives the same
        single-process serialization guarantee Postgres's Order row lock gives across processes. See
        that method's docstring for the full root-cause/state-machine reasoning."""
        from sanocea.packages.domain_contract.models import Refund

        with self._po_line_lock:
            order = self._entities["Order"].get(order_id)
            if order is None or order.merchant_id != merchant_id:
                raise NotFoundError(order_id)
            total_amount = int(order.total_amount)
            committed = sum(
                int(e.amount) for e in self._entities["Refund"].values()
                if e.merchant_id == merchant_id and e.order_id == order_id and e.status != "denied"
            )
            remaining = max(total_amount - committed, 0)
            if remaining <= 0:
                return None
            existing_for_return = next(
                (e for e in self._entities["Refund"].values() if e.merchant_id == merchant_id and e.return_id == return_id),
                None,
            )
            if existing_for_return is not None:
                return existing_for_return.model_dump(mode="json")
            refund = Refund(merchant_id=merchant_id, order_id=order_id, return_id=return_id, amount=remaining, currency=currency, status="permitted")
            self._entities["Refund"][refund.id] = copy.deepcopy(refund)
            return refund.model_dump(mode="json")

    def mark_acknowledgement_applied(self, merchant_id: str, acknowledgement_id: str, applied: bool) -> None:
        """In-memory equivalent of PostgresStore.mark_acknowledgement_applied. The in-memory store's own
        generic put() already supports updating an existing row by id (see put()'s own comment), so this
        method is provided purely for API parity between the two stores - PostgresStore's put() for
        SupplierAcknowledgement specifically does NOT support this (INSERT-only, ON CONFLICT DO NOTHING),
        which is the actual bug this pair of methods exists to work around."""
        entity = self._entities["SupplierAcknowledgement"].get(acknowledgement_id)
        if entity is None or entity.merchant_id != merchant_id:
            raise NotFoundError(acknowledgement_id)
        entity.applied = applied

    def atomic_apply_po_line_confirmation(self, merchant_id: str, line_id: str, delta: int) -> int:
        """Atomically increments PurchaseOrderLine.quantity_confirmed by `delta`, returning the
        resulting TRUE cumulative total (which may exceed quantity_ordered - callers decide what to do
        with an over-confirmation, this only guarantees the increment itself is race-free). A
        threading.Lock is sufficient here (single-process in-memory store); PostgresStore uses
        SELECT ... FOR UPDATE for the equivalent real-concurrency guarantee.
        """
        with self._po_line_lock:
            entity = self._entities["PurchaseOrderLine"].get(line_id)
            if entity is None or entity.merchant_id != merchant_id:
                raise NotFoundError(line_id)
            entity.quantity_confirmed = int(entity.quantity_confirmed) + delta
            return entity.quantity_confirmed

    def atomic_apply_acknowledgement(
        self, merchant_id: str, po_id: str, po_line_id: str, sku: str, location_ref: str, sequence: int, raw_delta: int,
    ) -> dict[str, Any]:
        """In-memory equivalent of PostgresStore.atomic_apply_acknowledgement - `self._po_line_lock` held
        across the WHOLE sequence-staleness-check + PO-line-increment + confirmed-inbound-increment
        sequence gives the same single-process serialization guarantee Postgres's row locks give across
        processes. See that method's docstring for the full root-cause/staleness-rule reasoning."""
        from sanocea.packages.domain_contract.models import Inventory, SupplierAcknowledgement

        with self._po_line_lock:
            applied_sequences = {
                e.sequence for e in self._entities["SupplierAcknowledgement"].values()
                if e.merchant_id == merchant_id and e.purchase_order_id == po_id and e.applied
            }
            if sequence in applied_sequences:
                return {"applied": False, "new_true_total": None, "legitimate_delta": 0, "over_confirmed": False}

            line = self._entities["PurchaseOrderLine"].get(po_line_id)
            if line is None or line.merchant_id != merchant_id:
                raise NotFoundError(po_line_id)
            previous_true_total = int(line.quantity_confirmed)
            new_true_total = previous_true_total + raw_delta
            line.quantity_confirmed = new_true_total

            legitimate_before = min(previous_true_total, line.quantity_ordered)
            legitimate_after = min(new_true_total, line.quantity_ordered)
            legitimate_delta = max(legitimate_after - legitimate_before, 0)

            if legitimate_delta:
                existing = next(
                    (e for e in self._entities["Inventory"].values() if e.merchant_id == merchant_id and e.sku == sku and e.location_ref == location_ref),
                    None,
                )
                if existing is None:
                    entity = Inventory(merchant_id=merchant_id, sku=sku, location_ref=location_ref, quantity=0, confirmed_inbound=max(legitimate_delta, 0))
                else:
                    entity = existing
                    entity.confirmed_inbound = max(entity.confirmed_inbound + legitimate_delta, 0)
                self._entities["Inventory"][entity.id] = copy.deepcopy(entity)

            return {
                "applied": True, "new_true_total": new_true_total, "legitimate_delta": legitimate_delta,
                "over_confirmed": new_true_total > line.quantity_ordered,
            }

    def atomic_transition_cancellation_status(self, merchant_id: str, cancellation_id: str, from_statuses: set[str], to_status: str) -> bool:
        """Step 7A - DB-atomic compare-and-swap for Cancellation.status. Reuses the SAME row-locking
        idiom as atomic_apply_po_line_confirmation (a threading.Lock here; SELECT ... FOR UPDATE + a
        conditional UPDATE in PostgresStore) rather than inventing a new subsystem.

        The REAL race this closes (found by a genuine, reproduced concurrency failure, not
        theoretical): a plain read-then-write status transition (e.g. approve_cancellation's old
        "approval_required" -> "approved" write) can silently REGRESS a row that a concurrent
        execute_cancellation call has already advanced further (e.g. all the way to "completed") back
        to an earlier state, because the plain write never re-checks the CURRENT persisted value under
        a lock before overwriting it - it was computed from a stale, already-superseded read. Every
        Cancellation status transition (approve, reject, the stale-execution check, and the completion
        claim) must go through this ONE compare-and-swap, not a bespoke read-then-write, or the same
        regression class recurs at each new call site.

        Returns True ONLY for the caller whose transition actually applied (the persisted status was
        still one of `from_statuses` at lock-acquisition time); every other concurrent caller gets
        False and must not proceed with the mutation/audit its own transition would have authorized.
        """
        with self._po_line_lock:
            entity = self._entities["Cancellation"].get(cancellation_id)
            if entity is None or entity.merchant_id != merchant_id:
                raise NotFoundError(cancellation_id)
            if entity.status not in from_statuses:
                return False
            entity.status = to_status
            return True

    def atomic_transition_refund_status(self, merchant_id: str, refund_id: str, from_statuses: set[str], to_status: str) -> bool:
        """Step 9 - the SAME compare-and-swap idiom as atomic_transition_cancellation_status, applied to
        Refund.status. Closes the same class of race for refund mutation-uncertainty recovery: a plain
        read-then-write resolution of a "mutation_uncertain"/"mutation_submitted" refund must never
        regress a row a concurrent resolution has already advanced further (e.g. to "completed").

        Returns True ONLY for the caller whose transition actually applied; every other concurrent
        caller gets False and must not proceed with reconciliation/audit/retry its own transition would
        have authorized.
        """
        with self._po_line_lock:
            entity = self._entities["Refund"].get(refund_id)
            if entity is None or entity.merchant_id != merchant_id:
                raise NotFoundError(refund_id)
            if entity.status not in from_statuses:
                return False
            entity.status = to_status
            return True

    def atomic_adjust_inventory(
        self, merchant_id: str, sku: str, location_ref: str, *,
        confirmed_inbound_delta: int = 0, quantity_delta: int = 0, available_delta: int = 0,
        reserved_delta: int = 0,
    ):
        """In-memory equivalent of PostgresStore.atomic_adjust_inventory - threading.Lock is sufficient
        for the single-process in-memory store; see that method's docstring for the real race this
        closes, and for why `reserved_delta`/`available` must never be used to CREATE a reservation
        (see `reserve_inventory_atomic` for that)."""
        from sanocea.packages.domain_contract.models import Inventory

        with self._inventory_lock:
            existing = next(
                (e for e in self._entities["Inventory"].values() if e.merchant_id == merchant_id and e.sku == sku and e.location_ref == location_ref),
                None,
            )
            if existing is None:
                entity = Inventory(
                    merchant_id=merchant_id, sku=sku, location_ref=location_ref,
                    quantity=max(quantity_delta, 0), available=max(available_delta, 0), confirmed_inbound=max(confirmed_inbound_delta, 0),
                    reserved=max(reserved_delta, 0),
                )
            else:
                entity = existing
                entity.confirmed_inbound = max(entity.confirmed_inbound + confirmed_inbound_delta, 0)
                entity.quantity = entity.quantity + quantity_delta
                entity.available = (entity.available if entity.available is not None else 0) + available_delta
                entity.reserved = max(entity.reserved + reserved_delta, 0)
            self._entities["Inventory"][entity.id] = copy.deepcopy(entity)
            return copy.deepcopy(entity)

    def reserve_inventory_atomic(
        self, merchant_id: str, sku: str, location_ref: str, *,
        quantity_requested: int, source_type: str, source_id: str, idempotency_key: str,
        order_line_id: str | None = None,
    ):
        """In-memory equivalent of PostgresStore.reserve_inventory_atomic - `self._inventory_lock` held
        across the whole check-then-increment gives the same single-process serialization guarantee
        Postgres's `SELECT ... FOR UPDATE` gives across processes. See that method's docstring for the
        concurrency reasoning this exists to satisfy."""
        from sanocea.packages.domain_contract.models import Inventory, InventoryReservation

        with self._inventory_lock:
            existing = next(
                (e for e in self._entities["InventoryReservation"].values() if e.merchant_id == merchant_id and e.idempotency_key == idempotency_key),
                None,
            )
            if existing is not None:
                return copy.deepcopy(existing)
            inv = next(
                (e for e in self._entities["Inventory"].values() if e.merchant_id == merchant_id and e.sku == sku and e.location_ref == location_ref),
                None,
            )
            reserve_qty = 0
            if inv is not None:
                reserve_qty = max(min(inv.ats, quantity_requested), 0)
                if reserve_qty > 0:
                    inv.reserved = max(inv.reserved + reserve_qty, 0)
                    inv.available = inv.ats
                    self._entities["Inventory"][inv.id] = copy.deepcopy(inv)
            reservation = InventoryReservation(
                merchant_id=merchant_id, sku=sku, location_ref=location_ref,
                source_type=source_type, source_id=source_id, order_line_id=order_line_id, idempotency_key=idempotency_key,
                quantity_requested=quantity_requested, quantity_reserved=reserve_qty,
            )
            self._entities["InventoryReservation"][reservation.id] = copy.deepcopy(reservation)
            return copy.deepcopy(reservation)

    def quarantine_inventory_atomic(
        self, merchant_id: str, sku: str, location_ref: str, *, quantity: int, reason: str = "inspection"
    ):
        """Atomically moves `quantity` from sellable stock to quarantine."""
        from sanocea.packages.domain_contract.models import Inventory

        with self._inventory_lock:
            inv = next(
                (e for e in self._entities["Inventory"].values() if e.merchant_id == merchant_id and e.sku == sku and e.location_ref == location_ref),
                None,
            )
            if inv is None:
                raise NotFoundError(f"Inventory({sku}@{location_ref})")
            current_sellable = inv.sellable if inv.sellable is not None else max(inv.quantity - inv.quarantine - inv.in_transit, 0)
            ats = max(current_sellable - inv.reserved, 0)
            if ats < quantity:
                raise ValueError(f"Insufficient available stock to quarantine: ats={ats}, requested={quantity}")
            inv.sellable = max(current_sellable - quantity, 0)
            inv.quarantine = inv.quarantine + quantity
            inv.available = inv.ats
            self._entities["Inventory"][inv.id] = copy.deepcopy(inv)
            return copy.deepcopy(inv)

    def release_quarantine_atomic(
        self, merchant_id: str, sku: str, location_ref: str, *, quantity: int
    ):
        """Atomically releases `quantity` from quarantine back to sellable stock."""
        from sanocea.packages.domain_contract.models import Inventory

        with self._inventory_lock:
            inv = next(
                (e for e in self._entities["Inventory"].values() if e.merchant_id == merchant_id and e.sku == sku and e.location_ref == location_ref),
                None,
            )
            if inv is None:
                raise NotFoundError(f"Inventory({sku}@{location_ref})")
            if inv.quarantine < quantity:
                raise ValueError(f"Cannot release {quantity} from quarantine; current quarantine is {inv.quarantine}")
            inv.quarantine = inv.quarantine - quantity
            current_sellable = inv.sellable if inv.sellable is not None else max(inv.quantity - inv.quarantine - inv.in_transit, 0)
            inv.sellable = current_sellable + quantity
            inv.available = inv.ats
            self._entities["Inventory"][inv.id] = copy.deepcopy(inv)
            return copy.deepcopy(inv)

    def adjust_reservation_atomic(self, merchant_id: str, reservation_id: str, *, mode: str, amount: int):
        """In-memory equivalent of PostgresStore.adjust_reservation_atomic - see that method's docstring
        for the clamp-to-remaining idempotency reasoning, which applies identically here."""
        with self._inventory_lock:
            reservation = self._entities["InventoryReservation"].get(reservation_id)
            if reservation is None or reservation.merchant_id != merchant_id:
                raise NotFoundError(reservation_id)
            reservation = copy.deepcopy(reservation)
            remaining = reservation.quantity_reserved - reservation.quantity_released - reservation.quantity_consumed
            apply_amount = max(min(amount, remaining), 0)
            if apply_amount > 0:
                if mode == "release":
                    reservation.quantity_released += apply_amount
                else:
                    reservation.quantity_consumed += apply_amount
                if reservation.quantity_released + reservation.quantity_consumed >= reservation.quantity_reserved:
                    reservation.status = "closed"
                self._entities["InventoryReservation"][reservation.id] = copy.deepcopy(reservation)
                inv = next(
                    (e for e in self._entities["Inventory"].values() if e.merchant_id == merchant_id and e.sku == reservation.sku and e.location_ref == reservation.location_ref),
                    None,
                )
                if inv is not None:
                    inv.reserved = max(inv.reserved - apply_amount, 0)
                    if mode == "release":
                        inv.available = inv.ats
                    else:
                        inv.quantity = max(inv.quantity - apply_amount, 0)
                        if inv.sellable is not None:
                            inv.sellable = max(inv.sellable - apply_amount, 0)
                        inv.available = inv.ats
                    self._entities["Inventory"][inv.id] = copy.deepcopy(inv)
            return reservation

    def reserve_order_lines_atomic(
        self, merchant_id: str, source_type: str, source_id: str, location_ref: str, lines: list[dict],
    ) -> dict:
        """In-memory equivalent of PostgresStore.reserve_order_lines_atomic - `self._inventory_lock` held
        across the WHOLE check-then-insert-then-mutate sequence gives the same single-process
        serialization guarantee Postgres's `SELECT ... FOR UPDATE` + unique-index-conflict combination
        gives across processes. See that method's docstring for the full atomicity/lock-ordering/
        idempotency-conflict reasoning."""
        from sanocea.packages.domain_contract.models import Inventory, InventoryReservation

        if not lines:
            return {"success": True, "conflict": False, "line_results": []}
        with self._inventory_lock:
            existing_keys = {
                e.idempotency_key for e in self._entities["InventoryReservation"].values() if e.merchant_id == merchant_id
            }
            if any(line["idempotency_key"] in existing_keys for line in lines):
                return {"success": False, "conflict": True, "line_results": []}

            def _inv(sku: str) -> Inventory | None:
                return next(
                    (e for e in self._entities["Inventory"].values() if e.merchant_id == merchant_id and e.sku == sku and e.location_ref == location_ref),
                    None,
                )

            shortfalls = []
            for line in lines:
                inv = _inv(line["sku"])
                available = inv.ats if inv else 0
                if available < line["quantity_requested"]:
                    shortfalls.append(line)

            if shortfalls:
                return {
                    "success": False, "conflict": False,
                    "line_results": [
                        {"sku": line["sku"], "requested": line["quantity_requested"], "reserved": 0, "shortfall": line["quantity_requested"]}
                        for line in lines
                    ],
                }

            for line in lines:
                reservation = InventoryReservation(
                    merchant_id=merchant_id, sku=line["sku"], location_ref=location_ref,
                    source_type=source_type, source_id=source_id, order_line_id=line.get("order_line_id"),
                    idempotency_key=line["idempotency_key"],
                    quantity_requested=line["quantity_requested"], quantity_reserved=line["quantity_requested"],
                )
                self._entities["InventoryReservation"][reservation.id] = copy.deepcopy(reservation)
                inv = _inv(line["sku"])
                inv.reserved = max(inv.reserved + line["quantity_requested"], 0)
                inv.available = inv.ats
                self._entities["Inventory"][inv.id] = copy.deepcopy(inv)
            return {
                "success": True, "conflict": False,
                "line_results": [
                    {"sku": line["sku"], "requested": line["quantity_requested"], "reserved": line["quantity_requested"], "shortfall": 0}
                    for line in lines
                ],
            }

    def get(self, model: type[T], merchant_id: str, entity_id: str) -> T:
        entity = self._entities[model.__name__].get(entity_id)
        if entity is None:
            raise NotFoundError(entity_id)
        if getattr(entity, "merchant_id", None) != merchant_id:
            raise TenantAccessError(f"{merchant_id} cannot access {entity_id}")
        return copy.deepcopy(entity)  # type: ignore[return-value]

    def list(self, model: type[T], merchant_id: str) -> list[T]:
        return [
            copy.deepcopy(entity)  # type: ignore[misc]
            for entity in self._entities[model.__name__].values()
            if getattr(entity, "merchant_id", None) == merchant_id
        ]

    def list_all_merchants(self) -> list[Any]:
        """In-memory equivalent of PostgresStore.list_all_merchants - see its docstring."""
        return [copy.deepcopy(entity) for entity in self._entities["Merchant"].values()]

    def find_one(
        self, model: type[T], merchant_id: str, **attrs: Any
    ) -> T | None:
        for entity in self.list(model, merchant_id):
            if all(getattr(entity, key) == value for key, value in attrs.items()):
                return entity
        return None

    def list_where(self, model: type[T], merchant_id: str, **field_equals: str) -> list[T]:
        """Mirrors PostgresStore.list_where's filter semantics for unit-test parity - values are
        stringified before comparison because PostgresStore compares against a JSONB->>text value."""
        return [
            entity for entity in self.list(model, merchant_id)
            if all(str(getattr(entity, field, None)) == str(value) for field, value in field_equals.items())
        ]

    def append_audit(self, event: AuditEvent) -> AuditEvent:
        self._audit.append(copy.deepcopy(event))
        return copy.deepcopy(event)

    def list_audit(self, merchant_id: str) -> list[AuditEvent]:
        return [copy.deepcopy(e) for e in self._audit if e.merchant_id == merchant_id]

    def store_raw_payload(self, payload: RawPayload) -> RawPayload:
        self._raw[payload.id] = copy.deepcopy(payload)
        return copy.deepcopy(payload)

    def get_raw_payload(self, merchant_id: str, payload_id: str) -> RawPayload:
        payload = self._raw[payload_id]
        if payload.merchant_id != merchant_id:
            raise TenantAccessError(f"{merchant_id} cannot access {payload_id}")
        return copy.deepcopy(payload)

    def put_external_mapping(self, mapping: ExternalIdMapping) -> ExternalIdMapping:
        key = (
            mapping.merchant_id,
            mapping.external_system,
            mapping.external_entity_type,
            mapping.external_id,
        )
        existing = self._external.get(key)
        if existing:
            mapping.id = existing.id
            mapping.first_seen_at = existing.first_seen_at
        mapping.last_seen_at = now_utc()
        self._external[key] = copy.deepcopy(mapping)
        return copy.deepcopy(mapping)

    def get_external_mapping(
        self,
        merchant_id: str,
        external_system: str,
        external_entity_type: str,
        external_id: str,
    ) -> ExternalIdMapping | None:
        mapping = self._external.get(
            (merchant_id, external_system, external_entity_type, external_id)
        )
        return copy.deepcopy(mapping) if mapping else None

    def set_config(self, merchant_id: str, config: dict[str, Any]) -> None:
        self._config[merchant_id] = copy.deepcopy(config)

    def get_config(self, merchant_id: str) -> dict[str, Any]:
        return copy.deepcopy(self._config[merchant_id])

    def set_credential_ref(self, merchant_id: str, ref: str, secret: str) -> None:
        self._credentials[merchant_id][ref] = secret

    def get_credential_ref(self, merchant_id: str, ref: str) -> str:
        if ref not in self._credentials[merchant_id]:
            raise TenantAccessError(f"{merchant_id} cannot access credential {ref}")
        return self._credentials[merchant_id][ref]

    def list_credential_refs(self, merchant_id: str) -> list[str]:
        return sorted(self._credentials[merchant_id])

    def reserve_idempotency(self, scope: str, key: str, result: Any = None) -> bool:
        idem_key = (scope, key)
        if idem_key in self._idempotency:
            return False
        self._idempotency[idem_key] = copy.deepcopy(result)
        return True

    def complete_idempotency(self, scope: str, key: str, result: Any) -> None:
        self._idempotency[(scope, key)] = copy.deepcopy(result)
        self._idempotency_completed.add((scope, key))

    def get_idempotency_result(self, scope: str, key: str) -> Any:
        if (scope, key) not in self._idempotency_completed:
            return None
        return copy.deepcopy(self._idempotency.get((scope, key)))

    def release_idempotency(self, scope: str, key: str) -> None:
        # Releases a reservation whose operation raised before completing, so a genuine retry can
        # actually re-attempt the mutation instead of polling forever for a result that will never
        # arrive (see IdempotencyService.run_once). Never releases an already-completed reservation.
        if (scope, key) not in self._idempotency_completed:
            self._idempotency.pop((scope, key), None)

    def list_approvals(self, merchant_id: str) -> list[Approval]:
        return self.list(Approval, merchant_id)

    def create_api_key(
        self, *, merchant_id: str | None, role: str, label: str | None = None,
        allowed_merchants: list[str] | None = None,
    ) -> tuple[str, str]:
        """Returns (key_id, raw_key). Only the hash is ever persisted - the raw key is returned exactly
        once, to the caller that requested it, and never again. `allowed_merchants`, when given, mints an
        internal-operator key scoped to that explicit set instead of a single merchant_id - see
        PostgresStore.create_api_key's own docstring; kept at parity here for unit-test/dev-harness use."""
        raw_key = generate_api_key()
        key_id = f"key_{secrets.token_hex(12)}"
        self._api_keys[hash_api_key(raw_key)] = {
            "id": key_id, "merchant_id": None if allowed_merchants else merchant_id, "role": role,
            "label": label, "revoked": False, "allowed_merchants": list(allowed_merchants) if allowed_merchants else None,
        }
        return key_id, raw_key

    def resolve_api_key(self, raw_key: str) -> dict[str, Any] | None:
        record = self._api_keys.get(hash_api_key(raw_key))
        if record is None or record["revoked"]:
            return None
        return dict(record)

    def revoke_api_key(self, key_id: str) -> None:
        for record in self._api_keys.values():
            if record["id"] == key_id:
                record["revoked"] = True

