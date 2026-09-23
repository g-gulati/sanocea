from __future__ import annotations

from sanocea.connectors.logistics import SimulatedLogisticsConnector
from sanocea.packages.domain_contract.models import AuditEvent, Inventory, InventoryReservation, Order, OrderLine
from sanocea.packages.post_order import PostOrderOperationsService
from sanocea.packages.post_order.allocation import AllocationRequirement, rank_candidate_locations


def _order_with_lines(store, merchant_id: str, order_number: str, lines: list[tuple[str, int]], *, total_amount: int = 100000) -> Order:
    order = Order(merchant_id=merchant_id, channel_id="chn_A_shopify", order_number=order_number, status="PAID", payment_status="paid", total_amount=total_amount, currency="INR")
    store.put(order)
    for sku, quantity in lines:
        store.put(OrderLine(merchant_id=merchant_id, order_id=order.id, sku=sku, title=sku, quantity=quantity, unit_amount=total_amount // max(quantity, 1)))
    return order


def _inv(store, merchant_id: str, sku: str, location: str) -> Inventory:
    return [i for i in store.list(Inventory, merchant_id) if i.sku == sku and i.location_ref == location][-1]


def _service(store, shopify):
    return PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store))


# --- pure ranking function (already proven against A-F directly in development; re-asserted here as
# part of the committed suite) --------------------------------------------------------------------

def test_rank_candidate_locations_scenarios_a_through_f():
    # A: priority Surat>Mumbai, requires 3 -> Surat
    assert rank_candidate_locations({"Surat": {"SKU-A": 5}, "Mumbai": {"SKU-A": 7}}, [AllocationRequirement("SKU-A", 3)], priority=["Surat", "Mumbai"])[0] == "Surat"
    # B: no priority, Mumbai has more ATS, requires 3 -> Mumbai
    assert rank_candidate_locations({"Surat": {"SKU-A": 2}, "Mumbai": {"SKU-A": 7}}, [AllocationRequirement("SKU-A", 3)], priority=None) == ["Mumbai"]
    # C: priority Mumbai>Surat, requires 3 -> Mumbai
    assert rank_candidate_locations({"Surat": {"SKU-A": 5}, "Mumbai": {"SKU-A": 7}}, [AllocationRequirement("SKU-A", 3)], priority=["Mumbai", "Surat"])[0] == "Mumbai"
    # D: neither location alone has 5 -> no eligible candidate, no split
    assert rank_candidate_locations({"Surat": {"SKU-A": 3}, "Mumbai": {"SKU-A": 2}}, [AllocationRequirement("SKU-A", 5)], priority=None) == []
    # E: Surat satisfies both lines, Mumbai only SKU-A -> Surat only
    assert rank_candidate_locations(
        {"Surat": {"SKU-A": 5, "SKU-B": 5}, "Mumbai": {"SKU-A": 5, "SKU-B": 0}},
        [AllocationRequirement("SKU-A", 2), AllocationRequirement("SKU-B", 1)], priority=None,
    ) == ["Surat"]
    # F: Surat only SKU-A, Mumbai only SKU-B -> no location satisfies BOTH, no implicit split
    assert rank_candidate_locations(
        {"Surat": {"SKU-A": 5, "SKU-B": 0}, "Mumbai": {"SKU-A": 0, "SKU-B": 5}},
        [AllocationRequirement("SKU-A", 2), AllocationRequirement("SKU-B", 1)], priority=None,
    ) == []


# --- service-level proofs: the full reserve_inventory_for_order(location=None) path ----------------

def test_scenario_a_priority_wins_over_higher_ats(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    store.set_config("mer_A", {"inventory": {"location_priority": ["Surat", "Mumbai"]}})
    service = _service(store, shopify)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-A", location_ref="Surat", quantity=5, available=5))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-A", location_ref="Mumbai", quantity=7, available=7))
    order = _order_with_lines(store, "mer_A", "ALLOC-A", [("SKU-A", 3)])
    result = service.reserve_inventory_for_order("mer_A", order)
    assert result["reserved"] is True
    assert _inv(store, "mer_A", "SKU-A", "Surat").reserved == 3
    assert _inv(store, "mer_A", "SKU-A", "Mumbai").reserved == 0


