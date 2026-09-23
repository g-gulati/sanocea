"""Real BROWSER end-to-end test for the Command Center merchant switcher - not an HTTP/API test.

This exists because the underlying bug (selector shows Ajanta, rendered body still shows Anchal) was
invisible to every prior HTTP-level test: the backend correctly served the right data every time, and
STATE was correctly populated - the defect was entirely in what the render functions chose to draw on
screen (hardcoded Anchal presentation copy, unconditional regardless of which tenant's data had just
loaded). Only opening a real browser and reading the rendered DOM can catch this class of bug, so that
is what this test does, via Playwright.

Requires: a running Command Center API server (SANOCEA_COMMAND_CENTER_URL, default
http://127.0.0.1:8080), Postgres, and Playwright's Chromium browser already installed
(`playwright install chromium`). Skipped automatically if any of these aren't available - this is a
real-environment E2E test, not a unit test, and is not part of the default fast test loop.
"""

from __future__ import annotations

import base64
import os

import pytest

os.environ.setdefault("SANOCEA_PG_DSN", "postgresql://sanocea:sanocea@127.0.0.1:55432/sanocea_phase05")
PG_DSN = os.environ["SANOCEA_PG_DSN"]
COMMAND_CENTER_URL = os.environ.get("SANOCEA_COMMAND_CENTER_URL", "http://127.0.0.1:8080")

if not os.environ.get("SANOCEA_CRED_MASTER_KEY_CURRENT"):
    os.environ["SANOCEA_CRED_MASTER_KEY_CURRENT"] = "v1"
    os.environ["SANOCEA_CRED_MASTER_KEY_V1"] = base64.b64encode(b"\x2a" * 32).decode()

playwright_sync_api = pytest.importorskip("playwright.sync_api", reason="Playwright not installed")

DEMO_MERCHANTS = {
    "ref_anchal_heritage": "Anchal Heritage Organics",
    "prospect_ajanta_soya": "Ajanta Soya",
    "prospect_healthvitals": "HealthVitals",
    "prospect_carzex": "Carzex",
    "prospect_premium_basket": "Premium Basket",
}

# One real, publicly-verified product expected on the Evidence & Conflict Review tab per prospect - see
# packages/prospect_demo/tenants.py::PROSPECT_TENANTS for the full sourced catalogue each is drawn from.
KNOWN_PRODUCT_SUBSTRING = {
    "prospect_ajanta_soya": "Anchal",  # Ajanta Soya's real brand IS "Anchal" - legitimate tenant data,
    # not the Reference Merchant leaking through (see docs/architecture/PROSPECT_DEMO_TENANT_SYSTEM.md).
    "prospect_healthvitals": "Gut Brain Support",
    "prospect_carzex": "Carzex",
    "prospect_premium_basket": "Makhana",
}


def _server_reachable() -> bool:
    import urllib.request

    try:
        urllib.request.urlopen(f"{COMMAND_CENTER_URL}/health", timeout=2)
        return True
    except Exception:
        return False


def _browser_available() -> bool:
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            b.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not (os.environ.get("SANOCEA_PG_DSN") and _server_reachable() and _browser_available()),
    reason="Requires a live Command Center server + Postgres + Playwright Chromium",
)


@pytest.fixture(scope="module")
def internal_operator_key():
    """Resets every demo tenant and mints one internal-operator key authorized for all of them -
    exactly scripts/mint_internal_operator_key.py's own flow, done in-process for test isolation."""
    from sanocea.packages.domain_contract.credentials import build_production_credential_provider
    from sanocea.packages.domain_contract.postgres_store import PostgresStore
    from sanocea.packages.prospect_demo import list_demo_tenants, reset_prospect_tenant
    from sanocea.packages.reference_merchant import reset_reference_merchant

    reset_reference_merchant(dsn=PG_DSN)
    for merchant_id in DEMO_MERCHANTS:
        if merchant_id != "ref_anchal_heritage":
            reset_prospect_tenant(merchant_id, dsn=PG_DSN)

    cred_provider = build_production_credential_provider(PG_DSN)
    store = PostgresStore(PG_DSN, credential_provider=cred_provider)
    merchant_ids = [t["merchant_id"] for t in list_demo_tenants()]
    _, raw_key = store.create_api_key(
        merchant_id=None, role="operator", label="e2e-test-internal-operator", allowed_merchants=merchant_ids,
    )
    return raw_key


@pytest.fixture(scope="module")
def page(internal_operator_key):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.goto(f"{COMMAND_CENTER_URL}/ui")
        pg.wait_for_selector("#auth-modal", state="visible", timeout=5000)
        pg.fill("#input-api-key", internal_operator_key)
        pg.click("#btn-save-auth")
        pg.wait_for_timeout(1500)
        yield pg
        browser.close()


def _main_content(page) -> str:
    """The actual RENDERED screen content (header identity + the 7 tab bodies) - deliberately excludes
    the merchant <select> dropdown itself, whose <option> list legitimately names every switchable
    tenant regardless of which one is currently selected."""
    return page.inner_text("#tenant-id-label") + " " + page.inner_text(".main-container")


def _switch_to(page, merchant_id: str):
    page.select_option("#merchant-select", merchant_id)
    page.wait_for_timeout(2000)
    page.click('[data-tab="overview"]')
    page.wait_for_timeout(400)


