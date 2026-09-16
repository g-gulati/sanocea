from __future__ import annotations

import pytest

from sanocea.connectors.suppliers import SimulatedSupplierConnector, SupplierSimulator
from sanocea.packages.domain_contract.models import (
    ExceptionRecord,
    InboundShipmentLine,
    Inventory,
    PurchaseOrderLine,
)
from sanocea.packages.procurement import ProcurementService


@pytest.fixture
def procurement(phase0):
    store, *_ = phase0
    store.set_config("mer_A", store.get_config("mer_A") | {"procurement": {"spending": {"auto_approve_limit": 1000000, "above_limit": "REQUIRE_APPROVAL"}}})
    service = ProcurementService(store, SimulatedSupplierConnector(store))
    supplier = service.upsert_supplier("mer_A", "Acme Supplies", default_lead_time_days=5)
    service.ingest_supplier_offer("mer_A", supplier.id, sku="SKU-A", supplier_sku="ACME-A", cost=500, currency="INR", moq=1, pack_quantity=1, lead_time_days=5)
    return store, service, supplier


def _po_lines(store, po_id):
    return [l for l in store.list(PurchaseOrderLine, "mer_A") if l.purchase_order_id == po_id]


def _dual_location_po(store, service, supplier):
    po = service.create_purchase_order("mer_A", supplier.id, [
        {"sku": "SKU-A", "quantity_ordered": 10, "location_ref": "Surat"},
        {"sku": "SKU-A", "quantity_ordered": 20, "location_ref": "Mumbai"},
    ])
    po = service.submit_purchase_order("mer_A", po.id)
    lines = _po_lines(store, po.id)
    line_surat = next(l for l in lines if l.location_ref == "Surat")
    line_mumbai = next(l for l in lines if l.location_ref == "Mumbai")
    return po, line_surat, line_mumbai


def _same_location_po(store, service, supplier):
    po = service.create_purchase_order("mer_A", supplier.id, [
        {"sku": "SKU-A", "quantity_ordered": 10, "location_ref": "Surat"},
        {"sku": "SKU-A", "quantity_ordered": 20, "location_ref": "Surat"},
    ])
    po = service.submit_purchase_order("mer_A", po.id)
    lines = _po_lines(store, po.id)
    assert {l.location_ref for l in lines} == {"Surat"}
    return po, lines[0], lines[1]


# --- 1/4: exact identity acknowledgement / inbound, same SKU / different location -----------------------

def test_acknowledgement_by_exact_line_ref_same_sku_different_locations(procurement):
    store, service, supplier = procurement
    po, line_surat, line_mumbai = _dual_location_po(store, service, supplier)

    service.record_supplier_acknowledgement(
        "mer_A", po.id, external_ref="ack-1", sequence=1,
        lines=[{"sku": "SKU-A", "quantity_confirmed": 15, "unit_cost": 500, "line_ref": line_mumbai.id}],
        status="partially_confirmed",
    )
    assert store.get(PurchaseOrderLine, "mer_A", line_mumbai.id).quantity_confirmed == 15
    assert store.get(PurchaseOrderLine, "mer_A", line_surat.id).quantity_confirmed == 0
    assert service.inventory_position("mer_A", "SKU-A", "Mumbai")["confirmed_inbound"] == 15
    assert service.inventory_position("mer_A", "SKU-A", "Surat")["confirmed_inbound"] == 0


def test_inbound_shipment_by_exact_line_ref_same_sku_different_locations(procurement):
    store, service, supplier = procurement
    po, line_surat, line_mumbai = _dual_location_po(store, service, supplier)
    service.record_supplier_acknowledgement(
        "mer_A", po.id, external_ref="ack-1", sequence=1,
        lines=[{"sku": "SKU-A", "quantity_confirmed": 20, "unit_cost": 500, "line_ref": line_mumbai.id}],
        status="confirmed",
    )
    shipment = service.record_inbound_shipment(
        "mer_A", po.id, external_shipment_ref="ship-1", sequence=1,
        lines=[{"sku": "SKU-A", "quantity_shipped": 20, "line_ref": line_mumbai.id}],
    )
    assert store.get(PurchaseOrderLine, "mer_A", line_mumbai.id).quantity_shipped == 20
    assert store.get(PurchaseOrderLine, "mer_A", line_surat.id).quantity_shipped == 0
    isl = next(l for l in store.list(InboundShipmentLine, "mer_A") if l.inbound_shipment_id == shipment.id)
    assert isl.purchase_order_line_id == line_mumbai.id


