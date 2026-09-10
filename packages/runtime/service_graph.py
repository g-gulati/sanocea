from __future__ import annotations

import os
from dataclasses import dataclass

from sanocea.connectors.chatwoot import ChatwootConnector
from sanocea.connectors.logistics.simulated import SimulatedLogisticsConnector
from sanocea.connectors.payments.simulated import SimulatedPaymentConnector
from sanocea.connectors.shopify import ShopifyConnector
from sanocea.connectors.shopify_live import ShopifyLiveConnector
from sanocea.connectors.suppliers import SimulatedSupplierConnector
from sanocea.connectors.woocommerce import WooCommerceConnector
from sanocea.packages.finance import FinanceOperationsService
from sanocea.packages.object_storage import S3ObjectStorage
from sanocea.packages.post_order.operations import PostOrderOperationsService
from sanocea.packages.procurement import ProcurementService
from sanocea.packages.product_onboarding import ProductOnboardingWorkflow
from sanocea.packages.runtime.commands import Services
from sanocea.packages.runtime.storefront_registry import ConnectorFactory, StorefrontConnectorRegistry
from sanocea.packages.support.workflow import SupportWorkflowService
from sanocea.workers.workflow import FakeTemporalEngine, OrderOrchestrator, SupportOrchestrator

"""Phase 4.5/4.6: the full connector/service/orchestrator graph, factored out of apps/api/app.py so it
can be built identically by both the FastAPI app and any out-of-process runner. Multi-platform
connector hardening: this is now the ONE place storefront connectors are chosen per merchant - built
around a StorefrontConnectorRegistry (merchant + channel -> connector), not a single global connector.
"shopify", "woocommerce", and "shopify_live" are registered by default. "shopify" is the in-memory
fault-injection simulator (its own zero-tolerance suite); "woocommerce" and "shopify_live" both do real
HTTP against a real platform (WooCommerce: a real local wp-env instance; shopify_live: a real Shopify
development store, once credentials exist - see
docs/architecture/shopify-dev-store-certification-preparation.md). All three are lazy per-merchant - a
factory is only invoked, and its config/credentials only required, for a merchant actually onboarded
onto that channel type. `extra_storefront_factories` registers any further platform without touching
this function's own logic or any domain service - "connector registration/configuration", never
domain-code branching.
"""


@dataclass
class ServiceGraph:
    logistics: SimulatedLogisticsConnector
    payments: SimulatedPaymentConnector
    suppliers: SimulatedSupplierConnector
    engine: FakeTemporalEngine
    post_order: PostOrderOperationsService
    order_orchestrator: OrderOrchestrator
    storefronts: StorefrontConnectorRegistry
    support: SupportWorkflowService
    support_orchestrator: SupportOrchestrator
    chatwoot: ChatwootConnector
    finance: FinanceOperationsService
    procurement: ProcurementService
    catalogue: ProductOnboardingWorkflow
    services: Services


def _build_storage() -> S3ObjectStorage | None:
    if not os.environ.get("SANOCEA_S3_BUCKET"):
        return None
    return S3ObjectStorage(
        endpoint_url=os.environ.get("SANOCEA_S3_ENDPOINT"),
        access_key_id=os.environ["SANOCEA_S3_ACCESS_KEY"],
        secret_access_key=os.environ["SANOCEA_S3_SECRET_KEY"],
        bucket=os.environ["SANOCEA_S3_BUCKET"],
    )


def _shopify_factory(store, workflow, merchant_id: str) -> ShopifyConnector:
    # merchant_id is unused - the simulator's construction needs no per-merchant credentials (unlike
    # WooCommerce). The registry still caches one INSTANCE per merchant_id (never shared across
    # merchants), which is a real, deliberate isolation improvement over the old single-global-instance
    # architecture: two Shopify merchants in one process no longer share one simulator's in-memory state.
    return ShopifyConnector(store, workflow)


def _woocommerce_factory(store, workflow, merchant_id: str) -> WooCommerceConnector:
    config = store.get_config(merchant_id).get("woocommerce", {})
    base_url = config.get("base_url")
    if not base_url:
        raise ValueError(f"merchant {merchant_id} has a woocommerce channel but no config.woocommerce.base_url")
    consumer_key = store.get_credential_ref(merchant_id, "woocommerce_consumer_key")
    consumer_secret = store.get_credential_ref(merchant_id, "woocommerce_consumer_secret")
    return WooCommerceConnector(store, workflow, base_url=base_url, consumer_key=consumer_key, consumer_secret=consumer_secret)


