"""ApprovalService - ONE authoritative resolution path for the `Approval` model (domain_contract/models.py),
regardless of which delivery channel (Command Center click, WhatsApp reply, email reply) triggers it.
Per the multi-channel live demo #2 spec: "There is ONE approval. Multiple notification/delivery channels
can act upon it." WhatsApp/email transports (increment E) will call `resolve()` exactly like the
Command Center route does - they never maintain their own approval state.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sanocea.packages.audit import AuditLedger
from sanocea.packages.domain_contract.models import Approval, Cancellation, Refund, now_utc

DEFAULT_APPROVAL_EXPIRY = timedelta(hours=24)


class ApprovalError(Exception):
    pass


class ApprovalService:
    def __init__(self, store) -> None:
        self.store = store
        self.audit = AuditLedger(store)

    def resolve(self, merchant_id: str, approval_id: str, *, decision: str, resolved_via: str, decided_by: str) -> dict[str, Any]:
        """Idempotent by design (Section 8/22 of the spec): a second identical resolution attempt - via
        the same or a different channel - returns `already_resolved: True` rather than erroring, so a
        duplicate WhatsApp webhook, a race between WhatsApp and email, or a double-tap APPROVE can never
        double-execute a channel correction."""
        approval = self.store.get(Approval, merchant_id, approval_id)
        if approval.merchant_id != merchant_id:
            raise ApprovalError("approval does not belong to this merchant")
        if approval.status != "pending":
            return {
                "approval_id": approval.id, "status": approval.status, "already_resolved": True,
                "resolved_via": approval.resolved_via,
                "message": "This request has already been resolved.",
            }
        if approval.expires_at and now_utc() > approval.expires_at:
            approval.status = "expired"
            self.store.put(approval)
            self.audit.record(
                merchant_id=merchant_id, actor=resolved_via, source="approval_service", action="approval_expired",
                object_type="Approval", object_id=approval.id, result="expired",
            )
            raise ApprovalError("approval reference has expired")

        approval.status = "approved" if decision == "approved" else "denied"
        approval.decided_by = decided_by
        approval.decided_at = now_utc()
        approval.resolved_via = resolved_via
        self.store.put(approval)
        self.audit.record(
            merchant_id=merchant_id, actor=resolved_via, source="approval_service", action="approval_resolved",
            object_type="Approval", object_id=approval.id, result=approval.status,
        )

        resumed_operation_id = None
        if approval.status == "approved" and approval.object_id:
            # Real defect fixed here (found tracing the Mariyal order-loop demo end to end): resolve()
            # used to flip the Approval's own status and stop - for cancel_order/create_return/refund
            # (and the new resolve_inventory_shortage), APPROVE never actually caused the underlying
            # governed operation to execute. One dispatch table, reusing the EXISTING per-domain
            # approve_X methods on PostOrderOperationsService unchanged (see packages/post_order/
            # operations.py) - not a second approval architecture, just closing the gap between
            # "Approval says approved" and "the operation actually ran."
            if approval.action == "channel_operation_correction":
                from sanocea.packages.channel_ops import ChannelOperationService

                resumed = ChannelOperationService(self.store).resume(merchant_id, approval.object_id)
                resumed_operation_id = resumed.id
            elif approval.action in ("cancel_order", "create_return", "refund", "resolve_inventory_shortage"):
                from sanocea.packages.runtime.service_graph import build_service_graph

                post_order = build_service_graph(self.store).post_order
                # approval.object_id is the ORDER id (that is what evaluate_cancellation/evaluate_refund
                # set it to) - but approve_cancellation/approve_refund each take THEIR OWN domain
                # object's id (Cancellation.id / Refund.id), not the order's. Resolving that correctly
                # here, rather than passing the wrong id through, is itself part of the same defect this
                # dispatch exists to close.
                if approval.action == "cancel_order":
                    cancellation = next((c for c in self.store.list(Cancellation, merchant_id) if c.order_id == approval.object_id), None)
                    if cancellation:
                        post_order.approve_cancellation(merchant_id, cancellation.id, decided_by)
                elif approval.action == "refund":
                    refund = next((r for r in self.store.list(Refund, merchant_id) if r.order_id == approval.object_id), None)
                    if refund:
                        post_order.approve_refund(merchant_id, refund.id, decided_by)
                elif approval.action == "create_return":
                    post_order.approve_return(merchant_id, approval.object_id, decided_by)
                elif approval.action == "resolve_inventory_shortage":
                    post_order.resume_inventory_shortage(merchant_id, approval)
                resumed_operation_id = approval.object_id
            elif approval.action == "price_change":
                product_id = approval.object_id
                evidence = approval.evidence or {}
                new_price = evidence.get("new_price")
                new_compare_at = evidence.get("compare_at_price") or evidence.get("new_compare_at_price")
                sku = evidence.get("sku")
                variant_gid = evidence.get("variant_gid")
                product_gid = evidence.get("product_gid")
                if product_id and new_price is not None:
                    from sanocea.packages.domain_contract.models import ProductDraft, Variant

                    for var in self.store.list(Variant, merchant_id):
                        if var.id == product_id or (sku and var.sku == sku):
                            var.price_hint["price"] = int(float(new_price))
                            self.store.put(var)
                    for draft in self.store.list(ProductDraft, merchant_id):
                        if draft.id == product_id or (sku and draft.sku == sku):
                            draft.price = int(float(new_price))
                            self.store.put(draft)

                # Push price correction to connected storefront if supported
                if variant_gid or sku:
                    try:
                        from sanocea.packages.runtime.service_graph import build_service_graph

                        connector = build_service_graph(self.store).storefronts.resolve(merchant_id)
                        if hasattr(connector, "update_variant_price"):
                            connector.update_variant_price(
                                merchant_id,
                                variant_gid=variant_gid,
                                product_gid=product_gid,
                                sku=sku,
                                price=new_price,
                                compare_at_price=new_compare_at,
                            )
                    except Exception:
                        pass
                resumed_operation_id = product_id
            elif approval.action == "catalog_unpublish":
                product_id = approval.object_id
                from sanocea.packages.domain_contract.models import Product

                prod = next((p for p in self.store.list(Product, merchant_id) if p.id == product_id), None)
                if prod:
                    prod.status = "archived"
                    self.store.put(prod)
                resumed_operation_id = product_id
            elif approval.action == "inventory_writeoff":
                evidence = approval.evidence or {}
                sku = evidence.get("sku")
                location_ref = evidence.get("location_ref")
                units = int(evidence.get("units", 0))
                if sku and units > 0:
                    from sanocea.packages.domain_contract.models import Inventory

                    for inv in self.store.list(Inventory, merchant_id):
                        if inv.sku == sku and (not location_ref or inv.location_ref == location_ref):
                            inv.quarantine = max(0, inv.quarantine - units)
                            inv.quantity = max(0, inv.quantity - units)
                            self.store.put(inv)
                resumed_operation_id = sku

        # Sequential WhatsApp delivery (explicit demo requirement): if a second shortage/order-flow
        # approval was already pending when this one got created, it was deliberately held back
        # unnotified (see PostOrderOperationsService._auto_notify_whatsapp) rather than sent alongside
        # this one - so the owner never has to type a reference to disambiguate two live messages.
        # Now that THIS one is resolved (approved or denied - either way it's off the queue), send the
        # next queued one, if any. Runs regardless of decision/action so a channel_operation_correction
        # resolution also releases a queued order-flow approval, and vice versa.
        try:
            from sanocea.packages.runtime.service_graph import build_service_graph

            build_service_graph(self.store).post_order.notify_next_pending_approval(merchant_id)
        except Exception:  # noqa: BLE001 - queued-notify failure must never break the resolution itself
            pass

        return {
            "approval_id": approval.id, "status": approval.status, "already_resolved": False,
            "resolved_via": resolved_via, "resumed_operation_id": resumed_operation_id,
        }

    def get_pending(self, merchant_id: str) -> list[Approval]:
        return self.store.list_where(Approval, merchant_id, status="pending")

    def request_approval(
        self,
        merchant_id: str,
        *,
        action: str,
        object_id: str | None,
        requested_by: str,
        summary: str,
        evidence: dict[str, Any],
        recommendation: str | None = None,
        reference: str | None = None,
        notify_channels: list[str] | None = None,
    ) -> Approval:
        """Create a pending approval record with structured evidence and audit logging."""
        import uuid

        approval = Approval(
            merchant_id=merchant_id,
            action=action,
            object_id=object_id,
            status="pending",
            requested_by=requested_by,
            summary=summary,
            evidence=evidence,
            recommendation=recommendation,
            reference=reference or f"APP-{uuid.uuid4().hex[:6].upper()}",
            notify_channels=notify_channels or ["command_center"],
            expires_at=now_utc() + DEFAULT_APPROVAL_EXPIRY,
        )
        self.store.put(approval)
        self.audit.record(
            merchant_id=merchant_id,
            actor=requested_by,
            source="approval_service",
            action="approval_requested",
            object_type="Approval",
            object_id=approval.id,
            evidence_ref=approval.reference,
            result="pending",
        )
        return approval