# --- 2/5: exact identity acknowledgement / inbound, same SKU / SAME location ------------------------------

def test_acknowledgement_by_exact_line_ref_same_sku_same_location(procurement):
    store, service, supplier = procurement
    po, line_1, line_2 = _same_location_po(store, service, supplier)
    service.record_supplier_acknowledgement(
        "mer_A", po.id, external_ref="ack-1", sequence=1,
        lines=[{"sku": "SKU-A", "quantity_confirmed": 18, "unit_cost": 500, "line_ref": line_2.id}],
        status="partially_confirmed",
    )
    assert store.get(PurchaseOrderLine, "mer_A", line_2.id).quantity_confirmed == 18
    assert store.get(PurchaseOrderLine, "mer_A", line_1.id).quantity_confirmed == 0
    assert service.inventory_position("mer_A", "SKU-A", "Surat")["confirmed_inbound"] == 18


def test_inbound_shipment_by_exact_line_ref_same_sku_same_location(procurement):
    store, service, supplier = procurement
    po, line_1, line_2 = _same_location_po(store, service, supplier)
    service.record_supplier_acknowledgement(
        "mer_A", po.id, external_ref="ack-1", sequence=1,
        lines=[{"sku": "SKU-A", "quantity_confirmed": 20, "unit_cost": 500, "line_ref": line_2.id}],
        status="confirmed",
    )
    service.record_inbound_shipment(
        "mer_A", po.id, external_shipment_ref="ship-1", sequence=1,
        lines=[{"sku": "SKU-A", "quantity_shipped": 20, "line_ref": line_2.id}],
    )
    assert store.get(PurchaseOrderLine, "mer_A", line_2.id).quantity_shipped == 20
    assert store.get(PurchaseOrderLine, "mer_A", line_1.id).quantity_shipped == 0


# --- 3/6: SKU-only ambiguous acknowledgement/inbound -> no mutation ---------------------------------------

def test_sku_only_ambiguous_acknowledgement_no_mutation(procurement):
    store, service, supplier = procurement
    po, line_surat, line_mumbai = _dual_location_po(store, service, supplier)
    service.record_supplier_acknowledgement(
        "mer_A", po.id, external_ref="ack-ambiguous", sequence=1,
        lines=[{"sku": "SKU-A", "quantity_confirmed": 5, "unit_cost": 500}],  # no line_ref
        status="partially_confirmed",
    )
    assert store.get(PurchaseOrderLine, "mer_A", line_surat.id).quantity_confirmed == 0
    assert store.get(PurchaseOrderLine, "mer_A", line_mumbai.id).quantity_confirmed == 0
    assert service.inventory_position("mer_A", "SKU-A", "Surat")["confirmed_inbound"] == 0
    assert service.inventory_position("mer_A", "SKU-A", "Mumbai")["confirmed_inbound"] == 0
    exceptions = store.list(ExceptionRecord, "mer_A")
    assert any(e.category == "acknowledgement_ambiguous_po_line" for e in exceptions)


def test_sku_only_ambiguous_inbound_no_mutation(procurement):
    store, service, supplier = procurement
    po, line_surat, line_mumbai = _dual_location_po(store, service, supplier)
    service.record_supplier_acknowledgement(
        "mer_A", po.id, external_ref="ack-1", sequence=1,
        lines=[{"sku": "SKU-A", "quantity_confirmed": 10, "unit_cost": 500, "line_ref": line_surat.id}],
        status="partially_confirmed",
    )
    service.record_inbound_shipment(
        "mer_A", po.id, external_shipment_ref="ship-ambiguous", sequence=1,
        lines=[{"sku": "SKU-A", "quantity_shipped": 5}],  # no line_ref
    )
    assert store.get(PurchaseOrderLine, "mer_A", line_surat.id).quantity_shipped == 0
    assert store.get(PurchaseOrderLine, "mer_A", line_mumbai.id).quantity_shipped == 0
    exceptions = store.list(ExceptionRecord, "mer_A")
    assert any(e.category == "shipment_ambiguous_po_line" for e in exceptions)


# --- 7: invalid explicit line reference -> no fallback to SKU ----------------------------------------------

