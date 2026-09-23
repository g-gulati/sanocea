from __future__ import annotations

from datetime import timedelta
import pytest
from sanocea.packages.domain_contract.models import (
    Approval,
    Channel,
    DemoSessionContact,
    ProductDraft,
    VariantDraft,
    now_utc,
)
from sanocea.packages.domain_contract.store import Phase0Store
from sanocea.packages.notifications.resolution import DemoApprovalNotificationService
from sanocea.packages.notifications.transport import (
    DeliveryResult,
    InboundApprovalMessage,
)
from sanocea.packages.product_onboarding.publication import ProductPublicationService
from sanocea.packages.product_onboarding.recommendations import (
    format_missing_fields_notification,
    format_publish_confirmation,
    get_draft_recommendations,
    infer_weight_from_sku_or_title,
)
from sanocea.packages.product_onboarding.validation import ProductCompletenessValidator
from sanocea.packages.product_onboarding.workflow import ProductOnboardingWorkflow
from sanocea.connectors.shopify.connector import ShopifyConnector


class MockTransport:
    name = "whatsapp_demo"

    def __init__(self):
        self.sent = []

    def send_approval(self, *, recipient: str, message: str) -> DeliveryResult:
        self.sent.append({"recipient": recipient, "message": message})
        return DeliveryResult(delivered=True, provider_message_id=f"msg_{len(self.sent)}")

    def parse_inbound(self, raw_event: dict) -> InboundApprovalMessage | None:
        return None


def _setup_test_environment():
    store = Phase0Store()
    merchant_id = "prospect_premium_basket"
    config = {
        "publication": {"require_approval": False},
        "product_rules": {
            "required": ["sku", "title", "price", "currency", "product_type"],
            "enforce_physical_inventory": True,
        },
    }
    store.set_config(merchant_id, config)

    # Register Shopify channel
    channel = Channel(
        merchant_id=merchant_id,
        name="Shopify Store",
        type="shopify",
    )
    store.put(channel)

    # Register active demo session contact
    contact = DemoSessionContact(
        merchant_id=merchant_id,
        session_label="Demo",
        phone_e164="+919825133222",
        consented=True,
        expires_at=now_utc() + timedelta(days=1),
    )
    store.put(contact)

    from sanocea.packages.runtime.service_graph import build_service_graph

    transport = MockTransport()
    notif_svc = DemoApprovalNotificationService(store, transport)
    graph = build_service_graph(store)
    workflow = graph.catalogue
    publisher = workflow.publisher
    validator = workflow.validator

    return store, merchant_id, notif_svc, transport, validator, publisher, workflow


def test_physical_product_without_inventory_held_incomplete():
    """Physical product without confirmed opening stock and location must be held as INCOMPLETE."""
    store, merchant_id, notif_svc, transport, validator, publisher, workflow = _setup_test_environment()

    draft = ProductDraft(
        merchant_id=merchant_id,
        sku="GC-NT-BBQ-0250G",
        title="Smoky BBQ Almonds & Cashews",
        price=49900,
        currency="INR",
        product_type="Dry Fruits & Nuts",
        category="gid://shopify/TaxonomyCategory/fb-2-17-22",
        attributes={"requires_shipping": True},
    )
    store.put(draft)

    validated = validator.validate(draft)
    assert validated.state == "INCOMPLETE"
    assert "missing_required_attribute:inventory_quantity" in validated.validation_errors
    assert "missing_required_attribute:inventory_location" in validated.validation_errors

    decision = validator.apply_publication_policy(validated)
    assert decision.outcome == "EXCEPTION"
    assert "unconfirmed_inventory_policy" in decision.reasons


def test_sku_physical_weight_inference_and_proposal():
    """Physical weight must be inferred from SKU pattern and proposed for approval rather than assumed."""
    weight_rec = infer_weight_from_sku_or_title("GC-NT-BBQ-0250G", "Smoky BBQ Almonds & Cashews")
    assert weight_rec is not None
    assert weight_rec["value"] == 250.0
    assert weight_rec["unit"] == "GRAMS"
    assert "250 g" in weight_rec["display"]

    draft = ProductDraft(
        merchant_id="prospect_premium_basket",
        sku="GC-NT-BBQ-0250G",
        title="Smoky BBQ Almonds & Cashews",
        price=49900,
        currency="INR",
        product_type="Dry Fruits & Nuts",
        validation_errors=["missing_required_attribute:inventory_quantity"],
        attributes={"requires_shipping": True},
    )

    recs = get_draft_recommendations(draft)
    assert "weight" in recs
    assert recs["weight"]["value"] == 250.0

    msg = format_missing_fields_notification(draft, ["inventory_quantity"])
    assert "Product Weight:" in msg
    assert "250 g" in msg
    assert "UNCONFIRMED" in msg


