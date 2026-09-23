from __future__ import annotations

import os

import pytest


def test_shopify_live_credentials_required_for_live_e2e():
    if not os.environ.get("SANOCEA_SHOPIFY_ADMIN_TOKEN"):
        pytest.skip("live Shopify E2E pending credentials")


def test_chatwoot_live_credentials_required_for_live_e2e():
    if not os.environ.get("SANOCEA_CHATWOOT_API_TOKEN"):
        pytest.skip("live Chatwoot E2E pending credentials/self-hosted instance")

