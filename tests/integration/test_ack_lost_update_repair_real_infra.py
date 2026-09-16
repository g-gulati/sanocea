from __future__ import annotations

import os
import threading
from uuid import uuid4

import pytest

from sanocea.connectors.suppliers import SimulatedSupplierConnector
from sanocea.packages.domain_contract import PostgresStore, TenantAccessError
from sanocea.packages.domain_contract.models import ExceptionRecord, Inventory, Merchant, PurchaseOrderLine, SupplierAcknowledgement
from sanocea.packages.procurement import ProcurementService


pytestmark = pytest.mark.skipif(
    not os.environ.get("SANOCEA_PG_DSN"),
    reason="requires real Postgres DSN in SANOCEA_PG_DSN",
)


def _setup(suffix: str):
    merchant_id = f"ack_repair_{suffix}"
    store = PostgresStore(os.environ["SANOCEA_PG_DSN"])
    store.migrate()
    store.put(Merchant(id=merchant_id, merchant_id=merchant_id, legal_name="AckRepair", display_name="AckRepair"))
    store.set_config(merchant_id, {"procurement": {"spending": {"auto_approve_limit": 100000000, "above_limit": "REQUIRE_APPROVAL"}}})
    connector = SimulatedSupplierConnector(store)
    service = ProcurementService(store, connector)
    supplier = service.upsert_supplier(merchant_id, "Acme Supplies", default_lead_time_days=5)
    service.ingest_supplier_offer(merchant_id, supplier.id, sku="SKU-A", supplier_sku="ACME-A", cost=500, currency="INR", moq=1, pack_quantity=1, lead_time_days=5)
    return merchant_id, store, connector, service, supplier


def _dual_location_po(store, service, merchant_id, supplier, *, mumbai_qty=100):
    po = service.create_purchase_order(merchant_id, supplier.id, [
        {"sku": "SKU-A", "quantity_ordered": 10, "location_ref": "Surat"},
        {"sku": "SKU-A", "quantity_ordered": mumbai_qty, "location_ref": "Mumbai"},
    ])
    po = service.submit_purchase_order(merchant_id, po.id)
    lines = [l for l in store.list(PurchaseOrderLine, merchant_id) if l.purchase_order_id == po.id]
    line_surat = next(l for l in lines if l.location_ref == "Surat")
    line_mumbai = next(l for l in lines if l.location_ref == "Mumbai")
    return po, line_surat, line_mumbai


def _inv(store, merchant_id, sku, location):
    rows = [i for i in store.list(Inventory, merchant_id) if i.sku == sku and i.location_ref == location]
    return rows[-1] if rows else None


# --- Item 5: duplicate acknowledgement replay remains idempotent ------------------------------------

def test_duplicate_acknowledgement_replay_applies_once():
    suffix = uuid4().hex[:8]
    merchant_id, store, connector, service, supplier = _setup(suffix)
    po, line_surat, line_mumbai = _dual_location_po(store, service, merchant_id, supplier)

    first = service.record_supplier_acknowledgement(
        merchant_id, po.id, external_ref="ack-dup", sequence=1,
        lines=[{"sku": "SKU-A", "quantity_confirmed": 40, "unit_cost": 500, "line_ref": line_mumbai.id}],
        status="partially_confirmed",
    )
    second = service.record_supplier_acknowledgement(
        merchant_id, po.id, external_ref="ack-dup", sequence=1,
        lines=[{"sku": "SKU-A", "quantity_confirmed": 40, "unit_cost": 500, "line_ref": line_mumbai.id}],
        status="partially_confirmed",
    )
    assert first.id == second.id
    line_after = store.get(PurchaseOrderLine, merchant_id, line_mumbai.id)
    assert line_after.quantity_confirmed == 40, "exact external_ref replay must not double-apply"
    assert service.inventory_position(merchant_id, "SKU-A", "Mumbai")["confirmed_inbound"] == 40


def test_exact_sequence_resent_with_different_ref_is_rejected_as_stale():
    """The corrected staleness definition: resending the SAME sequence number (not the same
    external_ref) is what must be rejected - a genuinely NEW, different, lower sequence number must
    NOT be (see test_distinct_sequences_apply_regardless_of_processing_order below)."""
    suffix = uuid4().hex[:8]
    merchant_id, store, connector, service, supplier = _setup(suffix)
    po, line_surat, line_mumbai = _dual_location_po(store, service, merchant_id, supplier)

    service.record_supplier_acknowledgement(
        merchant_id, po.id, external_ref="ack-seq1", sequence=1,
        lines=[{"sku": "SKU-A", "quantity_confirmed": 40, "unit_cost": 500, "line_ref": line_mumbai.id}],
        status="partially_confirmed",
    )
    stale = service.record_supplier_acknowledgement(
        merchant_id, po.id, external_ref="ack-seq1-resent", sequence=1,
        lines=[{"sku": "SKU-A", "quantity_confirmed": 999, "unit_cost": 500, "line_ref": line_mumbai.id}],
        status="confirmed",
    )
    assert stale.applied is False
    line_after = store.get(PurchaseOrderLine, merchant_id, line_mumbai.id)
    assert line_after.quantity_confirmed == 40, "a resent sequence must never add its quantity"
    exceptions = store.list(ExceptionRecord, merchant_id)
    assert any(e.category == "stale_acknowledgement_ignored" for e in exceptions)


