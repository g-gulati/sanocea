from __future__ import annotations

from typing import Any

REF_MERCHANT_ID = "ref_anchal_heritage"
REF_MERCHANT_LEGAL_NAME = "Anchal Heritage Consumer Goods Pvt Ltd"
REF_MERCHANT_DISPLAY_NAME = "Anchal Heritage Organics (Reference D2C Tenant)"

REF_LOCATIONS: dict[str, dict[str, Any]] = {
    "loc_delhi_hub": {
        "name": "Delhi Central Fulfillment Hub",
        "city": "New Delhi",
        "state": "Delhi",
        "pincode": "110001",
        "is_default": True,
        "priority": 1,
    },
    "loc_mumbai_hub": {
        "name": "Mumbai Bhiwandi Logistics Park",
        "city": "Bhiwandi",
        "state": "Maharashtra",
        "pincode": "421302",
        "is_default": False,
        "priority": 2,
    },
    "loc_bengaluru_hub": {
        "name": "Bengaluru South Distribution Node",
        "city": "Bengaluru",
        "state": "Karnataka",
        "pincode": "560100",
        "is_default": False,
        "priority": 3,
    },
}

REF_CHANNELS: dict[str, dict[str, Any]] = {
    "chn_shopify_live": {
        "name": "Anchal Online Store (Shopify D2C)",
        "platform": "shopify_live",
        "live": True,
        "shop_domain": "sanocea-commerce-os-dev.myshopify.com",
    },
    "chn_flipkart_in": {
        "name": "Flipkart India Marketplace",
        "platform": "flipkart",
        "live": False,
        "simulated": True,
    },
    "chn_amazon_in": {
        "name": "Amazon India Marketplace",
        "platform": "amazon",
        "live": False,
        "simulated": True,
    },
}

REF_CONFIG: dict[str, Any] = {
    "currency": "INR",
    "gstin": "07AAAAA0000A1Z5",
    "shopify_live": {
        "shop_domain": "sanocea-commerce-os-dev.myshopify.com",
        "api_version": "2026-07",
    },
    "product_rules": {
        "required": ["sku", "title", "price", "currency", "product_type"],
    },
    "publication": {
        "require_approval": True,
    },
    "inventory": {
        "default_location_ref": "loc_delhi_hub",
        "allocation_priority": ["loc_delhi_hub", "loc_mumbai_hub", "loc_bengaluru_hub"],
        "safety_stock_default": 10,
    },
    "policy": {
        "refund": {
            "automatic_limit": 50000,  # 50,000 paise = ₹500.00 max auto-refund
            "above_limit": "REQUIRE_APPROVAL",
        },
        "returns": {
            "window_days": 7,
            "condition_required": True,
        },
        "cancellation": {
            "auto_permit_before_fulfillment": True,
            "require_approval_after_allocation": False,
        },
    },
    "finance": {
        "tolerances": {
            "default": 0,
            "payment": 0,
            "cumulative_settlement": 0,
        },
        "expected_charges": {
            "fee": -100,
        },
    },
    "procurement": {
        "spending": {
            "auto_approve_limit": 500000,  # ₹5,000.00
            "above_limit": "REQUIRE_APPROVAL",
        },
        "cost_tolerance": {
            "pct": 0.05,
            "absolute": 500,
            "above_tolerance": "REQUIRE_APPROVAL",
        },
        "replenishment": {
            "default": {
                "safety_stock": 10,
                "target_stock": 100,
            },
        },
    },
}
