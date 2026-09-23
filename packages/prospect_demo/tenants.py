"""Prospect-specific demo tenant configuration.

This module holds DATA, not business logic - per-prospect configuration consumed by
`reset_prospect_tenant()` (reset.py) and the scenario seeders (scenarios.py). Adding a new prospect
tenant should require adding an entry here (research + configuration), never a new bespoke module of
business logic - see docs/architecture/PROSPECT_DEMO_TENANT_SYSTEM.md for the full design rationale.

The Reference Merchant (ref_anchal_heritage, packages/reference_merchant/) is NOT represented here and
is never modified by anything in this package - it remains the certification/reference tenant with its
own dedicated adversarial-ingestion lifecycle.

Every `public_products` entry is a real, independently-verified commercial fact obtained from the named
public source, never invented - see docs/architecture/PROSPECT_DEMO_TENANT_SYSTEM.md "Data
classification" for the PUBLIC_VERIFIED / PROSPECT_PROVIDED / SYNTHETIC_DEMO discipline this file follows.
Any field genuinely unknown from the public source is `None`, never guessed.
"""

from __future__ import annotations

from typing import Any

DEMO_DISCLOSURE_TEXT = (
    "Tailored demonstration using public catalogue information and simulated operational events."
)


def _default_policy_profile() -> dict[str, Any]:
    """Shared default operating policy - the same shape/values REF_CONFIG already uses for the
    certified Reference Merchant, reused as-is rather than reinvented per prospect (Phase F: config,
    not new software). A prospect config may override specific keys if research surfaces a genuinely
    different, evidenced policy need."""
    return {
        "publication": {"require_approval": True},
        "policy": {
            "refund": {"automatic_limit": 50000, "above_limit": "REQUIRE_APPROVAL"},
            "returns": {"window_days": 7, "condition_required": True},
            "cancellation": {"auto_permit_before_fulfillment": True, "require_approval_after_allocation": False},
            # Sept 2026, multi-channel live demo #2: a channel's own listed/observed price differing
            # from the approved canonical master by up to 2% is treated as routine (marketplace display
            # rounding, minor timing lag) and SANOCEA may correct it back automatically. Anything larger
            # is a commercial decision - could reflect a deliberate merchant/marketplace promotion - and
            # must reach the owner. See PolicyEngine.decide()'s "channel_price_correction" branch.
            "channel_price_correction": {"automatic_limit_percent": 2.0, "above_limit": "REQUIRE_APPROVAL"},
        },
        "finance": {
            "tolerances": {"default": 0, "payment": 0, "cumulative_settlement": 0},
            "expected_charges": {"fee": -100},
        },
        "inventory": {"safety_stock_default": 10},
        "product_rules": {"required": ["sku", "title", "price", "currency", "product_type"]},
        # Blinkit's real evidenced operating model (docs/architecture/channel-research/
        # quick-commerce-india-direct-access.md) is vendor-PO-to-dark-store: a PO is raised "at SKU
        # level" against a declared supply/case-pack unit. This is the merchant's own default case-pack
        # declaration SANOCEA can use to auto-complete a Blinkit vendor-onboarding submission that
        # arrives without one - a real merchant-registered fact, not a guess.
        "blinkit_vendor_defaults": {"default_case_pack_qty": 12},
    }