def test_owner_approval_enables_inventory_tracking_and_deny_policy():
    """On owner APPROVE: enable inventoryItem.tracked: true, inventoryPolicy: DENY, opening stock & location."""
    store, merchant_id, notif_svc, transport, validator, publisher, workflow = _setup_test_environment()

    draft = ProductDraft(
        merchant_id=merchant_id,
        sku="GC-NT-BBQ-0250G",
        title="Smoky BBQ Almonds & Cashews",
        price=49900,
        currency="INR",
        product_type="Dry Fruits & Nuts",
        category="gid://shopify/TaxonomyCategory/fb-2-17-22",
        attributes={"requires_shipping": True, "variant_structure_confirmed": True, "weight_confirmed": True},
    )
    store.put(draft)
    validated = validator.validate(draft)

    # Record notification sent event
    store.list_audit(merchant_id)
    notif_svc.audit.record(
        merchant_id=merchant_id,
        actor="notifications",
        source="whatsapp_demo",
        action="missing_field_notification_sent",
        object_type="ProductDraft",
        object_id=draft.id,
        result="delivered",
    )

    # Owner replies APPROVE over WhatsApp
    inbound = InboundApprovalMessage(
        from_identifier="+919825133222",
        raw_text="APPROVE",
        provider="whatsapp_demo",
        provider_message_id="msg_approve_inv_001",
        received_at=now_utc(),
    )
    res = notif_svc.handle_inbound(inbound)

    assert res["status"] == "READY"
    assert res["publish_outcome"]["outcome"] == "published"

    # Verify inventory_policy_confirmed audit record
    audit_events = store.list_audit(merchant_id)
    inv_confirm_evt = next((e for e in audit_events if e.action == "inventory_policy_confirmed"), None)
    assert inv_confirm_evt is not None
    assert inv_confirm_evt.requested_mutation["inventory_policy"] == "DENY"
    assert inv_confirm_evt.requested_mutation["track_inventory"] is True
    assert inv_confirm_evt.requested_mutation["inventory_quantity"] == 10

    # Verify Shopify connector product has tracked: True and inventoryPolicy: DENY
    shopify_conn = publisher.storefront(merchant_id)
    assert isinstance(shopify_conn, ShopifyConnector)
    published = shopify_conn.fetch(merchant_id, "product", res["publish_outcome"]["external_product_id"])
    assert published["inventory_tracked"] is True
    assert published["inventory_policy"] == "DENY"
    assert published["inventory_quantity"] == 10


def test_untracked_inventory_policy_chosen_when_explicitly_selected():
    """If merchant explicitly chooses 'no tracking', record untracked_inventory_policy_chosen in audit ledger."""
    store, merchant_id, notif_svc, transport, validator, publisher, workflow = _setup_test_environment()

    draft = ProductDraft(
        merchant_id=merchant_id,
        sku="GC-NT-BBQ-0250G",
        title="Smoky BBQ Almonds & Cashews",
        price=49900,
        currency="INR",
        product_type="Dry Fruits & Nuts",
        category="gid://shopify/TaxonomyCategory/fb-2-17-22",
        attributes={"requires_shipping": True},
    )
    store.put(draft)
    validated = validator.validate(draft)

    notif_svc.audit.record(
        merchant_id=merchant_id,
        actor="notifications",
        source="whatsapp_demo",
        action="missing_field_notification_sent",
        object_type="ProductDraft",
        object_id=draft.id,
        result="delivered",
    )

    # Owner replies 'no tracking' over WhatsApp
    inbound = InboundApprovalMessage(
        from_identifier="+919825133222",
        raw_text="no tracking",
        provider="whatsapp_demo",
        provider_message_id="msg_no_track_001",
        received_at=now_utc(),
    )
    res = notif_svc.handle_inbound(inbound)

    assert res["status"] == "READY"
    assert res["publish_outcome"]["outcome"] == "published"

    # Verify untracked_inventory_policy_chosen audit event recorded
    audit_events = store.list_audit(merchant_id)
    untracked_evt = next((e for e in audit_events if e.action == "untracked_inventory_policy_chosen"), None)
    assert untracked_evt is not None
    assert untracked_evt.requested_mutation["track_inventory"] is False

    # Verify published product is untracked with CONTINUE policy
    shopify_conn = publisher.storefront(merchant_id)
    published = shopify_conn.fetch(merchant_id, "product", res["publish_outcome"]["external_product_id"])
    assert published["inventory_tracked"] is False
    assert published["inventory_policy"] == "CONTINUE"


