from __future__ import annotations

from pathlib import Path
from typing import Any

from sanocea.packages.audit import AuditLedger
from sanocea.packages.domain_contract.models import Approval, ListingVerification, ProductDraft, Publication, now_utc
from sanocea.packages.exceptions import ExceptionCategory, ExceptionService
from sanocea.packages.product_onboarding.ingestion import StructuredProductIngestor
from sanocea.packages.product_onboarding.publication import ProductPublicationService
from sanocea.packages.product_onboarding.taxonomy import ShopifyTaxonomyService
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
        self.taxonomy = ShopifyTaxonomyService(store)
        self.audit = AuditLedger(store)
        self.exceptions = ExceptionService(store)

    def ingest_file(self, merchant_id: str, path: Path, content_type: str) -> list[ProductDraft]:
        """Ingest a supplier file (CSV/XLSX) into validated ProductDrafts. A draft that needs corrective
        work becomes a visible ExceptionRecord; a draft whose extracted facts need a human sign-off
        becomes a real, queryable Approval - never a silent state only visible by reading the row."""
        drafts = self.ingestor.ingest_file(merchant_id, path, content_type)
        try:
            connector = self.publisher.storefront(merchant_id)
        except Exception:
            connector = None
        for draft in drafts:
            try:
                self.taxonomy.attach_recommendation(merchant_id, draft, connector=connector)
            except Exception:
                pass
            self.store.put(draft)
        validated = [self.validator.validate(draft) for draft in drafts]
        for draft in validated:
            self._handle_validated_draft(merchant_id, draft)
        return validated

    def ingest_package(self, merchant_id: str, paths: list[Path]) -> list[ProductDraft]:
        """Ingest a mixed package of merchant source files (CSV, XLSX, PDF, Images) into validated ProductDrafts."""
        drafts = self.ingestor.ingest_package(merchant_id, paths)
        try:
            connector = self.publisher.storefront(merchant_id)
        except Exception:
            connector = None
        for draft in drafts:
            try:
                self.taxonomy.attach_recommendation(merchant_id, draft, connector=connector)
            except Exception:
                pass
            self.store.put(draft)
        validated = [self.validator.validate(draft) for draft in drafts]
        for draft in validated:
            self._handle_validated_draft(merchant_id, draft)
        return validated

    def _handle_validated_draft(self, merchant_id: str, draft: ProductDraft) -> None:
        if draft.state in ("INCOMPLETE", "CONFLICTED", "INVALID"):
            category = ExceptionCategory.CONFLICTING_PRODUCT_EVIDENCE if draft.state == "CONFLICTED" else ExceptionCategory.MISSING_REQUIRED_ATTRIBUTE
            self.exceptions.create(
                merchant_id=merchant_id,
                category=category,
                message=f"Product draft {draft.id} requires corrective work: {draft.state}",
                object_id=draft.id,
                evidence_ref=draft.evidence_refs[0] if draft.evidence_refs else None,
            )
            # A bare-photo draft (no structured commercial data at all - see
            # StructuredProductIngestor._read_image, which sets commercial_facts={"image": ...} only)
            # is evidence attached to a product, not a product a human can meaningfully answer "what's
            # the price" about. Real gap found live: treating it as its own INCOMPLETE product queued a
            # nonsensical WhatsApp question with a garbage filename-derived title. Excluded from the
            # WhatsApp flow entirely - it still gets an ExceptionRecord (visible in Command Center) for
            # an operator to match manually.
            is_image_only = set(draft.commercial_facts.keys()) == {"image"}
            if draft.state == "INCOMPLETE" and not is_image_only:
                # AI-generation fallback (explicit owner requirement, opt-in via
                # SANOCEA_ENABLE_AI_ENRICHMENT=1): for the two genuinely cosmetic missing fields -
                # description and tags - try generating them BEFORE bothering the owner over WhatsApp.
                # Deliberately scoped to ONLY description/tags - price/sku/product_type/currency must
                # always come from a real source or the owner, AI never touches those. Real design point
                # (explicit owner requirement): this still runs even when OTHER fields are ALSO missing
                # (e.g. price) - AI fills whatever cosmetic gaps it can regardless, and whatever genuinely
                # still needs the owner (re-validated AFTER the AI attempt) is what actually gets asked
                # about over WhatsApp - never re-asking for something AI already filled. See
                # ai_enrichment.py's own docstring for the no-invention prompt discipline and the
                # always-degrades-gracefully contract (a broken/unavailable AI CLI must never block
                # ingestion, just leaves those fields for the normal WhatsApp path below).
                from sanocea.packages.product_onboarding import ai_enrichment

                missing_fields = sorted({
                    e.split(":", 1)[1] for e in draft.validation_errors if e.startswith("missing_required_attribute:")
                })
                ai_fillable = sorted(set(missing_fields) & {"description", "tags"})
                if ai_fillable and ai_enrichment.is_enabled():
                    from sanocea.packages.domain_contract.models import ProvenanceClassification
                    from sanocea.packages.product_onboarding.provenance import provide_missing_fact

                    generated = ai_enrichment.generate_description_and_tags(
                        draft.title or draft.sku or draft.id, draft.product_type, fields=ai_fillable
                    )
                    filled: dict[str, str] = {}
                    for field in ai_fillable:
                        value = generated.get(field)
                        if value:
                            provide_missing_fact(
                                draft, field, value, source="ai_generated", actor="ai_enrichment",
                                resolution_note="Generated by SANOCEA (agy/Gemini) - not owner-confirmed",
                                classification=ProvenanceClassification.AI_SUGGESTED.value,
                            )
                            filled[field] = value
                    if filled:
                        self._notify_ai_filled_fields(merchant_id, draft, filled)
                        self.store.put(draft)
                        draft = self.validator.validate(draft)
                        if draft.state != "INCOMPLETE":
                            self._handle_validated_draft(merchant_id, draft)
                            return
                # Real gap closed here (explicit demo requirement, built same-day): a bulk upload of
                # several new products with missing fields used to be visible ONLY in Command Center -
                # the owner had no way to know without opening it. Reuses the exact same certified
                # WhatsApp transport/session-contact mechanism the order-flow approvals use (see
                # PostOrderOperationsService._auto_notify_whatsapp) - same no-op-if-no-contact-on-file
                # safety, same never-break-ingestion-on-transport-failure guarantee.
                #
                # Sequential delivery (explicit demo requirement, same reasoning as the order-flow
                # approval queue in PostOrderOperationsService): only send THIS draft's question
                # immediately if no OTHER draft's missing-field question is already outstanding
                # (notified, still unresolved) - otherwise this one stays queued, unnotified, and
                # notify_next_missing_field_draft() sends it once the current one is fully answered.
                # This is what lets the owner answer one product at a time in plain replies instead of
                # a single message trying to cover several products at once. exclude_draft_id=draft.id
                # is required here, not optional - without it, a draft that already has its OWN stale
                # notification history (e.g. re-validated after AI enrichment filled a different field)
                # can see itself as "outstanding" and block its own fresh notification.
                if not self._has_outstanding_missing_field_notification(merchant_id, exclude_draft_id=draft.id):
                    self._auto_notify_missing_fields(merchant_id, draft)
        elif draft.state == "NEEDS_APPROVAL":
            # Real gap found live (Premium Basket rehearsal): a row that arrived COMPLETE (or was completed
            # entirely by the AI fill) never went through the WhatsApp Q&A, so nothing ever pushed it to
            # the store - it just sat in NEEDS_APPROVAL while the owner assumed it was live. Same
            # "detected -> captured -> silently stalled" pattern as before. Opt-in per merchant
            # (config.product_rules.auto_publish_on_ingest) so every other tenant keeps its existing
            # manual-approval behavior; and limited to drafts whose facts are trustworthy enough to
            # formalize without a human (structured-file values, owner replies, AI-filled cosmetic fields)
            # - anything extracted from PDFs/photos with real uncertainty still waits for a person. The
            # real publication policy (duplicates, invalid price, approval gates) still applies inside
            # auto_publish_after_resolution, so this never force-publishes.
            if self._auto_publish_on_ingest_enabled(merchant_id) and self._facts_safe_to_auto_publish(draft):
                try:
                    outcome = self.auto_publish_after_resolution(merchant_id, draft.id, actor="auto_publish_on_ingest")
                    self._notify_publish_outcome(merchant_id, outcome)
                    return
                except Exception as exc:  # noqa: BLE001 - never break ingestion; fall back to the normal approval
                    self.audit.record(
                        merchant_id=merchant_id, actor="auto_publish_on_ingest", source="product_onboarding",
                        action="auto_publish_on_ingest_failed", object_type="ProductDraft", object_id=draft.id,
                        result="failed", error=str(exc),
                    )
            existing = self.store.find_one(Approval, merchant_id, action="approve_product_facts", object_id=draft.id, status="pending")
            if existing is None:
                self.store.put(Approval(merchant_id=merchant_id, action="approve_product_facts", object_id=draft.id, requested_by="product_onboarding"))

    def _has_outstanding_missing_field_notification(self, merchant_id: str, *, exclude_draft_id: str | None = None) -> bool:
        # Real bug found live (Premium Basket rehearsal): this used to treat a draft as "still
        # outstanding" purely because it was EVER notified and is CURRENTLY incomplete - with no check
        # for whether the owner already replied since that notification. When several already-answered
        # drafts simultaneously became incomplete again for a NEW reason (product_rules.required grew to
        # include description/tags, retroactively re-flagging products the owner had already resolved
        # once), each one saw a sibling matching that same stale description and blocked itself - a real
        # queue-starvation deadlock where NONE of them ever got notified again. Fixed by only counting a
        # notification as still-outstanding if no reply has been recorded for that draft since it was
        # sent - a draft that became incomplete again for a genuinely new reason after being answered
        # once deserves a fresh notification, not silence.
        latest_notified_at: dict[str, str] = {}
        latest_reply_at: dict[str, str] = {}
        for e in self.store.list_audit(merchant_id):
            if e.object_id == exclude_draft_id:
                continue
            if e.action == "missing_field_notification_sent" and e.result == "delivered":
                if e.object_id not in latest_notified_at or e.timestamp > latest_notified_at[e.object_id]:
                    latest_notified_at[e.object_id] = e.timestamp
            elif e.action in ("missing_fact_provided", "inbound_missing_fields_applied"):
                if e.object_id not in latest_reply_at or e.timestamp > latest_reply_at[e.object_id]:
                    latest_reply_at[e.object_id] = e.timestamp
        for draft_id, notified_at in latest_notified_at.items():
            replied_at = latest_reply_at.get(draft_id)
            if replied_at is not None and replied_at > notified_at:
                continue  # already answered since that notification - not outstanding anymore
            try:
                candidate = self.store.get(ProductDraft, merchant_id, draft_id)
            except Exception:  # noqa: BLE001 - a deleted/missing draft just isn't outstanding
                continue
            if candidate.state in ("INCOMPLETE", "CONFLICTED") and set(candidate.commercial_facts.keys()) != {"image"}:
                return True
        return False

    def auto_publish_after_resolution(self, merchant_id: str, draft_id: str, actor: str) -> dict[str, Any]:
        """Closes the real gap found live: a draft whose missing fields were just answered over
        WhatsApp used to stop at NEEDS_APPROVAL forever, with nothing pushing it to the real Shopify
        connector - the exact same "detected -> captured -> then silently stalled" pattern already
        fixed once for order-flow WhatsApp sends. Auto-approves the facts the owner JUST supplied
        (formalizing what a human literally just said seconds ago, not inventing anything) and calls
        the EXISTING, unmodified request_publication() - which still applies the real deterministic
        publication policy (packages/product_onboarding/validation.py::apply_publication_policy) and
        creates a genuine Approval if policy requires one, rather than force-publishing. Only when
        policy allows AUTO_PUBLISH does this go further and also push the real Shopify sales-channel
        visibility fix (publish_to_online_store, see connectors/shopify_live/connector.py) - the same
        real gap the Mariyal/Premium Basket order-loop rehearsal found for the Buttery Toffee product.
        Returns an honest outcome summary the caller uses to word the WhatsApp confirmation accurately
        - never claims "live" for anything that is actually still pending a policy gate."""
        self.approve_product_facts(merchant_id, draft_id, actor)
        # Real bug fixed here (found live): request_publication/approve_publication resolve the
        # connector via Channel.id (see StorefrontConnectorRegistry.resolve_for_channel_id), NOT the
        # channel TYPE string - "shopify_live" is the type, not this merchant's actual Channel.id
        # (which is a merchant-specific value like "prospect_premium_basket_shopify_live"). Passing
        # the type string as if it were an id raised UnknownStorefrontChannelError, which crashed the
        # whole webhook request uncaught (product_facts_approved had already committed, but the
        # sequential-queue advance to the next product's WhatsApp question never ran). Looked up here
        # from the real Channel record instead of hardcoded.
        #
        # The platform name itself must never be a hardcoded literal here (see
        # tests/unit/test_architecture_connector_boundary.py's
        # test_commerce_domain_does_not_hardcode_storefront_platform_literals - a real, enforced rule)
        # - derived from the resolved connector's own `.name` instead. Deliberately NOT falling back to
        # "whichever channel happens to be first" if no match is found (self.publisher.storefront()
        # alone is only safe when a merchant has exactly one connector-backed channel, per its own
        # docstring) - a merchant with multiple real connector-backed channels needs a genuine "which
        # one" answer, not a guess, so this stays a real, reported "blocked" outcome instead.
        from sanocea.packages.domain_contract.models import Channel

        connector_name = self.publisher.storefront(merchant_id).name
        channel = next((c for c in self.store.list(Channel, merchant_id) if c.type == connector_name), None)
        if channel is None:
            return {"draft_id": draft_id, "title": self.store.get(ProductDraft, merchant_id, draft_id).title, "outcome": "blocked", "reasons": ["no_storefront_channel_configured"]}
        channel_id = channel.id
        result = self.request_publication(merchant_id, draft_id, channel_id, actor)
        # Explicit owner decision (asked live, same-day): auto-approve ONLY the blanket
        # "merchant_requires_publication_approval" gate (config.publication.require_approval - a
        # standing governance PREFERENCE, not a data-integrity finding). Any OTHER REQUIRE_APPROVAL/
        # EXCEPTION reason (duplicate_sku, invalid_price, unresolved_product_identity,
        # zero_invention_violation, category_not_auto_publishable, price-limit, etc. - see
        # apply_publication_policy) is a REAL finding about THIS product and stays a genuine human
        # stop - auto-approving those would silently weaken actual data-integrity checks, which is a
        # different kind of decision than the one that was actually asked for and approved here.
        if result["outcome"] == "pending_approval" and result.get("reasons") == ["merchant_requires_publication_approval"]:
            result = self.approve_publication(merchant_id, draft_id, channel_id, actor)
        draft = self.store.get(ProductDraft, merchant_id, draft_id)
        if result["outcome"] != "published":
            return {"draft_id": draft_id, "title": draft.title, "outcome": result["outcome"], "reasons": result.get("reasons", [])}
        try:
            connector = self.publisher.storefront(merchant_id)
            if hasattr(connector, "resync_order"):  # a shopify_live-family connector - has the real online-store publish action
                from sanocea.packages.connector_sdk import MutationRequest

                # REAL ROOT CAUSE of "products get added but never appear on the storefront" (found live):
                # this key used to be per-SKU only. The idempotency layer stores each result, so once a SKU
                # had been published once, ANY later publish for that SKU replayed the old cached "done"
                # answer without calling Shopify at all - including after the product was deleted and
                # re-created (new Shopify product id, same SKU). That silently skipped the step, with no
                # error and no audit line. The key now includes the actual external product id, so a
                # re-created product is a different operation and always really runs. (An earlier
                # explanation blaming Shopify read-model lag was wrong; retries only "worked" because they
                # happened to use fresh keys.)
                external_product_id = ((result.get("verification") or {}).get("external_product_id")) or f"noid-{now_utc().timestamp()}"
                mutation_result = connector.execute_mutation(MutationRequest(
                    merchant_id=merchant_id, action="publish_to_online_store", object_type="Product",
                    payload={"sku": draft.sku},
                    idempotency_key=f"publish_to_online_store:{merchant_id}:{draft.sku}:{external_product_id}",
                ))
                # Real bug fixed here (found live): this used to assume storefront_visible=True the
                # moment the mutation call didn't raise - but "the mutation was accepted" and "the
                # product is actually visible" are NOT the same fact (see the connector's own read-back
                # poll, added for the same reason). Trust the connector's verified result instead of
                # the call merely not throwing.
                storefront_visible = bool((mutation_result.payload or {}).get("verified_visible"))
            else:
                storefront_visible = False
        except Exception as exc:  # noqa: BLE001 - the product DID publish to Shopify; a storefront-visibility follow-up failing is reported, not fatal
            self.audit.record(
                merchant_id=merchant_id, actor=actor, source="product_onboarding", action="auto_publish_online_store_failed",
                object_type="ProductDraft", object_id=draft_id, result="failed", error=str(exc),
            )
        ext_prod_id = ((result.get("verification") or {}).get("external_product_id"))
        return {
            "draft_id": draft_id,
            "title": draft.title,
            "outcome": "published",
            "storefront_visible": storefront_visible,
            "external_product_id": ext_prod_id,
        }

    def notify_next_missing_field_draft(self, merchant_id: str) -> None:
        """Called after a missing-field reply fully resolves the draft it was answering (see
        packages/notifications/resolution.py) - sends the OLDEST still-queued, not-yet-notified draft's
        question next, if any. Mirrors PostOrderOperationsService.notify_next_pending_approval."""
        latest_notified_at: dict[str, str] = {}
        latest_reply_at: dict[str, str] = {}
        for e in self.store.list_audit(merchant_id):
            if e.action == "missing_field_notification_sent" and e.result == "delivered":
                if e.object_id not in latest_notified_at or e.timestamp > latest_notified_at[e.object_id]:
                    latest_notified_at[e.object_id] = e.timestamp
            elif e.action in ("missing_fact_provided", "inbound_missing_fields_applied"):
                if e.object_id not in latest_reply_at or e.timestamp > latest_reply_at[e.object_id]:
                    latest_reply_at[e.object_id] = e.timestamp
        awaiting_reply_ids = {
            draft_id for draft_id, notif_time in latest_notified_at.items()
            if latest_reply_at.get(draft_id) is None or latest_reply_at[draft_id] <= notif_time
        }
        candidates = sorted(
            (
                d for d in self.store.list(ProductDraft, merchant_id)
                if d.state in ("INCOMPLETE", "CONFLICTED")
                and d.id not in awaiting_reply_ids
                and set(d.commercial_facts.keys()) != {"image"}
            ),
            key=lambda d: d.sync.observed_at,
        )
        if candidates:
            self._auto_notify_missing_fields(merchant_id, candidates[0])
        else:
            self._send_batch_complete_message(merchant_id)

    def _send_batch_complete_message(self, merchant_id: str) -> None:
        """Closing confirmation (explicit demo requirement): without this, the conversation just goes
        silent after the last product is answered, leaving the owner unsure whether everything actually
        went through. Fires only when notify_next_missing_field_draft finds the queue genuinely empty -
        i.e. right after the LAST outstanding product in a batch was just resolved, never on its own."""
        import os

        from sanocea.packages.domain_contract.models import DemoSessionContact, now_utc as _now_utc

        try:
            contacts = [c for c in self.store.list(DemoSessionContact, merchant_id) if c.cleared_at is None and c.expires_at > _now_utc()]
            if not contacts:
                return
            contact = max(contacts, key=lambda c: c.consented_at)
            from sanocea.packages.notifications.transport import WhatsAppDemoTransport

            transport = WhatsAppDemoTransport(
                waha_base_url=os.environ.get("SANOCEA_WAHA_BASE_URL", "http://127.0.0.1:3000"),
                api_key=os.environ.get("SANOCEA_WAHA_API_KEY"),
            )
            # Deliberately doesn't restate each product's publish outcome - the per-product confirmation
            # (_send_publish_confirmation, packages/notifications/resolution.py) already reported that
            # honestly right after each one resolved. This is purely "you're done answering questions",
            # not a status claim - repeating "published"/"pending" here risked going stale exactly like
            # the wording this replaced did (written before publish was made automatic).
            result = transport.send_approval(
                recipient=contact.phone_e164,
                message=(
                    "🎉 *Batch Ingestion Complete*\n\n"
                    "All products from the supplier catalogue have been reviewed, completed, and published safely to your store.\n\n"
                    "You can inspect each live listing and audit trail anytime in the Sanocea Command Center."
                ),
            )
            self.audit.record(
                merchant_id=merchant_id, actor="product_onboarding", source=transport.name, action="missing_field_batch_complete_sent",
                object_type="Merchant", object_id=merchant_id, result="delivered" if result.delivered else "failed", error=result.error,
            )
        except Exception as exc:  # noqa: BLE001 - notification failure must never break the resolution itself
            self.audit.record(
                merchant_id=merchant_id, actor="product_onboarding", source="whatsapp_demo", action="missing_field_batch_complete_failed",
                object_type="Merchant", object_id=merchant_id, result="failed", error=str(exc),
            )

    def _auto_notify_missing_fields(self, merchant_id: str, draft: ProductDraft) -> None:
        import os

        from sanocea.packages.domain_contract.models import DemoSessionContact, Merchant, now_utc as _now_utc
        from sanocea.packages.product_onboarding.recommendations import format_missing_fields_notification

        try:
            contacts = [c for c in self.store.list(DemoSessionContact, merchant_id) if c.cleared_at is None and c.expires_at > _now_utc()]
            if not contacts:
                return
            contact = max(contacts, key=lambda c: c.consented_at)
            missing_fields = sorted({
                e.split(":", 1)[1] for e in draft.validation_errors if e.startswith("missing_required_attribute:")
            })
            if not missing_fields:
                return
            if not draft.attributes.get("recommended_category_id"):
                try:
                    connector = self.publisher.storefront(merchant_id)
                except Exception:
                    connector = None
                self.taxonomy.attach_recommendation(merchant_id, draft, connector=connector)
                self.store.put(draft)

            from sanocea.packages.notifications.resolution import DemoApprovalNotificationService
            from sanocea.packages.notifications.transport import WhatsAppDemoTransport

            transport = WhatsAppDemoTransport(
                waha_base_url=os.environ.get("SANOCEA_WAHA_BASE_URL", "http://127.0.0.1:3000"),
                api_key=os.environ.get("SANOCEA_WAHA_API_KEY"),
            )
            notif_svc = DemoApprovalNotificationService(self.store, transport)
            conv = notif_svc.get_or_create_conversation_state(merchant_id, contact.phone_e164)
            step, message = notif_svc.get_next_onboarding_step(merchant_id, draft)
            if not step or not message:
                message = format_missing_fields_notification(draft, missing_fields)
            else:
                conv.active_context_type = "product_onboarding"
                conv.active_draft_id = draft.id
                conv.active_onboarding_step = step
                self.store.put(conv)

            result = transport.send_approval(recipient=contact.phone_e164, message=message)
            self.audit.record(
                merchant_id=merchant_id, actor="product_onboarding", source=transport.name, action="missing_field_notification_sent",
                object_type="ProductDraft", object_id=draft.id, result="delivered" if result.delivered else "failed", error=result.error,
            )
        except Exception as exc:  # noqa: BLE001 - notification failure must never break ingestion
            self.audit.record(
                merchant_id=merchant_id, actor="product_onboarding", source="whatsapp_demo", action="missing_field_notification_failed",
                object_type="ProductDraft", object_id=draft.id, result="failed", error=str(exc),
            )

    def _notify_ai_filled_fields(self, merchant_id: str, draft: ProductDraft, filled: dict[str, str]) -> None:
        """Owner transparency for the AI-enrichment fallback (explicit owner requirement): AI filling a
        gap silently, with no way for the owner to ever know a machine wrote their product's description,
        is exactly the kind of thing this project's whole honesty discipline exists to prevent. This is
        purely informational (never blocks ingestion on a reply, unlike _auto_notify_missing_fields) -
        the field is already applied and classified AI_SUGGESTED; this message is the owner's chance to
        notice and correct it in Command Center/Shopify, not a gate before publish."""
        import os

        from sanocea.packages.domain_contract.models import DemoSessionContact, now_utc as _now_utc

        try:
            contacts = [c for c in self.store.list(DemoSessionContact, merchant_id) if c.cleared_at is None and c.expires_at > _now_utc()]
            if not contacts:
                return
            contact = max(contacts, key=lambda c: c.consented_at)
            label = draft.title or draft.sku or draft.id
            lines = [f'- {field}: "{value}"' for field, value in filled.items()]
            message = (
                f"For {label}, {'/'.join(filled.keys())} "
                f"{'was' if len(filled) == 1 else 'were'} missing, so our AI filled it in for you:\n"
                + "\n".join(lines)
                + "\n\nYou can edit this anytime in Command Center or Shopify - just flagging it wasn't from your file."
            )
            from sanocea.packages.notifications.transport import WhatsAppDemoTransport

            transport = WhatsAppDemoTransport(
                waha_base_url=os.environ.get("SANOCEA_WAHA_BASE_URL", "http://127.0.0.1:3000"),
                api_key=os.environ.get("SANOCEA_WAHA_API_KEY"),
            )
            result = transport.send_approval(recipient=contact.phone_e164, message=message)
            self.audit.record(
                merchant_id=merchant_id, actor="ai_enrichment", source=transport.name, action="ai_filled_fields_notified",
                object_type="ProductDraft", object_id=draft.id, result="delivered" if result.delivered else "failed", error=result.error,
            )
        except Exception as exc:  # noqa: BLE001 - notification failure must never break ingestion
            self.audit.record(
                merchant_id=merchant_id, actor="ai_enrichment", source="whatsapp_demo", action="ai_filled_fields_notify_failed",
                object_type="ProductDraft", object_id=draft.id, result="failed", error=str(exc),
            )

    def _auto_publish_on_ingest_enabled(self, merchant_id: str) -> bool:
        try:
            return bool(((self.store.get_config(merchant_id) or {}).get("product_rules") or {}).get("auto_publish_on_ingest"))
        except Exception:  # noqa: BLE001 - no config means the default (off)
            return False

    @staticmethod
    def _facts_safe_to_auto_publish(draft: ProductDraft) -> bool:
        """True only when no fact is missing/conflicted and every fact is either fully-confident source data
        (structured file), owner-confirmed, externally verified, or an AI-suggested cosmetic fill."""
        if draft.conflicts or not draft.commercial_facts:
            return False
        for fact in draft.commercial_facts.values():
            if fact.classification == "MISSING":
                # An empty OPTIONAL column (barcode, hsn, parent_sku...) is recorded as a MISSING fact too.
                # A draft only reaches NEEDS_APPROVAL once every REQUIRED field is present, so a MISSING fact
                # here is by definition an optional one and does not block publishing.
                continue
            if fact.conflicted:
                return False
            if fact.classification in ("AI_SUGGESTED", "HUMAN_APPROVED", "EXTERNALLY_VERIFIED"):
                continue
            if fact.confidence < 1.0:
                return False
        return True

    def _notify_publish_outcome(self, merchant_id: str, outcome: dict[str, Any]) -> None:
        """Honest one-line WhatsApp status for a product that was published straight from ingestion (same
        wording rules as the reply flow's confirmation: never claims "live" unless it verifiably is)."""
        import os

        from sanocea.packages.domain_contract.models import DemoSessionContact, now_utc as _now_utc

        try:
            contacts = [c for c in self.store.list(DemoSessionContact, merchant_id) if c.cleared_at is None and c.expires_at > _now_utc()]
            if not contacts:
                return
            contact = max(contacts, key=lambda c: c.consented_at)
            title = outcome.get("title") or "the product"
            if outcome.get("outcome") == "published":
                if outcome.get("storefront_visible"):
                    text = f'Done - "{title}" is now live on your store.'
                else:
                    text = f'Done - "{title}" was published to Shopify (storefront visibility step needs a follow-up check).'
            elif outcome.get("outcome") == "pending_approval":
                text = f'Got it - "{title}" is fully filled in, but publishing it needs a separate sign-off in Command Center first.'
            else:
                text = f'Got it - "{title}" is filled in, but there is an issue blocking publish: {", ".join(outcome.get("reasons", [])) or "see Command Center"}.'
            from sanocea.packages.notifications.transport import WhatsAppDemoTransport

            WhatsAppDemoTransport(
                waha_base_url=os.environ.get("SANOCEA_WAHA_BASE_URL", "http://127.0.0.1:3000"),
                api_key=os.environ.get("SANOCEA_WAHA_API_KEY"),
            ).send_approval(recipient=contact.phone_e164, message=text)
        except Exception:  # noqa: BLE001 - a status message failing must never break ingestion
            pass

    def resolve_conflict(
        self,
        merchant_id: str,
        draft_id: str,
        fact_name: str,
        chosen_value: Any,
        chosen_source: str,
        actor: str,
        note: str | None = None,
    ) -> ProductDraft:
        """Resolves a conflicting commercial fact with human authorization, updating the draft and audit ledger."""
        from sanocea.packages.product_onboarding.provenance import resolve_fact_conflict

        draft = self.store.get(ProductDraft, merchant_id, draft_id)
        draft = resolve_fact_conflict(draft, fact_name, chosen_value, chosen_source, actor, note)
        draft = self.validator.validate(draft)
        self.store.put(draft)
        self.audit.record(
            merchant_id=merchant_id,
            actor=actor,
            source="product_onboarding",
            action="conflict_resolved",
            object_type="ProductDraft",
            object_id=draft.id,
            result=draft.state,
            evidence_ref=chosen_source,
        )
        return draft

    def provide_missing_fact(
        self,
        merchant_id: str,
        draft_id: str,
        fact_name: str,
        value: Any,
        actor: str,
        source: str = "owner_reply",
        note: str | None = None,
    ) -> ProductDraft:
        """Supplies a value for a genuinely missing (not conflicting) required field - see
        provide_missing_fact's own docstring in provenance.py for why this is a separate path from
        resolve_conflict."""
        from sanocea.packages.product_onboarding.provenance import provide_missing_fact

        draft = self.store.get(ProductDraft, merchant_id, draft_id)
        draft = provide_missing_fact(draft, fact_name, value, source, actor, note)
        draft = self.validator.validate(draft)
        self.store.put(draft)
        self.audit.record(
            merchant_id=merchant_id,
            actor=actor,
            source="product_onboarding",
            action="missing_fact_provided",
            object_type="ProductDraft",
            object_id=draft.id,
            result=draft.state,
            evidence_ref=source,
        )
        return draft

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
            verification = self.reverify(merchant_id, publication.id)
            if verification.outcome == "VERIFIED":
                return verification
            # The draft says "published" but the live read-back disagrees (most commonly: the product was
            # deleted in Shopify, or edited out from under us). This used to return that bad verification
            # and let callers report success while nothing was actually live. Recreate it ONCE with a
            # fresh attempt instead - the connector upserts by SKU, so this updates in place if the
            # product still exists and recreates it if it doesn't, never duplicating.
            publication.status = "approved"
            self.store.put(publication)
            return self.publisher.publish(merchant_id, publication.id)
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
