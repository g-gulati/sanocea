from __future__ import annotations

import pytest

from sanocea.connectors.chatwoot import ChatwootConnector
from sanocea.connectors.shopify import ShopifyConnector
from sanocea.packages.domain_contract.models import Channel, Merchant
from sanocea.packages.domain_contract.store import Phase0Store
from sanocea.workers.workflow import FakeTemporalEngine


@pytest.fixture
def phase0():
    store = Phase0Store()
    for merchant_id, name in [("mer_A", "Merchant A"), ("mer_B", "Merchant B")]:
        store.put(Merchant(id=merchant_id, merchant_id=merchant_id, legal_name=name, display_name=name))
    store.set_config(
        "mer_A",
        {
            "catalogue": {"ingestion": True, "auto_publish": False},
            "orders": {"monitoring": True},
            "inventory": {"reconcile": True},
            "support": {"email": True, "whatsapp": True, "voice": False},
            "returns": {"automation": True},
            "refunds": {"auto_execute": False},
            "marketplace": {"shopify": True, "amazon": False},
            "policy": {"refund": {"automatic_limit": 1000, "above_limit": "REQUIRE_APPROVAL"}},
        },
    )
    store.set_config("mer_B", {"marketplace": {"shopify": False}, "support": {"email": True}})
    store.put(
        Channel(
            id="chn_A_shopify",
            merchant_id="mer_A",
            type="shopify",
            name="Merchant A Shopify",
            credential_ref="shopify_webhook_secret",
            capabilities={"ingest_order_webhook": True},
        )
    )
    store.put(
        Channel(
            id="chn_A_chatwoot",
            merchant_id="mer_A",
            type="chatwoot",
            name="Merchant A Chatwoot",
            credential_ref="chatwoot_webhook_secret",
            capabilities={"ingest_conversation_webhook": True, "send_message": True},
        )
    )
    store.put(Channel(id="chn_B_email", merchant_id="mer_B", type="email", name="Merchant B Email"))
    store.set_credential_ref("mer_A", "shopify_webhook_secret", "shopify_secret_A")
    store.set_credential_ref("mer_A", "chatwoot_webhook_secret", "chatwoot_secret_A")
    store.set_credential_ref("mer_B", "shopify_webhook_secret", "shopify_secret_B")
    workflow = FakeTemporalEngine(store)
    shopify = ShopifyConnector(store, workflow)
    chatwoot = ChatwootConnector(store)
    return store, workflow, shopify, chatwoot