PROSPECT_TENANTS: dict[str, dict[str, Any]] = {
    # ================================================================================================
    "prospect_ajanta_soya": {
        "merchant_id": "prospect_ajanta_soya",
        "legal_name": "Ajanta Soya Limited",
        "display_name": "Ajanta Soya (Anchal) — Prospect Demo",
        "demo_type": "prospect_demo",
        "currency": "INR",
        "gstin": None,
        "deterministic_seed": 1001,
        "enabled_scenarios": ["reconciliation"],
        "known_channels": ["own_website", "jiomart", "amazon_in", "flipkart", "blinkit"],
        "public_catalogue_sources": [
            {
                "url": "https://ajantasoya.com/wp-json/wc/store/products?per_page=100",
                "description": "Official WooCommerce Store API product feed",
                "retrieval_date": "2026-09-16",
            },
            {
                "url": "https://www.jiomart.com/product/anchal-refined-sunflower-oil-1-litre-bottle-pack-of-6-mki9yb-72247377",
                "description": "JioMart product listing",
                "retrieval_date": "2026-09-16",
            },
        ],
        "public_products": [
            {
                "brand": "Anchal", "title": "Anchal Refined Sunflower Oil", "category": "Cooking Oil",
                "variant": "1L Bottle", "pack_size": "1L", "price_paise": 19600, "currency": "INR",
                "sku": "NRSO-4", "image_url": None,
                "product_url": "https://ajantasoya.com/product/anchal-refined-sunflower-oil/",
                "channel": "own_website", "source": "https://ajantasoya.com/wp-json/wc/store/products?per_page=100",
                "retrieval_date": "2026-09-16",
            },
            {
                "brand": "Anchal", "title": "Anchal Kachi Ghani Mustard Oil", "category": "Cooking Oil",
                "variant": "1L Bottle", "pack_size": "1L", "price_paise": 23600, "currency": "INR",
                "sku": "PKGMO-3", "image_url": None,
                "product_url": "https://ajantasoya.com/product/anchal-kachi-ghani-mustard-oil/",
                "channel": "own_website", "source": "https://ajantasoya.com/wp-json/wc/store/products?per_page=100",
                "retrieval_date": "2026-09-16",
            },
            {
                "brand": "Anchal", "title": "Anchal Refined Soyabean Oil", "category": "Cooking Oil",
                "variant": "1L Bottle", "pack_size": "1L", "price_paise": 13600, "currency": "INR",
                "sku": "NRSO-2", "image_url": None,
                "product_url": "https://ajantasoya.com/product/anchal-refined-soyabean-oil/",
                "channel": "own_website", "source": "https://ajantasoya.com/wp-json/wc/store/products?per_page=100",
                "retrieval_date": "2026-09-16",
            },
            {
                "brand": "Anchal", "title": "Anchal Refined Sunflower Oil 1 Litre Bottle Pack of 6",
                "category": "Cooking Oil", "variant": "1L x 6", "pack_size": "6L", "price_paise": None,
                "currency": "INR", "sku": None, "image_url": None,
                "product_url": "https://www.jiomart.com/product/anchal-refined-sunflower-oil-1-litre-bottle-pack-of-6-mki9yb-72247377",
                "channel": "jiomart",
                "source": "https://www.jiomart.com/product/anchal-refined-sunflower-oil-1-litre-bottle-pack-of-6-mki9yb-72247377",
                "retrieval_date": "2026-09-16",
            },
        ],
        "prospect_provided_context": {
            "stated_active_channels": ["Amazon", "Flipkart", "JioMart", "Blinkit", "own website"],
            "stated_pain_point": "Reconciliation consumes the majority of their team's time.",
        },
        "policy_profile": _default_policy_profile(),
    },
    # ================================================================================================
    "prospect_healthvitals": {
        "merchant_id": "prospect_healthvitals",
        "legal_name": "Dr J's HealthVitals LLP",
        "display_name": "Dr. J's HealthVitals — Prospect Demo",
        "demo_type": "prospect_demo",
        "currency": "INR",
        "gstin": None,
        "deterministic_seed": 1002,
        "enabled_scenarios": ["order_monitoring"],
        "known_channels": ["own_website", "amazon_in"],
        "public_catalogue_sources": [
            {
                "url": "https://drjshealthvitals.com/products.json",
                "description": "Official Shopify store product feed",
                "retrieval_date": "2026-09-16",
            },
            {
                "url": "https://www.amazon.in/stores/DrJsHealthVitals/page/554F7C1D-E4C0-4C23-804C-F9F5501F5B54",
                "description": "Official Amazon India brand storefront",
                "retrieval_date": "2026-09-16",
            },
        ],
        "public_products": [
            {
                "brand": "Dr. J's HealthVitals", "title": "Gut Brain Support", "category": "Gut health supplement",
                "variant": "30 Day Pack", "pack_size": "30 day", "price_paise": 139900, "currency": "INR",
                "sku": "GBS301", "image_url": None,
                "product_url": "https://drjshealthvitals.com/products/gut-brain-support",
                "channel": "own_website", "source": "https://drjshealthvitals.com/products.json",
                "retrieval_date": "2026-09-16",
            },
            {
                "brand": "Dr. J's HealthVitals", "title": "PCOS Hormone Balance", "category": "Hormone/PCOS supplement",
                "variant": "30 Day Pack", "pack_size": "30 day", "price_paise": 149900, "currency": "INR",
                "sku": None, "image_url": None,
                "product_url": "https://drjshealthvitals.com/products/pcos-hormone-balance",
                "channel": "own_website", "source": "https://drjshealthvitals.com/products.json",
                "retrieval_date": "2026-09-16",
            },
            {
                "brand": "Dr. J's HealthVitals", "title": "Beauty Elixir Collagen — Trial Pack",
                "category": "Beauty/collagen supplement", "variant": "10 Day Pack", "pack_size": "10 day",
                "price_paise": 99900, "currency": "INR", "sku": None, "image_url": None,
                "product_url": "https://drjshealthvitals.com/products/beauty-elixir-collagen-trial-pack",
                "channel": "own_website", "source": "https://drjshealthvitals.com/products.json",
                "retrieval_date": "2026-09-16",
            },
            {
                "brand": "Dr. J's HealthVitals", "title": "Complete Wellness — Trial Packs", "category": "Bundle",
                "variant": "Pack of 1", "pack_size": "1", "price_paise": 225100, "currency": "INR",
                "sku": "CWBTR1", "image_url": None,
                "product_url": "https://drjshealthvitals.com/products/complete-wellness-trial-packs",
                "channel": "own_website", "source": "https://drjshealthvitals.com/products.json",
                "retrieval_date": "2026-09-16",
            },
            {
                "brand": "Dr. J's HealthVitals",
                "title": "PCOS Hormone Balance Powder | 15 Sachets",
                "category": "Hormone/PCOS supplement", "variant": "15 Sachets", "pack_size": "15",
                "price_paise": None, "currency": "INR", "sku": None, "image_url": None,
                "product_url": "https://www.amazon.in/HEALTHVITALS-PCOS-Hormone-Balance-Sachets/dp/B0FNNKP8HL",
                "channel": "amazon_in", "source": "amazon.in listing (ASIN B0FNNKP8HL)",
                "retrieval_date": "2026-09-16",
            },
        ],
        "prospect_provided_context": {
            "stated_channel_split": "Website + Amazon are the bulk of orders, approximately 65/35.",
            "stated_pain_point": (
                "Current work requires someone to process, escalate and follow up. Operation is manual "
                "and important. They do not want someone checking multiple portals constantly."
            ),
        },
        "policy_profile": _default_policy_profile(),
    },
    # ================================================================================================
    "prospect_carzex": {
        "merchant_id": "prospect_carzex",
        "legal_name": "Carzex",
        "display_name": "Carzex — Prospect Demo",
        "demo_type": "prospect_demo",
        "currency": "INR",
        "gstin": None,
        "deterministic_seed": 1003,
        "enabled_scenarios": ["returns_reconciliation"],
        "known_channels": ["own_website", "amazon_in"],
        "public_catalogue_sources": [
            {
                "url": "https://carzex.com",
                "description": "Official website product pages",
                "retrieval_date": "2026-09-16",
            },
        ],
        "public_products": [
            {
                "brand": "Carzex",
                "title": "Multi Color Matrix Interior Ambient Running Atmosphere Light for Dashboard & 4 Doors",
                "category": "Interior Accessories", "variant": "App Controlled, Set of 6", "pack_size": "Set of 6",
                "price_paise": 82500, "currency": "INR", "sku": None, "image_url": None,
                "product_url": "https://carzex.com/product/carzex-multi-color-matrix-interior-ambient-running-atmosphere-light-for-dashboard-4-doors-app-controlled-set-of-6/",
                "channel": "own_website", "source": "carzex.com", "retrieval_date": "2026-09-16",
            },
            {
                "brand": "Carzex", "title": "Car Door Foot Step LED Sill Plate for Honda Accord",
                "category": "Exterior/Interior Accessories", "variant": "Set of 4 Pcs, Blue", "pack_size": "Set of 4",
                "price_paise": 119900, "currency": "INR", "sku": None, "image_url": None,
                "product_url": "https://carzex.com/product/carzex-car-door-foot-step-led-sill-plate-for-honda-accord-set-of-4-pcs-blue/",
                "channel": "own_website", "source": "carzex.com", "retrieval_date": "2026-09-16",
            },
            {
                "brand": "Carzex", "title": "iPH Car M612 H11/H8 Bi-Xenon Fog Light Projector Housing",
                "category": "Car Lightings", "variant": "H11/H8, without bulb", "pack_size": "single",
                "price_paise": 119900, "currency": "INR", "sku": None, "image_url": None,
                "product_url": "https://carzex.com/product/carzex-iph-car-m612-h11-h8-compatible-high-low-beam-12v-3-0-bi-xenon-fog-light-projector-housing-without-bulb/",
                "channel": "own_website", "source": "carzex.com", "retrieval_date": "2026-09-16",
            },
            {
                "brand": "Carzex", "title": "4 Pcs RGB Car Underbody Chassis Light",
                "category": "Exterior Accessories", "variant": "4 pcs", "pack_size": "4",
                "price_paise": 89900, "currency": "INR", "sku": None, "image_url": None,
                "product_url": None, "channel": "own_website", "source": "carzex.com search result",
                "retrieval_date": "2026-09-16",
            },
            {
                "brand": "Carzex", "title": "Waterproof Silver & Black Stripes Car Body Cover",
                "category": "Car Comfort & Safety", "variant": "Model-specific fitment", "pack_size": "1",
                "price_paise": 99900, "currency": "INR", "sku": None, "image_url": None,
                "product_url": None, "channel": "own_website", "source": "carzex.com search result",
                "retrieval_date": "2026-09-16",
            },
        ],
        "prospect_provided_context": {
            "stated_reason_for_demo": "Asked for a demo after outreach concerning Amazon returns/reconciliation.",
        },
        "policy_profile": _default_policy_profile(),
    },
    # ================================================================================================
    "prospect_premium_basket": {
        "merchant_id": "prospect_premium_basket",
        "legal_name": "The Premium Basket India",
        "display_name": "The Premium Basket — Prospect Demo",
        "demo_type": "prospect_demo",
        "currency": "INR",
        "gstin": None,
        "deterministic_seed": 1004,
        "enabled_scenarios": ["catalogue_operations"],
        "known_channels": [
            "own_website", "amazon_in", "amazon_us", "flipkart", "blinkit", "swiggy_instamart",
        ],
        "public_catalogue_sources": [
            {
                "url": "https://www.thepremiumbasket.in/products.json",
                "description": "Official Shopify store product feed",
                "retrieval_date": "2026-09-12",
            },
        ],
        "public_products": [
            {
                "brand": "The Premium Basket", "title": "Pure Roasted Makhana", "category": "Snacks",
                "variant": "Default", "pack_size": "50g", "price_paise": 24900, "currency": "INR",
                "sku": None, "image_url": "https://cdn.shopify.com/s/files/1/0980/4775/4538/files/1_44.png?v=1783488994",
                "product_url": "https://www.thepremiumbasket.in/products/pure-roasted-makhana",
                "channel": "own_website", "source": "https://www.thepremiumbasket.in/products.json",
                "retrieval_date": "2026-09-12",
            },
            {
                "brand": "The Premium Basket", "title": "Buttery Toffee Delight Makhana", "category": "Snacks",
                "variant": "50g x 2", "pack_size": "50g x 2", "price_paise": 20900, "currency": "INR",
                "sku": "GC-MK-BUT-0050G-2P", "image_url": "https://cdn.shopify.com/s/files/1/0980/4775/4538/files/MakhanaFOP-ButterlyToffeeDelight_Website.png?v=1783087564",
                "product_url": "https://www.thepremiumbasket.in/products/buttery-toffee-delight-makhana",
                "channel": "own_website", "source": "https://www.thepremiumbasket.in/products.json",
                "retrieval_date": "2026-09-12",
            },
            {
                "brand": "The Premium Basket", "title": "Black Salt and Cayenne Pepper Makhana", "category": "Snacks",
                "variant": "50g x 2", "pack_size": "50g x 2", "price_paise": 24900, "currency": "INR",
                "sku": "GC-MK-BSC-0050G-2P", "image_url": "https://cdn.shopify.com/s/files/1/0980/4775/4538/files/1_18.png?v=1783077306",
                "product_url": "https://www.thepremiumbasket.in/products/black-salt-and-cayenne-pepper-makhana",
                "channel": "own_website", "source": "https://www.thepremiumbasket.in/products.json",
                "retrieval_date": "2026-09-12",
            },
            {
                "brand": "The Premium Basket", "title": "Stuffed Dates Gift Box - 12 Premium Medjool Dates",
                "category": "Dry Fruits", "variant": "600g", "pack_size": "600g", "price_paise": 179900,
                "currency": "INR", "sku": "GC-DG-MCC-600g_2",
                "image_url": "https://cdn.shopify.com/s/files/1/0980/4775/4538/files/0_7.png?v=1781677353",
                "product_url": "https://www.thepremiumbasket.in/products/stuffed-dates-gift-box-12-premium-medjool-dates",
                "channel": "own_website", "source": "https://www.thepremiumbasket.in/products.json",
                "retrieval_date": "2026-09-12",
            },
            {
                "brand": "The Premium Basket", "title": "Bountiful Salted Three Mixed Nuts", "category": "Dry Fruits",
                "variant": "250g x 2", "pack_size": "250g x 2", "price_paise": 99900, "currency": "INR",
                "sku": "ND-MX-BST-0250-2GP", "image_url": "https://cdn.shopify.com/s/files/1/0980/4775/4538/files/BountifulSaltedThreeFOP.png?v=1780988666",
                "product_url": "https://www.thepremiumbasket.in/products/bountiful-salted-three-mixed-nuts",
                "channel": "own_website", "source": "https://www.thepremiumbasket.in/products.json",
                "retrieval_date": "2026-09-12",
            },
            {
                "brand": "The Premium Basket", "title": "Arabian Mabroom Dates", "category": "Dry Fruits",
                "variant": "Default", "pack_size": "unknown", "price_paise": 89900, "currency": "INR",
                "sku": "ND-DT-AMB-0000G", "image_url": "https://cdn.shopify.com/s/files/1/0980/4775/4538/files/0_c800c5a8-f7e2-44c4-ad3b-d34200b0ef68.png?v=1781266354",
                "product_url": "https://www.thepremiumbasket.in/products/arabian-mabroom-dates",
                "channel": "own_website", "source": "https://www.thepremiumbasket.in/products.json",
                "retrieval_date": "2026-09-12",
            },
        ],
        "prospect_provided_context": {
            "stated_active_channels": [
                "Amazon India", "Amazon US", "Flipkart", "Blinkit", "Swiggy Instamart", "Shopify",
            ],
            "stated_systems": ["Shopify", "Unicommerce", "Razorpay", "Tally Prime", "marketplace/q-commerce panels"],
        },
        "policy_profile": _default_policy_profile(),
    },
}
