from __future__ import annotations

from typing import Any

from sanocea.packages.audit import AuditLedger
from sanocea.packages.connector_sdk import MutationRequest
from sanocea.packages.domain_contract.models import (
    ConnectorCommand,
    ExceptionRecord,
    ExternalIdMapping,
    ListingVerification,
    ProductDraft,
    Publication,
    PublicationAttempt,
    now_utc,
)
from sanocea.packages.exceptions import ExceptionCategory, ExceptionService


class ProductPublicationService:
    def __init__(self, store, storefront_connector) -> None:
        self.store = store
        # storefront_connector may be a single connector (existing single-platform callers, unchanged
        # behavior) or a StorefrontConnectorRegistry (multi-merchant/multi-platform) - as_resolver()
        # normalizes both into self.storefront(merchant_id) -> the right connector for THAT merchant.
        from sanocea.packages.runtime.storefront_registry import as_resolver

        self.storefront = as_resolver(storefront_connector)
        self.audit = AuditLedger(store)
        self.exceptions = ExceptionService(store)

    def _prepare_publish_payload(self, draft: ProductDraft) -> dict[str, Any]:
        """A CONNECTOR-AGNOSTIC payload - title/sku/price/currency/product_type/attributes, no
        Shopify-specific wire shape (variants array, metafields namespace/key/value). Each connector's
        own execute_mutation() is responsible for translating this into whatever shape its own platform
        actually needs (Shopify: variants+metafields; WooCommerce: its own product body) - moved behind
        each connector's boundary. This fixes a real leak found in multi-platform connector hardening:
        this method used to be named prepare_shopify_payload() and build Shopify's own wire shape
        directly, forcing every OTHER connector (WooCommerce today, any future platform) to reverse the
        Shopify-specific shape back out of a "canonical" payload that was never actually canonical."""
        if "internal_only_field" in draft.attributes:
            raise ValueError("draft contains a field that must never be published externally: internal_only_field")
        return {
            "title": draft.title,
            "product_type": draft.product_type,
            "sku": draft.sku,
            "price": f"{(draft.price or 0) / 100:.2f}",
            "currency": draft.currency,
            "attributes": {k: str(v) for k, v in draft.attributes.items() if v not in (None, "")},
        }

    def create_publication(self, merchant_id: str, draft_id: str, channel_id: str) -> Publication:
        """Phase 4.6: get-or-create by (draft_id, channel_id) - a duplicate publication REQUEST for the
        same draft+channel must reuse the same Publication row rather than minting a second one, so a
        retried/duplicated command can never end up driving two independent publish() calls (each of
        which mints its own PublicationAttempt) toward the same external listing. This is on top of,
        not instead of, the connector-mutation-level idempotency key in publish() below - defence at
        both the canonical-entity layer and the external-mutation layer."""
        existing = self.store.find_one(Publication, merchant_id, product_draft_id=draft_id, channel_id=channel_id)
        if existing is not None and existing.status in ("approved", "publishing", "published"):
            return existing
        draft = self.store.get(ProductDraft, merchant_id, draft_id)
        if draft.state not in ("READY", "NEEDS_APPROVAL") or not draft.approved_for_publication:
            self.exceptions.create(
                merchant_id=merchant_id,
                category=ExceptionCategory.MISSING_REQUIRED_ATTRIBUTE if draft.state == "INCOMPLETE" else ExceptionCategory.AMBIGUOUS_PRODUCT_DATA,
                message=f"Product draft {draft.id} is not approved for publication: {draft.state}",
                object_id=draft.id,
                evidence_ref=draft.evidence_refs[0] if draft.evidence_refs else None,
            )
            raise ValueError("draft not publishable")
        publication = existing or Publication(
            merchant_id=merchant_id,
            product_draft_id=draft.id,
            channel_id=channel_id,
            status="approved",
        )
        publication.status = "approved"
        self.store.put(publication)
        return publication

    def publish(self, merchant_id: str, publication_id: str) -> ListingVerification:
        publication = self.store.get(Publication, merchant_id, publication_id)
        draft = self.store.get(ProductDraft, merchant_id, publication.product_draft_id)
        try:
            payload = self._prepare_publish_payload(draft)
        except Exception as exc:
            self.exceptions.create(
                merchant_id=merchant_id,
                category=ExceptionCategory.NON_PUBLISHABLE_ATTRIBUTE,
                message=str(exc),
                object_id=draft.id,
                evidence_ref=draft.evidence_refs[0] if draft.evidence_refs else None,
            )
            raise
        connector = self.storefront(merchant_id)
        command = ConnectorCommand(
            merchant_id=merchant_id,
            connector=connector.name,
            action="publish_product",
            object_type="ProductDraft",
            object_id=draft.id,
            payload=payload,
            idempotency_key=f"publish:{draft.id}:{publication.channel_id}",
            policy_decision="ALLOW" if draft.approved_for_publication else "REQUIRE_APPROVAL",
            status="approved" if draft.approved_for_publication else "pending",
        )
        self.store.put(command)
        publication.connector_command_id = command.id
        publication.status = "publishing"
        self.store.put(publication)
        attempt = PublicationAttempt(
            merchant_id=merchant_id,
            publication_id=publication.id,
            connector_command_id=command.id,
            request_payload=payload,
        )
        self.store.put(attempt)
        try:
            result = connector.execute_mutation(
                MutationRequest(
                    merchant_id=merchant_id,
                    action="publish_product",
                    object_type="ProductDraft",
                    payload=payload,
                    idempotency_key=command.idempotency_key,
                )
            )
        except Exception as exc:
            command.status = "failed"
            attempt.status = "failed"
            attempt.error = str(exc)
            self.store.put(command)
            self.store.put(attempt)
            self.exceptions.create(
                merchant_id=merchant_id,
                category=ExceptionCategory.PUBLICATION_FAILED,
                message=str(exc),
                object_id=draft.id,
                evidence_ref=draft.evidence_refs[0] if draft.evidence_refs else None,
            )
            raise
        command.status = "succeeded"
        command.external_ref = result.external_ref
        command.result = result.model_dump(mode="json")
        attempt.status = "succeeded"
        attempt.response_payload = result.model_dump(mode="json")
        publication.status = "published"
        publication.external_product_id = result.external_ref
        publication.published_at = now_utc()
        self.store.put(command)
        self.store.put(attempt)
        self.store.put(publication)
        self.store.put_external_mapping(
            ExternalIdMapping(
                merchant_id=merchant_id,
                sanocea_entity_type="Publication",
                sanocea_id=publication.id,
                external_system=connector.name,
                external_entity_type="product",
                external_id=str(result.external_ref),
                channel_id=publication.channel_id,
            )
        )
        return self.verify(merchant_id, publication.id)

    def verify(self, merchant_id: str, publication_id: str) -> ListingVerification:
        publication = self.store.get(Publication, merchant_id, publication_id)
        draft = self.store.get(ProductDraft, merchant_id, publication.product_draft_id)
        try:
            external = self.storefront(merchant_id).fetch(merchant_id, "product", str(publication.external_product_id))
        except Exception as exc:
            verification = ListingVerification(
                merchant_id=merchant_id,
                publication_id=publication.id,
                external_product_id=publication.external_product_id,
                outcome="FAILED",
                mismatches=[str(exc)],
            )
            self.store.put(verification)
            return verification
        # Compares against the CONNECTOR-NORMALIZED shape (title/sku/price/status - status always
        # "active"/"inactive") every connector's fetch("product", ...) must return - never a
        # provider-specific raw field name/vocabulary. See ShopifyConnector.fetch()'s docstring for the
        # leak this closed.
        mismatches = []
        if external.get("title") != draft.title:
            mismatches.append("title")
        if external.get("sku") != draft.sku:
            mismatches.append("sku")
        if external.get("price") != f"{(draft.price or 0) / 100:.2f}":
            mismatches.append("price")
        if external.get("status") != "active":
            mismatches.append("publication_status")
        outcome = "MISMATCH" if mismatches else "VERIFIED"
        verification = ListingVerification(
            merchant_id=merchant_id,
            publication_id=publication.id,
            external_product_id=publication.external_product_id,
            outcome=outcome,
            checked_fields={"title": external.get("title"), "sku": external.get("sku"), "price": external.get("price"), "status": external.get("status")},
            mismatches=mismatches,
        )
        self.store.put(verification)
        if mismatches:
            self.exceptions.create(
                merchant_id=merchant_id,
                category=ExceptionCategory.PUBLICATION_VERIFICATION_MISMATCH,
                message=f"Publication {publication.id} mismatched fields: {', '.join(mismatches)}",
                object_id=publication.id,
            )
        self.audit.record(
            merchant_id=merchant_id,
            actor="publication",
            source=self.storefront(merchant_id).name,
            action="listing_verified",
            object_type="Publication",
            object_id=publication.id,
            result=outcome,
        )
        return verification
