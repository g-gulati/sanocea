from __future__ import annotations

from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, Field

from sanocea.packages.audit import AuditLedger
from sanocea.packages.domain_contract.models import RawPayload
from sanocea.packages.domain_contract.store import Phase0Store
from sanocea.packages.idempotency import IdempotencyService


class CapabilityStatus(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    ASYNC_ONLY = "async_only"
    # Step 9Q.2 - two additions for connectors built against a channel's PUBLIC first-party contract
    # before real merchant/platform access exists (Flipkart being the first case): the capability is
    # real and its request/response shape is implemented and contract-tested, but cannot be exercised
    # against the live platform without credentials the merchant/platform has not yet issued.
    ACCESS_REQUIRED = "access_required"
    # The capability's EXISTENCE (or its exact request/response shape) was not confirmed by primary
    # documentation during research - never silently treated as SUPPORTED, never implemented against a
    # guessed schema. See docs/connectors/flipkart-certification.md for the exact items in this state.
    UNCONFIRMED = "unconfirmed"


class MutationMode(str, Enum):
    SYNC = "sync"
    ASYNC = "async"
    UNSUPPORTED = "unsupported"


class Capability(BaseModel):
    name: str
    status: CapabilityStatus
    mode: MutationMode | None = None
    api_versions: list[str] = Field(default_factory=list)
    notes: str | None = None


class ConnectorCapabilities(BaseModel):
    connector: str
    capabilities: dict[str, Capability]

    def require(self, name: str) -> Capability:
        """Step 9Q.2: only SUPPORTED/ASYNC_ONLY capabilities may actually be invoked. ACCESS_REQUIRED
        (real, contract-implemented, but no live credential yet) and UNCONFIRMED (existence/shape not
        established by primary documentation) both refuse execution here, with a distinct exception
        each - never silently degrade into "attempt it anyway" or a fabricated response."""
        capability = self.capabilities.get(name)
        if capability is None or capability.status == CapabilityStatus.UNSUPPORTED:
            raise UnsupportedCapability(name)
        if capability.status == CapabilityStatus.ACCESS_REQUIRED:
            raise CapabilityAccessRequired(name)
        if capability.status == CapabilityStatus.UNCONFIRMED:
            raise CapabilityUnconfirmed(name)
        return capability


class Page(BaseModel):
    items: list[dict[str, Any]]
    next_cursor: str | None = None


class MutationRequest(BaseModel):
    merchant_id: str
    action: str
    object_type: str
    payload: dict[str, Any]
    idempotency_key: str


class MutationResult(BaseModel):
    status: str
    external_ref: str | None = None
    async_operation_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class RateLimitState(BaseModel):
    limit: int | None = None
    remaining: int | None = None
    reset_at: str | None = None


class UnsupportedCapability(Exception):
    pass


class CapabilityAccessRequired(Exception):
    """The capability is really implemented against the platform's own documented contract, but cannot
    be exercised yet because no merchant/platform credential has been issued for it."""


class CapabilityUnconfirmed(Exception):
    """No primary documentation confirmed this capability's existence/shape - refusing to execute
    rather than guess. See docs/connectors/<connector>-certification.md for what's unconfirmed and
    why."""


class Connector(Protocol):
    name: str

    def describe_capabilities(self) -> ConnectorCapabilities: ...


class GuardedConnector:
    name = "base"

    def __init__(self, store: Phase0Store) -> None:
        self.store = store
        self.audit = AuditLedger(store)
        self.idempotency = IdempotencyService(store)

    def describe_capabilities(self) -> ConnectorCapabilities:
        raise NotImplementedError

    def validate_credentials(self, merchant_id: str, credential_ref: str) -> bool:
        self.store.get_credential_ref(merchant_id, credential_ref)
        return True

    def register_webhooks(self, merchant_id: str, channel_id: str) -> MutationResult:
        raise UnsupportedCapability("register_webhooks")

    def ingest_webhook(
        self, merchant_id: str, headers: dict[str, str], body: bytes
    ) -> dict[str, Any]:
        raise UnsupportedCapability("ingest_webhook")

    def poll_changes(self, merchant_id: str, cursor: str | None = None) -> Page:
        raise UnsupportedCapability("poll_changes")

    def fetch(self, merchant_id: str, entity_type: str, external_id: str) -> dict[str, Any]:
        raise UnsupportedCapability("fetch")

    def search(
        self, merchant_id: str, entity_type: str, filters: dict[str, Any], cursor: str | None = None
    ) -> Page:
        raise UnsupportedCapability("search")

    def propose_mutation(self, request: MutationRequest) -> MutationResult:
        self.describe_capabilities().require(request.action)
        return MutationResult(status="proposed", payload=request.payload)

    def execute_mutation(self, request: MutationRequest) -> MutationResult:
        self.describe_capabilities().require(request.action)

        def op() -> MutationResult:
            result = self._execute_mutation(request)
            self.audit.record(
                merchant_id=request.merchant_id,
                actor="connector",
                source=self.name,
                action=request.action,
                object_type=request.object_type,
                result=result.status,
                requested_mutation=request.payload,
            )
            return result

        result, _created = self.idempotency.run_once(
            f"{request.merchant_id}:connector-mutation:{self.name}:{request.action}",
            request.idempotency_key,
            op,
        )
        if isinstance(result, dict):
            return MutationResult.model_validate(result)
        return result

    def _execute_mutation(self, request: MutationRequest) -> MutationResult:
        raise UnsupportedCapability(request.action)

    def get_mutation_status(self, merchant_id: str, operation_id: str) -> MutationResult:
        raise UnsupportedCapability("get_mutation_status")

    def reconcile(self, merchant_id: str, scope: dict[str, Any]) -> list[dict[str, Any]]:
        raise UnsupportedCapability("reconcile")

    def map_error(self, error: Exception) -> dict[str, Any]:
        return {"connector": self.name, "error": type(error).__name__, "message": str(error)}

    def rate_limit_state(self, merchant_id: str) -> RateLimitState:
        return RateLimitState()

    def _store_raw(
        self,
        *,
        merchant_id: str,
        source: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        checksum: str,
    ) -> RawPayload:
        payload_headers = self._sanitize_headers(headers)
        raw = RawPayload(
            merchant_id=merchant_id,
            source=source,
            payload=payload,
            headers=payload_headers,
            checksum=checksum,
        )
        return self.store.store_raw_payload(raw)

    def _sanitize_headers(self, headers: dict[str, str]) -> dict[str, str]:
        sensitive = ("authorization", "cookie", "secret", "token", "signature", "hmac")
        sanitized: dict[str, str] = {}
        for key, value in headers.items():
            lowered = key.lower()
            sanitized[key] = "[redacted]" if any(marker in lowered for marker in sensitive) else value
        return sanitized
