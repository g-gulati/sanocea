from __future__ import annotations

from pathlib import Path
from typing import Any

from sanocea.packages.audit import AuditLedger
from sanocea.packages.domain_contract.models import Approval, ListingVerification, ProductDraft, Publication, now_utc
from sanocea.packages.exceptions import ExceptionCategory, ExceptionService
from sanocea.packages.product_onboarding.ingestion import StructuredProductIngestor
from sanocea.packages.product_onboarding.publication import ProductPublicationService
from sanocea.packages.product_onboarding.validation import ProductCompletenessValidator


class ProductOnboardingWorkflow:
    """Journey A, end to end: supplier/product input -> ingestion -> ProductDraft -> deterministic
    validation/completeness -> approval where required -> publication -> external/read-back
    verification -> canonical listing state. Phase 4.6 wires this behind authenticated command/query
    surfaces in apps/api rather than exposing StructuredProductIngestor/ProductCompletenessValidator/
    ProductPublicationService's individual methods directly - those stay internal collaborators."""

    def __init__(self, store, storage, storefront_connector) -> None:
        self.store = store
        self.ingestor = StructuredProductIngestor(store, storage)
        self.validator = ProductCompletenessValidator(store)
        self.publisher = ProductPublicationService(store, storefront_connector)
        self.audit = AuditLedger(store)
        self.exceptions = ExceptionService(store)

    def ingest_file(self, merchant_id: str, path: Path, content_type: str) -> list[ProductDraft]:
        """Ingest a supplier file (CSV/XLSX) into validated ProductDrafts. A draft that needs corrective
        work becomes a visible ExceptionRecord; a draft whose extracted facts need a human sign-off
        becomes a real, queryable Approval - never a silent state only visible by reading the row."""
        drafts = self.ingestor.ingest_file(merchant_id, path, content_type)
        validated = [self.validator.validate(draft) for draft in drafts]
        for draft in validated:
            if draft.state in ("INCOMPLETE", "CONFLICTED", "INVALID"):
                category = ExceptionCategory.CONFLICTING_PRODUCT_EVIDENCE if draft.state == "CONFLICTED" else ExceptionCategory.MISSING_REQUIRED_ATTRIBUTE
                self.exceptions.create(
                    merchant_id=merchant_id,
                    category=category,
                    message=f"Product draft {draft.id} requires corrective work: {draft.state}",
                    object_id=draft.id,
                    evidence_ref=draft.evidence_refs[0] if draft.evidence_refs else None,
                )
            elif draft.state == "NEEDS_APPROVAL":
                existing = self.store.find_one(Approval, merchant_id, action="approve_product_facts", object_id=draft.id, status="pending")
                if existing is None:
                    self.store.put(Approval(merchant_id=merchant_id, action="approve_product_facts", object_id=draft.id, requested_by="product_onboarding"))
        return validated

    def approve_product_facts(self, merchant_id: str, draft_id: str, approver_id: str) -> ProductDraft:
        """Resolves the pending approve_product_facts Approval (if any) with a real authenticated
        approver identity, then re-validates - a draft may move straight to READY here."""
        draft = self.store.get(ProductDraft, merchant_id, draft_id)
        approval = self.store.find_one(Approval, merchant_id, action="approve_product_facts", object_id=draft_id, status="pending")
        if approval is not None:
            approval.status = "approved"
            approval.decided_by = approver_id
            approval.decided_at = now_utc()
            self.store.put(approval)
        draft = self.validator.approve_extracted_facts(draft, approver_id)
        self.audit.record(merchant_id=merchant_id, actor=approver_id, source="product_onboarding", action="product_facts_approved", object_type="ProductDraft", object_id=draft.id, result=draft.state)
        return draft

    def request_publication(self, merchant_id: str, draft_id: str, channel_id: str, requested_by: str) -> dict[str, Any]:
        """The single safe entrypoint for publishing a draft. Applies the SAME deterministic publication
        policy (packages/product_onboarding/validation.py::apply_publication_policy) that the Phase 1
        workload always used but ProductOnboardingWorkflow itself never called - closing a real gap
        found while wiring this phase: the old approve_and_publish() force-published every draft handed
        to it, bypassing ALLOW/REQUIRE_APPROVAL/EXCEPTION policy entirely.

        Outcomes:
          AUTO_PUBLISH      -> publishes immediately, returns the ListingVerification.
          REQUIRE_APPROVAL  -> creates a real, queryable Approval; returns pending state, no publish.
          EXCEPTION         -> creates a visible ExceptionRecord; returns blocked state, no publish.
        """
        draft = self.store.get(ProductDraft, merchant_id, draft_id)
        draft = self.validator.validate(draft)
        decision = self.validator.apply_publication_policy(draft)
        if decision.outcome == "EXCEPTION":
            self.exceptions.create(
                merchant_id=merchant_id, category=ExceptionCategory.AMBIGUOUS_PRODUCT_DATA,
                message=f"Product draft {draft.id} cannot be published: {', '.join(decision.reasons)}",
                object_id=draft.id, evidence_ref=draft.evidence_refs[0] if draft.evidence_refs else None,
            )
            return {"outcome": "blocked", "reasons": decision.reasons, "draft_id": draft.id}
        if decision.outcome == "REQUIRE_APPROVAL":
            existing = self.store.find_one(Approval, merchant_id, action="approve_publication", object_id=draft.id, status="pending")
            if existing is None:
                self.store.put(Approval(merchant_id=merchant_id, action="approve_publication", object_id=draft.id, requested_by=requested_by))
            return {"outcome": "pending_approval", "reasons": decision.reasons, "draft_id": draft.id}
        # AUTO_PUBLISH - apply_publication_policy already set draft.approved_for_publication=True.
        verification = self._publish(merchant_id, draft.id, channel_id)
        return {"outcome": "published", "reasons": decision.reasons, "draft_id": draft.id, "verification": verification.model_dump(mode="json")}

    def approve_publication(self, merchant_id: str, draft_id: str, channel_id: str, approver_id: str) -> dict[str, Any]:
        """Resolves a pending approve_publication Approval with a real authenticated identity, then
        publishes. Never used to force-publish a draft that was never policy-evaluated - a caller must
        go through request_publication() first, exactly like refund/PO approval mirrors their own
        evaluate_*()-then-approve_*() pattern."""
        approval = self.store.find_one(Approval, merchant_id, action="approve_publication", object_id=draft_id, status="pending")
        if approval is None:
            raise ValueError(f"no pending publication approval for draft {draft_id}")
        approval.status = "approved"
        approval.decided_by = approver_id
        approval.decided_at = now_utc()
        self.store.put(approval)
        draft = self.validator.approve_publication(self.store.get(ProductDraft, merchant_id, draft_id), approver_id)
        verification = self._publish(merchant_id, draft.id, channel_id)
        return {"outcome": "published", "draft_id": draft.id, "verification": verification.model_dump(mode="json")}

    def _publish(self, merchant_id: str, draft_id: str, channel_id: str) -> ListingVerification:
        """create_publication() is idempotent by (draft_id, channel_id) and publish() is idempotent at
        the connector-mutation layer (idempotency_key=f"publish:{draft_id}:{channel_id}") - a duplicate
        call here (retried command, duplicated approval click) can never create a second external
        product/listing."""
        publication = self.publisher.create_publication(merchant_id, draft_id, channel_id)
        if publication.status == "published":
            return self.reverify(merchant_id, publication.id)
        return self.publisher.publish(merchant_id, publication.id)

    def reverify(self, merchant_id: str, publication_id: str) -> ListingVerification:
        return self.publisher.verify(merchant_id, publication_id)

    # --- Backward-compatible convenience wrapper (no external caller depends on the old force-publish
    # behaviour - see grep audit performed before this rewrite) ---------------------------------------

    def approve_and_publish(self, merchant_id: str, draft_id: str, channel_id: str, actor: str) -> ListingVerification:
        draft = self.store.get(ProductDraft, merchant_id, draft_id)
        draft = self.validator.approve_extracted_facts(draft, actor)
        draft = self.validator.approve_publication(draft, actor)
        return self._publish(merchant_id, draft.id, channel_id)
