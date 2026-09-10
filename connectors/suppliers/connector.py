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


class SimulatedSupplierConnector(GuardedConnector):
    """The PO-submission MUTATION layer only - mirrors SimulatedPaymentConnector's role in Phase 3.

    Deliberately narrow: this class exists to prove "submit PO -> supplier creates it -> response lost
    -> Sanocea retries -> one external PO, not two" using the SAME database-enforced idempotency
    primitive (GuardedConnector.execute_mutation -> IdempotencyService.run_once against the
    idempotency_records table, PRIMARY KEY (scope, key)) already proven in Phase 2.1/Phase 3. It is not
    the supply-chain behaviour simulator - see SupplierSimulator in this package for acknowledgement/
    shipment/adversarial event generation, which owns its own independent state.
    """

    name = "simulated_supplier"

    def __init__(self, store) -> None:
        super().__init__(store)
        self.purchase_orders: dict[str, dict[str, Any]] = {}
        self.purchase_orders_by_key: dict[str, str] = {}

    def describe_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            connector=self.name,
            capabilities={
                "create_purchase_order": Capability(name="create_purchase_order", status=CapabilityStatus.SUPPORTED, mode=MutationMode.ASYNC),
                "fetch_purchase_order": Capability(name="fetch_purchase_order", status=CapabilityStatus.SUPPORTED),
            },
        )

    def fetch(self, merchant_id: str, entity_type: str, external_id: str) -> dict[str, Any]:
        if entity_type != "purchase_order":
            raise KeyError(entity_type)
        po = self.purchase_orders[external_id]
        if po["merchant_id"] != merchant_id:
            raise PermissionError("cross-tenant purchase order access denied")
        return po

    def _execute_mutation(self, request: MutationRequest) -> MutationResult:
        simulate = request.payload.get("simulate")
        if simulate == "429":
            raise RuntimeError("supplier API 429 rate limited")
        if simulate == "500":
            raise RuntimeError("supplier API 500")
        if simulate == "timeout_before_mutation":
            raise TimeoutError("timeout before PO mutation")
        if request.action != "create_purchase_order":
            return super()._execute_mutation(request)
        key = self._business_key(request)
        existing = self.purchase_orders_by_key.get(key)
        if existing:
            return MutationResult(status="accepted", external_ref=existing, payload=self.purchase_orders[existing])
        external_ref = f"simpo-{hashlib.sha1(key.encode()).hexdigest()[:12]}"
        po = {
            "merchant_id": request.merchant_id,
            "external_ref": external_ref,
            "supplier_id": request.payload["supplier_id"],
            "lines": request.payload["lines"],
            "currency": request.payload["currency"],
            "status": "received",
        }
        self.purchase_orders[external_ref] = po
        self.purchase_orders_by_key[key] = external_ref
        if simulate == "timeout_after_mutation":
            raise TimeoutError("timeout after successful PO mutation")
        return MutationResult(status="accepted", external_ref=external_ref, payload=po)

    def find_purchase_order(self, merchant_id: str, purchase_order_id: str) -> dict[str, Any] | None:
        key = f"{merchant_id}:{purchase_order_id}"
        external = self.purchase_orders_by_key.get(key)
        return self.purchase_orders.get(external) if external else None

    def _business_key(self, request: MutationRequest) -> str:
        # Keyed on Sanocea's own purchase_order id (already unique per business intent thanks to
        # PurchaseOrder's own idempotency_key uniqueness at creation) - a real gateway would key on
        # whatever merchant-supplied PO reference is echoed back on every retry.
        return f"{request.merchant_id}:{request.payload['purchase_order_id']}"