def test_scenario_b_highest_ats_wins_with_no_priority_configured(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    service = _service(store, shopify)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-B", location_ref="Surat", quantity=2, available=2))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-B", location_ref="Mumbai", quantity=7, available=7))
    order = _order_with_lines(store, "mer_A", "ALLOC-B", [("SKU-B", 3)])
    result = service.reserve_inventory_for_order("mer_A", order)
    assert result["reserved"] is True
    assert _inv(store, "mer_A", "SKU-B", "Surat").reserved == 0
    assert _inv(store, "mer_A", "SKU-B", "Mumbai").reserved == 3


def test_scenario_c_priority_can_prefer_the_smaller_location(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    store.set_config("mer_A", {"inventory": {"location_priority": ["Mumbai", "Surat"]}})
    service = _service(store, shopify)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-C", location_ref="Surat", quantity=5, available=5))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-C", location_ref="Mumbai", quantity=7, available=7))
    order = _order_with_lines(store, "mer_A", "ALLOC-C", [("SKU-C", 3)])
    result = service.reserve_inventory_for_order("mer_A", order)
    assert result["reserved"] is True
    assert _inv(store, "mer_A", "SKU-C", "Mumbai").reserved == 3
    assert _inv(store, "mer_A", "SKU-C", "Surat").reserved == 0


def test_scenario_d_no_location_can_satisfy_alone_fails_without_split(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    service = _service(store, shopify)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-D", location_ref="Surat", quantity=3, available=3))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-D", location_ref="Mumbai", quantity=2, available=2))
    order = _order_with_lines(store, "mer_A", "ALLOC-D", [("SKU-D", 5)])
    result = service.reserve_inventory_for_order("mer_A", order)
    assert result["reserved"] is False
    assert result["lines"][0] == {"sku": "SKU-D", "requested": 5, "reserved": 0, "shortfall": 5}
    # NO split - neither location gets any reservation at all
    assert _inv(store, "mer_A", "SKU-D", "Surat").reserved == 0
    assert _inv(store, "mer_A", "SKU-D", "Mumbai").reserved == 0


def test_scenario_e_whole_multiline_order_goes_to_the_one_location_that_satisfies_all_lines(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    service = _service(store, shopify)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-EA", location_ref="Surat", quantity=5, available=5))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-EB", location_ref="Surat", quantity=5, available=5))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-EA", location_ref="Mumbai", quantity=5, available=5))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-EB", location_ref="Mumbai", quantity=0, available=0))  # Mumbai can't cover SKU-EB
    order = _order_with_lines(store, "mer_A", "ALLOC-E", [("SKU-EA", 2), ("SKU-EB", 1)])
    result = service.reserve_inventory_for_order("mer_A", order)
    assert result["reserved"] is True
    assert _inv(store, "mer_A", "SKU-EA", "Surat").reserved == 2
    assert _inv(store, "mer_A", "SKU-EB", "Surat").reserved == 1
    assert _inv(store, "mer_A", "SKU-EA", "Mumbai").reserved == 0
    assert _inv(store, "mer_A", "SKU-EB", "Mumbai").reserved == 0


