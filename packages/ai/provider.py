from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field

from sanocea.packages.domain_contract.models import now_utc


class AIResult(BaseModel):
    task: str
    provider: str
    model: str
    output: dict[str, Any]
    confidence: float
    evidence_refs: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: now_utc().isoformat())
    requires_human_approval: bool = True
    accepted: bool = False
    rejected: bool = False


class AIProvider(Protocol):
    def classify(self, text: str, labels: list[str], evidence_refs: list[str]) -> AIResult: ...

    def generate(self, task: str, input: dict[str, Any], evidence_refs: list[str]) -> AIResult: ...

    def map_attributes(self, raw: dict[str, Any], evidence_refs: list[str]) -> AIResult: ...


class DeterministicAIProvider:
    provider = "deterministic"
    model = "rules-v1"

    def classify(self, text: str, labels: list[str], evidence_refs: list[str]) -> AIResult:
        lowered = text.lower()
        intent = "unknown"
        if "where" in lowered or "status" in lowered or "order" in lowered:
            intent = "order_status"
        if "ship" in lowered or "tracking" in lowered:
            intent = "shipment_status"
        if "cancel" in lowered:
            intent = "cancellation_request"
        if "return" in lowered:
            intent = "return_request"
        if "refund" in lowered:
            intent = "refund_request"
        if "address" in lowered:
            intent = "address_change"
        if intent not in labels:
            intent = "unknown"
        return AIResult(
            task="classification",
            provider=self.provider,
            model=self.model,
            output={"label": intent},
            confidence=0.9 if intent != "unknown" else 0.2,
            evidence_refs=evidence_refs,
            requires_human_approval=False,
        )

    def generate(self, task: str, input: dict[str, Any], evidence_refs: list[str]) -> AIResult:
        title = input.get("title") or "Product"
        return AIResult(
            task=task,
            provider=self.provider,
            model=self.model,
            output={"copy": f"{title} prepared from approved supplier evidence."},
            confidence=0.75,
            evidence_refs=evidence_refs,
            requires_human_approval=True,
        )

    def map_attributes(self, raw: dict[str, Any], evidence_refs: list[str]) -> AIResult:
        return AIResult(
            task="attribute_mapping",
            provider=self.provider,
            model=self.model,
            output=raw,
            confidence=0.7,
            evidence_refs=evidence_refs,
            requires_human_approval=True,
        )

