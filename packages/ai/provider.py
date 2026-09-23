from __future__ import annotations

import re
from typing import Any, Protocol

from pydantic import BaseModel, Field

from sanocea.packages.domain_contract.models import now_utc

_WORD_RE = re.compile(r"[a-z0-9]+")


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

    def explain(self, question: str, evidence: dict[str, Any], evidence_refs: list[str]) -> AIResult:
        """Answers a free-text question about the merchant's OWN open exceptions/approvals, grounded
        entirely in `evidence` (already-fetched, already-scoped records - never the whole database, never
        fetched by this method itself). Must never mutate state; a recommended action is described in
        prose only, left for the caller to route through the real approval flow. `output["citations"]`
        maps each evidence_ref used back to which record it came from, so a caller can distinguish what
        was actually looked up from what the answer merely asserts."""
        ...


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

    # No real LLM is configured in this environment (no ANTHROPIC_API_KEY) - this implementation is
    # intentionally NOT a language model. It never fabricates an answer: it keyword-matches the question
    # against the real evidence records it was given and surfaces THEIR OWN already-written message/
    # summary/recommendation text verbatim, exactly the deterministic engine's own account of what
    # happened - honest under "don't fake intelligence" even without an LLM behind it. Swapping in a real
    # LLM-backed provider later is a drop-in: same AIProvider.explain signature, same evidence-only input.
    def explain(self, question: str, evidence: dict[str, Any], evidence_refs: list[str]) -> AIResult:
        items: list[dict[str, Any]] = []
        for exc in evidence.get("exceptions", []) or []:
            items.append({
                "ref": exc.get("id"), "kind": "exception", "severity": exc.get("severity"),
                "category": exc.get("category"), "text": exc.get("message") or "",
                "remediation_options": exc.get("remediation_options") or [],
            })
        for appr in evidence.get("approvals", []) or []:
            summary = appr.get("summary") or appr.get("action", "").replace("_", " ")
            items.append({
                "ref": appr.get("id"), "kind": "approval", "severity": None,
                "category": appr.get("action"), "text": summary,
                "recommendation": appr.get("recommendation"),
                "reference": appr.get("reference"),
            })

        q_tokens = {t for t in _WORD_RE.findall(question.lower()) if len(t) > 2}

        def score(item: dict[str, Any]) -> int:
            haystack = " ".join(str(v) for v in (item.get("text"), item.get("category"), item.get("reference")) if v).lower()
            hay_tokens = set(_WORD_RE.findall(haystack))
            return len(q_tokens & hay_tokens)

        scored = sorted(((score(i), i) for i in items), key=lambda pair: pair[0], reverse=True)
        matched = [i for s, i in scored if s > 0][:3]

        if not matched:
            return AIResult(
                task="explain", provider=self.provider, model=self.model,
                output={
                    "answer": "I don't see anything in this tenant's current open exceptions or approvals matching that - try asking about a specific order, channel, or 'what needs my attention?'.",
                    "citations": {},
                },
                confidence=0.15, evidence_refs=[], requires_human_approval=False,
            )

        lines = []
        citations: dict[str, str] = {}
        for item in matched:
            prefix = "🔴" if item.get("severity") == "critical" else ("🟠" if item.get("severity") == "warning" else "•")
            lines.append(f"{prefix} {item['text']}")
            if item.get("recommendation"):
                lines.append(f"   Recommended: {item['recommendation']}")
            elif item.get("remediation_options"):
                lines.append(f"   Options: {', '.join(item['remediation_options'])}")
            if item.get("ref"):
                citations[item["ref"]] = item["text"]

        return AIResult(
            task="explain", provider=self.provider, model=self.model,
            output={"answer": "\n".join(lines), "citations": citations},
            confidence=0.85 if len(matched) == 1 else 0.6,
            evidence_refs=[i["ref"] for i in matched if i.get("ref")],
            requires_human_approval=False,
        )

