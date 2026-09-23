from __future__ import annotations

from typing import Any


class SupplierSimulator:
    """An independently stateful stand-in for a supplier's own systems - NOT a pure function over
    canonical Sanocea objects (see Phase 3's audit finding about SimulatedSettlementProvider leaking
    Sanocea's own IDs; this simulator deliberately avoids that class of shortcut).

    Owns its own:
      - supplier-side stock/MOQ catalog, keyed by the supplier's OWN sku code (never Sanocea's sku
        directly, though callers commonly choose to reuse the same string for readability in tests)
      - acknowledgement/shipment sequence counters per external PO reference (independent of when
        Sanocea happens to receive/process an event - lets tests construct genuinely stale/out-of-order
        events)
      - an append-only event stream or record of everything it has ever emitted

    Sanocea-side PO submission/idempotency is handled separately by SimulatedSupplierConnector
    (mirrors SimulatedPaymentConnector's role); this class starts from an already-created external PO
    reference and simulates what the supplier does with it.
    """

    def __init__(self) -> None:
        self._stock: dict[str, int] = {}
        self._moq: dict[str, int] = {}
        self._ack_sequence: dict[str, int] = {}
        self._ship_sequence: dict[str, int] = {}
        self.events: list[dict[str, Any]] = []

    # --- Supplier-side catalog (independent state, not derived from Sanocea) -------------------------

    def register_stock(self, supplier_sku: str, available: int, moq: int = 1) -> None:
        self._stock[supplier_sku] = available
        self._moq[supplier_sku] = moq

    # --- Acknowledgement ------------------------------------------------------------------------------

    def acknowledge(
        self,
        external_po_ref: str,
        lines: list[dict[str, Any]],
        *,
        fault: str | None = None,
    ) -> dict[str, Any]:
        """lines: [{"sku": ..., "supplier_sku": ..., "quantity_ordered": ..., "unit_cost": ...,
        "line_ref": <optional>}, ...] - `lines` here represents what the supplier actually RECEIVED on
        submission (i.e. SimulatedSupplierConnector's stored `purchase_orders[ref]["lines"]`), so
        whatever `line_ref` Sanocea sent outbound is exactly what is echoed back on `confirmed_lines`
        below - the simulator never invents or looks up identity Sanocea did not actually hand it,
        staying faithful to what a real supplier integration could do (Step 5B).

        fault: None (full confirm) | "reject" | "partial" | "moq_reject" | "stock_shortage" |
               "cost_change" | "delayed" (metadata only - caller controls actual timing/ordering)
        """
        confirmed_lines: list[dict[str, Any]] = []
        status = "confirmed"
        if fault == "reject":
            status = "rejected"
        else:
            for line in lines:
                supplier_sku = line.get("supplier_sku") or line["sku"]
                quantity_ordered = int(line["quantity_ordered"])
                unit_cost = int(line["unit_cost"])
                quantity_confirmed = quantity_ordered
                if fault == "moq_reject" and quantity_ordered < self._moq.get(supplier_sku, 1):
                    quantity_confirmed = 0
                elif fault == "stock_shortage":
                    available = self._stock.get(supplier_sku, quantity_ordered)
                    quantity_confirmed = min(quantity_ordered, max(available, 0))
                    self._stock[supplier_sku] = max(available - quantity_confirmed, 0)
                elif fault == "partial":
                    quantity_confirmed = max(quantity_ordered // 2, 0)
                elif fault == "cost_change":
                    unit_cost = int(unit_cost * 1.15) + 1
                if quantity_confirmed > 0:
                    confirmed_line = {"sku": line["sku"], "quantity_confirmed": quantity_confirmed, "unit_cost": unit_cost}
                    if line.get("line_ref"):
                        confirmed_line["line_ref"] = line["line_ref"]
                    confirmed_lines.append(confirmed_line)
            if not confirmed_lines:
                status = "rejected"
            elif any(cl["quantity_confirmed"] < int(l["quantity_ordered"]) for cl, l in zip(confirmed_lines, lines)):
                status = "partially_confirmed"
        sequence = self._next(self._ack_sequence, external_po_ref)
        event = {
            "type": "acknowledgement",
            "external_po_ref": external_po_ref,
            "external_ref": f"{external_po_ref}-ack-{sequence}",
            "sequence": sequence,
            "status": status,
            "lines": confirmed_lines,
            "fault": fault,
        }
        self.events.append(event)
        return event

    # --- Dispatch (the supplier's OWN shipment manifest - not the warehouse's physical count) ---------

    def dispatch(
        self,
        external_po_ref: str,
        confirmed_lines: list[dict[str, Any]],
        *,
        fault: str | None = None,
    ) -> dict[str, Any]:
        """confirmed_lines: [{"sku": ..., "quantity_confirmed": ..., "line_ref": <optional>}, ...] (from
        a prior acknowledge()) - `line_ref`, if the acknowledgement carried one, is echoed through to
        `shipped_lines` unchanged (Step 5B: the simulator never invents identity beyond what it was
        actually given).

        fault: None (ship exactly what was confirmed) | "partial_shipment" (fewer units, rest presumably
               in a later shipment) | "delayed" (metadata only)
        """
        shipped_lines: list[dict[str, Any]] = []
        for line in confirmed_lines:
            quantity = int(line["quantity_confirmed"])
            if fault == "partial_shipment":
                quantity = max(quantity // 2, 0)
            if quantity > 0:
                shipped_line = {"sku": line["sku"], "quantity_shipped": quantity}
                if line.get("line_ref"):
                    shipped_line["line_ref"] = line["line_ref"]
                shipped_lines.append(shipped_line)
        sequence = self._next(self._ship_sequence, external_po_ref)
        event = {
            "type": "shipment",
            "external_po_ref": external_po_ref,
            "external_shipment_ref": f"{external_po_ref}-ship-{sequence}",
            "sequence": sequence,
            "lines": shipped_lines,
            "fault": fault,
        }
        self.events.append(event)
        return event

    # --- Adversarial event-stream helpers -------------------------------------------------------------

    def duplicate_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """Redeliver an exact copy of a previously emitted event - simulates a webhook retry / at-least-
        once delivery redelivering the identical event, with the SAME external_ref/sequence."""
        return dict(event)

    def stale_event(self, template_event: dict[str, Any], *, sequence: int) -> dict[str, Any]:
        """Construct an event with an explicitly OLD/lower sequence than one already emitted for this
        PO - simulates a genuinely out-of-order delivery (not a duplicate - a different external_ref
        carrying stale content)."""
        stale = dict(template_event)
        stale["sequence"] = sequence
        key = "external_ref" if template_event["type"] == "acknowledgement" else "external_shipment_ref"
        stale[key] = f"{template_event['external_po_ref']}-{template_event['type']}-stale-{sequence}"
        return stale

    def _next(self, counters: dict[str, int], key: str) -> int:
        counters[key] = counters.get(key, 0) + 1
        return counters[key]
