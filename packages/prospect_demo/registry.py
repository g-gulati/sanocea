"""Read-only listing of every demo tenant Manpreet can switch between in the Command Center - the
certified Reference Merchant plus every configured prospect. Display metadata only (id + name); it does
not grant access to anything - actual access is still gated per-merchant by the existing operator API
key mechanism (packages/authn/deps.py::require_operator), unchanged by this module."""

from __future__ import annotations

from typing import Any

from sanocea.packages.reference_merchant.tenant import REF_MERCHANT_DISPLAY_NAME, REF_MERCHANT_ID

from .tenants import PROSPECT_TENANTS


def list_demo_tenants() -> list[dict[str, Any]]:
    tenants = [{"merchant_id": REF_MERCHANT_ID, "display_name": REF_MERCHANT_DISPLAY_NAME, "demo_type": "reference_certification"}]
    for merchant_id, config in PROSPECT_TENANTS.items():
        tenants.append({"merchant_id": merchant_id, "display_name": config["display_name"], "demo_type": config["demo_type"]})
    return tenants
