from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sanocea.packages.domain_contract.models import Order, Refund


class SimulatedSettlementProvider:
    """A stateful stand-in for a payment gateway's settlement feed.

    Phase 3.1: this simulator no longer leaks Sanocea's internal order.id into the settlement payload it
    produces. Every payment/cod_collection entry carries a `provider_order_reference` - the same kind of
    opaque, provider-minted transaction reference a real gateway would use - which Sanocea must resolve
    through external_id_mappings (established when the payment was first observed). Callers supply the
    `references` mapping (order.id -> provider reference) that was established at observation time; the
    simulator uses it purely to know which of ITS OWN transaction references corresponds to which order
    when building settlement rows for that transaction - exactly the correlation a real gateway already
    has, since it minted the reference in the first place. It never reads or embeds order.id itself.

    Phase 4.6: the identical treatment for refund entries. Callers supply `refund_references`
    (refund.id -> provider-minted refund reference, established when execute_refund() first confirmed
    the refund externally); the simulator emits `provider_refund_reference`, never Sanocea's internal
    refund.id, and injects the same class of faults (corrupted/unknown reference) it already does for
    order references.
    """

    name = "simulated_settlements"

    def build_batch(
        self,
        merchant_id: str,
        orders: list[Order],
        refunds: list[Refund],
        references: dict[str, str],
        *,
        include_faults: bool = True,
        batch_label: str = "batch",
        refund_references: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        refund_references = refund_references or {}
        entries: list[dict[str, Any]] = []
        gross = 0
        for idx, order in enumerate(orders):
            if order.payment_status != "paid":
                continue
            reference = references.get(order.id)
            if reference is None:
                # The simulator has no provider reference for this order at all - it cannot fabricate
                # one (a real gateway can only settle a transaction it actually processed).
                continue
            settle_reference = reference
            if include_faults and idx % 23 == 0:
                # "Incorrect reference": a plausible-looking but corrupted reference - simulates a
                # provider-side typo/truncation rather than a wholly unknown transaction.
                settle_reference = f"{reference}-corrupt"
            amount = order.total_amount
            if include_faults and idx % 17 == 0:
                amount -= 500
            entry_type = "cod_collection" if idx % 9 == 0 else "payment"
            entries.append(
                {
                    "external_entry_id": f"{merchant_id}-{batch_label}-settle-{reference}",
                    "entry_type": entry_type,
                    "provider_order_reference": settle_reference,
                    "amount": amount,
                    "currency": order.currency,
                    "description": f"{entry_type} for provider reference {settle_reference}",
                }
            )
            gross += amount
            if idx % 8 == 0:
                entries.append(
                    {
                        "external_entry_id": f"{merchant_id}-{batch_label}-fee-{reference}",
                        "entry_type": "fee",
                        "order_id": order.id,
                        "amount": -120,
                        "currency": order.currency,
                        "description": "gateway fee",
                    }
                )
            if idx % 10 == 0:
                charge = -250
                if include_faults and idx % 20 == 0:
                    charge = -450
                entries.append(
                    {
                        "external_entry_id": f"{merchant_id}-{batch_label}-courier-{reference}",
                        "entry_type": "courier_charge",
                        "order_id": order.id,
                        "amount": charge,
                        "currency": order.currency,
                        "description": "courier charge",
                    }
                )
        for idx, refund in enumerate(refunds):
            if refund.status != "completed":
                continue
            reference = refund_references.get(refund.id)
            if reference is None:
                # Mirrors the order path: the simulator cannot fabricate a provider reference for a
                # refund it never actually processed.
                continue
            if include_faults and idx % 5 == 0:
                continue
            amount = -abs(refund.amount)
            if include_faults and idx % 7 == 0:
                amount += 300
            settle_reference = reference
            if include_faults and idx % 11 == 0:
                # "Corrupted reference": a plausible-looking but wrong refund reference.
                settle_reference = f"{reference}-corrupt"
            entries.append(
                {
                    "external_entry_id": f"{merchant_id}-{batch_label}-refund-{refund.id}",
                    "entry_type": "refund",
                    "provider_refund_reference": settle_reference,
                    "amount": amount,
                    "currency": refund.currency,
                    "description": "refund settlement",
                }
            )
        if include_faults and orders:
            # "Unknown reference": a provider transaction Sanocea has never observed at all (e.g. a
            # marketplace-collected order the channel connector missed) - must never resolve, never MATCH.
            entries.append(
                {
                    "external_entry_id": f"{merchant_id}-{batch_label}-unknown-entry",
                    "entry_type": "payment",
                    "provider_order_reference": f"unknown-provider-ref-{merchant_id}-{batch_label}",
                    "amount": 9999,
                    "currency": orders[0].currency,
                    "description": "unmatched marketplace payment - provider reference Sanocea never observed",
                }
            )
            entries.append(entries[-1].copy())
        net = sum(int(entry["amount"]) for entry in entries)
        return {
            "external_batch_id": f"{merchant_id}-{batch_label}-{len(orders)}-{len(refunds)}",
            "settlement_date": datetime.now(timezone.utc),
            "currency": orders[0].currency if orders else "INR",
            "gross_amount": gross,
            "net_amount": net,
            "entries": entries,
        }
