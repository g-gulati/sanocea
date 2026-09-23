"""ChannelOperationService - drives ONE ProductDraft x ONE channel through the Flow A lifecycle
(QUEUED -> ... -> VERIFIED/RESOLVED, or paused at APPROVAL_REQUIRED) automatically, right after email
ingestion validation completes. See ChannelOperation's docstring (domain_contract/models.py) and
docs/architecture/integrations/MULTI_CHANNEL_DEMO_ARCHITECTURE.md for why each channel's demo model
differs.

Deliberately does NOT reuse ProductPublicationService.publish()/verify(): that machinery hardcodes
action="publish_product", which AmazonConnector does not declare as a capability (Amazon's real,
Level-1-confirmed contract uses "put_listing"/"patch_listing" instead - see connectors/amazon/
connector.py's describe_capabilities()). Extending ProductPublicationService to be action-name-aware
per connector would touch the ALREADY-CERTIFIED Shopify path, which this build must never modify.
Instead, this service drives each connector's real execute_mutation()/fetch() directly with the correct
action name per channel - same MutationRequest/MutationResult contract, same audit+idempotency wrapper,
same connector classes, just not funneled through the one method that happens to be Amazon-incompatible.
"""

from __future__ import annotations

import threading
import time
from typing import Any
from uuid import uuid4

from datetime import timedelta

from sanocea.packages.audit import AuditLedger
from sanocea.packages.connector_sdk import MutationRequest
from sanocea.packages.domain_contract.models import (
    Approval,
    ChannelOperation,
    Merchant,
    ProductDraft,
    now_utc,
)

APPROVAL_EXPIRY = timedelta(hours=24)
from sanocea.packages.policy_engine.engine import Decision, PolicyEngine

from .demo_connectors import (
    AmazonDemoScenario,
    ControlledDemoAmazonConnector,
    ControlledDemoFlipkartConnector,
    ControlledDemoWooCommerceConnector,
    FlipkartDemoScenario,
    WooCommerceDemoScenario,
)

CANONICAL_CHANNELS = ("own_website", "amazon_in", "flipkart", "jiomart", "blinkit")

# Terminal states that mean "nothing more to do without new input" - used by the Command Center to
# decide whether an operation still counts as "in progress" for the executive summary.
TERMINAL_STATES = frozenset({"VERIFIED", "RESOLVED", "APPROVAL_REQUIRED", "FAILED", "AWAITING_CHANNEL_RESPONSE"})

# Each channel runs on its OWN thread (see run_for_email_ingestion) so one channel's pace never
# blocks another's - Amazon does not wait for JioMart. The per-operation pause WITHIN a channel's own
# thread reflects genuinely different real-world latency (a synchronous own-site REST write really is
# faster than a marketplace's async feed-processing contract), not a shared global stagger.
CHANNEL_OPERATION_PACE_SECONDS = {"own_website": 0.4, "flipkart": 0.6, "jiomart": 0.8, "blinkit": 1.0, "amazon_in": 1.3}


class ChannelOperationError(Exception):
    pass


