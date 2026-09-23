from __future__ import annotations

from typing import Any

from sanocea.packages.domain_contract.models import AuditEvent, ExternalRef
from sanocea.packages.domain_contract.store import Phase0Store

from .context import get_correlation_id


class AuditLedger:
    def __init__(self, store: Phase0Store) -> None:
        self.store = store

    def record(
        self,
        *,
        merchant_id: str,
        actor: str,
        source: str,
        action: str,
        object_type: str,
        result: str,
        object_id: str | None = None,
        workflow_id: str | None = None,
        evidence_ref: str | None = None,
        requested_mutation: dict[str, Any] | None = None,
        external_ref: ExternalRef | None = None,
        error: str | None = None,
        correlation_id: str | None = None,
    ) -> AuditEvent:
        return self.store.append_audit(
            AuditEvent(
                merchant_id=merchant_id,
                actor=actor,
                source=source,
                action=action,
                object_type=object_type,
                object_id=object_id,
                workflow_id=workflow_id,
                evidence_ref=evidence_ref,
                requested_mutation=requested_mutation,
                result=result,
                external_ref=external_ref,
                error=error,
                correlation_id=correlation_id or get_correlation_id(),
            )
        )

