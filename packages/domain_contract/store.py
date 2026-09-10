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

    def atomic_adjust_inventory(
        self, merchant_id: str, sku: str, location_ref: str, *,
        confirmed_inbound_delta: int = 0, quantity_delta: int = 0, available_delta: int = 0,
    ):
        """In-memory equivalent of PostgresStore.atomic_adjust_inventory - threading.Lock is sufficient
        for the single-process in-memory store; see that method's docstring for the real race this
        closes."""
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
                )
            else:
                entity = existing
                entity.confirmed_inbound = max(entity.confirmed_inbound + confirmed_inbound_delta, 0)
                entity.quantity = entity.quantity + quantity_delta
                entity.available = (entity.available if entity.available is not None else 0) + available_delta
            self._entities["Inventory"][entity.id] = copy.deepcopy(entity)
            return copy.deepcopy(entity)

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

    def create_api_key(self, *, merchant_id: str | None, role: str, label: str | None = None) -> tuple[str, str]:
        """Returns (key_id, raw_key). Only the hash is ever persisted - the raw key is returned exactly
        once, to the caller that requested it, and never again."""
        raw_key = generate_api_key()
        key_id = f"key_{secrets.token_hex(12)}"
        self._api_keys[hash_api_key(raw_key)] = {
            "id": key_id, "merchant_id": merchant_id, "role": role, "label": label, "revoked": False,
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

