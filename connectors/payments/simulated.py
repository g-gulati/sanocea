from __future__ import annotations

import hashlib
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


class SimulatedPaymentConnector(GuardedConnector):
    name = "simulated_payments"

    def __init__(self, store) -> None:
        super().__init__(store)
        self.refunds: dict[str, dict[str, Any]] = {}
        self.refunds_by_key: dict[str, str] = {}

    def describe_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            connector=self.name,
            capabilities={
                "create_refund": Capability(name="create_refund", status=CapabilityStatus.SUPPORTED, mode=MutationMode.ASYNC),
                "fetch_refund": Capability(name="fetch_refund", status=CapabilityStatus.SUPPORTED),
                "reconcile_refund": Capability(name="reconcile_refund", status=CapabilityStatus.SUPPORTED),
            },
        )

    def fetch(self, merchant_id: str, entity_type: str, external_id: str) -> dict[str, Any]:
        if entity_type != "refund":
            raise KeyError(entity_type)
        refund = self.refunds[external_id]
        if refund["merchant_id"] != merchant_id:
            raise PermissionError("cross-tenant refund access denied")
        return refund

    def _execute_mutation(self, request: MutationRequest) -> MutationResult:
        simulate = request.payload.get("simulate")
        if simulate == "429":
            raise RuntimeError("payment API 429 rate limited")
        if simulate == "500":
            raise RuntimeError("payment API 500")
        if simulate == "timeout_before_mutation":
            raise TimeoutError("timeout before refund mutation")
        if request.action != "create_refund":
            return super()._execute_mutation(request)
        key = self._business_key(request)
        existing = self.refunds_by_key.get(key)
        if existing:
            return MutationResult(status="accepted", external_ref=existing, payload=self.refunds[existing])
        external_ref = f"simrefund-{hashlib.sha1(key.encode()).hexdigest()[:12]}"
        refund = {
            "merchant_id": request.merchant_id,
            "external_ref": external_ref,
            "order_id": request.payload["order_id"],
            "amount": int(request.payload["amount"]),
            "currency": request.payload["currency"],
            "status": "succeeded",
            "reason": request.payload.get("reason"),
        }
        self.refunds[external_ref] = refund
        self.refunds_by_key[key] = external_ref
        if simulate == "timeout_after_mutation":
            raise TimeoutError("timeout after successful refund mutation")
        return MutationResult(status="accepted", external_ref=external_ref, payload=refund)

    def find_refund(self, merchant_id: str, order_id: str, amount: int, currency: str, reason: str | None = None) -> dict[str, Any] | None:
        key = f"{merchant_id}:{order_id}:{amount}:{currency}:{reason or ''}"
        external = self.refunds_by_key.get(key)
        return self.refunds.get(external) if external else None

    def _business_key(self, request: MutationRequest) -> str:
        return f"{request.merchant_id}:{request.payload['order_id']}:{int(request.payload['amount'])}:{request.payload['currency']}:{request.payload.get('reason') or ''}"
