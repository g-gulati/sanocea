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
    # intentionally NOT a language model. It never fabricates an answer: a question is first classified
    # into one of a FIXED set of operational intents (pricing, inventory, dispatch, delivery_delay, ndr,
    # rto, reconciliation, listing, approvals) by keyword match, then evidence is filtered by the
    # deterministic engine's OWN category/action fields for that intent ONLY - never a fuzzy cross-
    # category text-overlap score. This is deliberate: a loose keyword match ("pricing" vs. some unrelated
    # exception's text) previously produced a confidently wrong answer (a real fulfilment-delay exception
    # returned for a pricing question). The rule now is: strong category evidence, or an explicit "no
    # matching issue found" - never a broadened, lower-confidence guess. Swapping in a real LLM-backed
    # provider later is a drop-in: same AIProvider.explain signature, same evidence-only input.
    INTENTS: dict[str, dict[str, Any]] = {
        "pricing": {
            "keywords": ("pric", "discount", "promotion"),
            "exception_categories": ("cross_channel_listing_variance",),
            "approval_actions": ("price_change",),
        },
        "inventory": {
            "keywords": ("inventory", "stock", "out of stock", "oos", "stockout", "stock-out"),
            "exception_categories": ("inventory_conflict",),
            "approval_actions": ("resolve_inventory_shortage",),
        },
        "dispatch": {
            "keywords": ("dispatch", "fulfilment", "fulfillment", "order issue", "order problem"),
            "exception_categories": ("fulfilment_delay",),
            "approval_actions": ("escalate_fulfilment_delay",),
        },
        "rto": {
            # RTO-risk shipments are seeded under the same "shipment_delay" category as ordinary delays
            # (see packages/prospect_demo/scenarios.py::seed_delivery_exceptions_scenario) - disambiguated
            # from a plain delay by requiring the record's OWN text to actually say "RTO".
            "keywords": ("rto", "return to origin", "return-to-origin"),
            "exception_categories": ("shipment_delay",),
            "approval_actions": ("resolve_delivery_exception",),
            "require_text_contains": ("rto",),
        },
        "ndr": {
            "keywords": ("ndr", "non-delivery", "non delivery", "undelivered", "delivery report"),
            "exception_categories": ("ndr_detected",),
        },
        "delivery_delay": {
            "keywords": ("delay", "delayed", "late", "shipment", "transit", "delivery issue", "delivery"),
            "exception_categories": ("shipment_delay",),
            # excludes the RTO-flagged item above so a generic "delivery delay" question doesn't also
            # surface the RTO case under a different heading - "rto" questions have their own intent.
            "exclude_text_contains": ("rto",),
        },
        "reconciliation": {
            "keywords": ("reconcil", "settlement", "payment", "discrepanc"),
            "exception_categories": ("payment_inconsistency",),
        },
        "listing": {
            "keywords": ("listing", "content", "catalogue", "catalog"),
            "exception_categories": ("cross_channel_listing_variance",),
        },
        "approvals": {
            "keywords": ("approval", "approve", "decision", "pending", "sign off", "sign-off"),
            "approval_actions": "ALL",
        },
    }

    def _detect_intent(self, question: str) -> str | None:
        lowered = question.lower()
        for intent, spec in self.INTENTS.items():
            if any(kw in lowered for kw in spec["keywords"]):
                return intent
        return None

    # A named channel (e.g. "Blinkit", "Amazon") is a precise, unambiguous reference - unlike a generic
    # word, matching a question against it can't accidentally retrieve an unrelated category the way
    # broad keyword-overlap scoring did, so this is safe to check even when no category-intent matched.
    _CHANNEL_NAMES = ("blinkit", "amazon", "flipkart", "shopify", "jiomart", "swiggy instamart", "swiggy", "tata 1mg", "shiprocket")

    def explain(self, question: str, evidence: dict[str, Any], evidence_refs: list[str]) -> AIResult:
        lowered_q = question.lower()
        intent = self._detect_intent(question)

        if intent is None:
            channel = next((c for c in self._CHANNEL_NAMES if c in lowered_q), None)
            if channel is None:
                return AIResult(
                    task="explain", provider=self.provider, model=self.model,
                    output={"answer": "I don't have evidence for that. Try asking about pricing, inventory, dispatch, delivery delays, NDR/RTO, reconciliation, listing/content, or approvals.", "citations": {}},
                    confidence=0.0, evidence_refs=[], requires_human_approval=False,
                )
            all_items = self._collect_items(evidence, "ALL")
            matched = [i for i in all_items if channel in i["text"].lower()]
            if not matched:
                return AIResult(
                    task="explain", provider=self.provider, model=self.model,
                    output={"answer": f"I don't see any open issues mentioning {channel.title()} for this tenant right now.", "citations": {}},
                    confidence=0.9, evidence_refs=[], requires_human_approval=False,
                )
            return self._format_result(matched)

        spec = self.INTENTS[intent]
        items = self._collect_items(evidence, spec.get("approval_actions", ()), spec.get("exception_categories", ()))

        require = spec.get("require_text_contains")
        if require:
            items = [i for i in items if any(kw in i["text"].lower() for kw in require)]
        exclude = spec.get("exclude_text_contains")
        if exclude:
            items = [i for i in items if not any(kw in i["text"].lower() for kw in exclude)]

        if not items:
            label = intent.replace("_", " ")
            return AIResult(
                task="explain", provider=self.provider, model=self.model,
                output={"answer": f"I don't see any open {label} issues for this tenant right now.", "citations": {}},
                confidence=0.9, evidence_refs=[], requires_human_approval=False,
            )
        return self._format_result(items)

    @staticmethod
    def _collect_items(evidence: dict[str, Any], approval_actions, exception_categories: tuple = ()) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for exc in evidence.get("exceptions", []) or []:
            if approval_actions == "ALL" or exc.get("category") in exception_categories:
                items.append({
                    "ref": exc.get("id"), "severity": exc.get("severity"), "text": exc.get("message") or "",
                    "remediation_options": exc.get("remediation_options") or [],
                })
        for appr in evidence.get("approvals", []) or []:
            if approval_actions == "ALL" or appr.get("action") in approval_actions:
                summary = appr.get("summary") or appr.get("action", "").replace("_", " ")
                items.append({
                    "ref": appr.get("id"), "severity": None, "text": summary,
                    "recommendation": appr.get("recommendation"),
                })
        return items

    def _format_result(self, items: list[dict[str, Any]]) -> AIResult:
        lines = []
        citations: dict[str, str] = {}
        for item in items[:5]:
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
            confidence=0.9, evidence_refs=[i["ref"] for i in items if i.get("ref")],
            requires_human_approval=False,
        )