# --- Item 6: legitimate distinct cumulative acknowledgements both apply (sequential, deterministic) ---

def test_distinct_sequences_apply_regardless_of_processing_order():
    suffix = uuid4().hex[:8]
    merchant_id, store, connector, service, supplier = _setup(suffix)
    po, line_surat, line_mumbai = _dual_location_po(store, service, merchant_id, supplier)

    # Higher sequence processed FIRST, lower sequence processed SECOND - both are genuinely new/distinct.
    service.record_supplier_acknowledgement(
        merchant_id, po.id, external_ref="ack-seq2", sequence=2,
        lines=[{"sku": "SKU-A", "quantity_confirmed": 40, "unit_cost": 500, "line_ref": line_mumbai.id}],
        status="partially_confirmed",
    )
    result = service.record_supplier_acknowledgement(
        merchant_id, po.id, external_ref="ack-seq1", sequence=1,
        lines=[{"sku": "SKU-A", "quantity_confirmed": 60, "unit_cost": 500, "line_ref": line_mumbai.id}],
        status="confirmed",
    )
    assert result.applied is True
    line_after = store.get(PurchaseOrderLine, merchant_id, line_mumbai.id)
    assert line_after.quantity_confirmed == 100
    assert service.inventory_position(merchant_id, "SKU-A", "Mumbai")["confirmed_inbound"] == 100
    assert line_surat_unaffected(store, merchant_id, line_surat)


def line_surat_unaffected(store, merchant_id, line_surat):
    line_after = store.get(PurchaseOrderLine, merchant_id, line_surat.id)
    return line_after.quantity_confirmed == 0


# --- Item 7: over-confirmation classification remains correct -----------------------------------------

def test_over_confirmation_classification_correct_with_concurrent_distinct_deltas():
    """A=+70, B=+50 against an ordered quantity of 100 - cumulative true total 120 exceeds ordered;
    confirmed_inbound must be capped at 100 (the legitimate/ordered portion), and the over-confirmation
    exception must fire - matching the existing, unchanged Phase 4.1 contract."""
    suffix = uuid4().hex[:8]
    merchant_id, setup_store, _, setup_service, supplier = _setup(suffix)
    po, line_surat, line_mumbai = _dual_location_po(setup_store, setup_service, merchant_id, supplier, mumbai_qty=100)

    dsn = os.environ["SANOCEA_PG_DSN"]
    barrier = threading.Barrier(2)
    errors: list[str] = []

    def contribute(amount: int, seq: int) -> None:
        try:
            thread_store = PostgresStore(dsn)
            thread_service = ProcurementService(thread_store, SimulatedSupplierConnector(thread_store))
            barrier.wait(timeout=10)
            thread_service.record_supplier_acknowledgement(
                merchant_id, po.id, external_ref=f"ack-oc-{seq}", sequence=seq,
                lines=[{"sku": "SKU-A", "quantity_confirmed": amount, "unit_cost": 500, "line_ref": line_mumbai.id}],
                status="confirmed",
            )
        except BaseException as exc:  # noqa: BLE001
            errors.append(f"{type(exc).__name__}: {exc}")

    t1 = threading.Thread(target=contribute, args=(70, 1))
    t2 = threading.Thread(target=contribute, args=(50, 2))
    t1.start()
    t2.start()
    t1.join(timeout=20)
    t2.join(timeout=20)

    assert not errors, f"unexpected errors: {errors}"
    verify_store = PostgresStore(dsn)
    line_after = verify_store.get(PurchaseOrderLine, merchant_id, line_mumbai.id)
    assert line_after.quantity_confirmed == 120, "the TRUE cumulative total must be visible even when it exceeds ordered quantity"
    assert verify_store.get(PurchaseOrderLine, merchant_id, line_surat.id).quantity_confirmed == 0
    position = ProcurementService(verify_store, SimulatedSupplierConnector(verify_store)).inventory_position(merchant_id, "SKU-A", "Mumbai")
    assert position["confirmed_inbound"] == 100, "confirmed_inbound must be capped at the ordered quantity, never inflated by the over-confirmed excess"
    exceptions = [e for e in verify_store.list(ExceptionRecord, merchant_id) if e.category == "supplier_overconfirmation"]
    assert exceptions, "over-confirmation must still be flagged"


# --- Item 8: injected mid-transaction failure leaves PO-line and inbound state BOTH unchanged ---------