def test_scenario_f_no_single_location_covers_every_line_fails_without_implicit_split(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    service = _service(store, shopify)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-FA", location_ref="Surat", quantity=5, available=5))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-FB", location_ref="Surat", quantity=0, available=0))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-FA", location_ref="Mumbai", quantity=0, available=0))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-FB", location_ref="Mumbai", quantity=5, available=5))
    order = _order_with_lines(store, "mer_A", "ALLOC-F", [("SKU-FA", 2), ("SKU-FB", 1)])
    result = service.reserve_inventory_for_order("mer_A", order)
    assert result["reserved"] is False
    assert {(l["sku"], l["reserved"]) for l in result["lines"]} == {("SKU-FA", 0), ("SKU-FB", 0)}
    # neither location received ANY reservation - no implicit per-SKU split across locations
    assert _inv(store, "mer_A", "SKU-FA", "Surat").reserved == 0
    assert _inv(store, "mer_A", "SKU-FB", "Mumbai").reserved == 0


# --- explicit location remains authoritative --------------------------------------------------------

def test_explicit_location_is_attempted_only_even_when_another_location_has_more_stock(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    service = _service(store, shopify)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-EXP", location_ref="Surat", quantity=2, available=2))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-EXP", location_ref="Mumbai", quantity=100, available=100))
    order = _order_with_lines(store, "mer_A", "ALLOC-EXP", [("SKU-EXP", 3)])
    result = service.reserve_inventory_for_order("mer_A", order, location="Surat")
    assert result["reserved"] is False  # explicit means explicit - no fallback to Mumbai despite ample stock
    assert result["lines"][0] == {"sku": "SKU-EXP", "requested": 3, "reserved": 2, "shortfall": 1}
    assert _inv(store, "mer_A", "SKU-EXP", "Mumbai").reserved == 0


# --- default_location_ref no longer overrides allocation when insufficient -------------------------

def test_configured_default_location_does_not_override_when_insufficient(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    store.set_config("mer_A", {"inventory": {"default_location_ref": "Surat"}})
    service = _service(store, shopify)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-DEF", location_ref="Surat", quantity=1, available=1))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-DEF", location_ref="Mumbai", quantity=10, available=10))
    order = _order_with_lines(store, "mer_A", "ALLOC-DEF", [("SKU-DEF", 3)])
    result = service.reserve_inventory_for_order("mer_A", order)
    assert result["reserved"] is True
    assert _inv(store, "mer_A", "SKU-DEF", "Mumbai").reserved == 3  # NOT stuck at insufficient Surat
    assert _inv(store, "mer_A", "SKU-DEF", "Surat").reserved == 0


def test_configured_default_location_wins_when_it_is_sufficient(phase0):
    """default_location_ref still participates as a real (weak) preference - it is honored whenever it
    CAN fulfil, just no longer forced when it cannot."""
    store, _workflow, shopify, _chatwoot = phase0
    store.set_config("mer_A", {"inventory": {"default_location_ref": "Surat"}})
    service = _service(store, shopify)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-DEF2", location_ref="Surat", quantity=5, available=5))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-DEF2", location_ref="Mumbai", quantity=10, available=10))
    order = _order_with_lines(store, "mer_A", "ALLOC-DEF2", [("SKU-DEF2", 3)])
    result = service.reserve_inventory_for_order("mer_A", order)
    assert result["reserved"] is True
    assert _inv(store, "mer_A", "SKU-DEF2", "Surat").reserved == 3


# --- legacy single-location compatibility ------------------------------------------------------------

def test_legacy_single_location_merchant_unaffected(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    service = _service(store, shopify)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-LEG", location_ref="default", quantity=5, available=5))
    order = _order_with_lines(store, "mer_A", "ALLOC-LEG", [("SKU-LEG", 2)])
    result = service.reserve_inventory_for_order("mer_A", order)
    assert result["reserved"] is True
    assert _inv(store, "mer_A", "SKU-LEG", "default").reserved == 2


# --- allocation decision is audited/traceable ---------------------------------------------------------

def test_allocation_decision_is_audited_with_explainable_trace(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    store.set_config("mer_A", {"inventory": {"location_priority": ["Surat", "Mumbai"]}})
    service = _service(store, shopify)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-AUDIT", location_ref="Surat", quantity=5, available=5))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-AUDIT", location_ref="Mumbai", quantity=7, available=7))
    order = _order_with_lines(store, "mer_A", "ALLOC-AUDIT", [("SKU-AUDIT", 3)])
    service.reserve_inventory_for_order("mer_A", order)
    events = [e for e in store.list_audit("mer_A") if e.action == "location_allocation_decision" and e.object_id == order.id]
    assert len(events) == 1
    event = events[0]
    assert event.result == "allocated"
    trace = event.requested_mutation
    assert trace["selected_location"] == "Surat"
    assert trace["priority"] == ["Surat", "Mumbai"]
    assert {c["location"] for c in trace["candidates"]} == {"Surat", "Mumbai"}
    surat_candidate = next(c for c in trace["candidates"] if c["location"] == "Surat")
    assert surat_candidate["ats"] == {"SKU-AUDIT": 5}  # WHY Surat was eligible, preserved as evidence