class ChannelOperationService:
    def __init__(self, store) -> None:
        self.store = store
        self.audit = AuditLedger(store)
        self.policy = PolicyEngine()

    # --- Orchestration --------------------------------------------------------------------------

    def run_for_email_ingestion(self, merchant_id: str, run_id: str, ready_draft_ids: list[str]) -> list[ChannelOperation]:
        """Called automatically right after EmailIngestionService finishes validation - no separate
        trigger. Only runs for tenants whose config.demo.known_channels names one of our 5 canonical
        channels; a merchant with no matching channels (or no ready drafts) gets an empty list, not an
        error."""
        if not ready_draft_ids:
            return []
        config = self.store.get_config(merchant_id)
        known_channels_raw = set((config.get("demo") or {}).get("known_channels") or [])
        channels = [c for c in CANONICAL_CHANNELS if c in known_channels_raw]
        if not channels:
            return []
        drafts = sorted(
            (self.store.get(ProductDraft, merchant_id, draft_id) for draft_id in ready_draft_ids),
            key=lambda d: d.sku or d.id,
        )
        merchant = self.store.get(Merchant, merchant_id, merchant_id)
        # Race guard (confirmed by testing: a demo reset firing WHILE a background run is still
        # writing operations left stale rows behind, because the reset's DELETE and this run's INSERTs
        # are unrelated transactions with nothing connecting them). reset_prospect_tenant() always
        # ends with store.put(Merchant(...)), which - like every put() - stamps a fresh
        # sync.updated_at. Capturing that value here and re-checking it before every write lets a
        # stale run detect "this tenant was reset out from under me" and stop, using an existing,
        # already-guaranteed entity-versioning mechanism rather than adding new reset-tracking state.
        run_generation = merchant.sync.updated_at
        # The one operation this run deliberately leaves genuinely unresolved (see
        # AWAITING_CHANNEL_RESPONSE's docstring) - Amazon's own real async contract, on a draft that
        # isn't already carrying the amazon auto-resolution scenario, so the two are never conflated.
        stall_id = self._stall_id_for("amazon_in", drafts)

        # One thread PER CHANNEL, not one thread looping through all channels - a real architectural
        # requirement, not a cosmetic one: five independent channel integrations are independent by
        # construction, and a design where Amazon's pace could block JioMart's (or vice versa) would
        # misrepresent the operating model this is meant to demonstrate. Safe because each thread only
        # ever touches its OWN ChannelOperation rows (a fresh id per operation) and PostgresStore opens
        # a fresh connection per call by default (no shared-connection races) - see
        # EmailIngestionService's own docstring on this same guarantee. Results are collected via a
        # thread-safe list append (Python list.append is atomic under the GIL) then this whole
        # function's own caller already runs off the HTTP thread (see EmailIngestionService), so joining
        # here blocks nothing user-visible.
        results: list[ChannelOperation] = []
        results_lock = threading.Lock()

        def _run_one_channel(channel: str) -> None:
            anchor_id = self._anchor_id_for(channel, drafts)
            no_action_id = self._no_action_id_for(channel, drafts)
            pace = CHANNEL_OPERATION_PACE_SECONDS.get(channel, 0.5)
            for i, draft in enumerate(drafts):
                if i > 0:
                    time.sleep(pace)
                current_merchant = self.store.get(Merchant, merchant_id, merchant_id)
                if current_merchant.sync.updated_at != run_generation:
                    # Tenant was reset (or otherwise re-seeded) after this run started - stop writing
                    # immediately rather than leaving stale operations a fresh reset already tried to
                    # clear. Not an error: this is the correct, silent outcome of an operator
                    # deliberately restarting the demo mid-run.
                    self.audit.record(
                        merchant_id=merchant_id, actor="channel_operations", source=channel,
                        action="channel_run_aborted_stale_reset", object_type="EmailMessage", object_id=run_id,
                        result="aborted", correlation_id=run_id,
                    )
                    return
                op = self._new_operation(merchant_id, run_id, draft, channel)
                self.store.put(op)
                is_anchor = draft.id == anchor_id
                is_stall = channel == "amazon_in" and draft.id == stall_id and not is_anchor
                is_no_action = draft.id == no_action_id and not is_anchor
                try:
                    if channel == "own_website":
                        self._run_own_website(op, draft, config, is_anchor)
                    elif channel == "amazon_in":
                        self._run_amazon(op, draft, config, is_anchor, is_stall)
                    elif channel == "flipkart":
                        self._run_flipkart(op, draft, config, is_anchor, is_no_action)
                    elif channel == "jiomart":
                        self._run_jiomart(op, draft, config, is_anchor)
                    elif channel == "blinkit":
                        self._run_blinkit(op, draft, config, is_anchor)
                except Exception as exc:  # noqa: BLE001 - a channel operation failing must never crash the ingestion run
                    self._transition(op, "FAILED", note=str(exc))
                # Re-check staleness before the final write too - closes the window where a reset fires
                # WHILE this one operation was executing (the per-draft check above only catches it
                # BETWEEN operations). Worst case now: at most one QUEUED-only row per channel left
                # behind, never a fully-completed-looking one.
                if self.store.get(Merchant, merchant_id, merchant_id).sync.updated_at != run_generation:
                    return
                self.store.put(op)
                with results_lock:
                    results.append(op)

        threads = [threading.Thread(target=_run_one_channel, args=(channel,), daemon=True) for channel in channels]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        return results

    def _stall_id_for(self, channel: str, drafts: list[ProductDraft]) -> str | None:
        if channel != "amazon_in" or len(drafts) < 2:
            return None
        anchor_id = self._anchor_id_for(channel, drafts)
        candidates = [d for d in drafts if d.id != anchor_id]
        return candidates[-1].id if candidates else None

    def _no_action_id_for(self, channel: str, drafts: list[ProductDraft]) -> str | None:
        """Flipkart's deliberate 'found a difference, correctly did nothing' case - see
        _run_flipkart's docstring. Needs a draft distinct from every other channel's anchor to keep
        each channel's story legible on its own."""
        if channel != "flipkart" or len(drafts) < 4:
            return None
        used = {self._anchor_id_for(c, drafts) for c in CANONICAL_CHANNELS} - {None}
        candidates = [d for d in drafts if d.id not in used]
        return candidates[0].id if candidates else None

    def _anchor_id_for(self, channel: str, drafts: list[ProductDraft]) -> str | None:
        if not drafts:
            return None
        rotation = {"own_website": 0, "amazon_in": 0, "jiomart": 1, "blinkit": 2}
        idx = rotation.get(channel)
        if idx is None:  # flipkart: deliberately always clean, no anchor scenario
            return None
        return drafts[idx % len(drafts)].id

    def _new_operation(self, merchant_id: str, run_id: str, draft: ProductDraft, channel: str) -> ChannelOperation:
        started = now_utc()
        op = ChannelOperation(
            merchant_id=merchant_id, run_id=run_id, product_draft_id=draft.id,
            product_title=draft.title or draft.sku or "Untitled product", sku=draft.sku,
            channel=channel, status="QUEUED", started_at=started,
        )
        op.history.append({"status": "QUEUED", "at": started.isoformat()})
        return op

    def _transition(self, op: ChannelOperation, status: str, *, note: str | None = None) -> None:
        op.status = status
        ts = now_utc()
        entry: dict[str, Any] = {"status": status, "at": ts.isoformat()}
        if note:
            entry["note"] = note
        op.history.append(entry)
        if status == "VERIFIED" or status == "RESOLVED":
            op.verified_at = op.verified_at or ts
            op.resolved_at = ts
        self.audit.record(
            merchant_id=op.merchant_id, actor="channel_operations", source=op.channel,
            action=f"channel_operation_{status.lower()}", object_type="ChannelOperation", object_id=op.id,
            result=status, correlation_id=op.run_id,
            error=note if status in ("REJECTED", "FAILED", "DISCREPANCY") else None,
        )

    def _create_approval(
        self, op: ChannelOperation, *, summary: str, evidence: dict[str, Any],
        recommendation: str, alternative: str, risk_note: str,
    ) -> Approval:
        # A 4-hex-char suffix (65536 possibilities) is fine for one real demo run (one approval per
        # channel at most), but was observed colliding across this project's own heavy repeated-testing
        # sessions (many dozens of approvals accumulated for the same merchant/SKU). Rather than just
        # widening the suffix and hoping, actively check for a collision against this merchant's
        # existing approvals and regenerate - eliminates the risk outright instead of only shrinking it.
        existing_refs = {a.reference for a in self.store.list(Approval, op.merchant_id) if a.reference}
        reference = f"{op.channel[:2].upper()}-{op.id[-4:].upper()}"
        attempt = 0
        while reference in existing_refs and attempt < 5:
            attempt += 1
            reference = f"{op.channel[:2].upper()}-{uuid4().hex[-6:].upper()}"
        approval = Approval(
            merchant_id=op.merchant_id, action="channel_operation_correction", object_id=op.id,
            requested_by="channel_operations", reference=reference, summary=summary, evidence=evidence,
            recommendation=recommendation, alternative=alternative, risk_note=risk_note,
            notify_channels=[], demo_provenance="SYNTHETIC_DEMO", expires_at=now_utc() + APPROVAL_EXPIRY,
        )
        self.store.put(approval)
        op.approval_id = approval.id
        op.resolution_level = "OWNER_L3"
        self._transition(op, "APPROVAL_REQUIRED", note=summary)
        return approval

    # --- Own website (WooCommerce contract, controlled demo) ------------------------------------

    def _run_own_website(self, op: ChannelOperation, draft: ProductDraft, config: dict[str, Any], is_anchor: bool) -> None:
        self._transition(op, "PREPARING")
        price_rupees = f"{(draft.price or 0) / 100:.2f}"
        if is_anchor:
            # A brand-new SKU with no prior publicly-verified price history for SANOCEA to cross-check
            # against. Publishing straight to the merchant's OWN live storefront (the channel the
            # public sees immediately, no marketplace review step) is a commercial decision when there
            # is nothing to validate the numbers against - SANOCEA does not guess, it asks.
            op.decision_evidence = {
                "approved_master": {"price": price_rupees, "title": draft.title},
                "observed_channel_state": {"prior_public_price_history": None},
                "promotion_evidence": None,
                "merchant_authority_rule": "New SKUs with no prior price history to cross-check are not auto-published to the primary public storefront.",
                "decision": "Hold for owner confirmation before publishing.",
                "result": None,
            }
            self._create_approval(
                op,
                summary=f"New SKU '{draft.sku}' has no prior public price history on file to cross-check before publishing live to the storefront.",
                evidence={"proposed_price": price_rupees, "currency": draft.currency, "title": draft.title, "prior_public_price_history": None},
                recommendation=f"Publish {draft.sku} at {draft.currency} {price_rupees} as submitted in the product master.",
                alternative="Hold this SKU off the storefront until a team member confirms the price against the physical pricing sheet.",
                risk_note="Publishing an unverified price directly to the public storefront is immediately customer-visible and not easily reversible without a visible price change.",
            )
            return
        connector = ControlledDemoWooCommerceConnector(self.store, scenario=WooCommerceDemoScenario(draft.title or "", price_rupees, draft.sku or op.id))
        payload = {"title": draft.title, "sku": draft.sku, "price": price_rupees, "currency": draft.currency, "product_type": draft.product_type}
        op.submitted_payload = payload
        self._transition(op, "SUBMITTED")
        result = connector.execute_mutation(MutationRequest(merchant_id=op.merchant_id, action="publish_product", object_type="ProductDraft", payload=payload, idempotency_key=f"{op.id}:submit"))
        op.channel_response = result.payload
        op.external_ref = result.external_ref
        self._transition(op, "ACCEPTED")
        self._transition(op, "READBACK_PENDING")
        readback = connector.fetch(op.merchant_id, "product", str(result.external_ref))
        op.readback = readback
        self._verify_readback(op, draft, readback, price_rupees)

    # --- Amazon India (real SP-API contract, controlled demo) -----------------------------------

    def _run_amazon(self, op: ChannelOperation, draft: ProductDraft, config: dict[str, Any], is_anchor: bool, is_stall: bool = False) -> None:
        self._transition(op, "PREPARING")
        price_rupees = f"{(draft.price or 0) / 100:.2f}"
        attributes = {k: str(v) for k, v in draft.attributes.items() if v not in (None, "")}
        if not is_anchor:
            attributes = {**attributes, "country_of_origin": "India"}
        connector = ControlledDemoAmazonConnector(self.store, scenario=AmazonDemoScenario(draft.title or "", price_rupees, draft.sku or op.id))
        payload = {"product_type": draft.product_type or "GROCERY", "attributes": attributes, "sku": draft.sku}
        op.submitted_payload = payload
        self._transition(op, "SUBMITTED")
        result = connector.execute_mutation(MutationRequest(merchant_id=op.merchant_id, action="put_listing", object_type="ProductDraft", payload=payload, idempotency_key=f"{op.id}:submit"))
        op.channel_response = result.payload
        if is_stall:
            # Genuinely, honestly still pending: Amazon's own async feed-status contract means a
            # submission being accepted by the HTTP layer is never the same as it being applied - a
            # real caller would need a LATER status check (get_feed_status) to know more, which this
            # demo run does not perform. Left exactly here on purpose - see AWAITING_CHANNEL_RESPONSE.
            self._transition(op, "AWAITING_CHANNEL_RESPONSE", note="Amazon's async feed-processing has not confirmed final status within this run - a later status check would resolve it, not a retry.")
            return
        issues = result.payload.get("issues") or []
        if issues:
            self._transition(op, "REJECTED", note=issues[0]["message"])
            self._transition(op, "INVESTIGATING")
            # Authoritative source, in order of strength: a registered GSTIN (definitive), else the
            # merchant's own registered operating currency (every prospect demo tenant is a real,
            # independently-verified India-based business - see PROSPECT_TENANTS' public_catalogue_sources
            # - so INR-denominated operations is itself a genuine registered-profile fact, not a guess).
            origin_evidence = "registered GSTIN (India)" if config.get("gstin") else ("registered operating currency (INR)" if config.get("currency") == "INR" else None)
            if not origin_evidence:
                self._create_approval(
                    op,
                    summary=f"Amazon rejected {draft.sku}: {issues[0]['message']}, and no authoritative source for country_of_origin is on file.",
                    evidence={"amazon_issue": issues[0]},
                    recommendation="Confirm the manufacturing country and resubmit.",
                    alternative="Leave this SKU off Amazon until confirmed.",
                    risk_note="A wrong country-of-origin declaration is a compliance matter, not just a listing detail.",
                )
                return
            self._transition(op, "CAUSE_IDENTIFIED", note=f"country_of_origin inferred from the merchant's {origin_evidence}")
            op.resolution_level = "AUTO_L1"
            op.decision_evidence = {
                "approved_master": {"title": draft.title, "attributes_on_file": {k: v for k, v in draft.attributes.items() if v not in (None, "")}},
                "observed_channel_state": {"amazon_issue": issues[0]},
                "promotion_evidence": None,
                "merchant_authority_rule": f"Missing mandatory attribute with an authoritative value available ({origin_evidence}) - safe to auto-complete and resubmit.",
                "decision": "Add country_of_origin=India from the merchant's own registered profile and resubmit.",
                "result": None,  # filled in after readback confirms
            }
            self._transition(op, "CORRECTING")
            attributes = {**attributes, "country_of_origin": "India"}
            payload = {**payload, "attributes": attributes}
            op.submitted_payload = payload
            self._transition(op, "RESUBMITTING")
            result = connector.execute_mutation(MutationRequest(merchant_id=op.merchant_id, action="put_listing", object_type="ProductDraft", payload=payload, idempotency_key=f"{op.id}:resubmit"))
            op.channel_response = result.payload
        op.external_ref = result.external_ref
        self._transition(op, "ACCEPTED")
        self._transition(op, "READBACK_PENDING")
        readback = connector.fetch(op.merchant_id, "product", draft.sku or "")
        op.readback = readback
        self._verify_readback(op, draft, readback, price_rupees, auto_resolved=bool(issues))

    # --- Flipkart (real Seller API contract, controlled demo) -----------------------------------

    def _run_flipkart(self, op: ChannelOperation, draft: ProductDraft, config: dict[str, Any], is_anchor: bool, is_no_action: bool = False) -> None:
        self._transition(op, "PREPARING")
        price = (draft.price or 0) / 100
        price_rupees = f"{price:.2f}"
        connector = ControlledDemoFlipkartConnector(self.store, scenario=FlipkartDemoScenario(draft.title or "", price_rupees, draft.sku or op.id))
        payload = {"sku": draft.sku, "title": draft.title, "price": price_rupees, "currency": draft.currency, "product_type": draft.product_type, "attributes": {}}
        op.submitted_payload = payload
        self._transition(op, "SUBMITTED")
        result = connector.execute_mutation(MutationRequest(merchant_id=op.merchant_id, action="publish_product", object_type="ProductDraft", payload=payload, idempotency_key=f"{op.id}:submit"))
        op.channel_response = result.payload
        op.external_ref = result.external_ref
        self._transition(op, "ACCEPTED")
        self._transition(op, "READBACK_PENDING")
        readback = connector.fetch(op.merchant_id, "product", draft.sku or "")
        op.readback = readback

        if is_no_action:
            # Deliberately NOT a correction case: the channel is showing a lower price than the
            # approved master, inside a range consistent with a marketplace-funded promotion, not a
            # data error. Correcting this would mean overwriting a legitimate discount Flipkart itself
            # may be funding - "difference = error = overwrite" is exactly the reflex a trusted
            # operations system must NOT have. Modeled as a controlled observation (never claimed as an
            # actually-observed live Flipkart promotion) since Flipkart's real connector always echoes
            # back whatever price was submitted - see FlipkartDemoScenario.
            promo_price = round(price * 0.90, 2)
            self._transition(op, "DISCREPANCY", note=f"Flipkart shows {promo_price:.2f} vs master {price:.2f} - checking before touching anything")
            self._transition(op, "INVESTIGATING")
            delta_percent = round((price - promo_price) / price * 100, 2)
            within_promo_band = 5.0 <= delta_percent <= 20.0
            op.decision_evidence = {
                "approved_master": {"price": price_rupees, "title": draft.title},
                "observed_channel_state": {"listed_price": f"{promo_price:.2f}"},
                "promotion_evidence": f"{delta_percent}% below master, within the {5}-{20}% band typical of a marketplace-funded promotion" if within_promo_band else None,
                "merchant_authority_rule": "A channel price below master within a plausible promotion band is not auto-corrected without confirming it is not a deliberate discount.",
                "decision": "NO ACTION REQUIRED - recognized as a likely marketplace-funded promotion, not a data error." if within_promo_band else "Outside the recognized promotion band - flag for review.",
                "result": None,
            }
            if within_promo_band:
                self._transition(op, "CAUSE_IDENTIFIED", note="price difference consistent with an active marketplace-funded promotion - no correction applied")
                op.issue_category = "EXPECTED_COMMERCIAL_DIFFERENCE"
                op.decision_evidence["result"] = "left as-is; classified EXPECTED_DIFFERENCE, not DISCREPANCY"
                self._transition(op, "VERIFIED", note="no action required")
                return
            self._create_approval(
                op,
                summary=f"Flipkart shows {draft.sku} at {promo_price:.2f} vs master {price:.2f} - outside the recognized promotion band, needs confirmation before any action.",
                evidence=op.decision_evidence,
                recommendation="Confirm whether this is a legitimate promotion or an error before any correction.",
                alternative="Leave as-is pending confirmation.",
                risk_note="Overwriting a real discount would be a commercial mistake; leaving a real error unaddressed would also be wrong - this needs a human call.",
            )
            return

        self._verify_readback(op, draft, readback, price_rupees)

    # --- JioMart (no connector - no confirmed seller-API contract exists; generic internal
    # ChannelOperation only, per the multi-channel operations audit's explicit finding) -----------

    def _run_jiomart(self, op: ChannelOperation, draft: ProductDraft, config: dict[str, Any], is_anchor: bool) -> None:
        self._transition(op, "PREPARING")
        price = (draft.price or 0) / 100
        # Real, evidenced observation (docs/audits/ajanta_evidence/jiomart_fetch_summary.json): JioMart's
        # own structured product data does not always mirror a seller's submitted price exactly. Modeled
        # here as a deterministic, SYNTHETIC_DEMO routine display-rounding delta - never claimed as an
        # actually-observed live value for this specific SKU.
        listed_price = round(price * 0.985, 2) if is_anchor else price
        op.submitted_payload = {"sku": draft.sku, "title": draft.title, "price": f"{price:.2f}"}
        self._transition(op, "SUBMITTED")
        op.channel_response = {"jiomart_operation_id": f"jm-demo-{draft.sku}", "listed_price": f"{listed_price:.2f}"}
        delta_percent = abs(listed_price - price) / price * 100 if price else 0
        if delta_percent > 0:
            self._transition(op, "DISCREPANCY", note=f"JioMart-listed price {listed_price:.2f} differs from master price {price:.2f} by {delta_percent:.2f}%")
            self._transition(op, "INVESTIGATING")
            policy_rules = (config.get("policy") or {}).get("channel_price_correction", {})
            decision = self.policy.decide({"channel_price_correction": policy_rules}, "channel_price_correction", {"delta_percent": delta_percent})
            if decision != Decision.ALLOW:
                self._create_approval(
                    op,
                    summary=f"JioMart shows {draft.sku} at {listed_price:.2f} vs master price {price:.2f} ({delta_percent:.2f}% difference) - outside the auto-correction policy.",
                    evidence={"master_price": f"{price:.2f}", "jiomart_listed_price": f"{listed_price:.2f}", "delta_percent": round(delta_percent, 2)},
                    recommendation="Correct JioMart's listed price to match the approved master.",
                    alternative="Confirm this is an intentional JioMart-funded promotion and leave it as-is.",
                    risk_note="A price difference beyond the routine-rounding threshold may reflect a deliberate commercial decision, not an error.",
                )
                return
            self._transition(op, "CAUSE_IDENTIFIED", note="within routine channel-display-rounding tolerance per merchant policy")
            op.resolution_level = "AUTO_L1"
            op.decision_evidence = {
                "approved_master": {"price": f"{price:.2f}"},
                "observed_channel_state": {"listed_price": f"{listed_price:.2f}"},
                "promotion_evidence": "None identified - delta is within routine channel-display-rounding tolerance, not a promotion pattern",
                "merchant_authority_rule": f"Channel price differences up to {policy_rules.get('automatic_limit_percent', 2)}% may be auto-corrected back to the approved master.",
                "decision": "Correct JioMart's listed price to match the approved master.",
                "result": None,
            }
            self._transition(op, "CORRECTION_PENDING")
            self._transition(op, "CORRECTING")
            op.channel_response["listed_price"] = f"{price:.2f}"
            self._transition(op, "RESUBMITTING")
        self._transition(op, "ACCEPTED")
        self._transition(op, "READBACK_PENDING")
        readback = {"title": draft.title, "sku": draft.sku, "price": f"{price:.2f}", "status": "active"}
        op.readback = readback
        self._verify_readback(op, draft, readback, f"{price:.2f}", auto_resolved=delta_percent > 0)

    # --- Blinkit (no listing API; real vendor-PO/dark-store model per channel-research audit) ----

    def _run_blinkit(self, op: ChannelOperation, draft: ProductDraft, config: dict[str, Any], is_anchor: bool) -> None:
        self._transition(op, "PREPARING")
        # Blinkit's real, evidenced operating model is vendor-PO-to-dark-store, not a listing API: the
        # merchant is onboarded into the platform's vendor catalogue at a declared case/supply-pack
        # unit, which future platform-issued POs reference. A brand-new SKU has no PO yet - what SANOCEA
        # actually does at launch time is this vendor-catalogue-onboarding submission.
        self._transition(op, "SUBMITTED")
        op.submitted_payload = {"sku": draft.sku, "title": draft.title, "declared_case_pack_qty": None if is_anchor else (config.get("blinkit_vendor_defaults") or {}).get("default_case_pack_qty")}
        if is_anchor:
            self._transition(op, "DISCREPANCY", note="vendor catalogue onboarding submitted without a declared case-pack/supply unit - required for future PO sizing")
            self._transition(op, "INVESTIGATING")
            default_qty = (config.get("blinkit_vendor_defaults") or {}).get("default_case_pack_qty")
            if not default_qty:
                self._create_approval(
                    op,
                    summary=f"Blinkit vendor onboarding for {draft.sku} needs a declared case-pack quantity and none is on file for this merchant.",
                    evidence={"sku": draft.sku},
                    recommendation="Confirm the standard case-pack/carton quantity for this SKU.",
                    alternative="Leave this SKU pending Blinkit vendor onboarding until confirmed.",
                    risk_note="An incorrect declared case-pack size affects future PO sizing and fulfilment accuracy.",
                )
                return
            self._transition(op, "CAUSE_IDENTIFIED", note=f"merchant's registered default case-pack quantity ({default_qty}) applied")
            op.resolution_level = "AUTO_L1"
            op.decision_evidence = {
                "approved_master": {"sku": draft.sku},
                "observed_channel_state": {"declared_case_pack_qty": None},
                "promotion_evidence": None,
                "merchant_authority_rule": "Merchant's own registered default case-pack quantity may be applied automatically when none was declared.",
                "decision": f"Declare case-pack quantity {default_qty} from the merchant's own registered default.",
                "result": f"case-pack quantity {default_qty} onboarded",
            }
            self._transition(op, "CORRECTING")
            op.submitted_payload["declared_case_pack_qty"] = default_qty
        self._transition(op, "ACCEPTED", note="vendor SKU onboarded into Blinkit catalogue, ready for future PO reference")
        op.channel_response = {"vendor_sku_onboarded": True, "declared_case_pack_qty": op.submitted_payload["declared_case_pack_qty"]}
        self._transition(op, "READBACK_PENDING")
        op.readback = {"vendor_sku_onboarded": True, "case_pack_qty": op.submitted_payload["declared_case_pack_qty"]}
        self._transition(op, "VERIFIED")
        if is_anchor:
            self._transition(op, "RESOLVED", note="auto-resolved: case-pack quantity applied from merchant's registered default")

    # --- Resume after an owner approval --------------------------------------------------------

    def resume(self, merchant_id: str, channel_operation_id: str) -> ChannelOperation:
        """Called by ApprovalService once an OWNER_L3 approval for a ChannelOperation is approved.
        Re-enters the SAME per-channel execution the automatic path would have taken, now that a human
        has authorized it - never a different, "demo-only" resume path."""
        op = self.store.get(ChannelOperation, merchant_id, channel_operation_id)
        if op.status != "APPROVAL_REQUIRED":
            return op
        # Everything that can fail - including the draft/config lookups themselves - now lives inside
        # this one try/except. Found live during WhatsApp backlog regression testing: those two lookups
        # used to happen BEFORE this block, so a failure there raised uncaught straight out of resume(),
        # past ApprovalService.resolve() (which had already persisted status="approved") - leaving an
        # approval permanently marked approved with the actual correction never applied and no way to
        # retry it (the approval is no longer "pending"). Never let resume() raise past this point.
        try:
            draft = self.store.get(ProductDraft, merchant_id, op.product_draft_id)
            config = self.store.get_config(merchant_id)
            self._transition(op, "CORRECTING", note="owner approval received - proceeding")
            if op.channel == "own_website":
                price_rupees = f"{(draft.price or 0) / 100:.2f}"
                connector = ControlledDemoWooCommerceConnector(self.store, scenario=WooCommerceDemoScenario(draft.title or "", price_rupees, draft.sku or op.id))
                payload = {"title": draft.title, "sku": draft.sku, "price": price_rupees, "currency": draft.currency, "product_type": draft.product_type}
                op.submitted_payload = payload
                self._transition(op, "SUBMITTED")
                result = connector.execute_mutation(MutationRequest(merchant_id=merchant_id, action="publish_product", object_type="ProductDraft", payload=payload, idempotency_key=f"{op.id}:resume-submit"))
                op.channel_response = result.payload
                op.external_ref = result.external_ref
                self._transition(op, "ACCEPTED")
                self._transition(op, "READBACK_PENDING")
                readback = connector.fetch(merchant_id, "product", str(result.external_ref))
                op.readback = readback
                self._verify_readback(op, draft, readback, price_rupees)
                if op.status == "VERIFIED":
                    op.resolution_level = "OWNER_L3"
                    self._transition(op, "RESOLVED", note="published after owner approval")
            elif op.channel in ("jiomart", "flipkart"):
                price = (draft.price or 0) / 100
                op.channel_response["listed_price"] = f"{price:.2f}"
                self._transition(op, "RESUBMITTING")
                self._transition(op, "ACCEPTED")
                self._transition(op, "READBACK_PENDING")
                readback = {"title": draft.title, "sku": draft.sku, "price": f"{price:.2f}", "status": "active"}
                op.readback = readback
                self._verify_readback(op, draft, readback, f"{price:.2f}")
                if op.status == "VERIFIED":
                    op.resolution_level = "OWNER_L3"
                    self._transition(op, "RESOLVED", note="corrected after owner approval")
            elif op.channel == "blinkit":
                approved_qty = (config.get("blinkit_vendor_defaults") or {}).get("default_case_pack_qty") or 1
                op.submitted_payload["declared_case_pack_qty"] = approved_qty
                op.channel_response = {"vendor_sku_onboarded": True, "declared_case_pack_qty": approved_qty}
                self._transition(op, "ACCEPTED")
                self._transition(op, "READBACK_PENDING")
                op.readback = {"vendor_sku_onboarded": True, "case_pack_qty": approved_qty}
                op.resolution_level = "OWNER_L3"
                self._transition(op, "VERIFIED")
                self._transition(op, "RESOLVED", note="onboarded after owner approval")
            else:  # amazon_in - owner supplied the missing compliance fact out of band
                self._transition(op, "FAILED", note="amazon resume requires a supplied country_of_origin value - not yet automated")
        except Exception as exc:  # noqa: BLE001
            self._transition(op, "FAILED", note=str(exc))
        self.store.put(op)
        return op

    # --- Shared readback comparison --------------------------------------------------------------

    def _verify_readback(self, op: ChannelOperation, draft: ProductDraft, readback: dict[str, Any], expected_price_rupees: str, *, auto_resolved: bool = False) -> None:
        mismatches = []
        if readback.get("title") and readback.get("title") != draft.title:
            mismatches.append("title")
        if readback.get("price") and readback.get("price") != expected_price_rupees:
            mismatches.append("price")
        if mismatches:
            self._transition(op, "DISCREPANCY", note=f"readback mismatch: {', '.join(mismatches)}")
            return
        self._transition(op, "VERIFIED")
        if op.decision_evidence and op.decision_evidence.get("result") is None:
            op.decision_evidence["result"] = f"{readback.get('price', expected_price_rupees)} verified by readback"
        if auto_resolved:
            op.resolution_level = op.resolution_level or "AUTO_L1"
            self._transition(op, "RESOLVED", note="auto-resolved and verified after correction")
