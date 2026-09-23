"""Controlled-demo connector variants for the multi-channel live-demo build (Sept 2026).

Purpose: prospect demo tenants have no real Amazon/Flipkart/WooCommerce credentials (see the earlier
multi-channel operations audit). Rather than writing a parallel, from-scratch "fake marketplace" per
channel, this module subclasses the REAL, contract-built connector classes
(`connectors.amazon.AmazonConnector`, `connectors.flipkart.FlipkartConnector`,
`connectors.woocommerce.WooCommerceConnector`) and overrides ONLY the one seam every connector already
exposes for its outbound HTTP call - never touching payload-building, capability declarations, status
mapping, or any other real connector logic. Everything upstream of that seam (execute_mutation's
audit+idempotency wrapper, fetch()'s response normalization, the exact wire-shape each connector builds)
is the SAME code the real, credentialed path would run. Only the network call itself is replaced with a
deterministic, scenario-driven canned response - explicitly stamped `demo_provenance=SYNTHETIC_DEMO`
everywhere it surfaces, never claimed as a real marketplace interaction.

No credentials are ever read, stored, or required for any of these classes - `_DemoAuth` never performs
a token exchange, and each override method never opens a real socket.
"""

from __future__ import annotations

from typing import Any, Callable

from sanocea.connectors.amazon import AmazonConnector
from sanocea.connectors.flipkart import FlipkartConnector
from sanocea.connectors.woocommerce.connector import WooCommerceConnector

ResponseFn = Callable[[str, str, dict[str, Any] | None, dict[str, str] | None], tuple[int, dict[str, str], bytes]]


class _DemoAuth:
    """Satisfies MarketplaceAuthStrategy without ever performing a real token exchange - the demo
    connector subclasses below override the HTTP call itself, so auth_headers() is never actually
    invoked, but the real connector constructors require an auth object of this shape."""

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": "Bearer sanocea-controlled-demo-no-real-token"}

    def invalidate(self) -> None:
        return None


def _json_response(status: int, body: dict[str, Any] | list[Any]) -> tuple[int, dict[str, str], bytes]:
    import json

    return status, {"Content-Type": "application/json"}, json.dumps(body).encode()


class ControlledDemoAmazonConnector(AmazonConnector):
    """Overrides `_request` (MarketplaceConnector's one HTTP seam) with a deterministic scenario
    function supplied by ChannelOperationService. `describe_capabilities()`, `_execute_mutation()`,
    `fetch()` are all inherited UNCHANGED from the real AmazonConnector - the same request-building and
    response-parsing logic a live-credentialed Amazon integration would run."""

    def __init__(self, store, *, scenario: "AmazonDemoScenario") -> None:
        super().__init__(store, None, auth=_DemoAuth(), seller_id="SANOCEA-DEMO-SELLER")
        self._scenario = scenario

    def _request(self, method: str, url: str, *, body: dict[str, Any] | None = None, params: dict[str, str] | None = None, extra_headers: dict[str, str] | None = None, max_retries: int = 2, simulate: str | None = None) -> dict[str, Any]:
        status, _headers, response_body = self._scenario.respond(method, url, body, params)
        import json

        if status >= 400:
            raise ValueError(f"marketplace API {status}: {response_body.decode()}")
        return json.loads(response_body) if response_body else {}


class AmazonDemoScenario:
    """Real Amazon India Listings Items API response shapes (per docs/connectors/amazon.md /
    amazon-certification.md's Level-1-confirmed schema), populated deterministically from the submitted
    payload rather than fabricated per call - if `attributes.country_of_origin` is present the listing
    is accepted; if absent, Amazon returns its real documented shape for a validation issue (HTTP 200,
    `status: "INVALID"`, populated `issues[]` - submission accepted, mutation NOT applied, exactly the
    async "submitted != accepted" contract this connector already implements for real)."""

    def __init__(self, product_title: str, price_rupees: str, sku: str) -> None:
        self.product_title = product_title
        self.price_rupees = price_rupees
        self.sku = sku

    def respond(self, method: str, url: str, body: dict[str, Any] | None, params: dict[str, str] | None) -> tuple[int, dict[str, str], bytes]:
        if method in ("PUT", "PATCH") and "/listings/2021-08-01/items/" in url:
            attributes = (body or {}).get("attributes", {})
            if "country_of_origin" not in attributes:
                return _json_response(200, {
                    "sku": self.sku, "status": "INVALID", "submissionId": f"demo-sub-{self.sku}",
                    "issues": [{"code": "4005001", "message": "attributes.country_of_origin: a value is required for this product type", "severity": "ERROR"}],
                })
            return _json_response(200, {"sku": self.sku, "status": "ACCEPTED", "submissionId": f"demo-sub-{self.sku}", "issues": []})
        if method == "GET" and "/listings/2021-08-01/items/" in url:
            return _json_response(200, {
                "sku": self.sku,
                "summaries": [{"itemName": self.product_title, "status": ["BUYABLE"]}],
                "offers": [{"price": {"amount": self.price_rupees}}],
            })
        raise AssertionError(f"unhandled controlled-demo Amazon request: {method} {url}")