def test_allocation_failure_is_also_audited(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    service = _service(store, shopify)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-AUDITFAIL", location_ref="Surat", quantity=1, available=1))
    order = _order_with_lines(store, "mer_A", "ALLOC-AUDITFAIL", [("SKU-AUDITFAIL", 5)])
    service.reserve_inventory_for_order("mer_A", order)
    events = [e for e in store.list_audit("mer_A") if e.action == "location_allocation_decision" and e.object_id == order.id]
    assert len(events) == 1
    assert events[0].result == "failed"
    assert events[0].requested_mutation["selected_location"] is None


# --- bounded rollback-and-retry mechanism (the concurrency-race code path, exercised directly) --------

def test_partial_line_failure_at_a_location_rolls_back_the_whole_attempt(phase0):
    """Directly exercises `_attempt_reserve_order_at_location`'s rollback: line 1 succeeds, line 2 is
    short at the SAME location - Step 4: this is now a TRUE whole-transaction rollback (one call into
    `store.reserve_order_lines_atomic`), not a Python-level manual release loop - nothing is ever mutated
    for EITHER line if any line is insufficient, so there is nothing to leak or release after the fact.
    This is the exact mechanism the real concurrency test relies on when a race causes a ranked candidate
    to unexpectedly come up short between the allocator's ATS read and its atomic reserve attempt."""
    store, _workflow, shopify, _chatwoot = phase0
    service = _service(store, shopify)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-ROLL-A", location_ref="Surat", quantity=5, available=5))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-ROLL-B", location_ref="Surat", quantity=1, available=1))
    order = _order_with_lines(store, "mer_A", "ALLOC-ROLL", [("SKU-ROLL-A", 2), ("SKU-ROLL-B", 5)])
    order_lines = [l for l in store.list(OrderLine, "mer_A") if l.order_id == order.id]
    attempt = service._attempt_reserve_order_at_location("mer_A", order, order_lines, "Surat")
    assert attempt["outcome"] == "insufficient"
    assert _inv(store, "mer_A", "SKU-ROLL-A", "Surat").reserved == 0  # NEVER reserved, not rolled back after the fact
    assert _inv(store, "mer_A", "SKU-ROLL-B", "Surat").reserved == 0
    reservations = [r for r in store.list(InventoryReservation, "mer_A") if r.source_id == order.id]
    assert reservations == []  # no reservation rows were ever created for this failed whole-order attempt


# --- platform neutrality: the allocator consumes only canonical inventory/order/config, provably ------

def test_allocator_module_has_no_platform_specific_imports():
    """The allocator's only real dependency is the standard-library `dataclasses` module - zero coupling
    to any connector, canonical-model, or store module, let alone a specific platform. This is what
    actually makes it "reusable by every future connector unchanged" (Amazon/Flipkart/Myntra/Meesho or
    otherwise) - not merely the absence of platform names in prose."""
    import ast
    import inspect

    from sanocea.packages.post_order import allocation

    tree = ast.parse(inspect.getsource(allocation))
    imported_modules = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert imported_modules == {"__future__", "dataclasses"}