def test_unknown_line_ref_acknowledgement_never_falls_back_to_sku(procurement):
    store, service, supplier = procurement
    po = service.create_purchase_order("mer_A", supplier.id, [{"sku": "SKU-A", "quantity_ordered": 10, "location_ref": "Surat"}])
    po = service.submit_purchase_order("mer_A", po.id)
    line = _po_lines(store, po.id)[0]
    service.record_supplier_acknowledgement(
        "mer_A", po.id, external_ref="ack-badref", sequence=1,
        lines=[{"sku": "SKU-A", "quantity_confirmed": 10, "unit_cost": 500, "line_ref": "pol_does_not_exist"}],
        status="confirmed",
    )
    # Even though SKU-A is unambiguous on this PO (a single matching line), an explicit BAD line_ref
    # must be refused outright, never silently falling back to the SKU match.
    assert store.get(PurchaseOrderLine, "mer_A", line.id).quantity_confirmed == 0
    exceptions = store.list(ExceptionRecord, "mer_A")
    assert any(e.category == "acknowledgement_unknown_po_line" for e in exceptions)


def test_unknown_line_ref_inbound_never_falls_back_to_sku(procurement):
    store, service, supplier = procurement
    po = service.create_purchase_order("mer_A", supplier.id, [{"sku": "SKU-A", "quantity_ordered": 10, "location_ref": "Surat"}])
    po = service.submit_purchase_order("mer_A", po.id)
    line = _po_lines(store, po.id)[0]
    service.record_supplier_acknowledgement("mer_A", po.id, external_ref="ack-1", sequence=1, lines=[{"sku": "SKU-A", "quantity_confirmed": 10, "unit_cost": 500}], status="confirmed")
    service.record_inbound_shipment(
        "mer_A", po.id, external_shipment_ref="ship-badref", sequence=1,
        lines=[{"sku": "SKU-A", "quantity_shipped": 10, "line_ref": "pol_does_not_exist"}],
    )
    assert store.get(PurchaseOrderLine, "mer_A", line.id).quantity_shipped == 0
    exceptions = store.list(ExceptionRecord, "mer_A")
    assert any(e.category == "shipment_unknown_po_line" for e in exceptions)


# --- 8: cumulative acknowledgement stays scoped to exact line ----------------------------------------------

def test_cumulative_acknowledgement_stays_scoped_to_exact_line(procurement):
    store, service, supplier = procurement
    po, line_surat, line_mumbai = _dual_location_po(store, service, supplier)
    service.record_supplier_acknowledgement(
        "mer_A", po.id, external_ref="ack-a2-part1", sequence=1,
        lines=[{"sku": "SKU-A", "quantity_confirmed": 12, "unit_cost": 500, "line_ref": line_mumbai.id}],
        status="partially_confirmed",
    )
    assert store.get(PurchaseOrderLine, "mer_A", line_mumbai.id).quantity_confirmed == 12
    assert service.inventory_position("mer_A", "SKU-A", "Mumbai")["confirmed_inbound"] == 12

    service.record_supplier_acknowledgement(
        "mer_A", po.id, external_ref="ack-a2-part2", sequence=2,
        lines=[{"sku": "SKU-A", "quantity_confirmed": 8, "unit_cost": 500, "line_ref": line_mumbai.id}],
        status="confirmed",
    )
    assert store.get(PurchaseOrderLine, "mer_A", line_mumbai.id).quantity_confirmed == 20
    assert service.inventory_position("mer_A", "SKU-A", "Mumbai")["confirmed_inbound"] == 20
    assert store.get(PurchaseOrderLine, "mer_A", line_surat.id).quantity_confirmed == 0
    assert service.inventory_position("mer_A", "SKU-A", "Surat")["confirmed_inbound"] == 0


# --- 9: duplicate/replayed event remains idempotent ---------------------------------------------------------

def test_duplicate_acknowledgement_event_remains_idempotent_with_exact_line(procurement):
    store, service, supplier = procurement
    po, line_surat, line_mumbai = _dual_location_po(store, service, supplier)
    first = service.record_supplier_acknowledgement(
        "mer_A", po.id, external_ref="ack-dup", sequence=1,
        lines=[{"sku": "SKU-A", "quantity_confirmed": 20, "unit_cost": 500, "line_ref": line_mumbai.id}],
        status="confirmed",
    )
    second = service.record_supplier_acknowledgement(
        "mer_A", po.id, external_ref="ack-dup", sequence=1,
        lines=[{"sku": "SKU-A", "quantity_confirmed": 20, "unit_cost": 500, "line_ref": line_mumbai.id}],
        status="confirmed",
    )
    assert first.id == second.id
    assert store.get(PurchaseOrderLine, "mer_A", line_mumbai.id).quantity_confirmed == 20


