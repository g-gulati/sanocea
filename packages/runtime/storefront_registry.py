from __future__ import annotations

from typing import Any, Callable

from sanocea.packages.domain_contract.models import Channel

"""Phase: multi-platform connector hardening. Replaces the single-storefront-connector-per-process
architecture with a tenant/channel-aware resolver: merchant + channel -> connector instance/config/
credentials. Domain services never see this class - they hold a resolver callable
(`Callable[[str], Connector]`, `self.storefront(merchant_id)`), never a specific connector, so which
platform a merchant uses is entirely infrastructure/runtime composition, never domain-code branching.
"""


class UnknownStorefrontChannelError(Exception):
    """No registered storefront channel type is configured for this merchant."""

    def __init__(self, merchant_id: str) -> None:
        super().__init__(f"merchant {merchant_id} has no configured storefront channel")
        self.merchant_id = merchant_id


class ChannelMismatchError(Exception):
    """The caller (typically a webhook route) expected a specific channel type for this merchant, but
    the merchant is actually configured for a different one - e.g. a request arriving at
    /webhooks/shopify/{merchant_id} for a merchant actually configured for WooCommerce. This is the
    explicit "one platform failure doesn't route/fall back to another connector" guarantee: a mismatch
    is a hard error, never a silent fallback to whichever connector happens to be cached."""

    def __init__(self, merchant_id: str, expected: str, actual: str | None) -> None:
        super().__init__(f"merchant {merchant_id} is configured for channel {actual!r}, not the expected {expected!r}")
        self.merchant_id = merchant_id
        self.expected = expected
        self.actual = actual


ConnectorFactory = Callable[[Any, Any, str], Any]  # (store, workflow, merchant_id) -> Connector


class StorefrontConnectorRegistry:
    """merchant + channel -> connector instance/config/credentials.

    One process can serve Merchant A on Shopify and Merchant B on WooCommerce (or any future platform)
    simultaneously: each merchant's connector is built ONCE (via the factory registered for that
    merchant's configured Channel.type), from THAT merchant's own credentials
    (store.get_credential_ref is already merchant-scoped - see TenantAccessError), and cached per
    merchant_id - never shared or reused across merchants, so cross-merchant/cross-platform
    contamination is structurally impossible, not just policy.

    Registering a new platform is exactly `registry.register("newplatform", factory)` - no change to
    any domain service, no change to this class's own logic.
    """

    def __init__(self, store, workflow) -> None:
        self.store = store
        self.workflow = workflow
        self._factories: dict[str, ConnectorFactory] = {}
        self._cache: dict[str, Any] = {}

    def register(self, channel_type: str, factory: ConnectorFactory) -> None:
        self._factories[channel_type] = factory

    def channel_type_for(self, merchant_id: str) -> str | None:
        storefront_channels = [c for c in self.store.list(Channel, merchant_id) if c.type in self._factories]
        return storefront_channels[0].type if storefront_channels else None

    def resolve(self, merchant_id: str) -> Any:
        channel_type = self.channel_type_for(merchant_id)
        if channel_type is None:
            raise UnknownStorefrontChannelError(merchant_id)
        return self.resolve_for_channel_type(merchant_id, channel_type)

    def resolve_expect(self, merchant_id: str, expected_channel_type: str) -> Any:
        actual = self.channel_type_for(merchant_id)
        if actual != expected_channel_type:
            raise ChannelMismatchError(merchant_id, expected_channel_type, actual)
        return self.resolve_for_channel_type(merchant_id, expected_channel_type)

    def resolve_for_channel_type(self, merchant_id: str, channel_type: str) -> Any:
        """P0 Remediation: every merchant + channel type resolves to ONE authoritative connector
        instance across all resolution paths (`resolve()`, `resolve_for_channel_type()`, and
        `resolve_for_channel_id()`). Eliminates the dual-cache split where resolve() cached under
        merchant_id while resolve_for_channel_type() cached under f"{merchant_id}:{channel_type}",
        which created desynchronized in-memory connector instances."""
        cache_key = f"{merchant_id}:{channel_type}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        if channel_type not in self._factories:
            raise UnknownStorefrontChannelError(merchant_id)
        matching = [c for c in self.store.list(Channel, merchant_id) if c.type == channel_type]
        if not matching:
            raise UnknownStorefrontChannelError(merchant_id)
        connector = self._factories[channel_type](self.store, self.workflow, merchant_id)
        self._cache[cache_key] = connector
        # Alias self._cache[merchant_id] if this is the merchant's primary/first storefront
        primary_type = self.channel_type_for(merchant_id)
        if primary_type == channel_type:
            self._cache[merchant_id] = connector
        return connector

    def resolve_for_channel_id(self, merchant_id: str, channel_id: str) -> Any:
        """Same as resolve_for_channel_type, but starting from a specific Channel.id (what
        Publication.channel_id and Order.channel_id actually carry) rather than a bare type string."""
        channels = [c for c in self.store.list(Channel, merchant_id) if c.id == channel_id]
        if not channels:
            raise UnknownStorefrontChannelError(merchant_id)
        return self.resolve_for_channel_type(merchant_id, channels[0].type)

    def __call__(self, merchant_id: str) -> Any:
        return self.resolve(merchant_id)


def as_resolver(value: Any) -> Callable[[str], Any]:
    """Normalizes a constructor argument that may be EITHER a plain, single connector instance (the
    shape every existing test/caller already passes - one merchant, one platform, unchanged since
    before this phase) OR a StorefrontConnectorRegistry (multi-merchant, multi-platform) into a single
    `Callable[[str], Connector]` calling convention. This is what makes the rename/rewire in
    PostOrderOperationsService/ProductPublicationService/OrderMonitoringService purely mechanical and
    behavior-preserving: every existing positional-argument call site
    (`PostOrderOperationsService(store, some_connector, logistics)`) keeps working unchanged - it just
    gets wrapped in a resolver that always returns that same connector, regardless of merchant_id."""
    if value is None:
        return lambda merchant_id: None
    if isinstance(value, StorefrontConnectorRegistry):
        return value
    return lambda merchant_id: value


def as_channel_resolver(value: Any) -> Callable[[str, str], Any]:
    """Step 9Q.2 - the channel-aware counterpart to as_resolver(), for callers that know a SPECIFIC
    channel_id (Publication.channel_id, Order.channel_id) and must not rely on resolve()'s "whichever
    channel happens to be first" behavior once a merchant has more than one storefront. For the single-
    connector case (every existing caller, unchanged), channel_id is accepted and ignored - there is
    only ever one connector to return, exactly as as_resolver() already behaves."""
    if value is None:
        return lambda merchant_id, channel_id: None
    if isinstance(value, StorefrontConnectorRegistry):
        return value.resolve_for_channel_id
    return lambda merchant_id, channel_id: value
