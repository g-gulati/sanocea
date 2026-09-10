from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sanocea.packages.audit import AuditLedger
from sanocea.packages.connector_sdk import MutationRequest
from sanocea.packages.domain_contract.models import (
    Approval,
    Cancellation,
    ConnectorCommand,
    Exchange,
    ExternalIdMapping,
    FulfilmentObservation,
    Inventory,
    InventoryObservation,
    Order,
    OrderLine,
    ReconciliationResult,
    Refund,
    Return,
    Shipment,
    ShipmentObservation,
    TrackingEvent,
    now_utc,
)
from sanocea.packages.exceptions import ExceptionCategory, ExceptionService
from sanocea.packages.policy_engine import Decision, PolicyEngine


@dataclass
class Phase2Counters:
    inventory_observations: int = 0
    inventory_discrepancies: int = 0
    inventory_auto_reconciled: int = 0
    inventory_human_interventions: int = 0
    overselling_prevented: int = 0
    fulfilments_monitored: int = 0
    fulfilment_straight_through: int = 0
    fulfilment_sla_exceptions: int = 0
    fulfilment_auto_remediated: int = 0
    fulfilment_escalated: int = 0
    shipments: int = 0
    tracking_events: int = 0
    ndrs: int = 0
    ndrs_auto_resolved: int = 0
    rtos: int = 0
    delivery_exceptions: int = 0
    logistics_human_interventions: int = 0
    cancellation_requests: int = 0
    cancellations_auto_permitted: int = 0
    cancellations_approval_gated: int = 0
    duplicate_cancellations: int = 0
    return_requests: int = 0
    return_eligibility_determined: int = 0
    returns_approval_gated: int = 0
    returns_rejected_by_policy: int = 0
    returns_completed: int = 0
    returns_escalated: int = 0
    exchange_requests: int = 0
    exchanges_completed: int = 0
    exchanges_escalated: int = 0
    refund_requests: int = 0
    refund_eligibility_determined: int = 0
    refunds_auto_permitted: int = 0
    refunds_approval_gated: int = 0
    refunds_reconciled: int = 0
    uncertain_mutations: int = 0
    duplicate_refunds: int = 0
    refund_submitted: int = 0
    refund_completed: int = 0
    duplicate_returns: int = 0
    duplicate_exchanges: int = 0
    policy_approvals: int = 0
    capability_gap_escalations: int = 0
    genuine_human_judgment: int = 0
    deterministic_operations: int = 0
    ai_assisted_operations: int = 0
    straight_through_operations: int = 0
    automated_remediations: int = 0
    approval_only_touches: int = 0
    corrective_interventions: int = 0
    fully_manual_cases: int = 0
    ai_calls: int = 0
    zero_tolerance_failures: dict[str, bool] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        total = max(
            self.inventory_observations
            + self.fulfilments_monitored
            + self.shipments
            + self.cancellation_requests
            + self.return_requests
            + self.exchange_requests
            + self.refund_requests,
            1,
        )
        data["founder_human_intervention_rate"] = round((self.approval_only_touches + self.corrective_interventions + self.fully_manual_cases) / total, 4)
        data["ai_dependency_rate"] = round(self.ai_calls / total, 4)
        data["deterministic_first_resolution_rate"] = round((total - self.ai_calls) / total, 4)
        return data


