from __future__ import annotations

import pytest

from sanocea.connectors.shopify import ShopifyConnector
from sanocea.packages.connector_sdk import MutationRequest
from sanocea.packages.domain_contract import Phase0Store
from sanocea.packages.domain_contract.models import Channel, ProductDraft
from sanocea.packages.product_onboarding import ProductCompletenessValidator, ProductPublicationService
from sanocea.packages.runtime.storefront_registry import StorefrontConnectorRegistry, UnknownStorefrontChannelError


def _setup_registry():
    store = Phase0Store()
    workflow = None
    merchant_id = "mer_singleton_test"
    store.put(Channel(id="chn_shopify_main", merchant_id=merchant_id, type="shopify", name="Shopify Main"))
    
    instantiations = 0

    def shopify_factory(s, w, mid):
        nonlocal instantiations
        instantiations += 1
        return ShopifyConnector(s, w)

    registry = StorefrontConnectorRegistry(store, workflow)
    registry.register("shopify", shopify_factory)
    return store, workflow, merchant_id, registry, lambda: instantiations


def test_all_resolution_paths_return_identical_singleton_instance():
    """Prove resolve(), resolve_for_channel_type(), resolve_for_channel_id(), resolve_expect(),
    and registry() all return the exact same Python object in memory, with factory called exactly ONCE."""
    store, workflow, merchant_id, registry, get_instantiations = _setup_registry()

    c1 = registry.resolve(merchant_id)
    c2 = registry.resolve_for_channel_type(merchant_id, "shopify")
    c3 = registry.resolve_for_channel_id(merchant_id, "chn_shopify_main")
    c4 = registry.resolve_expect(merchant_id, "shopify")
    c5 = registry(merchant_id)

    assert c1 is c2, "resolve() and resolve_for_channel_type() must return the identical instance"
    assert c2 is c3, "resolve_for_channel_type() and resolve_for_channel_id() must return the identical instance"
    assert c3 is c4, "resolve_for_channel_id() and resolve_expect() must return the identical instance"
    assert c4 is c5, "resolve_expect() and __call__() must return the identical instance"
    assert get_instantiations() == 1, "Connector factory must be invoked exactly once across all resolution paths"


def test_reverse_call_order_preserves_singleton_instance():
    """Prove that resolving via channel_id first, then resolve() second, also returns the exact same instance."""
    store, workflow, merchant_id, registry, get_instantiations = _setup_registry()

    c_id = registry.resolve_for_channel_id(merchant_id, "chn_shopify_main")
    c_res = registry.resolve(merchant_id)
    c_type = registry.resolve_for_channel_type(merchant_id, "shopify")

    assert c_id is c_res is c_type
    assert get_instantiations() == 1


def test_adversarial_publication_cannot_diverge_across_resolution_paths():
    """Adversarial proof: ProductPublicationService resolves its connector via
    resolve_for_channel_id(), while an external caller/monitoring check resolves via
    resolve(merchant_id). Prove that state mutations made during publication are
    immediately visible on the connector retrieved via resolve().
    """
    store, workflow, merchant_id, registry, _ = _setup_registry()

    draft = ProductDraft(
        merchant_id=merchant_id,
        sku="SKU-SINGLETON-1",
        title="Authoritative Connector Shirt",
        price=59900,
        currency="INR",
        product_type="apparel",
    )
    store.put(draft)
    validator = ProductCompletenessValidator(store)
    draft = validator.validate(draft)
    draft = validator.approve_publication(draft, "test_operator")

    service = ProductPublicationService(store, registry)
    publication = service.create_publication(merchant_id, draft.id, "chn_shopify_main")
    verification = service.publish(merchant_id, publication.id)
    assert verification.outcome == "VERIFIED"

    # Now inspect the connector via resolve(merchant_id) - the path an operator/test check uses
    observed_connector = registry.resolve(merchant_id)
    ext_id = verification.external_product_id

    # Must be present in observed_connector's external_products dictionary
    assert ext_id in observed_connector.external_products, (
        "Product published via resolve_for_channel_id() must be immediately visible in connector obtained via resolve()"
    )
    assert observed_connector.external_products[ext_id]["title"] == "Authoritative Connector Shirt"

    # A second duplicate publication request must resolve to the identical product and not duplicate
    pub2 = service.create_publication(merchant_id, draft.id, "chn_shopify_main")
    assert pub2.id == publication.id, "create_publication must be idempotent"


def test_multichannel_isolation_preserved_with_singleton_guarantee():
    """When a merchant has multiple channels (e.g. Shopify + WooCommerce), each channel
    resolves to its own authoritative singleton instance without cross-contamination."""
    store = Phase0Store()
    merchant_id = "mer_multi_channel"
    store.put(Channel(id="chn_shopify", merchant_id=merchant_id, type="shopify", name="Shopify"))
    store.put(Channel(id="chn_woocommerce", merchant_id=merchant_id, type="woocommerce", name="WooCommerce"))

    shopify_calls = 0
    woo_calls = 0

    def shopify_factory(s, w, mid):
        nonlocal shopify_calls
        shopify_calls += 1
        return ShopifyConnector(s, w)

    class DummyWooCommerce:
        pass

    def woo_factory(s, w, mid):
        nonlocal woo_calls
        woo_calls += 1
        return DummyWooCommerce()

    registry = StorefrontConnectorRegistry(store, None)
    registry.register("shopify", shopify_factory)
    registry.register("woocommerce", woo_factory)

    # Resolve each channel multiple times through different paths
    s1 = registry.resolve_for_channel_id(merchant_id, "chn_shopify")
    s2 = registry.resolve_for_channel_type(merchant_id, "shopify")
    s3 = registry.resolve(merchant_id)  # primary channel is shopify

    w1 = registry.resolve_for_channel_id(merchant_id, "chn_woocommerce")
    w2 = registry.resolve_for_channel_type(merchant_id, "woocommerce")

    assert s1 is s2 is s3
    assert w1 is w2
    assert s1 is not w1, "Different channel types must resolve to different connectors"
    assert shopify_calls == 1, "Shopify connector factory must be called only once"
    assert woo_calls == 1, "WooCommerce connector factory must be called only once"