# --- 10: full PO -> ack -> inbound -> receipt chain preserves location -------------------------------------

def test_complete_po_to_ack_to_inbound_to_receipt_chain_preserves_location(procurement):
    store, service, supplier = procurement
    po, line_surat, line_mumbai = _dual_location_po(store, service, supplier)

    # Supplier acknowledges A2 partially: 12 -> only Mumbai confirmed inbound +12.
    service.record_supplier_acknowledgement(
        "mer_A", po.id, external_ref="ack-a2-p1", sequence=1,
        lines=[{"sku": "SKU-A", "quantity_confirmed": 12, "unit_cost": 500, "line_ref": line_mumbai.id}],
        status="partially_confirmed",
    )
    assert service.inventory_position("mer_A", "SKU-A", "Mumbai")["confirmed_inbound"] == 12
    assert service.inventory_position("mer_A", "SKU-A", "Surat")["confirmed_inbound"] == 0

    # Supplier later confirms remaining 8 -> A2 cumulative confirmed 20 -> Mumbai inbound 20.
    service.record_supplier_acknowledgement(
        "mer_A", po.id, external_ref="ack-a2-p2", sequence=2,
        lines=[{"sku": "SKU-A", "quantity_confirmed": 8, "unit_cost": 500, "line_ref": line_mumbai.id}],
        status="confirmed",
    )
    assert store.get(PurchaseOrderLine, "mer_A", line_mumbai.id).quantity_confirmed == 20
    assert service.inventory_position("mer_A", "SKU-A", "Mumbai")["confirmed_inbound"] == 20

    # Inbound shipment references A2 -> resolves A2 only.
    service.record_inbound_shipment(
        "mer_A", po.id, external_shipment_ref="ship-a2", sequence=1,
        lines=[{"sku": "SKU-A", "quantity_shipped": 20, "line_ref": line_mumbai.id}],
    )
    assert store.get(PurchaseOrderLine, "mer_A", line_mumbai.id).quantity_shipped == 20
    assert store.get(PurchaseOrderLine, "mer_A", line_surat.id).quantity_shipped == 0

    # Goods receipt references A2 -> Mumbai on_hand increases, Mumbai inbound decreases, Surat untouched.
    service.record_goods_receipt("mer_A", po.id, external_receipt_ref="rcpt-a2", lines=[{"po_line_id": line_mumbai.id, "quantity_received": 20}])
    assert service.inventory_position("mer_A", "SKU-A", "Mumbai")["on_hand"] == 20
    assert service.inventory_position("mer_A", "SKU-A", "Mumbai")["confirmed_inbound"] == 0
    assert service.inventory_position("mer_A", "SKU-A", "Surat")["on_hand"] == 0

    # Then independently process A1 -> Surat lifecycle remains isolated from A2.
    service.record_supplier_acknowledgement(
        "mer_A", po.id, external_ref="ack-a1", sequence=3,
        lines=[{"sku": "SKU-A", "quantity_confirmed": 10, "unit_cost": 500, "line_ref": line_surat.id}],
        status="confirmed",
    )
    service.record_inbound_shipment(
        "mer_A", po.id, external_shipment_ref="ship-a1", sequence=2,
        lines=[{"sku": "SKU-A", "quantity_shipped": 10, "line_ref": line_surat.id}],
    )
    service.record_goods_receipt("mer_A", po.id, external_receipt_ref="rcpt-a1", lines=[{"po_line_id": line_surat.id, "quantity_received": 10}])
    assert service.inventory_position("mer_A", "SKU-A", "Surat")["on_hand"] == 10
    assert service.inventory_position("mer_A", "SKU-A", "Mumbai")["on_hand"] == 20, "A2's earlier receipt must remain unaffected by A1's independent lifecycle"

    po_final = store.get(type(po), "mer_A", po.id)
    assert po_final.status == "RECEIVED"