def test_injected_failure_mid_acknowledgement_transaction_rolls_back_both_consequences():
    """Simulate a crash between the PurchaseOrderLine mutation and the Inventory (confirmed_inbound)
    mutation, both inside atomic_apply_acknowledgement's single transaction. The whole transaction must
    roll back - the PO line must NOT show the delta applied while inbound is left at 0, or vice versa."""
    suffix = uuid4().hex[:8]
    merchant_id, store, connector, service, supplier = _setup(suffix)
    po, line_surat, line_mumbai = _dual_location_po(store, service, merchant_id, supplier)

    real_execute = None

    class _FailingCursor:
        def __init__(self, real_cursor):
            self._real = real_cursor

        def execute(self, sql, params=None):
            if "INSERT INTO inventory" in sql:
                raise RuntimeError("injected failure before the confirmed_inbound mutation commits")
            return self._real.execute(sql, params)

        def __getattr__(self, name):
            return getattr(self._real, name)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return self._real.__exit__(*exc)

    class _FailingConnection:
        def __init__(self, real_conn):
            self._real = real_conn

        def cursor(self, *args, **kwargs):
            return _FailingCursor(self._real.cursor(*args, **kwargs))

        def __getattr__(self, name):
            return getattr(self._real, name)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return self._real.__exit__(*exc)

    real_connect = store.connect

    def failing_connect():
        # Every connect() call is wrapped - harmless for the many unrelated queries earlier in
        # record_supplier_acknowledgement (get PurchaseOrder, insert the ack row, list PO lines, etc.),
        # since the wrapper only ever interferes with the ONE specific "INSERT INTO inventory" statement
        # that atomic_apply_acknowledgement itself issues.
        return _FailingConnection(real_connect())

    store.connect = failing_connect
    try:
        with pytest.raises(RuntimeError, match="injected failure"):
            service.record_supplier_acknowledgement(
                merchant_id, po.id, external_ref="ack-inject", sequence=1,
                lines=[{"sku": "SKU-A", "quantity_confirmed": 40, "unit_cost": 500, "line_ref": line_mumbai.id}],
                status="partially_confirmed",
            )
    finally:
        store.connect = real_connect

    verify_store = PostgresStore(os.environ["SANOCEA_PG_DSN"])
    line_after = verify_store.get(PurchaseOrderLine, merchant_id, line_mumbai.id)
    assert line_after.quantity_confirmed == 0, "the PO-line mutation must have rolled back along with the failed inbound mutation"
    mumbai_inv = _inv(verify_store, merchant_id, "SKU-A", "Mumbai")
    assert mumbai_inv is None or mumbai_inv.confirmed_inbound == 0, "confirmed_inbound must not reflect a partially-applied transaction"

    # Safe retry after the injected failure: a fresh attempt with the SAME external_ref must succeed
    # cleanly (the failed attempt's ack row, if persisted before the injected failure, must not block it).
    retry = service.record_supplier_acknowledgement(
        merchant_id, po.id, external_ref="ack-inject-retry", sequence=2,
        lines=[{"sku": "SKU-A", "quantity_confirmed": 40, "unit_cost": 500, "line_ref": line_mumbai.id}],
        status="partially_confirmed",
    )
    assert retry.applied is True
    assert store.get(PurchaseOrderLine, merchant_id, line_mumbai.id).quantity_confirmed == 40


# --- Item 9: tenant isolation ----------------------------------------------------------------------------

def test_acknowledgement_repair_tenant_isolation():
    suffix = uuid4().hex[:8]
    merchant_id, store, connector, service, supplier = _setup(suffix)
    other_id = f"ack_repair_other_{suffix}"
    store.put(Merchant(id=other_id, merchant_id=other_id, legal_name="Other", display_name="Other"))
    po, line_surat, line_mumbai = _dual_location_po(store, service, merchant_id, supplier)
    service.record_supplier_acknowledgement(
        merchant_id, po.id, external_ref="ack-1", sequence=1,
        lines=[{"sku": "SKU-A", "quantity_confirmed": 40, "unit_cost": 500, "line_ref": line_mumbai.id}],
        status="partially_confirmed",
    )
    assert store.list(PurchaseOrderLine, other_id) == []
    assert [i for i in store.list(Inventory, other_id) if i.sku == "SKU-A"] == []
    with pytest.raises(TenantAccessError):
        store.get(PurchaseOrderLine, other_id, line_mumbai.id)


# --- Item 10: Step 5B exact line_ref identity remains intact under the repaired atomic path -----------

def test_line_ref_identity_intact_same_sku_different_locations_under_repair():
    suffix = uuid4().hex[:8]
    merchant_id, store, connector, service, supplier = _setup(suffix)
    po, line_surat, line_mumbai = _dual_location_po(store, service, merchant_id, supplier)

    service.record_supplier_acknowledgement(
        merchant_id, po.id, external_ref="ack-mumbai", sequence=1,
        lines=[{"sku": "SKU-A", "quantity_confirmed": 40, "unit_cost": 500, "line_ref": line_mumbai.id}],
        status="partially_confirmed",
    )
    assert store.get(PurchaseOrderLine, merchant_id, line_mumbai.id).quantity_confirmed == 40
    assert store.get(PurchaseOrderLine, merchant_id, line_surat.id).quantity_confirmed == 0
    assert service.inventory_position(merchant_id, "SKU-A", "Mumbai")["confirmed_inbound"] == 40
    assert service.inventory_position(merchant_id, "SKU-A", "Surat")["confirmed_inbound"] == 0