class ControlledDemoFlipkartConnector(FlipkartConnector):
    def __init__(self, store, *, scenario: "FlipkartDemoScenario") -> None:
        super().__init__(store, None, auth=_DemoAuth())
        self._scenario = scenario

    def _request(self, method: str, url: str, *, body: dict[str, Any] | None = None, params: dict[str, str] | None = None, extra_headers: dict[str, str] | None = None, max_retries: int = 2, simulate: str | None = None) -> dict[str, Any]:
        status, _headers, response_body = self._scenario.respond(method, url, body, params)
        import json

        if status >= 400:
            raise ValueError(f"marketplace API {status}: {response_body.decode()}")
        return json.loads(response_body) if response_body else {}


class FlipkartDemoScenario:
    """Real Flipkart Seller API listings response shape (`/sellers/v3/listings`, Level 1 confirmed base
    path per docs/connectors/flipkart-certification.md) - clean accept-and-list path only; Flipkart is
    the deliberately "normal, no drama" channel in this demo per the architecture note."""

    def __init__(self, product_title: str, price_rupees: str, sku: str) -> None:
        self.product_title = product_title
        self.price_rupees = price_rupees
        self.sku = sku

    def respond(self, method: str, url: str, body: dict[str, Any] | None, params: dict[str, str] | None) -> tuple[int, dict[str, str], bytes]:
        if method == "POST" and url.endswith("/sellers/v3/listings"):
            return _json_response(200, {"listingId": f"FK-{self.sku}", "skuId": self.sku, "status": "ACTIVE"})
        if method == "GET" and url.endswith("/sellers/v3/listings"):
            return _json_response(200, {"title": self.product_title, "skuId": self.sku, "sellingPrice": self.price_rupees, "status": "ACTIVE"})
        raise AssertionError(f"unhandled controlled-demo Flipkart request: {method} {url}")


class ControlledDemoWooCommerceConnector(WooCommerceConnector):
    def __init__(self, store, *, scenario: "WooCommerceDemoScenario") -> None:
        super().__init__(store, None, base_url="https://demo-controlled.invalid", consumer_key="demo", consumer_secret="demo")
        self._scenario = scenario

    def _request_with_headers(self, method: str, path: str, *, body: dict[str, Any] | None = None, params: dict[str, str] | None = None) -> tuple[Any, dict[str, str]]:
        status, headers, response_body = self._scenario.respond(method, path, body, params)
        import json

        if status >= 400:
            raise ValueError(f"WooCommerce API {status}: {response_body.decode()}")
        return (json.loads(response_body) if response_body else None), headers


class WooCommerceDemoScenario:
    """Real WooCommerce REST API v3 product response shape - own-website is the "commercial ambiguity
    escalates to the owner" channel in this demo (see ChannelOperationService); when that applies, the
    connector is never even called (ChannelOperationService stops before submission), so this scenario
    only ever needs to answer the clean-publish path."""

    def __init__(self, product_title: str, price_rupees: str, sku: str) -> None:
        self.product_title = product_title
        self.price_rupees = price_rupees
        self.sku = sku
        self._external_id = f"9{abs(hash(sku)) % 100000}"

    def respond(self, method: str, path: str, body: dict[str, Any] | None, params: dict[str, str] | None) -> tuple[int, dict[str, str], bytes]:
        if method == "GET" and path == "products":
            return _json_response(200, [])  # no pre-existing product for any of these new SKUs
        if method == "POST" and path == "products":
            return _json_response(201, {"id": int(self._external_id), "sku": self.sku, "name": self.product_title, "regular_price": self.price_rupees, "status": "publish"})
        if method == "GET" and path == f"products/{self._external_id}":
            return _json_response(200, {"id": int(self._external_id), "sku": self.sku, "name": self.product_title, "regular_price": self.price_rupees, "status": "publish"})
        raise AssertionError(f"unhandled controlled-demo WooCommerce request: {method} {path}")