# --- 11: legacy unique-SKU payload remains compatible --------------------------------------------------------

def test_legacy_unique_sku_ack_and_inbound_payload_still_works(procurement):
    store, service, supplier = procurement
    po = service.create_purchase_order("mer_A", supplier.id, [{"sku": "SKU-A", "quantity_ordered": 10, "location_ref": "Surat"}])
    po = service.submit_purchase_order("mer_A", po.id)
    line = _po_lines(store, po.id)[0]

    # No line_ref anywhere - exactly the pre-Step-5B payload shape.
    service.record_supplier_acknowledgement("mer_A", po.id, external_ref="ack-legacy", sequence=1, lines=[{"sku": "SKU-A", "quantity_confirmed": 10, "unit_cost": 500}], status="confirmed")
    service.record_inbound_shipment("mer_A", po.id, external_shipment_ref="ship-legacy", sequence=1, lines=[{"sku": "SKU-A", "quantity_shipped": 10}])
    service.record_goods_receipt("mer_A", po.id, external_receipt_ref="rcpt-legacy", lines=[{"raw_sku_reference": "SKU-A", "quantity_received": 10}])

    assert store.get(PurchaseOrderLine, "mer_A", line.id).quantity_confirmed == 10
    assert store.get(PurchaseOrderLine, "mer_A", line.id).quantity_shipped == 10
    assert store.get(PurchaseOrderLine, "mer_A", line.id).quantity_received == 10
    assert service.inventory_position("mer_A", "SKU-A", "Surat")["on_hand"] == 10


# --- 12: tenant isolation --------------------------------------------------------------------------------------

def test_upstream_po_line_identity_records_remain_tenant_scoped(procurement):
    store, service, supplier = procurement
    po, line_surat, line_mumbai = _dual_location_po(store, service, supplier)
    service.record_supplier_acknowledgement(
        "mer_A", po.id, external_ref="ack-1", sequence=1,
        lines=[{"sku": "SKU-A", "quantity_confirmed": 20, "unit_cost": 500, "line_ref": line_mumbai.id}],
        status="confirmed",
    )
    assert store.list(PurchaseOrderLine, "mer_B") == []
    assert [i for i in store.list(Inventory, "mer_B") if i.sku == "SKU-A"] == []


# --- Supplier simulator round-trip ------------------------------------------------------------------------

def test_supplier_simulator_round_trips_line_ref_end_to_end(procurement):
    """Uses the REAL SimulatedSupplierConnector submission payload (what a real supplier would actually
    receive) and the REAL SupplierSimulator (not a hand-constructed ack/shipment dict) to prove line_ref
    genuinely round-trips through submission -> acknowledgement -> shipment, without the simulator ever
    inventing identity it wasn't handed."""
    store, service, supplier = procurement
    po, line_surat, line_mumbai = _dual_location_po(store, service, supplier)

    submitted_lines = service.supplier_connector.purchase_orders[po.external_ref]["lines"]
    assert all("line_ref" in l for l in submitted_lines), "the outbound payload must carry line_ref for every line"
    submitted_line_mumbai = next(l for l in submitted_lines if l["line_ref"] == line_mumbai.id)

    sim = SupplierSimulator()
    ack_event = sim.acknowledge(po.external_ref, [submitted_line_mumbai])
    assert ack_event["lines"][0]["line_ref"] == line_mumbai.id

    service.record_supplier_acknowledgement(
        "mer_A", po.id, external_ref=ack_event["external_ref"], sequence=ack_event["sequence"],
        lines=ack_event["lines"], status=ack_event["status"],
    )
    assert store.get(PurchaseOrderLine, "mer_A", line_mumbai.id).quantity_confirmed == 20
    assert store.get(PurchaseOrderLine, "mer_A", line_surat.id).quantity_confirmed == 0

    ship_event = sim.dispatch(po.external_ref, ack_event["lines"])
    assert ship_event["lines"][0]["line_ref"] == line_mumbai.id
    service.record_inbound_shipment(
        "mer_A", po.id, external_shipment_ref=ship_event["external_shipment_ref"], sequence=ship_event["sequence"],
        lines=ship_event["lines"],
    )
    assert store.get(PurchaseOrderLine, "mer_A", line_mumbai.id).quantity_shipped == 20
    assert store.get(PurchaseOrderLine, "mer_A", line_surat.id).quantity_shipped == 0