def _shopify_live_factory(store, workflow, merchant_id: str) -> ShopifyLiveConnector:
    # Shopify Dev-Store certification preparation: registered by default (like shopify/woocommerce)
    # under its own distinct channel type "shopify_live" so it can NEVER be accidentally selected for a
    # merchant configured on the "shopify" (simulator) channel - only a merchant explicitly onboarded
    # with a "shopify_live" channel resolves to this connector. Lazy, per-merchant - this factory is
    # never called, and no config/credentials are required, until a merchant actually uses it. See
    # docs/architecture/shopify-dev-store-certification-preparation.md.
    # AUTH HARDENING: no access_token credential exists or is ever accepted here - Shopify's own
    # current mechanism for a headless integration acting on a store in its own organization is the
    # client-credentials grant (Client ID + Client Secret exchanged for a short-lived token by
    # ShopifyLiveConnector itself). See connectors/shopify_live/auth.py and
    # docs/architecture/shopify-dev-store-certification-preparation.md.
    config = store.get_config(merchant_id).get("shopify_live", {})
    shop_domain = config.get("shop_domain")
    if not shop_domain:
        raise ValueError(f"merchant {merchant_id} has a shopify_live channel but no config.shopify_live.shop_domain")
    client_id = store.get_credential_ref(merchant_id, "shopify_live_client_id")
    client_secret = store.get_credential_ref(merchant_id, "shopify_live_client_secret")
    return ShopifyLiveConnector(
        store, workflow, shop_domain=shop_domain, client_id=client_id, client_secret=client_secret,
        api_version=config.get("api_version", "2026-07"),
        webhook_delivery_base_url=config.get("webhook_delivery_base_url"),
        # default_location_gid intentionally NOT read from config - discovered programmatically by the
        # connector itself on first inventory operation (see ShopifyLiveConnector._ensure_location_gid).
    )


def build_service_graph(store, *, extra_storefront_factories: dict[str, ConnectorFactory] | None = None) -> ServiceGraph:
    logistics = SimulatedLogisticsConnector(store)
    payments = SimulatedPaymentConnector(store)
    suppliers = SimulatedSupplierConnector(store)
    engine = FakeTemporalEngine(store)
    post_order = PostOrderOperationsService(store, None, logistics, payments)
    order_orchestrator = OrderOrchestrator(store, engine, post_order)

    storefronts = StorefrontConnectorRegistry(store, order_orchestrator)
    storefronts.register("shopify", _shopify_factory)
    storefronts.register("woocommerce", _woocommerce_factory)
    storefronts.register("shopify_live", _shopify_live_factory)
    for channel_type, factory in (extra_storefront_factories or {}).items():
        storefronts.register(channel_type, factory)

    # post_order.storefront was constructed with a placeholder (None -> always returns None) above,
    # because PostOrderOperationsService must exist before order_orchestrator, which the registry
    # itself needs - the same "mutual reference after construction" shape already used for
    # support/chatwoot below. Reassigning it to the REGISTRY (not a single connector) is what makes
    # post_order merchant-aware: self.storefront(merchant_id) now resolves per-merchant/per-platform.
    post_order.storefront = storefronts

    support = SupportWorkflowService(store, None, post_order=post_order)
    support_orchestrator = SupportOrchestrator(support)
    chatwoot = ChatwootConnector(store, support_orchestrator)
    # SupportWorkflowService.handle_conversation() sends AUTOMATIC responses through self.chatwoot -
    # constructed after `support` above, so wired back in here (the same "duck-typed mutual reference"
    # shape order_orchestrator already uses). Chatwoot is NOT a storefront connector (it's the support
    # channel) - it stays a single shared instance; its own per-merchant credential lookup
    # (get_credential_ref) already happens per-call, not baked into construction, so this was never
    # subject to the single-connector-slot problem the storefront registry closes.
    support.chatwoot = chatwoot
    finance = FinanceOperationsService(store)
    procurement = ProcurementService(store, suppliers)
    catalogue = ProductOnboardingWorkflow(store, _build_storage(), storefronts)
    services = Services(store=store, post_order=post_order, finance=finance, procurement=procurement, catalogue=catalogue)
    return ServiceGraph(
        logistics=logistics, payments=payments, suppliers=suppliers, engine=engine, post_order=post_order,
        order_orchestrator=order_orchestrator, storefronts=storefronts, support=support, support_orchestrator=support_orchestrator,
        chatwoot=chatwoot, finance=finance, procurement=procurement, catalogue=catalogue, services=services,
    )