class PostOrderOperationsService:
    def __init__(self, store, storefront_connector, logistics_connector, payment_connector=None) -> None:
        self.store = store
        # storefront_connector may be a single connector (existing single-platform callers, unchanged)
        # or a StorefrontConnectorRegistry (multi-merchant/multi-platform) - as_resolver() normalizes
        # both into one calling convention: self.storefront(merchant_id) -> the right connector for
        # THAT merchant. Domain code here never knows or branches on which platform that is.
        from sanocea.packages.runtime.storefront_registry import as_resolver

        self.storefront = as_resolver(storefront_connector)
        self.logistics = logistics_connector
        self.payments = payment_connector
        self.audit = AuditLedger(store)
        self.exceptions = ExceptionService(store)
        self.policy = PolicyEngine()
        self._inventory_cache: dict[tuple[str, str, str], Inventory] = {}
        self._shipment_by_order: dict[tuple[str, str], Shipment] = {}
        self._tracking_sequence: dict[tuple[str, str], int] = {}

    def reserve_inventory_for_order(self, merchant_id: str, order: Order, location: str = "default") -> dict[str, Any]:
        """Phase 4.5: the missing link between order ingestion and inventory truth. Idempotent - calling
        this twice for the same order (e.g. a retried workflow signal) must not double-reserve; guarded
        by the same 'sanocea_internal' ConnectorCommand marker pattern already used elsewhere in this
        service (see _record_internal_command), not by a workflow-layer check.
        """
        idempotency_key = f"reserve_inventory:{order.id}"
        existing = [c for c in self.store.list(ConnectorCommand, merchant_id) if c.action == "reserve_inventory" and c.idempotency_key == idempotency_key]
        if existing:
            lines = existing[0].payload.get("lines", [])
            return {"reserved": not any(l.get("shortfall") for l in lines), "already_done": True, "lines": lines}

        order_lines = [l for l in self.store.list(OrderLine, merchant_id) if l.order_id == order.id]
        line_results: list[dict[str, Any]] = []
        any_shortfall = False
        for line in order_lines:
            if not line.sku:
                continue
            candidates = [i for i in self.store.list(Inventory, merchant_id) if i.sku == line.sku and i.location_ref == location]
            inv = candidates[-1] if candidates else None
            if inv is None:
                self.exceptions.create(
                    merchant_id=merchant_id, category=ExceptionCategory.INVENTORY_CONFLICT,
                    message=f"No inventory record for sku={line.sku} - cannot reserve for order {order.order_number}",
                    object_id=order.id, remediation_options=["create_inventory_record"],
                )
                line_results.append({"sku": line.sku, "requested": line.quantity, "reserved": 0, "shortfall": line.quantity})
                any_shortfall = True
                continue
            available = inv.available if inv.available is not None else inv.quantity
            reserve_qty = min(available, line.quantity)
            shortfall = line.quantity - reserve_qty
            inv.available = max(available - reserve_qty, 0)
            inv.reserved += reserve_qty
            self.store.put(inv)
            line_results.append({"sku": line.sku, "requested": line.quantity, "reserved": reserve_qty, "shortfall": shortfall})
            if shortfall > 0:
                any_shortfall = True
                self.exceptions.create(
                    merchant_id=merchant_id, category=ExceptionCategory.INVENTORY_CONFLICT,
                    message=f"Insufficient inventory for sku={line.sku} on order {order.order_number}: requested {line.quantity}, reserved {reserve_qty}",
                    object_id=order.id, remediation_options=["expedite_replenishment", "cancel_line", "backorder"],
                )
        self._record_internal_command(merchant_id, "reserve_inventory", "Order", order.id, {"lines": line_results}, idempotency_key)
        self.audit.record(
            merchant_id=merchant_id, actor="post_order", source="inventory_reservation", action="order_inventory_reserved",
            object_type="Order", object_id=order.id, result="shortfall" if any_shortfall else "reserved",
        )
        return {"reserved": not any_shortfall, "already_done": False, "lines": line_results}

    def observe_inventory(self, merchant_id: str, sku: str, canonical_qty: int, external_qty: int, location: str = "default") -> str:
        status = "observed"
        if external_qty < 0:
            status = "divergent"
        elif canonical_qty != external_qty:
            status = "divergent"
        inventory_key = (merchant_id, sku, location)
        inventory = self._inventory_cache.get(inventory_key)
        if inventory is None:
            existing_inventory = [
                item
                for item in self.store.list(Inventory, merchant_id)
                if item.sku == sku and item.location_ref == location
            ]
            inventory = existing_inventory[-1] if existing_inventory else Inventory(merchant_id=merchant_id, sku=sku, location_ref=location, quantity=external_qty)
        inventory.quantity = external_qty
        inventory.available = external_qty
        inventory.status = status
        self.store.put(inventory)
        self._inventory_cache[inventory_key] = inventory
        # Channel identity derived from the injected connector, not hardcoded - a real multi-platform
        # bug found while wiring the WooCommerce platform-independence test (2026-09): this literal
        # used to say "shopify" regardless of which connector was actually configured.
        self.store.put(InventoryObservation(merchant_id=merchant_id, sku=sku, observed_quantity=external_qty, source=self.storefront(merchant_id).name, status=status))
        if status == "divergent":
            exc = self.exceptions.create(
                merchant_id=merchant_id,
                category=ExceptionCategory.INVENTORY_CONFLICT,
                message=f"Inventory divergence sku={sku} canonical={canonical_qty} external={external_qty}",
                object_id=inventory.id,
                remediation_options=["refresh_inventory", "manual_stock_check"],
            )
            self._append_reconciliation(merchant_id, "inventory", sku, canonical_qty, external_qty, "divergent", exc.id)
            return "exception"
        self._append_reconciliation(merchant_id, "inventory", sku, canonical_qty, external_qty, "matched", None)
        return "matched"

    def monitor_fulfilment(self, merchant_id: str, order: Order, status: str, age_hours: int) -> str:
        canonical = self._canonical_fulfilment_status(status)
        self.store.put(FulfilmentObservation(merchant_id=merchant_id, order_id=order.id, source=self.storefront(merchant_id).name, status=canonical))
        thresholds = self.store.get_config(merchant_id).get("sla_thresholds", {})
        limit = int(thresholds.get("order_unfulfilled_hours", 24))
        if canonical in {"pending", "ready"} and age_hours > limit:
            self.exceptions.create(
                merchant_id=merchant_id,
                category=ExceptionCategory.FULFILMENT_DELAY,
                message=f"Order {order.order_number} fulfilment delayed {age_hours}h",
                object_id=order.id,
                remediation_options=["refresh_fulfilment", "contact_fulfilment_partner"],
            )
            return "exception"
        return "straight_through"

    def create_or_observe_shipment(self, merchant_id: str, order: Order, simulate: str | None = None) -> tuple[str, str | None]:
        shipment_key = (merchant_id, order.id)
        cached_shipment = self._shipment_by_order.get(shipment_key)
        if cached_shipment:
            return "existing", self.logistics.shipments_by_order.get(order.id)
        if order.id in self.logistics.shipments_by_order:
            existing_shipments = [shipment for shipment in self.store.list(Shipment, merchant_id) if shipment.order_id == order.id]
            if existing_shipments:
                self._shipment_by_order[shipment_key] = existing_shipments[-1]
            return "existing", self.logistics.shipments_by_order.get(order.id)
        command = ConnectorCommand(
            merchant_id=merchant_id,
            connector=self.logistics.name,
            action="create_shipment",
            object_type="Order",
            object_id=order.id,
            payload={"order_id": order.id} | ({"simulate": simulate} if simulate else {}),
            idempotency_key=f"shipment:{order.id}",
            policy_decision="ALLOW",
            status="approved",
        )
        self.store.put(command)
        try:
            result = self.logistics.execute_mutation(
                MutationRequest(
                    merchant_id=merchant_id,
                    action="create_shipment",
                    object_type="Order",
                    payload=command.payload,
                    idempotency_key=command.idempotency_key,
                )
            )
        except TimeoutError:
            existing = self.logistics.shipments_by_order.get(order.id)
            if existing:
                command.status = "succeeded"
                command.external_ref = existing
                self.store.put(command)
                return "auto_remediated_uncertain", existing
            command.status = "uncertain"
            self.store.put(command)
            self.exceptions.create(merchant_id=merchant_id, category=ExceptionCategory.EXTERNAL_MUTATION_UNCERTAIN, message="Shipment mutation uncertain", object_id=order.id)
            return "uncertain", None
        except RuntimeError as exc:
            command.status = "failed"
            self.store.put(command)
            category = ExceptionCategory.CONNECTOR_RATE_LIMITED if "429" in str(exc) else ExceptionCategory.CONNECTOR_5XX
            self.exceptions.create(merchant_id=merchant_id, category=category, message=str(exc), object_id=order.id)
            return "failed", None
        command.status = "succeeded"
        command.external_ref = result.external_ref
        command.result = result.model_dump(mode="json")
        self.store.put(command)
        external = result.payload
        shipment = Shipment(
            merchant_id=merchant_id,
            order_id=order.id,
            carrier=external["carrier"],
            tracking_number=external["tracking_number"],
            status=external["status"],
        )
        self.store.put(shipment)
        self._shipment_by_order[shipment_key] = shipment
        self.store.put_external_mapping(
            ExternalIdMapping(
                merchant_id=merchant_id,
                sanocea_entity_type="Shipment",
                sanocea_id=shipment.id,
                external_system=self.logistics.name,
                external_entity_type="shipment",
                external_id=str(result.external_ref),
            )
        )
        return "created", result.external_ref

    def ingest_tracking(self, merchant_id: str, shipment_ref: str) -> str:
        external = self.logistics.fetch(merchant_id, "tracking", shipment_ref)
        mapping = self.store.get_external_mapping(merchant_id, self.logistics.name, "shipment", shipment_ref)
        if not mapping:
            self.exceptions.create(merchant_id=merchant_id, category="unknown_tracking_reference", message=f"Unknown tracking ref {shipment_ref}", object_id=None)
            return "exception"
        shipment = self.store.get(Shipment, merchant_id, mapping.sanocea_id)
        sequence_key = (merchant_id, shipment.id)
        latest_sequence = self._tracking_sequence.get(sequence_key, 0)
        result = "observed"
        for event in external.get("events", []):
            sequence = int(event.get("sequence", 0))
            if sequence < latest_sequence:
                self.audit.record(merchant_id=merchant_id, actor="logistics", source=self.logistics.name, action="stale_tracking_event_ignored", object_type="Shipment", object_id=shipment.id, result="ignored")
                continue
            tracking = TrackingEvent(
                merchant_id=merchant_id,
                shipment_id=shipment.id,
                carrier_code=external["carrier"],
                description=event["description"],
                occurred_at=datetime.fromisoformat(event["occurred_at"]),
                status=event["status"],
                external_sequence=sequence,
            )
            try:
                self.store.put(tracking)
            except Exception:
                continue
            latest_sequence = max(latest_sequence, sequence)
            shipment.status = event["status"]
            self.store.put(shipment)
            self._tracking_sequence[sequence_key] = latest_sequence
            self.store.put(ShipmentObservation(merchant_id=merchant_id, order_id=shipment.order_id, source=self.logistics.name, status=shipment.status, tracking_number=shipment.tracking_number, last_tracking_at=tracking.occurred_at))
            if event["status"] == "NDR":
                self.exceptions.create(merchant_id=merchant_id, category=ExceptionCategory.NDR_DETECTED, message=f"NDR detected for {shipment.tracking_number}", object_id=shipment.id, remediation_options=["reattempt_delivery", "contact_customer"])
                result = "ndr"
            elif event["status"].startswith("RTO"):
                self.exceptions.create(merchant_id=merchant_id, category="rto_detected", message=f"RTO state {event['status']} for {shipment.tracking_number}", object_id=shipment.id, remediation_options=["inventory_reconcile", "refund_review"])
                result = "rto"
            elif event["status"] in {"DELIVERY_FAILED", "EXCEPTION"}:
                self.exceptions.create(merchant_id=merchant_id, category=ExceptionCategory.SHIPMENT_DELAY, message=f"Delivery exception {event['status']}", object_id=shipment.id)
                result = "exception"
        return result

    def request_ndr_reattempt(self, merchant_id: str, shipment_ref: str) -> str:
        result = self._execute_logistics_command(
            merchant_id=merchant_id,
            action="request_ndr_action",
            object_type="Shipment",
            object_id=shipment_ref,
            payload={"shipment_ref": shipment_ref, "ndr_action": "REATTEMPT"},
            idempotency_key=f"ndr-reattempt:{shipment_ref}",
        )
        return "accepted" if result and result.status == "accepted" else "uncertain"

    def evaluate_cancellation(self, merchant_id: str, order: Order) -> Cancellation:
        existing = self._existing_for_order(Cancellation, merchant_id, order.id)
        if existing:
            return existing
        config = self.store.get_config(merchant_id)
        mode = config.get("cancellations", {}).get("before_fulfilment", "REQUIRE_APPROVAL")
        status = "eligible"
        approval_id = None
        if order.fulfillment_status:
            status = "denied"
        elif mode == "REQUIRE_APPROVAL":
            approval = Approval(merchant_id=merchant_id, action="cancel_order", object_id=order.id, requested_by="policy")
            self.store.put(approval)
            approval_id = approval.id
            status = "approval_required"
        cancellation = Cancellation(merchant_id=merchant_id, order_id=order.id, status=status, reason="customer_request", approval_id=approval_id)
        self.store.put(cancellation)
        return cancellation

    def execute_cancellation(self, merchant_id: str, cancellation_id: str, simulate: str | None = None) -> Cancellation:
        cancellation = self.store.get(Cancellation, merchant_id, cancellation_id)
        if cancellation.status in {"completed", "external_confirmed"}:
            return cancellation
        if cancellation.status not in {"eligible", "approved"}:
            return cancellation
        order = self.store.get(Order, merchant_id, cancellation.order_id)
        shipment_ref = self.logistics.shipments_by_order.get(order.id)
        if shipment_ref:
            result = self._execute_logistics_command(
                merchant_id=merchant_id,
                action="cancel_shipment",
                object_type="Cancellation",
                object_id=cancellation.id,
                payload={"shipment_ref": shipment_ref} | ({"simulate": simulate} if simulate else {}),
                idempotency_key=f"cancel:{order.id}",
            )
            if result is None:
                cancellation.status = "mutation_uncertain"
                self.store.put(cancellation)
                return cancellation
        cancellation.status = "completed"
        order.status = "CANCELLED"
        self.store.put(order)
        self.store.put(cancellation)
        self.audit.record(merchant_id=merchant_id, actor="cancellation", source="post_order", action="cancellation_completed", object_type="Cancellation", object_id=cancellation.id, result="completed")
        return cancellation

    def evaluate_return(self, merchant_id: str, order: Order, reason: str) -> Return:
        existing = self._existing_for_order(Return, merchant_id, order.id)
        if existing:
            return existing
        config = self.store.get_config(merchant_id)
        return_days = int(config.get("returns", {}).get("window_days", 7))
        placed = order.placed_at or order.sync.observed_at
        eligible = placed > datetime.now(timezone.utc) - timedelta(days=return_days)
        status = "eligible" if eligible else "rejected"
        approval_id = None
        return_policy = config.get("returns", {})
        if eligible and return_policy.get("mode", "REQUIRE_APPROVAL") == "REQUIRE_APPROVAL" and not return_policy.get("auto_authorize", False):
            approval = Approval(merchant_id=merchant_id, action="create_return", object_id=order.id, requested_by="policy")
            self.store.put(approval)
            approval_id = approval.id
            status = "approval_required"
        if eligible and return_policy.get("auto_authorize", False) and not approval_id:
            status = "authorized"
        record = Return(merchant_id=merchant_id, order_id=order.id, status=status, reason=reason, eligibility="eligible" if eligible else "outside_window", approval_id=approval_id)
        self.store.put(record)
        return record

    def progress_return(self, merchant_id: str, return_id: str, event: str) -> Return:
        record = self.store.get(Return, merchant_id, return_id)
        if event == "pickup_requested":
            result = self._execute_logistics_command(
                merchant_id=merchant_id,
                action="request_return_pickup",
                object_type="Return",
                object_id=record.id,
                payload={"return_id": record.id, "order_id": record.order_id},
                idempotency_key=f"return-pickup:{record.id}",
            )
            if result is None:
                record.status = "mutation_uncertain"
                self.store.put(record)
                return record
        transitions = {
            "authorize": "authorized",
            "pickup_requested": "pickup_requested",
            "picked_up": "in_transit",
            "received": "received",
            "inspection_passed": "accepted",
            "inspection_failed": "rejected",
            "closed": "completed",
        }
        record.status = transitions.get(event, record.status)
        self.store.put(record)
        self.audit.record(merchant_id=merchant_id, actor="returns", source="post_order", action=f"return_{event}", object_type="Return", object_id=record.id, result=record.status)
        return record

    def evaluate_exchange(self, merchant_id: str, order: Order, requested_variant_sku: str, simulate: str | None = None) -> Exchange:
        existing = self._existing_for_order(Exchange, merchant_id, order.id)
        if existing:
            return existing
        inventory = [item for item in self.store.list(Inventory, merchant_id) if item.sku == requested_variant_sku and (item.available or item.quantity) > 0]
        status = "eligible" if inventory else "escalated"
        if inventory:
            config = self.store.get_config(merchant_id)
            if config.get("exchanges", {}).get("auto_reserve", True):
                selected = inventory[0]
                selected.available = max((selected.available or selected.quantity) - 1, 0)
                selected.reserved += 1
                selected.status = "reserved_for_exchange"
                self.store.put(selected)
                self._record_internal_command(
                    merchant_id=merchant_id,
                    action="reserve_exchange_inventory",
                    object_type="Exchange",
                    object_id=order.id,
                    payload={"sku": requested_variant_sku, "simulate": simulate} if simulate else {"sku": requested_variant_sku},
                    idempotency_key=f"exchange-reserve:{order.id}:{requested_variant_sku}",
                    external_ref=selected.id,
                )
                status = "reserved"
        exchange = Exchange(merchant_id=merchant_id, order_id=order.id, requested_variant_sku=requested_variant_sku, status=status)
        self.store.put(exchange)
        if not inventory:
            self.exceptions.create(merchant_id=merchant_id, category=ExceptionCategory.INVENTORY_CONFLICT, message=f"Exchange SKU unavailable: {requested_variant_sku}", object_id=order.id)
        return exchange

    def complete_exchange(self, merchant_id: str, exchange_id: str) -> Exchange:
        exchange = self.store.get(Exchange, merchant_id, exchange_id)
        if exchange.status in {"eligible", "reserved"}:
            exchange.status = "completed"
        self.store.put(exchange)
        self.audit.record(merchant_id=merchant_id, actor="exchange", source="post_order", action="exchange_completed", object_type="Exchange", object_id=exchange.id, result=exchange.status)
        return exchange

    def evaluate_refund(self, merchant_id: str, order: Order, amount: int) -> Refund:
        existing = [
            refund
            for refund in self.store.list(Refund, merchant_id)
            if refund.order_id == order.id and refund.amount == min(amount, order.total_amount)
        ]
        if existing:
            return existing[-1]
        config = self.store.get_config(merchant_id)
        decision = self._refund_decision(config, order, amount)
        status = "permitted" if decision == Decision.ALLOW else "approval_required"
        approval_id = None
        if decision == Decision.REQUIRE_APPROVAL:
            approval = Approval(merchant_id=merchant_id, action="refund", object_id=order.id, requested_by="policy")
            self.store.put(approval)
            approval_id = approval.id
        refund = Refund(merchant_id=merchant_id, order_id=order.id, amount=min(amount, order.total_amount), currency=order.currency, status=status, approval_id=approval_id)
        self.store.put(refund)
        return refund

    def approve_refund(self, merchant_id: str, refund_id: str, approver_id: str) -> Refund:
        """Phase 4.5: approval identity is a real authenticated principal id (an api_keys.id, resolved
        by packages/authn), never free-text 'human'. Mirrors ProcurementService.approve_purchase_order
        for consistency across engines."""
        refund = self.store.get(Refund, merchant_id, refund_id)
        if refund.status != "approval_required":
            return refund
        refund.status = "approved"
        self.store.put(refund)
        if refund.approval_id:
            approval = self.store.get(Approval, merchant_id, refund.approval_id)
            if approval.status == "pending":
                approval.status = "approved"
                approval.decided_by = approver_id
                approval.decided_at = now_utc()
                self.store.put(approval)
        self.audit.record(merchant_id=merchant_id, actor=approver_id, source="post_order", action="refund_approved", object_type="Refund", object_id=refund.id, result="approved")
        return refund

    def execute_refund(self, merchant_id: str, refund_id: str, reason: str = "customer_refund", simulate: str | None = None) -> Refund:
        if self.payments is None:
            raise RuntimeError("payment connector required for refund execution")
        refund = self.store.get(Refund, merchant_id, refund_id)
        order = self.store.get(Order, merchant_id, refund.order_id)
        if refund.status not in {"permitted", "auto_approved", "approved", "reconciled", "completed"}:
            return refund
        if refund.status in {"reconciled", "completed"}:
            return refund
        command = ConnectorCommand(
            merchant_id=merchant_id,
            connector=self.payments.name,
            action="create_refund",
            object_type="Refund",
            object_id=refund.id,
            payload={"order_id": order.id, "amount": refund.amount, "currency": refund.currency, "reason": reason} | ({"simulate": simulate} if simulate else {}),
            idempotency_key=f"refund:{order.id}:{refund.amount}:{refund.currency}:{reason}",
            policy_decision="ALLOW",
            status="approved",
        )
        self.store.put(command)
        refund.status = "mutation_submitted"
        self.store.put(refund)
        try:
            result = self.payments.execute_mutation(MutationRequest(merchant_id=merchant_id, action="create_refund", object_type="Refund", payload=command.payload, idempotency_key=command.idempotency_key))
        except TimeoutError:
            external = self.payments.find_refund(merchant_id, order.id, refund.amount, refund.currency, reason)
            if external:
                command.status = "succeeded"
                command.external_ref = external["external_ref"]
                self.store.put(command)
                refund.status = "external_confirmed"
                self.store.put(refund)
                self._register_refund_reference(merchant_id, refund.id, str(external["external_ref"]))
                return self.reconcile_refund(merchant_id, refund.id, external["external_ref"])
            command.status = "uncertain"
            refund.status = "mutation_uncertain"
            self.store.put(command)
            self.store.put(refund)
            self.exceptions.create(merchant_id=merchant_id, category=ExceptionCategory.EXTERNAL_MUTATION_UNCERTAIN, message="Refund mutation uncertain", object_id=refund.id)
            return refund
        except RuntimeError as exc:
            command.status = "failed"
            self.store.put(command)
            category = ExceptionCategory.CONNECTOR_RATE_LIMITED if "429" in str(exc) else ExceptionCategory.CONNECTOR_5XX
            self.exceptions.create(merchant_id=merchant_id, category=category, message=str(exc), object_id=refund.id)
            return refund
        command.status = "succeeded"
        command.external_ref = result.external_ref
        command.result = result.model_dump(mode="json")
        self.store.put(command)
        refund.status = "external_confirmed"
        self.store.put(refund)
        self._register_refund_reference(merchant_id, refund.id, str(result.external_ref))
        return self.reconcile_refund(merchant_id, refund.id, str(result.external_ref))

    def _register_refund_reference(self, merchant_id: str, refund_id: str, external_ref: str) -> None:
        """Phase 4.6: the moment a real gateway integration would hand back ITS OWN reference for this
        refund - recorded in external_id_mappings so Phase 3's settlement-entry reconciliation can
        resolve a refund settlement entry through a real external-identifier lookup instead of trusting
        Sanocea's internal refund_id directly off an incoming settlement payload (mirrors observe_payment
        registering the equivalent Order mapping in Phase 3.1)."""
        self.store.put_external_mapping(
            ExternalIdMapping(
                merchant_id=merchant_id,
                sanocea_entity_type="Refund",
                sanocea_id=refund_id,
                external_system=self.payments.name,
                external_entity_type="refund",
                external_id=external_ref,
            )
        )

    def reconcile_refund(self, merchant_id: str, refund_id: str, external_ref: str) -> Refund:
        refund = self.store.get(Refund, merchant_id, refund_id)
        external = self.payments.fetch(merchant_id, "refund", external_ref)
        mismatches = []
        if int(external["amount"]) != refund.amount:
            mismatches.append("amount")
        if external["currency"] != refund.currency:
            mismatches.append("currency")
        if external["status"] != "succeeded":
            mismatches.append("status")
        if mismatches:
            exc = self.exceptions.create(merchant_id=merchant_id, category="refund_reconciliation_mismatch", message=f"Refund mismatch: {', '.join(mismatches)}", object_id=refund.id)
            self._append_reconciliation(merchant_id, "refund", refund.id, refund.model_dump(mode="json"), external, "divergent", exc.id)
            return refund
        refund.status = "reconciled"
        self.store.put(refund)
        self._append_reconciliation(merchant_id, "refund", refund.id, refund.model_dump(mode="json"), external, "matched", None)
        refund.status = "completed"
        self.store.put(refund)
        return refund

    def _append_reconciliation(self, merchant_id: str, scope: str, key: str, canonical: Any, external: Any, result: str, exception_id: str | None) -> None:
        if hasattr(self.store, "append_reconciliation_result"):
            self.store.append_reconciliation_result(
                ReconciliationResult(
                    merchant_id=merchant_id,
                    scope={"scope": scope, "key": key},
                    canonical_ref={"value": canonical},
                    external_ref={"value": external},
                    result=result,
                    exception_id=exception_id,
                )
            )

    def _execute_logistics_command(
        self,
        merchant_id: str,
        action: str,
        object_type: str,
        object_id: str | None,
        payload: dict[str, Any],
        idempotency_key: str,
    ):
        existing = [
            command
            for command in self.store.list(ConnectorCommand, merchant_id)
            if command.idempotency_key == idempotency_key and command.action == action and command.status == "succeeded"
        ]
        if existing:
            external_ref = existing[-1].external_ref
            payload = self.logistics.fetch(merchant_id, "shipment", external_ref) if external_ref and external_ref.startswith("simship-") else {"external_ref": external_ref}
            from sanocea.packages.connector_sdk import MutationResult

            return MutationResult(status="accepted", external_ref=external_ref, payload=payload)
        command = ConnectorCommand(
            merchant_id=merchant_id,
            connector=self.logistics.name,
            action=action,
            object_type=object_type,
            object_id=object_id,
            payload=payload,
            idempotency_key=idempotency_key,
            policy_decision="ALLOW",
            status="approved",
        )
        self.store.put(command)
        try:
            result = self.logistics.execute_mutation(
                MutationRequest(
                    merchant_id=merchant_id,
                    action=action,
                    object_type=object_type,
                    payload=payload,
                    idempotency_key=idempotency_key,
                )
            )
        except TimeoutError:
            command.status = "uncertain"
            self.store.put(command)
            self.exceptions.create(merchant_id=merchant_id, category=ExceptionCategory.EXTERNAL_MUTATION_UNCERTAIN, message=f"{action} mutation uncertain", object_id=object_id)
            return None
        except RuntimeError as exc:
            command.status = "failed"
            self.store.put(command)
            category = ExceptionCategory.CONNECTOR_RATE_LIMITED if "429" in str(exc) else ExceptionCategory.CONNECTOR_5XX
            self.exceptions.create(merchant_id=merchant_id, category=category, message=str(exc), object_id=object_id)
            return None
        command.status = "succeeded"
        command.external_ref = str(result.external_ref) if result.external_ref else None
        command.result = result.model_dump(mode="json")
        self.store.put(command)
        return result

    def _record_internal_command(self, merchant_id: str, action: str, object_type: str, object_id: str | None, payload: dict[str, Any], idempotency_key: str, external_ref: str | None = None) -> None:
        existing = [command for command in self.store.list(ConnectorCommand, merchant_id) if command.idempotency_key == idempotency_key and command.action == action]
        if existing:
            return
        self.store.put(
            ConnectorCommand(
                merchant_id=merchant_id,
                connector="sanocea_internal",
                action=action,
                object_type=object_type,
                object_id=object_id,
                payload=payload,
                idempotency_key=idempotency_key,
                policy_decision="ALLOW",
                status="succeeded",
                external_ref=external_ref,
            )
        )

    def _canonical_fulfilment_status(self, status: str | None) -> str:
        mapping = {
            None: "pending",
            "unfulfilled": "pending",
            "ready": "ready",
            "processing": "processing",
            "fulfilled": "fulfilled",
            "partial": "partially_fulfilled",
            "cancelled": "cancelled",
            "failed": "failed",
        }
        return mapping.get(status, "unknown")

    def _refund_decision(self, config: dict[str, Any], order: Order, amount: int) -> Decision:
        refund_policy = config.get("refunds") or config.get("policy", {}).get("refund", {})
        if order.payment_status != "paid":
            return Decision.DENY
        if amount <= 0 or amount > order.total_amount:
            return Decision.DENY
        permitted_states = refund_policy.get("permitted_order_states")
        if permitted_states and order.status not in permitted_states:
            return Decision.DENY
        automatic_limit = int(refund_policy.get("automatic_limit", 0))
        if amount <= automatic_limit:
            return Decision.ALLOW
        above = refund_policy.get("above_limit", "REQUIRE_APPROVAL")
        return Decision(above if above in Decision._value2member_map_ else "REQUIRE_APPROVAL")

    def _existing_for_order(self, model, merchant_id: str, order_id: str):
        matches = [item for item in self.store.list(model, merchant_id) if item.order_id == order_id]
        return matches[-1] if matches else None
