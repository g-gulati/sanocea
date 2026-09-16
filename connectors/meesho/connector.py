from __future__ import annotations

from typing import Any

from sanocea.packages.connector_sdk import (
    Capability,
    CapabilityStatus,
    ConnectorCapabilities,
    MarketplaceConnector,
    Page,
    Transport,
)

from .auth import StaticSupplierCredentialsAuth

"""Meesho connector - Step 9Q.4.

IMPORTANT DECISION RULE applied honestly: this is NOT a case of Meesho being unreachable without an
approved OMS/intermediary - direct, per-supplier credential issuance from Meesho itself (email-based,
see auth.py) is evidenced and available to Sanocea. The actual blocker is narrower and different: no
Meesho-owned primary documentation of the REQUEST/RESPONSE SCHEMA for any business operation (listing
create/update, order read, fulfilment, returns, settlement) was reachable during this step's direct
research - only Level 5 vendor-integration summaries describing CAPABILITY EXISTENCE, never field-level
contracts. "No capability may be marked SUPPORTED merely because another integration vendor claims it
exists" is the operative constraint this connector honors throughout: every business capability below is
UNCONFIRMED, not because Meesho lacks these features (multiple independent sources agree it has them),
but because this connector has no confirmed schema to implement them against without fabricating one.

What IS real and implemented: the auth mechanism (static per-supplier-location credentials - see
auth.py for its own, separately-disclosed evidence grade and the one thing about it that remains
genuinely unknown, the `security` header's derivation).

See docs/connectors/meesho-certification.md for the full per-capability breakdown and
docs/connectors/meesho.md for the complete evidence trail, including every source checked and why each
attempt at primary documentation failed.
"""

PRODUCTION_BASE_URL = "https://merchant.meesho.com"
SANDBOX_BASE_URL = "https://merchant.meeshotest.in"


class MeeshoConnector(MarketplaceConnector):
    name = "meesho"

    def __init__(
        self, store, workflow, *, auth: StaticSupplierCredentialsAuth,
        base_url: str = PRODUCTION_BASE_URL, transport: Transport | None = None,
    ) -> None:
        super().__init__(store, workflow, auth=auth, transport=transport)
        self.base_url = base_url

    def describe_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            connector=self.name,
            capabilities={
                "auth": Capability(
                    name="auth", status=CapabilityStatus.SUPPORTED,
                    notes="Static per-supplier-location credentials (client-id/security/timestamp/supplier_identifier headers) - Level 5 evidence (two independent technical integrators agree on specifics), no Meesho-owned primary source reached. See auth.py for the one unresolved detail (security header derivation).",
                ),
                "catalogue_read": Capability(name="catalogue_read", status=CapabilityStatus.UNCONFIRMED, notes="No endpoint path or response schema found in any source reached - only 'catalog sync is available' (Unicommerce), which is a capability claim, not a contract."),
                "catalogue_write": Capability(name="catalogue_write", status=CapabilityStatus.UNCONFIRMED, notes="Same as catalogue_read - existence plausible, schema unconfirmed."),
                "inventory_read": Capability(name="inventory_read", status=CapabilityStatus.UNCONFIRMED),
                "inventory_write": Capability(name="inventory_write", status=CapabilityStatus.UNCONFIRMED, notes="Unicommerce mentions facility-wise inventory sync, no schema."),
                "order_ingest": Capability(name="order_ingest", status=CapabilityStatus.UNCONFIRMED, notes="Multiple sources agree order status sync exists and 'Manual Order Sync would not work' (i.e. it is a real, non-optional API path, not portal-only) - but no order object schema, endpoint path, or pagination contract was found anywhere reached."),
                "order_confirmation": Capability(name="order_confirmation", status=CapabilityStatus.UNCONFIRMED, notes="EasyEcom's own KB describes 'Order Confirmation' as a feature - ambiguous whether this is a real API call or EasyEcom automating the supplier portal on the seller's behalf ('another OMS having access != Sanocea being eligible for that access' applies directly here)."),
                "fulfilment_update": Capability(name="fulfilment_update", status=CapabilityStatus.UNCONFIRMED, notes="Confirmed (multiple sources): Meesho generates shipping labels itself; the seller/integrator only FETCHES the Meesho-generated label, never creates a shipment/tracking number of their own. The exact fetch endpoint/schema is unconfirmed."),
                "cancellation": Capability(name="cancellation", status=CapabilityStatus.UNCONFIRMED, notes="EasyEcom's KB states seller-initiated cancellation is possible ONLY before order confirmation, and becomes fully disabled after API integration is turned on - a real, specific, disclosed operational constraint, but still no confirmed request schema."),
                "return_refund": Capability(name="return_refund", status=CapabilityStatus.UNCONFIRMED, notes="Sources agree returns/RTO sync exists as a status-visibility feed (Unicommerce: order-status-sync only, no seller-initiated return ACTION documented). No evidence of a seller-facing refund-initiation operation at all - Meesho likely owns the financial action outright, consistent with Flipkart Minutes/quick-commerce vendor findings elsewhere in this codebase, but not independently confirmed for Meesho specifically."),
                "settlement_ingest": Capability(name="settlement_ingest", status=CapabilityStatus.UNCONFIRMED, notes="NO EVIDENCE FOUND of any settlement/payment API, report, or downloadable file for Meesho in any source reached this step - the strongest possible negative finding available (absence across every source checked), not merely 'not searched'."),
                "order_notifications": Capability(name="order_notifications", status=CapabilityStatus.UNCONFIRMED, notes="One secondhand mention of 'order status updates via webhook' with zero registration/payload/signature details - insufficient to implement anything against."),
                "fetch": Capability(name="fetch", status=CapabilityStatus.UNCONFIRMED, notes="Gates every read - see the per-entity capabilities above, all UNCONFIRMED."),
                "search": Capability(name="search", status=CapabilityStatus.UNCONFIRMED),
            },
        )

    def fetch(self, merchant_id: str, entity_type: str, external_id: str) -> dict[str, Any]:
        self.describe_capabilities().require("fetch")
        raise KeyError(entity_type)  # unreachable - require("fetch") always refuses first; see above.

    def search(self, merchant_id: str, entity_type: str, filters: dict[str, Any], cursor: str | None = None) -> Page:
        self.describe_capabilities().require("search")
        raise KeyError(entity_type)  # unreachable - same as fetch().

    def connector_health(self) -> dict[str, Any]:
        """Overrides MarketplaceConnector's generic token-expiry-based health report: Meesho's auth is
        STATIC (no token/expiry concept at all - see auth.py), so the generic base implementation would
        always report authenticated=False even though static credentials are configured and ready. This
        is Class A (adapter-local) - the base method's assumption of a refreshable token is real and
        correct for Flipkart/Amazon, just doesn't fit Meesho's static-credential shape, and overriding it
        here does not require changing the generic method itself."""
        return {"connector": self.name, "authenticated": True, "auth_mode": "static_credentials"}