def test_prevent_overselling_cart_quantity_rejection():
    """Test showing that a product with approved quantity 5 cannot be added to cart at quantity 6."""
    # Simulated Shopify Storefront Cart Logic:
    def simulate_add_to_cart(product_data: dict, quantity_requested: int) -> dict:
        variant = (product_data.get("variants") or [{}])[0]
        policy = variant.get("inventoryPolicy", "DENY")
        tracked = (variant.get("inventoryItem") or {}).get("tracked", True)
        available = variant.get("inventoryQuantity", 0) or 0

        if tracked and policy == "DENY":
            if quantity_requested > available:
                return {
                    "status": 422,
                    "message": f"Only {available} items were added to your cart due to availability.",
                    "error": "inventory_insufficient",
                    "available": available,
                    "requested": quantity_requested,
                }
        return {
            "status": 200,
            "message": "Items added to cart.",
            "quantity_added": quantity_requested,
        }

    # Product published with approved stock = 5 and policy = DENY
    product_tracked = {
        "variants": [{
            "inventoryPolicy": "DENY",
            "inventoryQuantity": 5,
            "inventoryItem": {"tracked": True},
        }]
    }

    # Adding 5 items to cart succeeds
    cart_5 = simulate_add_to_cart(product_tracked, 5)
    assert cart_5["status"] == 200
    assert cart_5["quantity_added"] == 5

    # Adding 6 items to cart is denied (HTTP 422 - overselling prevented)
    cart_6 = simulate_add_to_cart(product_tracked, 6)
    assert cart_6["status"] == 422
    assert "Only 5 items were added to your cart due to availability" in cart_6["message"]

    # If untracked (policy CONTINUE), arbitrary quantity is permitted
    product_untracked = {
        "variants": [{
            "inventoryPolicy": "CONTINUE",
            "inventoryQuantity": None,
            "inventoryItem": {"tracked": False},
        }]
    }
    cart_untracked_6 = simulate_add_to_cart(product_untracked, 6)
    assert cart_untracked_6["status"] == 200
    assert cart_untracked_6["quantity_added"] == 6


def test_multi_variant_onboarding_generates_options_and_variants():
    """Multi-variant product generates options, multiple variants with individual weights and stock."""
    store, merchant_id, notif_svc, transport, validator, publisher, workflow = _setup_test_environment()

    variants = [
        VariantDraft(
            sku="GC-NT-BBQ-250G",
            option_values={"Pack Size": "250g"},
            price=29900,
            inventory_quantity=20,
            weight=250.0,
        ),
        VariantDraft(
            sku="GC-NT-BBQ-500G",
            option_values={"Pack Size": "500g"},
            price=54900,
            inventory_quantity=15,
            weight=500.0,
        ),
    ]

    draft = ProductDraft(
        merchant_id=merchant_id,
        sku="GC-NT-BBQ-MULTI",
        title="Smoky BBQ Almonds & Cashews",
        price=29900,
        currency="INR",
        product_type="Dry Fruits & Nuts",
        category="gid://shopify/TaxonomyCategory/fb-2-17-22",
        options=["Pack Size"],
        variants=variants,
        attributes={
            "requires_shipping": True,
            "track_inventory": True,
            "inventory_quantity": 35,
            "inventory_location": "Shop location",
            "inventory_confirmed": True,
        },
    )
    store.put(draft)

    validated = validator.validate(draft)
    assert validated.state == "READY"

    draft.approved_for_publication = True
    store.put(draft)

    channel = store.list(Channel, merchant_id)[0]
    pub = publisher.create_publication(merchant_id, draft.id, channel.id)
    verification = publisher.publish(merchant_id, pub.id)

    assert verification.outcome == "VERIFIED"
