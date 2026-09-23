from __future__ import annotations

from typing import Any

from sanocea.packages.audit import AuditLedger
from sanocea.packages.connector_sdk import MutationRequest
from sanocea.packages.domain_contract.models import (
    ConnectorCommand,
    ExceptionRecord,
    ExternalIdMapping,
    ListingVerification,
    Merchant,
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
        from sanocea.packages.runtime.storefront_registry import as_channel_resolver, as_resolver

        self.storefront = as_resolver(storefront_connector)
        # Step 9Q.2 - publish()/verify() below are the one existing case that already carries a SPECIFIC
        # channel_id (Publication.channel_id) even before any merchant has more than one storefront -
        # this resolves the CORRECT connector for that channel rather than self.storefront(merchant_id)'s
        # "whichever channel happens to be first" behavior, which only ever mattered once a merchant
        # actually has two storefronts (Step 9Q.2's Shopify+Flipkart scenario is the first one built).
        self.storefront_for_channel = as_channel_resolver(storefront_connector)
        self.audit = AuditLedger(store)
        self.exceptions = ExceptionService(store)

    def _prepare_publish_payload(self, merchant_id: str, draft: ProductDraft) -> dict[str, Any]:
        """A CONNECTOR-AGNOSTIC payload - title/sku/price/currency/product_type/attributes/options/variants.
        Each connector translates this into its platform-specific wire shape."""
        if "internal_only_field" in draft.attributes:
            raise ValueError("draft contains a field that must never be published externally: internal_only_field")

        # Real gap found live (Premium Basket rehearsal, screenshot evidence): a published product's
        # storefront vendor showed the DEV STORE's own default ("Sanocea Commerce OS Dev") instead of the
        # merchant's real name - no CSV/WhatsApp field ever sets attributes["vendor"], so it was always
        # absent and Shopify fell back to its own default. This is not a guess (unlike product taxonomy
        # category, deliberately left unmapped below in the connector - see its own comment): every
        # product onboarded through THIS merchant's own catalogue upload is, by definition, sold by this
        # merchant, so defaulting vendor to their real display_name is a correct fact, not an invention -
        # only applied when the draft didn't already carry an explicit vendor value of its own.
        attributes = dict(draft.attributes)
        if not attributes.get("vendor"):
            try:
                merchant = self.store.get(Merchant, merchant_id, merchant_id)
                if merchant and getattr(merchant, "display_name", None):
                    attributes["vendor"] = merchant.display_name
            except Exception:
                pass

        variants_payload = []
        for v in draft.variants:
            if v.status == "ACTIVE":
                variants_payload.append({
                    "id": v.id,
                    "sku": v.sku,
                    "barcode": v.barcode,
                    "price": f"{(v.price or draft.price or 0) / 100:.2f}",
                    "compare_at_price": f"{v.compare_at_price / 100:.2f}" if v.compare_at_price else None,
                    "option_values": v.option_values,
                    "inventory_quantity": v.inventory_quantity,
                })

        category = draft.category or draft.attributes.get("category") or draft.attributes.get("recommended_category_id")
        return {
            "title": draft.title,
            "product_type": draft.product_type,
            "category": category,
            "sku": draft.sku,
            "price": f"{(draft.price or 0) / 100:.2f}",
            "currency": draft.currency,
            "attributes": {k: str(v) for k, v in attributes.items() if v not in (None, "")},
            "options": draft.options,
            "variants": variants_payload,
            "track_inventory": draft.attributes.get("track_inventory") is not False,
            "inventory_quantity": draft.attributes.get("inventory_quantity"),
            "inventory_location": draft.attributes.get("inventory_location"),
            "inventory_location_id": draft.attributes.get("inventory_location_id"),
            "weight": draft.attributes.get("weight"),
            "weight_unit": draft.attributes.get("weight_unit") or "GRAMS",
            "requires_shipping": draft.attributes.get("requires_shipping", True) is not False and not draft.attributes.get("is_digital"),
        }

    def create_publication(self, merchant_id: str, draft_id: str, channel_id: str) -> Publication:
        """Phase 4.6: get-or-create by (draft_id, channel_id) - a duplicate publication REQUEST for the
        same draft+channel must reuse the same Publication row rather than minting a second one."""
        existing = self.store.find_one(Publication, merchant_id, product_draft_id=draft_id, channel_id=channel_id)
        if existing is not None and existing.status in ("approved", "publishing", "published"):
            return existing
        draft = self.store.get(ProductDraft, merchant_id, draft_id)
        if (
            draft.state not in ("READY", "NEEDS_APPROVAL")
            or not draft.approved_for_publication
            or draft.conflicts
            or draft.identity_status != "RESOLVED"
        ):
            self.exceptions.create(
                merchant_id=merchant_id,
                category=ExceptionCategory.CONFLICTING_PRODUCT_EVIDENCE if (draft.conflicts or draft.identity_status in ("CONFLICT", "AMBIGUOUS")) else (ExceptionCategory.MISSING_REQUIRED_ATTRIBUTE if draft.state == "INCOMPLETE" else ExceptionCategory.AMBIGUOUS_PRODUCT_DATA),
                message=f"Product draft {draft.id} is not approved for publication: state={draft.state}, identity={draft.identity_status} (conflicts: {draft.conflicts})",
                object_id=draft.id,
                evidence_ref=draft.evidence_refs[0] if draft.evidence_refs else None,
            )
            raise ValueError(f"draft not publishable: state={draft.state}, identity={draft.identity_status}")
        publication = existing or Publication(
            merchant_id=merchant_id,
            product_draft_id=draft.id,
            channel_id=channel_id,
            status="approved",
        )
        publication.status = "approved"
        self.store.put(publication)
        return publication

    def _attempt_count(self, merchant_id: str, publication_id: str) -> int:
        return sum(1 for a in self.store.list(PublicationAttempt, merchant_id) if a.publication_id == publication_id)

    def publish(self, merchant_id: str, publication_id: str) -> ListingVerification:
        publication = self.store.get(Publication, merchant_id, publication_id)
        draft = self.store.get(ProductDraft, merchant_id, publication.product_draft_id)
        if draft.state != "READY" or not draft.approved_for_publication or draft.conflicts or draft.identity_status != "RESOLVED":
            raise ValueError(
                f"Product draft {draft.id} is not publishable: state={draft.state}, approved={draft.approved_for_publication}, "
                f"conflicts={draft.conflicts}, identity_status={draft.identity_status}"
            )
        try:
            payload = self._prepare_publish_payload(merchant_id, draft)
        except Exception as exc:
            self.exceptions.create(
                merchant_id=merchant_id,
                category=ExceptionCategory.NON_PUBLISHABLE_ATTRIBUTE,
                message=str(exc),
                object_id=draft.id,
                evidence_ref=draft.evidence_refs[0] if draft.evidence_refs else None,
            )
            raise
        connector = self.storefront_for_channel(merchant_id, publication.channel_id)
        command = ConnectorCommand(
            merchant_id=merchant_id,
            connector=connector.name,
            action="publish_product",
            object_type="ProductDraft",
            object_id=draft.id,
            payload=payload,
            # Real bug class found live (see auto_publish_after_resolution for the sibling one): this key
            # used to be fixed per draft+channel, so once a draft had been published, a later publish of
            # that SAME draft (e.g. after the product was deleted in Shopify) replayed the cached result
            # and never touched Shopify. The attempt number makes each genuine re-publish a distinct
            # operation. Safe against double-creates because the Shopify connector itself upserts by SKU
            # (_find_product_gid_by_sku) - a repeat attempt updates the same product, never duplicates it.
            idempotency_key=f"publish:{draft.id}:{publication.channel_id}:a{self._attempt_count(merchant_id, publication.id)}",
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
            external = self.storefront_for_channel(merchant_id, publication.channel_id).fetch(merchant_id, "product", str(publication.external_product_id))
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
        if draft.product_type and "product_type" in external and external.get("product_type") != draft.product_type:
            mismatches.append("product_type")
        expected_category = draft.category or draft.attributes.get("category") or draft.attributes.get("recommended_category_id")
        if expected_category and "category" in external and external.get("category") != expected_category:
            mismatches.append("category")
        if draft.attributes.get("track_inventory") is not False and "inventory_tracked" in external:
            if external.get("inventory_tracked") is False:
                mismatches.append("inventory_tracked")
            if draft.attributes.get("inventory_quantity") is not None and "inventory_quantity" in external:
                if external.get("inventory_quantity") != draft.attributes.get("inventory_quantity"):
                    mismatches.append("inventory_quantity")
        checked = {
            "title": external.get("title"),
            "sku": external.get("sku"),
            "price": external.get("price"),
            "status": external.get("status"),
            "product_type": external.get("product_type"),
            "category": external.get("category"),
            "category_full_name": external.get("category_full_name"),
            "inventory_quantity": external.get("inventory_quantity"),
            "inventory_tracked": external.get("inventory_tracked"),
            "inventory_policy": external.get("inventory_policy"),
        }
        outcome = "MISMATCH" if mismatches else "VERIFIED"
        verification = ListingVerification(
            merchant_id=merchant_id,
            publication_id=publication.id,
            external_product_id=publication.external_product_id,
            outcome=outcome,
            checked_fields={k: v for k, v in checked.items() if v is not None},
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
            source=self.storefront_for_channel(merchant_id, publication.channel_id).name,
            action="listing_verified",
            object_type="Publication",
            object_id=publication.id,
            result=outcome,
        )
        return verification