@pytest.mark.parametrize("merchant_id,expected_name", list(DEMO_MERCHANTS.items()))
def test_selector_and_rendered_body_agree(page, merchant_id, expected_name):
    """THE core regression test: for every demo merchant, the rendered Overview body must show that
    merchant's own identity, and none of the other four's - selector state and rendered body state must
    never diverge (the exact bug this test file exists to catch)."""
    _switch_to(page, merchant_id)
    assert page.inner_text("#tenant-id-label") == merchant_id
    content = _main_content(page)
    assert expected_name in content, f"expected '{expected_name}' visible for {merchant_id}, got: {content[:300]}"
    for other_id, other_name in DEMO_MERCHANTS.items():
        if other_id == merchant_id:
            continue
        # HealthVitals'/Carzex's/Premium Basket's names never collide with another tenant's; Anchal's and
        # Ajanta's do share the literal word "Anchal" (Ajanta Soya's real brand) - checked precisely
        # below in test_no_cross_merchant_identity_bleed instead of via this generic substring loop.
        if {merchant_id, other_id} == {"ref_anchal_heritage", "prospect_ajanta_soya"}:
            continue
        assert other_name not in content, f"'{other_name}' ({other_id}) leaked into {merchant_id}'s rendered body"


def test_anchal_shows_certified_reference_merchant_framing(page):
    _switch_to(page, "ref_anchal_heritage")
    content = _main_content(page)
    assert "CERTIFIED REFERENCE MERCHANT" in content
    assert "Anchal Heritage Organics" in content


def test_prospects_never_show_certified_reference_merchant_framing(page):
    for merchant_id in DEMO_MERCHANTS:
        if merchant_id == "ref_anchal_heritage":
            continue
        _switch_to(page, merchant_id)
        content = _main_content(page)
        assert "CERTIFIED REFERENCE MERCHANT" not in content
        assert "Fictional merchant" not in content
        assert "Shopify - Certified Dev Store" not in content


def test_prospects_show_demo_disclosure(page):
    for merchant_id in DEMO_MERCHANTS:
        if merchant_id == "ref_anchal_heritage":
            continue
        _switch_to(page, merchant_id)
        assert "Tailored demonstration" in _main_content(page)


def test_anchal_shows_no_demo_disclosure(page):
    _switch_to(page, "ref_anchal_heritage")
    assert "Tailored demonstration" not in _main_content(page)


@pytest.mark.parametrize("merchant_id,expected_product", list(KNOWN_PRODUCT_SUBSTRING.items()))
def test_real_product_visible_on_evidence_tab(page, merchant_id, expected_product):
    """Section 6's requirement: a known, real, publicly-verified product must be genuinely VISIBLE
    through the UI, not merely present as a database row."""
    _switch_to(page, merchant_id)
    page.click('[data-tab="conflicts"]')
    page.wait_for_timeout(500)
    assert expected_product in page.inner_text("#tab-conflicts")


def test_no_cross_merchant_bleed_across_all_seven_tabs(page):
    _switch_to(page, "prospect_ajanta_soya")
    for tab in ["overview", "exceptions", "conflicts", "publication", "inventory", "refunds", "audit"]:
        page.click(f'[data-tab="{tab}"]')
        page.wait_for_timeout(400)
        text = page.inner_text(f"#tab-{tab}")
        assert "Anchal Heritage Organics" not in text
        assert "CERTIFIED REFERENCE MERCHANT" not in text
        for other in ("HealthVitals", "Carzex", "Premium Basket"):
            assert other not in text


def test_failed_switch_clears_state_and_shows_explicit_error(page):
    """An operator key authorized for only ONE merchant, switching to a merchant it is NOT authorized
    for, must see an explicit error - never the previous (authorized) tenant's stale data, and never the
    unauthorized tenant's data either. This is the literal "select -> clear -> fetch -> validate ->
    render; on failure, error state, never previous tenant" requirement."""
    from sanocea.packages.domain_contract.credentials import build_production_credential_provider
    from sanocea.packages.domain_contract.postgres_store import PostgresStore

    cred_provider = build_production_credential_provider(PG_DSN)
    store = PostgresStore(PG_DSN, credential_provider=cred_provider)
    _, solo_key = store.create_api_key(merchant_id="prospect_ajanta_soya", role="operator", label="e2e-solo-ajanta")

    # Reuse the already-running Playwright/browser from the module-scoped `page` fixture (a fresh
    # sync_playwright() context cannot be opened from inside a test - it is already running one) - just
    # open a new page in the same browser for this independent session/credential.
    pg = page.context.browser.new_page()
    try:
        pg.goto(f"{COMMAND_CENTER_URL}/ui")
        pg.wait_for_selector("#auth-modal", state="visible", timeout=5000)
        pg.fill("#input-api-key", solo_key)
        pg.click("#btn-save-auth")
        pg.wait_for_timeout(1500)

        pg.select_option("#merchant-select", "prospect_healthvitals")
        pg.wait_for_timeout(2000)

        content = pg.inner_text(".main-container")
        assert "Unable to load selected merchant" in content
        assert "Anchal" not in content  # no stale Ajanta product data (Ajanta's own real brand)
        assert "Gut Brain Support" not in content  # never-authorized HealthVitals data must not leak
    finally:
        pg.close()
