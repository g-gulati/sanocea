from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from sanocea.packages.connector_sdk import (
    Capability,
    CapabilityStatus,
    ConnectorCapabilities,
    GuardedConnector,
    MutationMode,
    MutationRequest,
    MutationResult,
)


class SimulatedLogisticsConnector(GuardedConnector):
    name = "simulated_logistics"

    def __init__(self, store) -> None:
        super().__init__(store)
        self.shipments: dict[str, dict[str, Any]] = {}
        self.shipments_by_order: dict[str, str] = {}
        self.ndr_actions_by_key: dict[str, str] = {}
        self.return_pickups_by_key: dict[str, str] = {}
        self.cancelled_shipments_by_key: dict[str, str] = {}
        self.rate_limited = False
        self.fail_next: str | None = None

    def describe_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            connector=self.name,
            capabilities={
                "create_shipment": Capability(name="create_shipment", status=CapabilityStatus.SUPPORTED, mode=MutationMode.ASYNC),
                "fetch_shipment": Capability(name="fetch_shipment", status=CapabilityStatus.SUPPORTED),
                "fetch_tracking": Capability(name="fetch_tracking", status=CapabilityStatus.SUPPORTED),
                "cancel_shipment": Capability(name="cancel_shipment", status=CapabilityStatus.SUPPORTED, mode=MutationMode.ASYNC),
                "request_ndr_action": Capability(name="request_ndr_action", status=CapabilityStatus.SUPPORTED, mode=MutationMode.ASYNC),
                "request_return_pickup": Capability(name="request_return_pickup", status=CapabilityStatus.SUPPORTED, mode=MutationMode.ASYNC),
                "fetch_serviceability": Capability(name="fetch_serviceability", status=CapabilityStatus.SUPPORTED),
                "reconcile_shipment": Capability(name="reconcile_shipment", status=CapabilityStatus.SUPPORTED),
            },
        )

    def fetch(self, merchant_id: str, entity_type: str, external_id: str) -> dict[str, Any]:
        if entity_type in {"shipment", "tracking"}:
            shipment = self.shipments[external_id]
            if shipment["merchant_id"] != merchant_id:
                raise PermissionError("cross-tenant shipment access denied")
            return shipment
        if entity_type == "serviceability":
            return {"postal_code": external_id, "serviceable": not external_id.startswith("000")}
        raise KeyError(entity_type)

    def seed_shipment(self, merchant_id: str, order_id: str, status: str, tracking_number: str | None = None, sequence: int = 1) -> str:
        tracking_number = tracking_number or f"NST{hashlib.sha1(order_id.encode()).hexdigest()[:10].upper()}"
        external_ref = f"simship-{hashlib.sha1((merchant_id + order_id).encode()).hexdigest()[:12]}"
        self.shipments[external_ref] = {
            "merchant_id": merchant_id,
            "order_id": order_id,
            "external_ref": external_ref,
            "tracking_number": tracking_number,
            "carrier": "SanoceaSim Express",
            "status": status,
            "sequence": sequence,
            "events": [
                {
                    "status": status,
                    "description": status.replace("_", " ").title(),
                    "occurred_at": (datetime.now(timezone.utc) - timedelta(hours=max(0, 10 - sequence))).isoformat(),
                    "sequence": sequence,
                }
            ],
        }
        self.shipments_by_order[order_id] = external_ref
        return external_ref

    def push_event(self, external_ref: str, status: str, sequence: int, hours_ago: int = 0, description: str | None = None) -> dict[str, Any]:
        shipment = self.shipments[external_ref]
        event = {
            "status": status,
            "description": description or status.replace("_", " ").title(),
            "occurred_at": (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat(),
            "sequence": sequence,
        }
        shipment["events"].append(event)
        if sequence >= int(shipment.get("sequence", 0)):
            shipment["status"] = status
            shipment["sequence"] = sequence
        return event

    def _execute_mutation(self, request: MutationRequest) -> MutationResult:
        simulate = request.payload.get("simulate")
        if simulate == "429":
            raise RuntimeError("logistics API 429 rate limited")
        if simulate == "500":
            raise RuntimeError("logistics API 500")
        if simulate == "timeout_before_mutation":
            raise TimeoutError("timeout before logistics mutation")
        if request.action == "create_shipment":
            order_id = str(request.payload["order_id"])
            existing = self.shipments_by_order.get(order_id)
            if existing:
                return MutationResult(status="accepted", external_ref=existing, payload=self.shipments[existing])
            external_ref = self.seed_shipment(request.merchant_id, order_id, "CREATED", sequence=1)
            if simulate == "timeout_after_mutation":
                raise TimeoutError("timeout after successful logistics mutation")
            return MutationResult(status="accepted", external_ref=external_ref, payload=self.shipments[external_ref])
        if request.action == "request_ndr_action":
            existing = self.ndr_actions_by_key.get(request.idempotency_key)
            if existing:
                return MutationResult(status="accepted", external_ref=existing, payload=self.shipments[existing])
            external_ref = str(request.payload["shipment_ref"])
            action = str(request.payload.get("ndr_action", "REATTEMPT"))
            self.push_event(external_ref, action, int(self.shipments[external_ref]["sequence"]) + 1)
            self.ndr_actions_by_key[request.idempotency_key] = external_ref
            return MutationResult(status="accepted", external_ref=external_ref, payload=self.shipments[external_ref])
        if request.action == "request_return_pickup":
            existing = self.return_pickups_by_key.get(request.idempotency_key)
            if existing:
                return MutationResult(status="accepted", external_ref=existing, payload={"return_pickup_ref": existing})
            external_ref = f"simreturn-{hashlib.sha1(request.idempotency_key.encode()).hexdigest()[:12]}"
            self.return_pickups_by_key[request.idempotency_key] = external_ref
            if simulate == "timeout_after_mutation":
                raise TimeoutError("timeout after successful return pickup mutation")
            return MutationResult(status="accepted", external_ref=external_ref, payload={"return_pickup_ref": external_ref})
        if request.action == "cancel_shipment":
            existing = self.cancelled_shipments_by_key.get(request.idempotency_key)
            if existing:
                return MutationResult(status="accepted", external_ref=existing, payload=self.shipments[existing])
            external_ref = str(request.payload["shipment_ref"])
            self.push_event(external_ref, "CANCELLED", int(self.shipments[external_ref]["sequence"]) + 1)
            self.cancelled_shipments_by_key[request.idempotency_key] = external_ref
            if simulate == "timeout_after_mutation":
                raise TimeoutError("timeout after successful shipment cancellation")
            return MutationResult(status="accepted", external_ref=external_ref, payload=self.shipments[external_ref])
        return super()._execute_mutation(request)
