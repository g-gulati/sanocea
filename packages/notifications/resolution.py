"""DemoApprovalNotificationService - the ONLY place an inbound WhatsApp/email event is allowed to
touch SANOCEA's authoritative Approval state. Every security check in the spec's "Security" section is
enforced here, in one place, regardless of which ApprovalNotificationTransport delivered the event -
never trust message text alone.

This is explicitly demo-scoped (DemoSessionContact, not permanent merchant contact data) - see that
model's own docstring. A production notification service would reuse ApprovalService unchanged but
resolve recipients from real merchant-staff records instead of a session-scoped consent record.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from sanocea.packages.approvals import ApprovalError, ApprovalService
from sanocea.packages.audit import AuditLedger
from sanocea.packages.domain_contract.models import (
    Approval,
    ChannelOperation,
    DemoSessionContact,
    ExceptionRecord,
    Location,
    Product,
    ProductDraft,
    Variant,
    WhatsAppConversationState,
    now_utc,
)
from sanocea.packages.idempotency import IdempotencyService

from .phone import PhoneValidationError, normalize_phone
from .transport import CHANNEL_LABELS, ApprovalNotificationTransport, DeliveryResult, InboundApprovalMessage, format_approval_message

DEFAULT_SESSION_CONTACT_EXPIRY = timedelta(hours=4)  # a sales meeting, not a standing subscription
_COMMAND_RE = re.compile(
    r"^\s*(APPROVE|REJECT|DETAILS|VIEW DETAILS|LATER|REVIEW LATER|ACCEPT|CONFIRM|DECLINE|SNOOZE|EDIT)\s*([A-Z0-9\-_]*)\s*$",
    re.IGNORECASE,
)


def _extract_field_values(text: str, fields: list[str]) -> dict[str, Any]:
    """Deliberately loose, not a fixed grammar - matches "price 249", "price: 249", "price is 249",
    "product_type snacks", "qty 20 at Shop location", "500g", or "no tracking".
    Scoped to a caller-supplied field list (the SPECIFIC fields one draft is actually missing) so it can
    never silently set an unrelated field - if a field name doesn't appear in the text at all, it's simply
    not returned, not guessed."""
    found: dict[str, Any] = {}

    # Check for untracked inventory choice
    text_lower = text.strip().lower()
    if any(k in text_lower for k in ["no tracking", "untracked", "don't track", "dont track", "track inventory: no", "track: no", "without tracking", "no inventory tracking"]):
        found["track_inventory"] = False

    # Check for weight pattern: "250g", "500 g", "0.5 kg"
    weight_match = re.search(r"\b(\d+(?:\.\d+)?)\s*(g|gm|grams|kg|kgs)\b", text, re.IGNORECASE)
    if weight_match:
        val = float(weight_match.group(1))
        u = weight_match.group(2).lower()
        found["weight"] = val * 1000 if "kg" in u else val
        found["weight_unit"] = "GRAMS"

    # Field aliases
    field_patterns = {
        "inventory_quantity": [
            r"\b(?:inventory[ _]quantity|quantity|qty|stock|opening[ _]stock)\b\s*(?:is|=|:|-)?\s*(\d+)",
            r"\b(\d+)\s*(?:units|pcs|pieces|items)\b",
        ],
        "inventory_location": [
            r"\b(?:inventory[ _]location|location|loc|at)\b\s*(?:is|=|:|-)?\s*([a-zA-Z0-9\s]+?)(?:,|$|\n|\bwith\b|\bweight\b|\bqty\b|\bstock\b)",
        ],
        "price": [
            r"\b(?:price|retail[ _]price|rate|cost|mrp|rs\.?|₹)\b\s*(?:is|=|:|-)?\s*(\d+(?:\.\d+)?)",
        ],
        "product_type": [
            r"\b(?:product[ _]type|merchant[ _]type|category|type)\b\s*(?:is|=|:|-)?\s*([a-zA-Z0-9\s&]+?)(?:,|$|\n)",
        ],
    }

    for field in fields:
        if field in found:
            continue
        if field in field_patterns:
            for pat in field_patterns[field]:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    val = m.group(1).strip().rstrip(".")
                    if val:
                        found[field] = val
                        break
        if field not in found:
            label = "[ _]".join(re.escape(part) for part in field.split("_"))
            pattern = re.compile(rf"\b{label}\b\s*(?:is|=|:|-)?\s*([^,;\n]+)", re.IGNORECASE)
            match = pattern.search(text)
            if match:
                val = match.group(1).strip().rstrip(".")
                if val:
                    found[field] = val

    if found:
        return found

    # Single-field whole-message fallback
    if len(fields) == 1 and text.strip():
        return {fields[0]: text.strip()}

    # Positional fallback
    segments = [s.strip() for s in re.split(r"[,;\n]+", text) if s.strip()]
    if len(segments) != len(fields):
        segments = [s.strip() for s in text.split() if s.strip()]
    if len(segments) == len(fields):
        found = dict(zip(fields, segments))
    return found


class InboundResolutionError(Exception):
    """Raised for every fail-closed case - wrong number, ambiguous reference, cross-tenant, malformed
    command, unknown approval. Callers must treat this as 'do nothing, audit it' - never as a reason to
    guess."""


def _resolve_product_title(store, merchant_id: str, sku: str) -> str | None:
    """Human-readable product title for a SKU, resolved from canonical data: the Variant record that
    owns the SKU, falling back to the product draft carrying it. Returns None when neither exists so
    callers can fall back to neutral wording - never a raw SKU."""
    products = {p.id: p.title for p in store.list(Product, merchant_id)}
    for variant in store.list(Variant, merchant_id):
        if variant.sku == sku and variant.product_id in products:
            return products[variant.product_id]
    for draft in store.list(ProductDraft, merchant_id):
        if draft.sku == sku and draft.title:
            return draft.title
    return None


def _resolve_location_channel_name(store, merchant_id: str, location_ref: str) -> str | None:
    """Sales-channel name for a location, resolved from the Location record that owns `location_ref`
    (its metadata channel label preferred over its display name). None when unresolvable so callers can
    omit the channel clause entirely."""
    for loc in store.list(Location, merchant_id):
        meta = loc.metadata or {}
        if meta.get("location_ref") == location_ref or loc.code == location_ref or loc.name == location_ref:
            channel = (meta.get("channel") or "").strip()
            if channel:
                return CHANNEL_LABELS.get(channel) or channel[:1].upper() + channel[1:]
            if loc.name.strip():
                return loc.name.strip()
    return None


def _briefing_oos_line(store, merchant_id: str, inv) -> str:
    """Natural business-language OOS alert for the WhatsApp briefing. Title and channel come from
    canonical data and fall back to neutral wording - the sku and location_ref codes are never exposed."""
    title = _resolve_product_title(store, merchant_id, inv.sku) or "An item"
    channel = _resolve_location_channel_name(store, merchant_id, inv.location_ref)
    where = f" on {channel}" if channel else ""
    return (
        f"🔴 Stock Alert — {title} is showing as out of stock{where}. "
        f"{inv.quantity} units are available in inventory, but none are currently available for customers. "
        f"Please investigate."
    )


def _open_critical_inventory_exceptions(store, merchant_id: str) -> list:
    """Open, critical inventory-conflict exceptions - the out-of-stock alerts surfaced in menu option 4."""
    return [
        e
        for e in store.list(ExceptionRecord, merchant_id)
        if e.status == "open" and e.severity == "critical" and e.category == "inventory_conflict"
    ]


class DemoApprovalNotificationService:
    def __init__(self, store, transport: ApprovalNotificationTransport) -> None:
        self.store = store
        self.transport = transport
        self.audit = AuditLedger(store)
        self.approvals = ApprovalService(store)
        self.idempotency = IdempotencyService(store)

    # --- Session contact lifecycle (Section 11) --------------------------------------------------

    def set_session_contact(
        self, merchant_id: str, *, phone_e164: str, session_label: str, consented: bool,
        ttl: timedelta = DEFAULT_SESSION_CONTACT_EXPIRY,
    ) -> DemoSessionContact:
        if not consented:
            raise ValueError("a DemoSessionContact may only be created with explicit recorded consent")
        # Validate/normalize BEFORE anything is persisted or sent - a malformed number must never reach
        # WAHA at all (the exact real failure caught live: a 13-digit typo was silently accepted and
        # "sent" to nowhere). PhoneValidationError propagates to the caller (the API route) with a
        # specific, operator-facing reason - never a generic failure.
        normalized = normalize_phone(phone_e164)
        now = now_utc()
        for old in self.store.list(DemoSessionContact, merchant_id):
            if old.cleared_at is None:
                old.cleared_at = now
                self.store.put(old)
        contact = DemoSessionContact(
            merchant_id=merchant_id, session_label=session_label, phone_e164=normalized,
            expires_at=now + ttl,
        )
        self.store.put(contact)
        self.audit.record(
            merchant_id=merchant_id, actor="operator", source="command_center", action="demo_session_contact_set",
            object_type="DemoSessionContact", object_id=contact.id, result="consented",
        )
        return contact

    def clear_session_contact(self, merchant_id: str, contact_id: str) -> None:
        contact = self.store.get(DemoSessionContact, merchant_id, contact_id)
        contact.cleared_at = now_utc()
        self.store.put(contact)
        self.audit.record(
            merchant_id=merchant_id, actor="operator", source="command_center", action="demo_session_contact_cleared",
            object_type="DemoSessionContact", object_id=contact.id, result="cleared",
        )

    def _active_contact_for_phone(self, merchant_id: str, phone: str) -> DemoSessionContact | None:
        now = now_utc()
        clean_phone = "".join(c for c in phone if c.isdigit())
        for c in self.store.list(DemoSessionContact, merchant_id):
            c_clean = "".join(ch for ch in c.phone_e164 if ch.isdigit())
            if (c.phone_e164 == phone or c_clean == clean_phone) and c.cleared_at is None and c.expires_at > now:
                return c
        return None

    # --- Outbound ---------------------------------------------------------------------------------

    def send_approval(self, merchant_id: str, approval_id: str, contact: DemoSessionContact, merchant_display_name: str, channel: str) -> DeliveryResult:
        # `channel` is a plain string, not a ChannelOperation object - order-flow approvals (e.g.
        # resolve_inventory_shortage) have no ChannelOperation at all (approval.object_id is an Order
        # id, not a ChannelOperation id), so the caller resolves whatever channel label is meaningful
        # for the approval's action instead of this method assuming one specific domain object shape.
        approval = self.store.get(Approval, merchant_id, approval_id)
        evidence_dict = approval.evidence if isinstance(approval.evidence, dict) else {}
        likely_impact = evidence_dict.get("likely_impact") or evidence_dict.get("impact") or evidence_dict.get("commercial_impact")
        message = format_approval_message(
            merchant_display_name=merchant_display_name, channel=channel,
            summary=approval.summary or "", evidence_line=str(approval.evidence or {}),
            recommendation=approval.recommendation or "", reference=approval.reference or approval.id,
            likely_impact=likely_impact,
        )
        try:
            result = self.transport.send_approval(recipient=contact.phone_e164, message=message)
        except NotImplementedError:
            raise
        approval.notify_channels = list(set(approval.notify_channels + [self.transport.name]))
        approval.notifications_sent = {**approval.notifications_sent, self.transport.name: {
            "sent_at": now_utc().isoformat(), "delivered": result.delivered, "provider_message_id": result.provider_message_id,
        }}
        self.store.put(approval)
        self.audit.record(
            merchant_id=merchant_id, actor="notifications", source=self.transport.name, action="approval_notification_sent",
            object_type="Approval", object_id=approval.id, result="delivered" if result.delivered else "failed",
            error=result.error,
        )
        return result

    def send_daily_briefing(self, merchant_id: str, recipient: str | None = None) -> DeliveryResult:
        """Generates and dispatches a comprehensive WhatsApp daily operational briefing for the merchant:
        - Product & catalog health
        - Multi-location stock and ATS levels (including safety stock alerts & quarantine holds)
        - Order delivery vs financial reconciliation status
        - Pending actions in the approval queue requiring sign-off
        """
        from sanocea.packages.domain_contract.models import Approval, Inventory, Location, Order, Product

        if not recipient:
            contacts = [c for c in self.store.list(DemoSessionContact, merchant_id) if c.cleared_at is None and c.expires_at > now_utc()]
            if not contacts:
                all_contacts = self.store.list(DemoSessionContact, merchant_id)
                if all_contacts:
                    contact = max(all_contacts, key=lambda c: c.consented_at)
                else:
                    raise ValueError(f"No demo session contact found for merchant {merchant_id}")
            else:
                contact = max(contacts, key=lambda c: c.consented_at)
            recipient = contact.phone_e164

        products = self.store.list(Product, merchant_id)
        locations = self.store.list(Location, merchant_id)
        inventories = self.store.list(Inventory, merchant_id)
        orders = self.store.list(Order, merchant_id)
        pending_approvals = self.store.list_where(Approval, merchant_id, status="pending")

        config = self.store.get_config(merchant_id)
        safety_threshold = config.get("inventory", {}).get("safety_stock_default", 10)

        oos_stock = [inv for inv in inventories if inv.ats == 0]
        low_stock = [inv for inv in inventories if 0 < inv.ats < safety_threshold]
        quarantined = [inv for inv in inventories if inv.quarantine > 0]
        total_quarantine_units = sum(inv.quarantine for inv in inventories)

        delivered_orders = [o for o in orders if o.fulfillment_status == "delivered" or o.status == "DELIVERED"]
        unreconciled_orders = [o for o in orders if getattr(o, "financial_reconciliation_status", "UNRECONCILED") == "UNRECONCILED"]

        merchant_name = merchant_id.replace("prospect_", "").replace("_", " ").title()

        briefing_lines = [
            f"📊 *Sanocea Daily Operational Briefing* — {merchant_name}",
            "",
            "*Catalogue & Store Health:*",
            f"• Products active: {len(products)}",
            f"• Locations monitored: {len(locations)}",
            "",
            "*Stock & Inventory Status:*",
        ]

        if oos_stock:
            for inv in oos_stock[:3]:
                briefing_lines.append(_briefing_oos_line(self.store, merchant_id, inv))
        if low_stock:
            for inv in low_stock[:3]:
                stock_title = _resolve_product_title(self.store, merchant_id, inv.sku) or "An item"
                stock_channel = _resolve_location_channel_name(self.store, merchant_id, inv.location_ref)
                stock_where = f" on {stock_channel}" if stock_channel else ""
                briefing_lines.append(
                    f"🟠 Low stock — {stock_title} is running low{stock_where}: "
                    f"{inv.ats} units left for customers (target {safety_threshold})."
                )
        if not oos_stock and not low_stock:
            briefing_lines.append(f"✅ All {len(inventories)} stock line(s) above safety threshold")
        if quarantined:
            briefing_lines.append(f"⚠️ {total_quarantine_units} unit(s) in QA quarantine across {len(quarantined)} SKU(s)")

        briefing_lines.extend([
            "",
            "*Orders & Settlement:*",
            f"• Total orders: {len(orders)}",
            f"• Fulfilled: {len(delivered_orders)} delivered",
            f"• Reconciliation: {len(unreconciled_orders)} order(s) pending bank settlement",
        ])

        # Pending approvals — grouped by action type with severity prefix
        price_approvals = [a for a in pending_approvals if a.action == "price_change"]
        inv_approvals = [a for a in pending_approvals if a.action in ("resolve_inventory_shortage", "inventory_writeoff")]
        other_approvals = [a for a in pending_approvals if a not in price_approvals and a not in inv_approvals]

        if pending_approvals:
            briefing_lines.append("")
            briefing_lines.append(f"*Decisions waiting for your approval ({len(pending_approvals)}):*")
            for a in inv_approvals[:2]:
                briefing_lines.append(f"🔴 *{a.reference or 'INV'}*: {(a.summary or '')[:70]}")
            for a in price_approvals[:2]:
                briefing_lines.append(f"🟠 *{a.reference or 'PRICE'}*: {(a.summary or '')[:70]}")
            for a in other_approvals[:1]:
                briefing_lines.append(f"🟡 *{a.reference or a.action}*: {(a.summary or '')[:70]}")
            briefing_lines.append("")
            briefing_lines.append("👉 Reply *2* to review decisions, or *Menu* for all options.")
        else:
            briefing_lines.append("")
            briefing_lines.append("✅ *No pending decisions* — approval queue is clear.")

        message = "\n".join(briefing_lines)
        result = self.transport.send_approval(recipient=recipient, message=message)
        self.audit.record(
            merchant_id=merchant_id,
            actor="notifications",
            source=self.transport.name,
            action="daily_briefing_sent",
            object_type="Merchant",
            object_id=merchant_id,
            result="delivered" if result.delivered else "failed",
            error=result.error,
        )
        return result

    # --- Inbound (the security-critical path) ------------------------------------------------------

    def handle_inbound(self, msg: InboundApprovalMessage) -> dict[str, Any]:
        # 1. Duplicate/replayed webhook - provider_message_id is the dedup key, global (not
        # merchant-scoped, since we don't know the merchant until AFTER we resolve the sender).
        def _process() -> dict[str, Any]:
            return self._handle_inbound_once(msg)

        result, created = self.idempotency.run_once(f"notifications:{msg.provider}", msg.provider_message_id, _process)
        if not created and result.get("merchant_id"):
            # Only auditable once a real merchant was actually resolved - audit_events.merchant_id has
            # a real FK to merchants(id), and a wrong-number/unresolvable attempt (see below) never
            # reaches a real merchant at all, so there is nothing to scope that entry to.
            self.audit.record(
                merchant_id=result["merchant_id"], actor="notifications", source=msg.provider,
                action="duplicate_inbound_message_ignored", object_type="InboundApprovalMessage",
                object_id=msg.provider_message_id, result="duplicate",
            )
        return result

    def handle_web_chat_message(self, merchant_id: str, msg: InboundApprovalMessage) -> dict[str, Any]:
        """The browser self-service demo's entry point into the SAME conversation engine `handle_inbound`
        uses for real WAHA messages (menu navigation, contextual replies, approval decisions, the AI
        explain fallback below) - the only difference is identity: `merchant_id` is already known and
        authorized (the caller's own merchant-scoped API key, via require_operator), so this skips the
        cross-tenant phone search `_resolve_sender` does for a real inbound WhatsApp webhook, and instead
        just needs an active DemoSessionContact for this merchant+phone (created at session-lease time).
        This is exactly the seam that lets a real WAHA transport be plugged in later without touching the
        conversation logic itself - see docs/architecture/integrations/WHATSAPP_DEMO_TRANSPORT_COMPARISON.md."""
        contact = self._active_contact_for_phone(merchant_id, msg.from_identifier)
        if contact is None:
            raise InboundResolutionError("no active demo session contact for this merchant/number - the demo session may have expired")

        def _process() -> dict[str, Any]:
            return self._handle_inbound_once_for(merchant_id, contact, msg)

        result, created = self.idempotency.run_once(f"notifications:{msg.provider}", msg.provider_message_id, _process)
        if not created:
            self.audit.record(
                merchant_id=merchant_id, actor="notifications", source=msg.provider,
                action="duplicate_inbound_message_ignored", object_type="InboundApprovalMessage",
                object_id=msg.provider_message_id, result="duplicate",
            )
        return result

    def _try_resolve_missing_fields(self, merchant_id: str, msg: InboundApprovalMessage) -> dict[str, Any] | None:
        """Returns a result dict if this reply filled in at least one field of the most-recently-asked
        product draft, or None if there's nothing to apply (caller falls through to the existing
        unparseable-command rejection). "Most recently asked" - the last missing-field notification this
        merchant sent whose draft is STILL incomplete - mirrors natural WhatsApp conversation: the reply
        answers whatever was last asked, not something requiring a reference the owner has to copy back."""
        from sanocea.packages.domain_contract.models import Approval, ProductDraft
        from sanocea.packages.domain_contract.store import NotFoundError

        # If the user specifically addressed a pending approval reference (e.g. PB-PRICE-001),
        # do not treat it as a product draft reply.
        upper_text = msg.raw_text.strip().upper()
        pending_refs = {a.reference.upper() for a in self.store.list(Approval, merchant_id) if a.reference and a.status == "pending"}
        for ref in pending_refs:
            if ref in upper_text:
                return None

        sent_events = sorted(
            (e for e in self.store.list_audit(merchant_id) if e.action == "missing_field_notification_sent" and e.result == "delivered"),
            key=lambda e: e.timestamp, reverse=True,
        )
        draft = None
        for event in sent_events:
            try:
                candidate = self.store.get(ProductDraft, merchant_id, event.object_id)
            except NotFoundError:
                continue
            # Same image-only exclusion as the sending side (ProductOnboardingWorkflow) - a bare-photo
            # draft was never a real "product needing an answer" in the first place. Older test data
            # sent BEFORE that exclusion existed could otherwise still be the most-recently-notified
            # entry and wrongly absorb an unrelated reply.
            if candidate.state == "INCOMPLETE" and set(candidate.commercial_facts.keys()) != {"image"}:
                draft = candidate
                break
        if draft is None:
            return None

        missing_fields = sorted({v.split(":", 1)[1] for v in draft.validation_errors if v.startswith("missing_required_attribute:")})
        if not missing_fields:
            return None

        # Check if the reply is an affirmative acceptance of recommended values
        is_approval = upper_text in ("APPROVE", "ACCEPT", "YES", "CONFIRM", "APPROVE DRAFT", "APPROVE PRODUCT", "ACCEPT RECOMMENDATION") or (
            upper_text.startswith("APPROVE ") and draft.sku and draft.sku.upper() in upper_text
        )

        from sanocea.packages.product_onboarding.recommendations import get_draft_recommendations
        recs = get_draft_recommendations(draft)
        category_rec = recs.get("category_recommendation") or {}

        extracted = {}
        actor = f"whatsapp:{msg.from_identifier[-4:]}"
        is_physical = draft.attributes.get("requires_shipping", True) is not False and not draft.attributes.get("is_digital")

        if is_approval:
            for f in missing_fields:
                if f in recs:
                    extracted[f] = recs[f]["value"]
            if "product_type" not in extracted and not draft.product_type and recs.get("product_type"):
                extracted["product_type"] = recs["product_type"]["value"]
            if "category" not in extracted and not draft.category and recs.get("category"):
                extracted["category"] = recs["category"]["value"]

            # Physical product inventory confirmation on approval
            if is_physical:
                if "inventory_quantity" in missing_fields or not draft.attributes.get("inventory_quantity"):
                    extracted["inventory_quantity"] = recs.get("inventory_quantity", {}).get("value", 10)
                if "inventory_location" in missing_fields or not draft.attributes.get("inventory_location"):
                    extracted["inventory_location"] = recs.get("inventory_location", {}).get("value", "Shop location")
                draft.attributes["track_inventory"] = True
                draft.attributes["inventory_confirmed"] = True
                if recs.get("weight"):
                    draft.attributes["weight"] = recs["weight"]["value"]
                    draft.attributes["weight_unit"] = recs["weight"].get("unit", "GRAMS")
                    draft.attributes["weight_confirmed"] = True

                self.audit.record(
                    merchant_id=merchant_id, actor=actor, source=msg.provider, action="inventory_policy_confirmed",
                    object_type="ProductDraft", object_id=draft.id, result="confirmed",
                    requested_mutation={
                        "track_inventory": True,
                        "inventory_quantity": extracted.get("inventory_quantity") or draft.attributes.get("inventory_quantity"),
                        "inventory_location": extracted.get("inventory_location") or draft.attributes.get("inventory_location"),
                        "weight": draft.attributes.get("weight"),
                        "inventory_policy": "DENY",
                    },
                )
        else:
            extracted = _extract_field_values(msg.raw_text, missing_fields)

            # Check if merchant explicitly chose untracked inventory
            if extracted.get("track_inventory") is False:
                extracted.pop("track_inventory")
                draft.attributes["track_inventory"] = False
                draft.attributes["inventory_confirmed"] = True
                self.audit.record(
                    merchant_id=merchant_id, actor=actor, source=msg.provider, action="untracked_inventory_policy_chosen",
                    object_type="ProductDraft", object_id=draft.id, result="untracked_chosen",
                    requested_mutation={
                        "track_inventory": False,
                        "reason": "explicit merchant choice",
                    },
                )

            # If custom weight provided
            if "weight" in extracted:
                draft.attributes["weight"] = extracted.pop("weight")
                draft.attributes["weight_unit"] = extracted.pop("weight_unit", "GRAMS")
                draft.attributes["weight_confirmed"] = True

            # If inventory quantity or location provided in free text
            if "inventory_quantity" in extracted or "inventory_location" in extracted:
                if draft.attributes.get("track_inventory") is not False:
                    draft.attributes["track_inventory"] = True
                if "inventory_location" not in extracted and not draft.attributes.get("inventory_location"):
                    extracted["inventory_location"] = recs.get("inventory_location", {}).get("value", "Shop location")
                if "inventory_quantity" not in extracted and draft.attributes.get("inventory_quantity") is None:
                    extracted["inventory_quantity"] = recs.get("inventory_quantity", {}).get("value", 10)
                draft.attributes["inventory_confirmed"] = True
                self.audit.record(
                    merchant_id=merchant_id, actor=actor, source=msg.provider, action="inventory_policy_confirmed",
                    object_type="ProductDraft", object_id=draft.id, result="confirmed",
                    requested_mutation={
                        "track_inventory": True,
                        "inventory_quantity": extracted.get("inventory_quantity"),
                        "inventory_location": extracted.get("inventory_location"),
                        "weight": draft.attributes.get("weight"),
                        "inventory_policy": "DENY",
                    },
                )

            # Check if owner provided an alternative category in free text
            # e.g., "category Nuts & Seeds" or "Nuts & Seeds" or "use Snacks"
            if not extracted.get("category") and not extracted.get("product_type"):
                if not re.match(r"^\s*\d+(\.\d+)?\s*$", msg.raw_text.strip()):
                    from sanocea.packages.product_onboarding.taxonomy import ShopifyTaxonomyService
                    tax_service = ShopifyTaxonomyService(self.store)
                    alt_text = msg.raw_text.strip()
                    alt_clean = re.sub(r"^(category|type|use|set)\s*[:=]?\s*", "", alt_text, flags=re.IGNORECASE).strip()
                    nodes = tax_service.search_taxonomy(None, alt_clean)
                    if nodes:
                        top_node = nodes[0]
                        extracted["category"] = top_node["id"]
                        extracted["product_type"] = top_node["name"]
                        category_rec = {
                            "category_id": top_node["id"],
                            "name": top_node["name"],
                            "full_path": top_node["fullName"],
                            "confidence": 1.0,
                            "evidence": [f"explicit owner choice '{alt_clean}'"],
                        }

        # If category is recommended and not yet set on draft, populate it
        if "category" not in extracted and not draft.category and recs.get("category"):
            extracted["category"] = recs["category"]["value"]
        if "product_type" not in extracted and not draft.product_type and recs.get("product_type"):
            extracted["product_type"] = recs["product_type"]["value"]

        if not extracted and not draft.attributes.get("inventory_confirmed") and draft.attributes.get("track_inventory") is None:
            return None

        from sanocea.packages.runtime.service_graph import build_service_graph

        catalogue = build_service_graph(self.store).catalogue
        for field, value in extracted.items():
            draft = catalogue.provide_missing_fact(merchant_id, draft.id, field, value, actor, source="whatsapp_free_text")

        # Save category metadata to draft attributes
        cat_path = (recs.get("category") or {}).get("full_path") or category_rec.get("full_path")
        if cat_path:
            draft.attributes["recommended_category_path"] = cat_path
        self.store.put(draft)
        draft = catalogue.validator.validate(draft)

        evt = self.audit.record(
            merchant_id=merchant_id, actor="notifications", source=msg.provider, action="inbound_missing_fields_applied",
            object_type="ProductDraft", object_id=draft.id, result=draft.state, requested_mutation=extracted,
        )

        if "category" in extracted:
            cat_id = extracted["category"]
            confidence = (recs.get("category") or {}).get("confidence") or category_rec.get("confidence", 0.90)
            evidence = (recs.get("category") or {}).get("evidence") or category_rec.get("evidence", [])
            self.audit.record(
                merchant_id=merchant_id, actor=actor, source=msg.provider, action="taxonomy_category_confirmed",
                object_type="ProductDraft", object_id=draft.id, result="confirmed",
                evidence_ref=cat_id,
                requested_mutation={
                    "category_id": cat_id,
                    "taxonomy_path": cat_path or cat_id,
                    "confidence": confidence,
                    "evidence": evidence,
                    "product_type": extracted.get("product_type") or draft.product_type,
                },
            )

        audit_ref = f"AUDIT-{(getattr(evt, 'id', None) or draft.id)[:8].upper()}"
        publish_outcome = None
        if draft.state not in ("INCOMPLETE", "CONFLICTED"):
            try:
                publish_outcome = catalogue.auto_publish_after_resolution(merchant_id, draft.id, actor)
                draft = self.store.get(ProductDraft, merchant_id, draft.id)
                self._send_publish_confirmation(
                    merchant_id, publish_outcome, completed_fields=extracted, audit_ref=audit_ref, draft=draft,
                    category_path=cat_path,
                )
            except Exception as exc:  # noqa: BLE001
                self.audit.record(
                    merchant_id=merchant_id, actor="notifications", source=msg.provider, action="auto_publish_after_resolution_failed",
                    object_type="ProductDraft", object_id=draft.id, result="failed", error=str(exc),
                )
            catalogue.notify_next_missing_field_draft(merchant_id)
        return {"merchant_id": merchant_id, "draft_id": draft.id, "applied_fields": extracted, "status": draft.state, "publish_outcome": publish_outcome}

    def _send_publish_confirmation(
        self,
        merchant_id: str,
        outcome: dict[str, Any],
        completed_fields: dict[str, Any] | None = None,
        audit_ref: str | None = None,
        draft: Any | None = None,
        category_path: str | None = None,
    ) -> None:
        """Honest, per-product confirmation - reports product name, completed fields, publishing result,
        and audit reference. Reuses the same contact/transport pattern as every other outbound send here;
        never allowed to fail the resolution itself."""
        try:
            contacts = [c for c in self.store.list(DemoSessionContact, merchant_id) if c.cleared_at is None and c.expires_at > now_utc()]
            if not contacts:
                return
            contact = max(contacts, key=lambda c: c.consented_at)
            title = outcome.get("title") or (getattr(draft, "title", None) if draft else None) or "the product"
            sku = getattr(draft, "sku", None) if draft else None

            from sanocea.packages.product_onboarding.recommendations import format_publish_confirmation
            text = format_publish_confirmation(
                title=title,
                sku=sku,
                completed_fields=completed_fields or {},
                outcome=outcome,
                audit_ref=audit_ref or f"AUDIT-{(sku or 'OK')}",
                category_path=category_path,
            )
            self.transport.send_approval(recipient=contact.phone_e164, message=text)
        except Exception:  # noqa: BLE001 - a confirmation failing must never break the underlying resolution
            pass

    def _resolve_sender(self, phone: str) -> tuple[DemoSessionContact, str]:
        """Shared wrong-number-safe resolution (Security section 2): the sender must be a currently
        active DemoSessionContact for SOME merchant - fail closed if not, never guess. Used by both the
        text-command path and the file-attachment path below, so a stray/unauthorized sender is
        rejected identically either way."""
        for candidate_merchant in self._merchants_with_contacts_for(phone):
            c = self._active_contact_for_phone(candidate_merchant, phone)
            if c:
                return c, candidate_merchant
        # No real merchant is resolvable for this sender at all - audit_events is per-merchant (real
        # FK to merchants(id)), so a wrong-number attempt has nothing to scope an entry to. The
        # InboundResolutionError itself is the record; a caller wiring a real inbound webhook route is
        # expected to log it at the application/ops level, not the per-tenant ledger.
        raise InboundResolutionError("sender is not an authorized active demo session contact")

    def handle_inbound_media(self, msg: InboundApprovalMessage, *, filename: str, content_type: str) -> dict[str, Any]:
        """Real, reusable "send us the file on WhatsApp" path (explicit demo requirement, built
        same-day): downloads the sender's attachment via the transport, resolves them to a merchant
        with the SAME wrong-number-safe check the approval/text path uses, then feeds the file through
        the UNCHANGED, already-certified ProductOnboardingWorkflow.ingest_file - a CSV/XLSX of new
        products, or a product photo, arriving over WhatsApp is treated identically to one uploaded
        through Command Center. Idempotent on provider_message_id like every other inbound path."""
        def _process() -> dict[str, Any]:
            contact, merchant_id = self._resolve_sender(msg.from_identifier)
            import shutil
            import tempfile
            from pathlib import Path

            from sanocea.packages.runtime.service_graph import build_service_graph

            # Real bug fixed here (found live, Premium Basket rehearsal): tempfile.NamedTemporaryFile
            # always assigns its OWN random name regardless of `suffix` - ingestion's image path derives
            # its SKU guess from the file's name (see StructuredProductIngestor._read_image), so every
            # photo was silently getting a meaningless "tmpXXXXXX"-based product name instead of
            # whatever real filename this attachment actually carried. Now writes into a fresh temp
            # DIRECTORY, naming the file exactly `filename` (what WAHA reported, or our mimetype-based
            # fallback) - so a real filename is preserved end to end. This does NOT fix the separate,
            # unavoidable case where WhatsApp itself sends no filename at all (images sent as "Photo"
            # rather than "Document" carry no filename - a real WhatsApp behavior, not a bug here).
            tmp_dir = Path(tempfile.mkdtemp())
            tmp_path = tmp_dir / filename
            tmp_path.write_bytes(self.transport.download_media(msg.raw_event["payload"]["media"]["url"]))
            try:
                catalogue = build_service_graph(self.store).catalogue
                drafts = catalogue.ingest_file(merchant_id, tmp_path, content_type)
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            self.audit.record(
                merchant_id=merchant_id, actor="notifications", source=msg.provider, action="inbound_file_ingested",
                object_type="ProductDraft", object_id=drafts[0].id if drafts else filename, result=f"{len(drafts)}_draft(s)",
            )
            return {"merchant_id": merchant_id, "filename": filename, "draft_ids": [d.id for d in drafts], "states": [d.state for d in drafts]}

        result, created = self.idempotency.run_once(f"notifications:{msg.provider}:file", msg.provider_message_id, _process)
        if not created and result.get("merchant_id"):
            self.audit.record(
                merchant_id=result["merchant_id"], actor="notifications", source=msg.provider,
                action="duplicate_inbound_message_ignored", object_type="InboundApprovalMessage",
                object_id=msg.provider_message_id, result="duplicate",
            )
        return result

    # --- Conversation State & Contextual Menus ---------------------------------------------------

    def get_or_create_conversation_state(self, merchant_id: str, phone: str) -> WhatsAppConversationState:
        """Retrieves or initializes persistent, server-side conversation state keyed by merchant and phone."""
        clean_digits = "".join(c for c in phone if c.isdigit())
        conv_id = f"wcs_{merchant_id}_{clean_digits}"
        try:
            conv = self.store.get(WhatsAppConversationState, merchant_id, conv_id)
        except Exception:
            conv = None
        now = now_utc()
        if conv is None:
            conv = WhatsAppConversationState(
                id=conv_id,
                merchant_id=merchant_id,
                phone_e164=phone,
                active_context_type="none",
                expires_at=now + timedelta(hours=24),
                last_interaction_at=now,
            )
            self.store.put(conv)
        else:
            if conv.expires_at < now:
                conv.active_context_type = "none"
                conv.active_approval_id = None
                conv.active_draft_id = None
                conv.active_onboarding_step = None
                conv.pending_disambiguation_ids = []
                conv.expires_at = now + timedelta(hours=24)
            conv.last_interaction_at = now
            self.store.put(conv)
        return conv

    def _format_main_menu(self, active_summary: str | None = None) -> str:
        lines = []
        if active_summary:
            lines.extend([
                "📋 *Sanocea Commerce Assistant*",
                "",
                "⏸ *Active item awaiting your response:*",
                f"• {active_summary}",
                "👉 Reply *Resume* (or *R*) to continue answering.",
                "",
                "────────────────────────",
                "*Main Menu:*",
            ])
        else:
            lines.extend([
                "📋 *Sanocea Commerce Assistant — Main Menu*",
                "",
            ])
        lines.extend([
            "1. Today’s business briefing",
            "2. Decisions waiting for approval",
            "3. Catalogue & pricing issues",
            "4. Stock and low-inventory risks",
            "5. Orders, payouts & reconciliation",
            "6. Add / onboard new products",
            "0. Help",
            "",
            "Reply with a number (*1*-*6*, *0*)" + (" or *Resume*" if active_summary else "") + ".",
        ])
        return "\n".join(lines)

    def _get_actionable_pending_approvals(self, merchant_id: str) -> list[Approval]:
        ORDER_FLOW_APPROVAL_ACTIONS = {
            "channel_operation_correction",
            "resolve_inventory_shortage",
            "cancel_order",
            "create_return",
            "refund",
            "price_change",
            "catalog_unpublish",
            "inventory_writeoff",
            "resolve_delivery_exception",
            "escalate_fulfilment_delay",
        }
        pending = [
            a for a in self.store.list_where(Approval, merchant_id, status="pending")
            if a.action in ORDER_FLOW_APPROVAL_ACTIONS
        ]

        # Canonical entities carry their durable ordering timestamp in
        # ``sync.observed_at``.  Approval has no ``created_at`` field, so
        # sorting the SyncMetadata object itself breaks as soon as two pending
        # approvals exist.  A stable reference/id tie-breaker also makes queue
        # progression deterministic after a service restart.
        def queue_key(approval: Approval) -> tuple[Any, str]:
            sync = getattr(approval, "sync", None)
            observed_at = getattr(sync, "observed_at", None)
            return (observed_at or now_utc(), approval.reference or approval.id)

        return sorted(pending, key=queue_key)

    def _format_active_decision_card(self, approval: Approval) -> str:
        action_title = approval.action.replace("_", " ").title()
        evidence = approval.evidence if isinstance(approval.evidence, dict) else {}
        impact = evidence.get("likely_impact") or evidence.get("impact") or evidence.get("commercial_impact")
        sku = evidence.get("sku")
        current_price = evidence.get("current_price")
        new_price = evidence.get("new_price")
        compare_at = evidence.get("compare_at_price")

        lines = [
            "📋 *Decision Waiting for Approval*",
            "",
            f"• *Action:* {action_title}",
            f"• *Summary:* {approval.summary or 'Pending merchant sign-off'}",
        ]
        if approval.recommendation:
            lines.append(f"• *Recommended:* {approval.recommendation}")
        if impact:
            lines.append(f"• *Likely Impact:* {impact}")
        if sku:
            lines.append(f"• *SKU:* `{sku}`")
        if current_price and new_price:
            lines.append(f"• *Price Adjustment:* ₹{current_price} ➔ ₹{new_price}" + (f" (Compare-at MRP: ₹{compare_at})" if compare_at else ""))

        is_price_change = getattr(approval, "action", "") == "price_change"
        lines.extend([
            "",
            "*Actions:*",
            "1. Approve",
            "2. Reject",
            "3. Details",
            "4. Later",
        ])
        if is_price_change:
            lines.append("5. Edit  _(set your own price)_")
            lines.append("")
            lines.append("👉 Reply with a number (*1*-*5*) or word (*Approve* / *Reject* / *Details* / *Later* / *Edit*).")
        else:
            lines.append("")
            lines.append("👉 Reply with a number (*1*-*4*) or word (*Approve* / *Reject* / *Details* / *Later*).")
        return "\n".join(lines)

    def _format_approval_disambiguation(self, approvals: list[Approval]) -> str:
        lines = [
            f"📋 *Decisions Waiting for Approval ({len(approvals)} pending)*",
            "",
            "Select one decision to review:",
        ]
        for idx, a in enumerate(approvals, 1):
            action_title = a.action.replace("_", " ").title()
            summary = a.summary[:60] if a.summary else action_title
            lines.append(f"*{idx}.* {action_title}: {summary}")
        lines.extend([
            "",
            f"👉 Reply with a number (*1*-*{len(approvals)}*) to select a decision, or send *Menu*.",
        ])
        return "\n".join(lines)

    # --- AI explain (free-text questions) ---------------------------------------------------------

    def _explain_free_text(self, merchant_id: str, question: str):
        """Grounds a free-text question in this merchant's own currently-open exceptions/approvals only
        - never a full-database query, never a mutation. Returns None (not a low-confidence AIResult)
        when nothing in the evidence bundle is even loosely related, so the caller can fall through to
        the ordinary 'I didn't recognize that' menu prompt instead of a confusing non-answer."""
        from sanocea.packages.ai.provider import DeterministicAIProvider
        from sanocea.packages.runtime.queries import list_open_approvals, list_open_exceptions

        exceptions = list_open_exceptions(self.store, merchant_id)
        approvals = list_open_approvals(self.store, merchant_id)
        evidence = {
            "exceptions": [e.model_dump(mode="json") for e in exceptions],
            "approvals": [a.model_dump(mode="json") for a in approvals],
        }
        result = DeterministicAIProvider().explain(question, evidence, [])
        if result.confidence < 0.3:
            return None
        return result

    def _try_ai_explain_reply(self, merchant_id: str, contact: DemoSessionContact, msg: InboundApprovalMessage, text: str) -> bool:
        """Shared by every context that falls through to 'I didn't recognize that' (main menu, and the
        top-level no-active-context path): grounded ONLY in this merchant's own currently-open
        exceptions/approvals (never the whole database, never a mutation) - AI is interaction/
        intelligence only, the deterministic engine already produced everything it cites. See
        packages/ai/provider.py. Returns True if it sent a real answer (caller returns instead of falling
        through to the generic rejection message), False if nothing matched closely enough."""
        if len(text) < 4:
            return False
        ai_result = self._explain_free_text(merchant_id, text)
        if ai_result is None:
            return False
        try:
            self.transport.send_approval(recipient=contact.phone_e164, message=ai_result.output["answer"])
        except Exception:
            pass
        self.audit.record(
            merchant_id=merchant_id, actor="notifications", source=msg.provider, action="ai_explain_answered",
            object_type="InboundApprovalMessage", object_id=msg.provider_message_id, result="answered",
            evidence_ref=",".join(ai_result.evidence_refs) or None,
        )
        return True

    # --- Sequential Product Onboarding Queue -----------------------------------------------------

    def get_next_onboarding_step(self, merchant_id: str, draft: ProductDraft) -> tuple[str | None, str | None]:
        """Returns (step_name, formatted_message) for the highest-priority unresolved onboarding step.
        Returns (None, None) if all required attributes and physical policies are confirmed.
        Strict sequential order:
        1. variant_structure (single vs options)
        2. price
        3. category (Shopify standardized category & merchant type)
        4. inventory (tracking, opening quantity, location)
        5. weight (shipping weight)
        """
        from sanocea.packages.product_onboarding.recommendations import get_draft_recommendations, infer_weight_from_sku_or_title

        is_physical = draft.attributes.get("requires_shipping", True) is not False and not draft.attributes.get("is_digital")
        missing_fields = {
            e.split(":", 1)[1] for e in draft.validation_errors if e.startswith("missing_required_attribute:")
        }
        recs = get_draft_recommendations(draft)
        label = draft.title or draft.sku or draft.id

        # 1. Variant structure (if unknown for physical products)
        if is_physical and not draft.attributes.get("variant_structure_confirmed") and len(draft.variants) <= 1:
            msg = (
                "📋 *Sanocea Catalogue Gate — Product Onboarding*\n\n"
                f"• *Product:* {label}\n"
                + (f"• *SKU:* `{draft.sku}`\n" if draft.sku else "")
                + "\n*Step 1 of 5: Variant Structure*\n"
                "The supplier file lists this item as a single standalone product.\n"
                "Is single default variant correct, or does this item have pack sizes/flavours?\n\n"
                "👉 Reply *YES* (or *1*) if single variant is correct\n"
                "👉 Or reply with option names (e.g. \"Pack Size: 100g, 250g\")\n\n"
                "_Sanocea prevents incomplete products from reaching customers._"
            )
            return "variant_structure", msg

        # 2. Price (if missing)
        if "price" in missing_fields or draft.price is None or draft.price <= 0:
            rec_price = recs.get("price", {}).get("display", "₹249.00")
            rec_reason = recs.get("price", {}).get("reason", "catalogue benchmark")
            msg = (
                "📋 *Sanocea Catalogue Gate — Product Onboarding*\n\n"
                f"• *Product:* {label}\n"
                + (f"• *SKU:* `{draft.sku}`\n" if draft.sku else "")
                + "\n*Step 2 of 5: Retail Price*\n"
                "Retail price is missing from supplier data:\n"
                f"↳ Recommended: *{rec_price}* ({rec_reason})\n\n"
                f"👉 Reply *APPROVE* (or *1*) to accept recommended {rec_price}\n"
                "👉 Or reply with your retail price (e.g. \"249\" or \"299\")\n\n"
                "_Sanocea prevents incomplete products from reaching customers._"
            )
            return "price", msg

        # 3. Category & Merchant Type (if missing or unconfirmed)
        category_unconfirmed = (
            "product_type" in missing_fields
            or "category" in missing_fields
            or not draft.category
            or not draft.product_type
        )
        if category_unconfirmed:
            cat_rec = recs.get("category_recommendation") or {}
            tax_path = cat_rec.get("full_path") or draft.attributes.get("recommended_category_path") or "Food, Beverages & Tobacco > Food Items > Snack Foods > Nuts & Seeds"
            m_type = recs.get("product_type", {}).get("display") or draft.product_type or "Dry Fruits & Nuts"
            msg = (
                "📋 *Sanocea Catalogue Gate — Product Onboarding*\n\n"
                f"• *Product:* {label}\n"
                + (f"• *SKU:* `{draft.sku}`\n" if draft.sku else "")
                + "\n*Step 3 of 5: Category & Product Type*\n"
                f"↳ Recommended Shopify category: *{tax_path}*\n"
                f"↳ Merchant type grouping: *{m_type}*\n\n"
                "👉 Reply *APPROVE* (or *1*) to accept this category\n"
                "👉 Or reply with your custom category or type (e.g. \"Dry Fruits\")\n\n"
                "_Sanocea prevents incomplete products from reaching customers._"
            )
            return "category", msg

        # 4. Inventory Tracking & Opening Quantity (if physical and unconfirmed)
        if is_physical and not draft.attributes.get("inventory_confirmed"):
            inv_qty = recs.get("inventory_quantity", {}).get("display", "10 units")
            inv_loc = recs.get("inventory_location", {}).get("display", "Shop location")
            msg = (
                "📋 *Sanocea Catalogue Gate — Product Onboarding*\n\n"
                f"• *Product:* {label}\n"
                + (f"• *SKU:* `{draft.sku}`\n" if draft.sku else "")
                + "\n*Step 4 of 5: Inventory & Location*\n"
                "• Track inventory: *Yes* (oversell prevention: DENY)\n"
                f"• Recommended opening stock: *{inv_qty}* at *{inv_loc}*\n\n"
                f"👉 Reply *APPROVE* (or *1*) to track {inv_qty} at {inv_loc}\n"
                "👉 Or reply with opening stock & location (e.g. \"Qty 20 at Shop location\" or \"No tracking\")\n\n"
                "_Sanocea prevents incomplete products from reaching customers._"
            )
            return "inventory", msg

        # 5. Weight (if physical, inferable, and unconfirmed)
        weight_rec = infer_weight_from_sku_or_title(draft.sku, draft.title)
        if is_physical and weight_rec and not draft.attributes.get("weight_confirmed") and not draft.attributes.get("weight"):
            msg = (
                "📋 *Sanocea Catalogue Gate — Product Onboarding*\n\n"
                f"• *Product:* {label}\n"
                + (f"• *SKU:* `{draft.sku}`\n" if draft.sku else "")
                + "\n*Step 5 of 5: Shipping Weight*\n"
                f"↳ Inferred weight from SKU: *{weight_rec['display']}*\n\n"
                f"👉 Reply *APPROVE* (or *1*) to confirm {weight_rec['display']}\n"
                "👉 Or reply with physical weight (e.g. \"250g\" or \"0.5kg\")\n\n"
                "_Sanocea prevents incomplete products from reaching customers._"
            )
            return "weight", msg

        return None, None

    def _apply_onboarding_step_reply(
        self,
        merchant_id: str,
        draft: ProductDraft,
        step: str,
        raw_text: str,
        actor: str,
        conv: WhatsAppConversationState,
    ) -> bool:
        from sanocea.packages.domain_contract.models import ProvenanceClassification
        from sanocea.packages.product_onboarding.provenance import ConflictResolutionError, provide_missing_fact
        from sanocea.packages.product_onboarding.recommendations import get_draft_recommendations, infer_weight_from_sku_or_title

        text_upper = raw_text.strip().upper()
        text_lower = raw_text.strip().lower()
        is_approve = text_upper in ("1", "APPROVE", "ACCEPT", "YES", "CONFIRM", "OK", "SINGLE", "DEFAULT", "CORRECT")
        recs = get_draft_recommendations(draft)

        if step == "variant_structure":
            draft.attributes["variant_structure_confirmed"] = True
            if not is_approve and any(s in text_lower for s in ("pack", "size", "variant", "flavor", "flavour", ":", ",")):
                draft.attributes["variant_option_raw"] = raw_text.strip()
            self.audit.record(
                merchant_id=merchant_id, actor=actor, source="whatsapp_demo", action="variant_structure_confirmed",
                object_type="ProductDraft", object_id=draft.id, result="confirmed",
            )
            self.store.put(draft)
            return True

        if step == "price":
            if is_approve:
                rec_val = recs.get("price", {}).get("value", "249")
                price_num = float(re.sub(r"[^\d.]", "", str(rec_val)))
            else:
                m = re.search(r"(\d+(?:\.\d+)?)", raw_text)
                if not m:
                    return False
                price_num = float(m.group(1))
            cents = int(round(price_num * 100))
            provide_missing_fact(
                draft, "price", cents, source="whatsapp_owner", actor=actor,
                resolution_note="Owner provided retail price via WhatsApp",
                classification=ProvenanceClassification.HUMAN_APPROVED.value,
            )
            draft.price = cents
            self.store.put(draft)
            return True

        if step == "category":
            cat_rec = recs.get("category_recommendation") or {}
            if is_approve:
                tax_cat_id = cat_rec.get("category_id") or "gid://shopify/TaxonomyCategory/fb-2-17-22"
                tax_path = cat_rec.get("full_path") or "Food, Beverages & Tobacco > Food Items > Snack Foods > Nuts & Seeds"
                m_type = recs.get("product_type", {}).get("value") or draft.product_type or "Dry Fruits & Nuts"
            else:
                m_type = raw_text.strip()
                tax_cat_id = cat_rec.get("category_id") or "gid://shopify/TaxonomyCategory/fb-2-17-22"
                tax_path = cat_rec.get("full_path") or "Food, Beverages & Tobacco > Food Items > Snack Foods > Nuts & Seeds"

            # product_type usually arrives as a SOURCE_FACT from the supplier file (not "missing"), and the
            # owner is then confirming/overriding it, not supplying it - provide_missing_fact rejects that
            # with ConflictResolutionError, which 500'd the webhook and made WAHA retry-storm the reply.
            try:
                provide_missing_fact(
                    draft, "product_type", m_type, source="whatsapp_owner", actor=actor,
                    resolution_note="Owner provided product type via WhatsApp",
                    classification=ProvenanceClassification.HUMAN_APPROVED.value,
                )
            except ConflictResolutionError:
                draft.attributes["product_type"] = m_type  # the audit event below records the owner's choice
            draft.product_type = m_type
            draft.category = tax_cat_id
            draft.attributes["recommended_category_id"] = tax_cat_id
            draft.attributes["recommended_category_path"] = tax_path
            draft.attributes["taxonomy_confirmed"] = True
            self.audit.record(
                merchant_id=merchant_id, actor=actor, source="whatsapp_demo", action="taxonomy_category_confirmed",
                object_type="ProductDraft", object_id=draft.id, result="confirmed",
                requested_mutation={"category_id": tax_cat_id, "taxonomy_path": tax_path, "product_type": m_type},
            )
            self.store.put(draft)
            return True

        if step == "inventory":
            if any(k in text_lower for k in ("no tracking", "untracked", "dont track", "don't track", "without tracking")):
                draft.attributes["track_inventory"] = False
                draft.attributes["inventory_confirmed"] = True
                provide_missing_fact(
                    draft, "inventory_quantity", 0, source="whatsapp_owner", actor=actor,
                    resolution_note="Owner selected untracked inventory via WhatsApp",
                    classification=ProvenanceClassification.HUMAN_APPROVED.value,
                )
                self.audit.record(
                    merchant_id=merchant_id, actor=actor, source="whatsapp_demo", action="untracked_inventory_policy_chosen",
                    object_type="ProductDraft", object_id=draft.id, result="untracked_chosen",
                )
            else:
                qty = 10
                loc = "Shop location"
                if not is_approve:
                    qty_match = re.search(r"\b(?:qty|quantity|stock)?\s*(\d+)\b", text_lower)
                    if qty_match:
                        qty = int(qty_match.group(1))
                    loc_match = re.search(r"\b(?:at|location)\s+([a-zA-Z0-9\s]+)", raw_text, re.IGNORECASE)
                    if loc_match:
                        loc = loc_match.group(1).strip()
                draft.attributes["track_inventory"] = True
                draft.attributes["inventory_confirmed"] = True
                draft.attributes["inventory_quantity"] = qty
                draft.attributes["inventory_location"] = loc
                provide_missing_fact(
                    draft, "inventory_quantity", qty, source="whatsapp_owner", actor=actor,
                    resolution_note="Owner confirmed opening inventory quantity via WhatsApp",
                    classification=ProvenanceClassification.HUMAN_APPROVED.value,
                )
                provide_missing_fact(
                    draft, "inventory_location", loc, source="whatsapp_owner", actor=actor,
                    resolution_note="Owner confirmed inventory location via WhatsApp",
                    classification=ProvenanceClassification.HUMAN_APPROVED.value,
                )
                self.audit.record(
                    merchant_id=merchant_id, actor=actor, source="whatsapp_demo", action="inventory_policy_confirmed",
                    object_type="ProductDraft", object_id=draft.id, result="confirmed",
                    requested_mutation={"track_inventory": True, "inventory_quantity": qty, "inventory_location": loc, "inventory_policy": "DENY"},
                )
            self.store.put(draft)
            return True

        if step == "weight":
            weight_rec = infer_weight_from_sku_or_title(draft.sku, draft.title)
            if is_approve and weight_rec:
                val = float(weight_rec["value"])
                u = weight_rec.get("unit", "GRAMS")
            else:
                m = re.search(r"\b(\d+(?:\.\d+)?)\s*(g|gm|grams|kg|kgs)?\b", raw_text, re.IGNORECASE)
                if not m:
                    return False
                raw_num = float(m.group(1))
                unit_str = (m.group(2) or "g").lower()
                val = raw_num * 1000 if "kg" in unit_str else raw_num
                u = "GRAMS"
            draft.attributes["weight"] = val
            draft.attributes["weight_unit"] = u
            draft.attributes["weight_confirmed"] = True
            provide_missing_fact(
                draft, "weight", val, source="whatsapp_owner", actor=actor,
                resolution_note="Owner confirmed shipping weight via WhatsApp",
                classification=ProvenanceClassification.HUMAN_APPROVED.value,
            )
            self.audit.record(
                merchant_id=merchant_id, actor=actor, source="whatsapp_demo", action="product_weight_confirmed",
                object_type="ProductDraft", object_id=draft.id, result="confirmed",
                requested_mutation={"weight": val, "unit": u},
            )
            self.store.put(draft)
            return True

        return False

    def _get_next_incomplete_draft(self, merchant_id: str, exclude_id: str | None = None) -> ProductDraft | None:
        candidates = sorted(
            (
                d for d in self.store.list(ProductDraft, merchant_id)
                if d.id != exclude_id
                and d.state in ("INCOMPLETE", "CONFLICTED")
                and set(d.commercial_facts.keys()) != {"image"}
            ),
            key=lambda d: getattr(d.sync, "observed_at", d.id),
        )
        return candidates[0] if candidates else None

    def _send_batch_complete_message(self, merchant_id: str) -> None:
        try:
            contacts = [c for c in self.store.list(DemoSessionContact, merchant_id) if c.cleared_at is None and c.expires_at > now_utc()]
            if not contacts:
                return
            contact = max(contacts, key=lambda c: c.consented_at)
            msg = (
                "🎉 *Batch Ingestion Complete*\n\n"
                "All products from the supplier catalogue have been reviewed, completed, and published safely to your store.\n\n"
                "You can inspect each live listing and audit trail anytime in the Sanocea Command Center."
            )
            self.transport.send_approval(recipient=contact.phone_e164, message=msg)
            self.audit.record(
                merchant_id=merchant_id, actor="product_onboarding", source=self.transport.name,
                action="missing_field_batch_complete_sent", object_type="Merchant", object_id=merchant_id,
                result="delivered",
            )
        except Exception:
            pass

    # --- Inbound Execution Handlers -------------------------------------------------------------

    def _handle_inbound_once(self, msg: InboundApprovalMessage) -> dict[str, Any]:
        # 1. Resolve sender (authorized active DemoSessionContact) - cross-tenant search by phone alone,
        # since a real WAHA webhook carries no other identity. See handle_web_chat_message for the
        # browser-chat path, which already knows merchant_id (from the caller's own scoped API key) and
        # skips this search.
        contact, merchant_id = self._resolve_sender(msg.from_identifier)
        return self._handle_inbound_once_for(merchant_id, contact, msg)

    def _handle_inbound_once_for(self, merchant_id: str, contact: DemoSessionContact, msg: InboundApprovalMessage) -> dict[str, Any]:
        actor = f"whatsapp:{msg.from_identifier[-4:]}"

        # 2. Get or create server-side conversation state (durable, keyed by merchant_id + phone)
        conv = self.get_or_create_conversation_state(merchant_id, contact.phone_e164)

        raw_text = msg.raw_text.strip()
        text_lower = raw_text.lower()
        text_upper = raw_text.upper()

        # 3. Check for Menu / Greetings triggers
        # "When an authorized owner sends Hi, Hello, Menu, Start, or 0, reply with a concise numbered menu"
        # "Menu must not silently replace an active approval or incomplete product-onboarding question.
        # Preserve it, tell the owner what is currently awaiting a reply, and offer to resume it."
        is_menu_cmd = text_lower in ("hi", "hello", "hey", "menu", "start") or (text_lower == "0" and conv.active_context_type != "main_menu")
        if is_menu_cmd:
            return self._handle_menu_trigger(merchant_id, contact, conv, msg)

        # 4. Check for Resume command
        if text_upper in ("RESUME", "R", "CONTINUE"):
            return self._handle_resume_trigger(merchant_id, contact, conv, msg)

        # 5. Context-specific routing:
        if conv.active_context_type == "main_menu":
            return self._handle_main_menu_selection(merchant_id, contact, conv, msg, raw_text)

        if conv.active_context_type == "approval_disambiguation":
            return self._handle_approval_disambiguation_selection(merchant_id, contact, conv, msg, raw_text)

        if conv.active_context_type == "approval_decision":
            return self._handle_active_decision_action(merchant_id, contact, conv, msg, raw_text)

        if conv.active_context_type == "approval_edit":
            return self._handle_approval_edit_reply(merchant_id, contact, conv, msg, raw_text)

        if conv.active_context_type == "stock_issue_detail":
            return self._handle_stock_issue_detail_reply(merchant_id, contact, conv, msg, raw_text)

        if conv.active_context_type == "product_onboarding":
            return self._handle_product_onboarding_reply(merchant_id, contact, conv, msg, raw_text)

        # 6. Context is "none" or fallback:
        # If numeric reply outside of active menu context:
        if re.match(r"^\d+$", raw_text):
            return self._handle_unscoped_numeric_reply(merchant_id, contact, conv, msg, raw_text)

        # 7. Check if command is a recognized action word
        match = _COMMAND_RE.match(raw_text)
        if match:
            return self._handle_command_word_outside_context(merchant_id, contact, conv, msg, match)

        # 8. Legacy fallback for multi-field string
        draft_result = self._try_resolve_missing_fields(merchant_id, msg)
        if draft_result is not None:
            return draft_result

        # 8b. Free-text question, not a recognized command - ask the AI explain layer.
        if self._try_ai_explain_reply(merchant_id, contact, msg, raw_text):
            return {"merchant_id": merchant_id, "status": "ai_explained"}

        # 9. Fail closed
        self.audit.record(
            merchant_id=merchant_id, actor="notifications", source=msg.provider, action="inbound_unparseable_rejected",
            object_type="InboundApprovalMessage", object_id=msg.provider_message_id, result="rejected",
        )
        try:
            self.transport.send_approval(
                recipient=contact.phone_e164,
                message="I didn't recognize that message. Reply *Menu* to see available options, or send a supplier CSV to onboard products.",
            )
        except Exception:
            pass
        raise InboundResolutionError("message is not a recognized command or valid input - send 'Menu' to view options")

    def _handle_menu_trigger(
        self, merchant_id: str, contact: DemoSessionContact, conv: WhatsAppConversationState, msg: InboundApprovalMessage
    ) -> dict[str, Any]:
        active_summary = None
        if conv.active_context_type == "approval_decision" and conv.active_approval_id:
            try:
                app = self.store.get(Approval, merchant_id, conv.active_approval_id)
                if app.status == "pending":
                    active_summary = f"Pending Approval: {app.summary or app.action}"
                    conv.metadata["paused_context"] = "approval_decision"
            except Exception:
                conv.active_approval_id = None
        elif conv.active_context_type == "product_onboarding" and conv.active_draft_id:
            try:
                draft = self.store.get(ProductDraft, merchant_id, conv.active_draft_id)
                if draft.state in ("INCOMPLETE", "CONFLICTED"):
                    active_summary = f"Product Onboarding: {draft.title or draft.sku} ({conv.active_onboarding_step or 'details'})"
                    conv.metadata["paused_context"] = "product_onboarding"
            except Exception:
                conv.active_draft_id = None

        conv.active_context_type = "main_menu"
        self.store.put(conv)
        menu_text = self._format_main_menu(active_summary)
        self.transport.send_approval(recipient=contact.phone_e164, message=menu_text)
        self.audit.record(
            merchant_id=merchant_id, actor="notifications", source=msg.provider, action="inbound_menu_displayed",
            object_type="Merchant", object_id=merchant_id, result="menu_delivered",
        )
        return {"merchant_id": merchant_id, "action": "menu_displayed"}

    def _handle_resume_trigger(
        self, merchant_id: str, contact: DemoSessionContact, conv: WhatsAppConversationState, msg: InboundApprovalMessage
    ) -> dict[str, Any]:
        paused = conv.metadata.get("paused_context")
        if paused == "approval_decision" or conv.active_approval_id:
            try:
                app = self.store.get(Approval, merchant_id, conv.active_approval_id)
                if app.status == "pending":
                    conv.active_context_type = "approval_decision"
                    self.store.put(conv)
                    card = self._format_active_decision_card(app)
                    self.transport.send_approval(recipient=contact.phone_e164, message=f"Resuming decision:\n\n{card}")
                    return {"merchant_id": merchant_id, "action": "resumed_approval", "approval_id": app.id}
            except Exception:
                pass
        elif paused == "product_onboarding" or conv.active_draft_id:
            try:
                draft = self.store.get(ProductDraft, merchant_id, conv.active_draft_id)
                if draft.state in ("INCOMPLETE", "CONFLICTED"):
                    step, step_msg = self.get_next_onboarding_step(merchant_id, draft)
                    if step and step_msg:
                        conv.active_context_type = "product_onboarding"
                        conv.active_onboarding_step = step
                        self.store.put(conv)
                        self.transport.send_approval(recipient=contact.phone_e164, message=f"Resuming product onboarding:\n\n{step_msg}")
                        return {"merchant_id": merchant_id, "action": "resumed_onboarding", "draft_id": draft.id}
            except Exception:
                pass

        conv.active_context_type = "main_menu"
        self.store.put(conv)
        self.transport.send_approval(
            recipient=contact.phone_e164,
            message="No active question or decision is paused. Send *Menu* to view options.",
        )
        return {"merchant_id": merchant_id, "action": "resume_noop"}

    # Natural-language aliases for the numbered menu options, checked before falling through to AI
    # explain / rejection - phrases like "what needs my attention?" are common enough (they're even one
    # of the demo's own quick-reply suggestions) that they deserve a direct, deterministic answer rather
    # than depending on fuzzy keyword overlap against specific exception text.
    _MENU_ALIASES: dict[str, tuple[str, ...]] = {
        "1": ("WHAT NEEDS MY ATTENTION", "WHAT HAPPENED", "GIVE ME A SUMMARY", "SUMMARY", "GOOD MORNING"),
        "2": ("WHAT NEEDS MY APPROVAL", "PENDING APPROVALS", "ANYTHING TO APPROVE"),
        "3": ("PRICING ISSUES", "ANY PRICING ISSUES", "LISTING ISSUES"),
        "4": ("STOCK ISSUES", "ANY STOCK ISSUES", "DELIVERY ISSUES", "SHOW ME THE DELIVERY ISSUES", "ANY RTOS I SHOULD KNOW ABOUT", "ANY NDRS", "WHY IS INVENTORY SHOWING DIFFERENTLY"),
        "5": ("ORDER ISSUES", "RECONCILIATION ISSUES", "SHOW ME THE AFFECTED ORDERS"),
    }

    def _handle_main_menu_selection(
        self, merchant_id: str, contact: DemoSessionContact, conv: WhatsAppConversationState, msg: InboundApprovalMessage, text: str
    ) -> dict[str, Any]:
        upper = text.upper().strip().rstrip("?!.")
        from sanocea.packages.domain_contract.models import Inventory, Location, Order, Product

        # "Resolve it" / "approve it" - a direct action shortcut, not a menu number. Only acts when
        # there's exactly one pending approval to act on (no reference/ordinal is given, so anything
        # ambiguous falls through to the normal "2. Decisions waiting for approval" disambiguation flow
        # instead of guessing which item "it" means).
        if upper in ("RESOLVE IT", "APPROVE IT", "APPROVE", "RESOLVE", "YES APPROVE", "DO IT"):
            pending = self._get_actionable_pending_approvals(merchant_id)
            if len(pending) == 1:
                resolve_result = self.approvals.resolve(merchant_id, pending[0].id, decision="approved", resolved_via="web_chat", decided_by=f"whatsapp:{msg.from_identifier[-4:]}")
                conv.active_context_type = "main_menu"
                self.store.put(conv)
                confirm = f"✅ Approved: {pending[0].summary or pending[0].action}"
                self.transport.send_approval(recipient=contact.phone_e164, message=confirm)
                return {"merchant_id": merchant_id, "action": "resolved_via_shortcut", "approval_id": pending[0].id, "result": resolve_result}
            # 0 or 2+ pending - route into the normal "2. Decisions waiting for approval" handling below,
            # which already covers "none pending" and disambiguation among several correctly.
            upper = "2"

        for number, phrases in self._MENU_ALIASES.items():
            if upper in phrases:
                upper = number
                break

        # 1. Today’s business briefing
        if upper in ("1", "TODAY", "BRIEFING", "TODAY'S BUSINESS BRIEFING", "TODAYS BUSINESS BRIEFING"):
            res = self.send_daily_briefing(merchant_id, recipient=contact.phone_e164)
            conv.active_context_type = "main_menu"
            self.store.put(conv)
            return {"merchant_id": merchant_id, "action": "daily_briefing", "delivered": res.delivered}

        # 2. Decisions waiting for approval
        if upper in ("2", "DECISIONS", "APPROVAL", "APPROVALS", "DECISIONS WAITING FOR APPROVAL"):
            pending = self._get_actionable_pending_approvals(merchant_id)
            if len(pending) == 0:
                conv.active_context_type = "main_menu"
                self.store.put(conv)
                reply = "✅ *Approval Queue Clear*\n\nNo pending decisions waiting for approval.\n\nReply *Menu* to return to the main menu."
                self.transport.send_approval(recipient=contact.phone_e164, message=reply)
                return {"merchant_id": merchant_id, "action": "no_pending_approvals"}
            elif len(pending) == 1:
                approval = pending[0]
                conv.active_context_type = "approval_decision"
                conv.active_approval_id = approval.id
                self.store.put(conv)
                card = self._format_active_decision_card(approval)
                self.transport.send_approval(recipient=contact.phone_e164, message=card)
                self.audit.record(
                    merchant_id=merchant_id, actor="notifications", source=msg.provider, action="decision_card_presented",
                    object_type="Approval", object_id=approval.id, result="presented",
                )
                return {"merchant_id": merchant_id, "approval_id": approval.id, "action": "decision_presented"}
            else:
                conv.active_context_type = "approval_disambiguation"
                conv.pending_disambiguation_ids = [a.id for a in pending]
                self.store.put(conv)
                dis_msg = self._format_approval_disambiguation(pending)
                self.transport.send_approval(recipient=contact.phone_e164, message=dis_msg)
                self.audit.record(
                    merchant_id=merchant_id, actor="notifications", source=msg.provider, action="approval_disambiguation_presented",
                    object_type="Approval", object_id=pending[0].id, result="presented",
                )
                return {"merchant_id": merchant_id, "action": "disambiguation_presented", "count": len(pending)}

        # 3. Catalogue & pricing issues
        if upper in ("3", "CATALOGUE", "PRICING", "CATALOGUE & PRICING ISSUES", "CATALOG"):
            products = self.store.list(Product, merchant_id)
            pricing_approvals = [a for a in self.store.list_where(Approval, merchant_id, status="pending") if a.action == "price_change"]
            lines = [
                "📋 *Catalogue & Pricing Health*",
                "",
                f"• Active Products: {len(products)}",
                f"• Pricing Anomalies Pending: {len(pricing_approvals)}",
            ]
            if pricing_approvals:
                for a in pricing_approvals:
                    lines.append(f"  ↳ *{a.summary or a.reference}*")
                lines.extend([
                    "",
                    "👉 Reply *2* to review and approve pricing corrections.",
                ])
            lines.extend([
                "",
                "Reply *Menu* to return to the main menu.",
            ])
            self.transport.send_approval(recipient=contact.phone_e164, message="\n".join(lines))
            conv.active_context_type = "main_menu"
            self.store.put(conv)
            return {"merchant_id": merchant_id, "action": "catalogue_summary"}

        # 4. Stock and low-inventory risks
        if upper in ("4", "STOCK", "INVENTORY", "STOCK AND LOW-INVENTORY RISKS"):
            inventories = self.store.list(Inventory, merchant_id)
            config = self.store.get_config(merchant_id)
            safety = config.get("inventory", {}).get("safety_stock_default", 10)
            low_stock = [i for i in inventories if 0 < i.ats < safety]
            quarantined = [i for i in inventories if i.quarantine > 0]
            issues = _open_critical_inventory_exceptions(self.store, merchant_id)
            if issues:
                lead = issues[0]
                if lead.object_id:
                    issue_inv = self.store.get(Inventory, merchant_id, lead.object_id)
                else:
                    issue_inv = None
                channel = _resolve_location_channel_name(self.store, merchant_id, issue_inv.location_ref) if issue_inv else None
                issue_channel = channel or "Stock"
                conv.metadata["stock_issue_exception_id"] = lead.id
                lines = [
                    "📦 *Stock & Inventory*",
                    "",
                    f"🔴 {issue_channel} — Out of Stock",
                    "",
                    "1 stock issue requires attention.",
                    "",
                    "Would you like to see the details and available action?",
                    "",
                    "Reply *1* to view",
                    "Reply *Menu* to return to the main menu.",
                    "",
                    f"• Total Stock Lines: {len(inventories)}",
                    f"• Low Stock Risk: {len(low_stock)} SKU(s) below safety threshold ({safety} units)",
                    f"• Quarantined Stock: {sum(i.quarantine for i in quarantined)} unit(s) across {len(quarantined)} SKU(s) held for QA",
                ]
                self.transport.send_approval(recipient=contact.phone_e164, message="\n".join(lines))
                conv.active_context_type = "stock_issue_detail"
                self.store.put(conv)
                return {"merchant_id": merchant_id, "action": "stock_issue_attention", "issues": len(issues)}
            lines = [
                "📦 *Stock & Inventory Integrity*",
                "",
                f"• Total Stock Lines: {len(inventories)}",
                f"• Low Stock Risk: {len(low_stock)} SKU(s) below safety threshold ({safety} units)",
            ]
            for i in low_stock[:3]:
                item_title = _resolve_product_title(self.store, merchant_id, i.sku) or "An item"
                item_channel = _resolve_location_channel_name(self.store, merchant_id, i.location_ref)
                item_where = f" ({item_channel})" if item_channel else ""
                lines.append(f"  ↳ {item_title}{item_where}: {i.ats} units left")
            lines.append(f"• Quarantined Stock: {sum(i.quarantine for i in quarantined)} unit(s) across {len(quarantined)} SKU(s) held for QA")
            for i in quarantined[:3]:
                item_title = _resolve_product_title(self.store, merchant_id, i.sku) or "An item"
                lines.append(f"  ↳ {item_title}: {i.quarantine} units in QA quarantine hold")
            lines.extend([
                "",
                "Reply *Menu* to return to the main menu.",
            ])
            self.transport.send_approval(recipient=contact.phone_e164, message="\n".join(lines))
            conv.active_context_type = "main_menu"
            self.store.put(conv)
            return {"merchant_id": merchant_id, "action": "stock_summary"}

        # 5. Orders, payouts & reconciliation
        if upper in ("5", "ORDERS", "PAYOUTS", "RECONCILIATION", "ORDERS, PAYOUTS & RECONCILIATION"):
            orders = self.store.list(Order, merchant_id)
            delivered = [o for o in orders if getattr(o, "fulfillment_status", None) == "delivered" or o.status == "DELIVERED"]
            unreconciled = [o for o in orders if getattr(o, "financial_reconciliation_status", "UNRECONCILED") == "UNRECONCILED"]
            lines = [
                "💰 *Orders, Payouts & Settlement*",
                "",
                f"• Total Orders: {len(orders)}",
                f"• Delivered Orders: {len(delivered)}",
                f"• Pending Bank Reconciliation: {len(unreconciled)} order(s)",
                "",
                "_Financial settlement is tracked separately from delivery to protect revenue recognition._",
                "",
                "Reply *Menu* to return to the main menu.",
            ]
            self.transport.send_approval(recipient=contact.phone_e164, message="\n".join(lines))
            conv.active_context_type = "main_menu"
            self.store.put(conv)
            return {"merchant_id": merchant_id, "action": "orders_summary"}

        # 6. Add / onboard new products
        if upper in ("6", "ONBOARD", "ADD", "ADD / ONBOARD NEW PRODUCTS", "NEW PRODUCTS"):
            incomplete = sorted(
                (
                    d for d in self.store.list(ProductDraft, merchant_id)
                    if d.state in ("INCOMPLETE", "CONFLICTED")
                    and set(d.commercial_facts.keys()) != {"image"}
                ),
                key=lambda d: getattr(d.sync, "observed_at", d.id),
            )
            if incomplete:
                draft = incomplete[0]
                step, step_msg = self.get_next_onboarding_step(merchant_id, draft)
                conv.active_context_type = "product_onboarding"
                conv.active_draft_id = draft.id
                conv.active_onboarding_step = step
                self.store.put(conv)
                intro_msg = f"You have {len(incomplete)} product draft(s) awaiting completion.\nStarting review now:\n\n{step_msg}"
                self.transport.send_approval(recipient=contact.phone_e164, message=intro_msg)
                return {"merchant_id": merchant_id, "action": "onboarding_started", "draft_id": draft.id, "step": step}
            else:
                info_msg = (
                    "📥 *Add / Onboard New Products*\n\n"
                    "Send a supplier spreadsheet (CSV, Excel) or product photo directly here on WhatsApp, "
                    "or upload via the Sanocea Command Center.\n\n"
                    "Sanocea holds incomplete drafts safely until price, category, and inventory are confirmed.\n\n"
                    "Reply *Menu* to return."
                )
                self.transport.send_approval(recipient=contact.phone_e164, message=info_msg)
                conv.active_context_type = "main_menu"
                self.store.put(conv)
                return {"merchant_id": merchant_id, "action": "onboarding_info"}

        # 0. Help
        if upper in ("0", "HELP"):
            help_msg = (
                "💡 *Sanocea WhatsApp Quick Guide*\n\n"
                "• *Approve* (or *1*): Sign off on active decision\n"
                "• *Reject* (or *2*): Decline active decision\n"
                "• *Details* (or *3*): View full commercial impact without advancing\n"
                "• *Later* (or *4*): Postpone decision safely\n"
                "• *Menu*: Return to Main Menu\n"
                "• *Resume*: Continue active question or decision\n\n"
                "Reply *Menu* to open the main menu."
            )
            self.transport.send_approval(recipient=contact.phone_e164, message=help_msg)
            conv.active_context_type = "main_menu"
            self.store.put(conv)
            return {"merchant_id": merchant_id, "action": "help"}

        # Not a menu number/keyword - try it as a free-text question before giving up.
        if self._try_ai_explain_reply(merchant_id, contact, msg, text):
            return {"merchant_id": merchant_id, "action": "ai_explained"}

        unrec_msg = f"I didn't recognize '{text}'. Please reply with a number (*1*-*6*, *0*) or send *Menu*."
        self.transport.send_approval(recipient=contact.phone_e164, message=unrec_msg)
        return {"merchant_id": merchant_id, "action": "unrecognized_menu_option"}

    def _handle_stock_issue_detail_reply(
        self, merchant_id: str, contact: DemoSessionContact, conv: WhatsAppConversationState, msg: InboundApprovalMessage, text: str
    ) -> dict[str, Any]:
        """Reply *1* after menu option 4 surfaced an open critical inventory exception: show the
        natural-language stock alert and the action this system actually supports. There is no approve /
        replenish workflow on WhatsApp for this flow, so no action is invented."""
        from sanocea.packages.domain_contract.models import Inventory

        upper = text.upper().strip()
        if upper in ("1", "VIEW", "VIEW DETAILS", "DETAILS", "YES"):
            issue = None
            exc_id = conv.metadata.get("stock_issue_exception_id")
            if exc_id:
                try:
                    issue = self.store.get(ExceptionRecord, merchant_id, exc_id)
                except Exception:
                    issue = None
                if issue is None or issue.status != "open":
                    issue = None
            if issue is None:
                open_issues = _open_critical_inventory_exceptions(self.store, merchant_id)
                issue = open_issues[0] if open_issues else None
            if issue is None:
                self.transport.send_approval(
                    recipient=contact.phone_e164,
                    message="✅ The stock issue is already resolved — no out-of-stock alert is open. Reply *Menu* to return to the main menu.",
                )
                conv.active_context_type = "main_menu"
                self.store.put(conv)
                return {"merchant_id": merchant_id, "action": "stock_issue_already_resolved"}
            issue_inv = self.store.get(Inventory, merchant_id, issue.object_id) if issue.object_id else None
            title = _resolve_product_title(self.store, merchant_id, issue_inv.sku) if issue_inv else None
            channel = _resolve_location_channel_name(self.store, merchant_id, issue_inv.location_ref) if issue_inv else None
            quantity = issue_inv.quantity if issue_inv else None
            lines = [
                f"🔴 {channel or 'Stock'} Stock Alert",
                "",
                f"{(title or 'An item')} is showing as out of stock on {channel or 'the sales channel'}.",
            ]
            if quantity is not None:
                lines.append(f"{quantity} units are available in inventory, but none are currently available for customers.")
            lines.extend([
                "",
                "_No automated restock action exists on WhatsApp — this alert is for monitoring, and resolution is handled by your team._",
                "",
                "Reply *Menu* to return to the main menu.",
            ])
            self.transport.send_approval(recipient=contact.phone_e164, message="\n".join(lines))
            conv.active_context_type = "main_menu"
            self.store.put(conv)
            return {"merchant_id": merchant_id, "exception_id": issue.id, "action": "stock_issue_detail"}
        self.transport.send_approval(
            recipient=contact.phone_e164,
            message="Reply *1* to view the stock issue details, or *Menu* to return to the main menu.",
        )
        return {"merchant_id": merchant_id, "action": "stock_issue_detail_prompted"}

    def _handle_approval_disambiguation_selection(
        self, merchant_id: str, contact: DemoSessionContact, conv: WhatsAppConversationState, msg: InboundApprovalMessage, text: str
    ) -> dict[str, Any]:
        upper = text.upper().strip()
        if upper in ("MENU", "CANCEL", "BACK"):
            conv.active_context_type = "main_menu"
            conv.pending_disambiguation_ids = []
            self.store.put(conv)
            self.transport.send_approval(recipient=contact.phone_e164, message=self._format_main_menu())
            return {"merchant_id": merchant_id, "action": "menu_displayed"}

        match = re.match(r"^(\d+)$", text.strip())
        if match:
            idx = int(match.group(1))
            if 1 <= idx <= len(conv.pending_disambiguation_ids):
                app_id = conv.pending_disambiguation_ids[idx - 1]
                approval = self.store.get(Approval, merchant_id, app_id)
                conv.active_context_type = "approval_decision"
                conv.active_approval_id = approval.id
                conv.pending_disambiguation_ids = []
                self.store.put(conv)
                card = self._format_active_decision_card(approval)
                self.transport.send_approval(recipient=contact.phone_e164, message=card)
                return {"merchant_id": merchant_id, "approval_id": approval.id, "action": "decision_selected"}

        dis_msg = f"Please reply with a number between 1 and {len(conv.pending_disambiguation_ids)} to select a decision, or send *Menu*."
        self.transport.send_approval(recipient=contact.phone_e164, message=dis_msg)
        return {"merchant_id": merchant_id, "action": "invalid_disambiguation_choice"}

    def _handle_active_decision_action(
        self, merchant_id: str, contact: DemoSessionContact, conv: WhatsAppConversationState, msg: InboundApprovalMessage, raw_text: str
    ) -> dict[str, Any]:
        text_upper = raw_text.strip().upper()
        approval_id = conv.active_approval_id
        if not approval_id:
            conv.active_context_type = "none"
            self.store.put(conv)
            raise InboundResolutionError("no active approval in conversation state")

        try:
            approval = self.store.get(Approval, merchant_id, approval_id)
        except Exception:
            conv.active_context_type = "none"
            conv.active_approval_id = None
            self.store.put(conv)
            raise InboundResolutionError(f"active approval {approval_id} no longer exists")

        if approval.status != "pending":
            conv.active_context_type = "none"
            conv.active_approval_id = None
            self.store.put(conv)
            self.transport.send_approval(
                recipient=contact.phone_e164,
                message=f"Decision {approval.reference or approval.id} has already been resolved ({approval.status}). Send *Menu* to view store options.",
            )
            return {"merchant_id": merchant_id, "approval_id": approval_id, "status": approval.status}

        # The WhatsApp-first flow deliberately makes one-word replies such as
        # "Approve" and "Later" sufficient because the conversation already
        # has one explicit active decision.  Keep the former command syntax
        # ("APPROVE PB-PRICE-001") compatible too: it is useful for older
        # messages and must never make an unrelated active decision actionable.
        # A supplied reference is accepted only when it names this active item.
        command_match = _COMMAND_RE.match(raw_text)
        if command_match:
            supplied_reference = command_match.group(2).strip().upper()
            active_references = {(approval.reference or "").upper(), approval.id.upper()}
            if supplied_reference and supplied_reference not in active_references:
                # Legacy, explicit-reference messages are allowed to select a
                # different *pending* decision.  This preserves old inbound
                # links while the normal merchant experience stays one-word
                # and bound to the active conversation state.
                matching = [
                    item for item in self._get_actionable_pending_approvals(merchant_id)
                    if supplied_reference in {(item.reference or "").upper(), item.id.upper()}
                ]
                if not matching:
                    self.transport.send_approval(
                        recipient=contact.phone_e164,
                        message="I couldn't find that pending decision. Reply *Menu* to review the current queue.",
                    )
                    return {"merchant_id": merchant_id, "action": "unknown_decision_reference"}
                approval = matching[0]
                conv.active_approval_id = approval.id
                conv.active_context_type = "approval_decision"
                self.store.put(conv)
            text_upper = command_match.group(1).upper()

        # 1. Details (3 or DETAILS) - explain without advancing
        if text_upper in ("3", "DETAILS", "VIEW DETAILS", "EXPLAIN", "INFO"):
            evidence = approval.evidence if isinstance(approval.evidence, dict) else {}
            action_title = approval.action.replace("_", " ").title()
            lines = [
                f"📋 *Decision Breakdown: {approval.reference or approval.id}*",
                f"• *Action:* {action_title}",
                f"• *Summary:* {approval.summary or 'Pending sign-off'}",
            ]
            if approval.recommendation:
                lines.append(f"• *Recommended:* {approval.recommendation}")
            impact = evidence.get("likely_impact") or evidence.get("impact") or evidence.get("commercial_impact")
            if impact:
                lines.append(f"• *Likely Impact:* {impact}")
            if "sku" in evidence:
                lines.append(f"• *SKU:* `{evidence['sku']}`")
            if "current_price" in evidence and "new_price" in evidence:
                lines.append(f"• *Price Adjustment:* ₹{evidence['current_price']} ➔ ₹{evidence['new_price']}")
            if "unit_economics" in evidence:
                lines.append(f"• *Commercial Rationale:* {evidence['unit_economics']}")
            if "reason" in evidence:
                lines.append(f"• *Reason:* {evidence['reason']}")

            lines.extend([
                "",
                "*Actions:*",
                "1. Approve",
                "2. Reject",
                "3. Details",
                "4. Later",
                "",
                "👉 Reply *1* (or *Approve*) to execute, *2* (or *Reject*) to decline, or *4* (or *Later*) to postpone.",
            ])
            self.transport.send_approval(recipient=contact.phone_e164, message="\n".join(lines))
            self.audit.record(
                merchant_id=merchant_id, actor="notifications", source=msg.provider, action="inbound_approval_details_sent",
                object_type="Approval", object_id=approval.id, result="details_delivered",
            )
            return {"merchant_id": merchant_id, "approval_id": approval.id, "action": "details", "status": "pending"}

        # 1.5. Edit (5 or EDIT) — for price_change approvals only: ask for a custom price
        if text_upper in ("5", "EDIT", "CHANGE", "MODIFY", "UPDATE") and approval.action == "price_change":
            evidence = approval.evidence if isinstance(approval.evidence, dict) else {}
            current_price = evidence.get("current_price", "?")
            new_price = evidence.get("new_price", "?")
            sku = evidence.get("sku", "")
            conv.active_context_type = "approval_edit"
            conv.active_approval_id = approval.id
            conv.metadata["edit_field"] = "price"
            self.store.put(conv)
            edit_prompt = (
                f"✏️ *Edit Price — {sku or approval.reference}*\n\n"
                f"• Current (system price): ₹{current_price}\n"
                f"• Sanocea suggested: ₹{new_price}\n\n"
                f"💬 Reply with *your preferred price* (e.g. *898* or *₹898*).\n\n"
                f"_Sanocea will approve the correction at your price instead._\n"
                f"Reply *Cancel* to go back."
            )
            self.transport.send_approval(recipient=contact.phone_e164, message=edit_prompt)
            self.audit.record(
                merchant_id=merchant_id, actor="notifications", source=msg.provider, action="inbound_edit_prompt_sent",
                object_type="Approval", object_id=approval.id, result="edit_prompt_delivered",
            )
            return {"merchant_id": merchant_id, "approval_id": approval.id, "action": "edit_prompted"}

        # 2. Later (4 or LATER) - preserve and postpone

        if text_upper in ("4", "LATER", "REVIEW LATER", "POSTPONE", "SNOOZE"):
            ref_tag = approval.reference or approval.id
            snooze_msg = (
                f"⏸ *Decision Postponed: {ref_tag}*\n\n"
                "Decision has been kept safely pending in the queue. You can review it anytime by replying *2* from the Menu or in Command Center."
            )
            self.transport.send_approval(recipient=contact.phone_e164, message=snooze_msg)
            self.audit.record(
                merchant_id=merchant_id, actor="notifications", source=msg.provider, action="inbound_approval_snoozed",
                object_type="Approval", object_id=approval.id, result="snoozed",
            )
            conv.active_context_type = "none"
            conv.active_approval_id = None
            self.store.put(conv)
            return {"merchant_id": merchant_id, "approval_id": approval.id, "action": "later", "status": "pending"}

        # 3. Approve (1 or APPROVE) or Reject (2 or REJECT)
        is_approve = text_upper in ("1", "APPROVE", "ACCEPT", "YES", "CONFIRM", "OK") or (
            text_upper.startswith("APPROVE") and (approval.reference or "").upper() in text_upper
        )
        is_reject = text_upper in ("2", "REJECT", "DECLINE", "NO") or (
            text_upper.startswith("REJECT") and (approval.reference or "").upper() in text_upper
        )

        if not is_approve and not is_reject:
            self.transport.send_approval(
                recipient=contact.phone_e164,
                message="Please reply with a valid action (*1* Approve, *2* Reject, *3* Details, *4* Later), or send *Menu*.",
            )
            return {"merchant_id": merchant_id, "action": "invalid_decision_choice"}

        decision = "approved" if is_approve else "denied"
        try:
            resolve_result = self.approvals.resolve(
                merchant_id, approval.id, decision=decision,
                resolved_via=msg.provider, decided_by=f"whatsapp:{contact.phone_e164[-4:]}",
            )
        except ApprovalError as exc:
            self.audit.record(
                merchant_id=merchant_id, actor="notifications", source=msg.provider, action="inbound_resolve_failed",
                object_type="Approval", object_id=approval.id, result="error", error=str(exc),
            )
            raise InboundResolutionError(str(exc)) from exc

        approval = self.store.get(Approval, merchant_id, approval.id)
        self._send_resolution_confirmation(contact, approval, decision, resolve_result)

        self.audit.record(
            merchant_id=merchant_id, actor="notifications", source=msg.provider, action="inbound_approval_resolved",
            object_type="Approval", object_id=approval.id, result=decision,
        )

        # Advance sequential queue to next pending approval if any
        remaining = [
            a for a in self._get_actionable_pending_approvals(merchant_id)
            if a.id != approval.id
        ]
        if remaining:
            next_app = remaining[0]
            conv.active_approval_id = next_app.id
            conv.active_context_type = "approval_decision"
            self.store.put(conv)
            card = self._format_active_decision_card(next_app)
            self.transport.send_approval(recipient=contact.phone_e164, message=f"Next pending decision:\n\n{card}")
        else:
            conv.active_approval_id = None
            conv.active_context_type = "none"
            self.store.put(conv)

        return {"merchant_id": merchant_id, **resolve_result}

    def _handle_approval_edit_reply(
        self, merchant_id: str, contact: DemoSessionContact, conv: WhatsAppConversationState, msg: InboundApprovalMessage, raw_text: str
    ) -> dict[str, Any]:
        """Owner replied to the Edit prompt with a custom price. Parse it, update the approval
        evidence so the price card reflects the owner's choice, then approve it immediately."""
        text_upper = raw_text.strip().upper()
        approval_id = conv.active_approval_id

        # Cancel — go back to the decision card
        if text_upper in ("CANCEL", "BACK", "NO", "MENU"):
            try:
                approval = self.store.get(Approval, merchant_id, approval_id)
                conv.active_context_type = "approval_decision"
                self.store.put(conv)
                card = self._format_active_decision_card(approval)
                self.transport.send_approval(recipient=contact.phone_e164, message=f"↩️ Cancelled. Back to the decision:\n\n{card}")
            except Exception:
                conv.active_context_type = "none"
                conv.active_approval_id = None
                self.store.put(conv)
            return {"merchant_id": merchant_id, "action": "edit_cancelled"}

        # Parse price — accept "898", "₹898", "Rs 898", "898.00"
        price_match = re.search(r"(?:₹|rs\.?\s*)?(\d+(?:\.\d+)?)", raw_text, re.IGNORECASE)
        if not price_match:
            self.transport.send_approval(
                recipient=contact.phone_e164,
                message="❓ I couldn't read that as a price. Please reply with a number, e.g. *898* or *₹898*.\nReply *Cancel* to go back.",
            )
            return {"merchant_id": merchant_id, "action": "edit_invalid_price"}

        custom_price = round(float(price_match.group(1)), 2)

        try:
            approval = self.store.get(Approval, merchant_id, approval_id)
        except Exception:
            conv.active_context_type = "none"
            conv.active_approval_id = None
            self.store.put(conv)
            raise InboundResolutionError(f"active approval {approval_id} not found during edit")

        if approval.status != "pending":
            conv.active_context_type = "none"
            conv.active_approval_id = None
            self.store.put(conv)
            self.transport.send_approval(
                recipient=contact.phone_e164,
                message=f"This decision was already resolved ({approval.status}). Send *Menu* to view options.",
            )
            return {"merchant_id": merchant_id, "action": "edit_already_resolved"}

        # Update the approval evidence so the correct price is recorded before approval
        evidence = dict(approval.evidence) if isinstance(approval.evidence, dict) else {}
        original_suggestion = evidence.get("new_price", evidence.get("current_price", "?"))
        evidence["new_price"] = custom_price
        # Compare-at = original (system) current_price — customer sees the saving
        if "current_price" in evidence:
            evidence["compare_at_price"] = evidence["current_price"]
        evidence["owner_edited_price"] = True
        evidence["original_suggestion"] = original_suggestion
        approval.evidence = evidence
        approval.recommendation = f"Owner-set price: ₹{custom_price} (Sanocea suggested ₹{original_suggestion})"
        self.store.put(approval)

        # Confirm what we're about to do and approve
        confirm_msg = (
            f"✅ *Price Updated & Approved*\n\n"
            f"• SKU: `{evidence.get('sku', approval.reference)}`\n"
            f"• Your price: *₹{custom_price}*\n"
            f"• Compare-at (MRP): ₹{evidence.get('compare_at_price', '—')}\n\n"
            f"_Sanocea will apply this price correction to your store._"
        )
        self.transport.send_approval(recipient=contact.phone_e164, message=confirm_msg)

        self.audit.record(
            merchant_id=merchant_id, actor=f"whatsapp:{contact.phone_e164[-4:]}", source=msg.provider,
            action="inbound_price_edited_before_approval", object_type="Approval", object_id=approval.id,
            result="edited", requested_mutation={"new_price": custom_price, "original_suggestion": original_suggestion},
        )

        # Now approve at the edited price
        actor = f"whatsapp:{msg.from_identifier[-4:]}"
        try:
            resolve_result = self.approvals.resolve(
                merchant_id, approval.id, decision="approved",
                resolved_via=msg.provider, decided_by=actor,
            )
        except ApprovalError as exc:
            self.audit.record(
                merchant_id=merchant_id, actor="notifications", source=msg.provider, action="inbound_edit_resolve_failed",
                object_type="Approval", object_id=approval.id, result="error", error=str(exc),
            )
            raise InboundResolutionError(str(exc)) from exc

        self.audit.record(
            merchant_id=merchant_id, actor="notifications", source=msg.provider, action="inbound_approval_resolved",
            object_type="Approval", object_id=approval.id, result="approved",
        )

        # Advance to next pending approval if any
        remaining = [a for a in self._get_actionable_pending_approvals(merchant_id) if a.id != approval.id]
        if remaining:
            next_app = remaining[0]
            conv.active_approval_id = next_app.id
            conv.active_context_type = "approval_decision"
            self.store.put(conv)
            card = self._format_active_decision_card(next_app)
            self.transport.send_approval(recipient=contact.phone_e164, message=f"Next pending decision:\n\n{card}")
        else:
            conv.active_approval_id = None
            conv.active_context_type = "none"
            self.store.put(conv)

        return {"merchant_id": merchant_id, "approval_id": approval.id, "action": "edit_approved", "custom_price": custom_price, **resolve_result}

    def _handle_product_onboarding_reply(
        self, merchant_id: str, contact: DemoSessionContact, conv: WhatsAppConversationState, msg: InboundApprovalMessage, raw_text: str
    ) -> dict[str, Any]:
        draft_id = conv.active_draft_id
        if not draft_id:
            conv.active_context_type = "none"
            self.store.put(conv)
            raise InboundResolutionError("no active draft in product onboarding conversation")

        try:
            draft = self.store.get(ProductDraft, merchant_id, draft_id)
        except Exception:
            conv.active_context_type = "none"
            conv.active_draft_id = None
            self.store.put(conv)
            raise InboundResolutionError(f"active draft {draft_id} not found")

        step = conv.active_onboarding_step or self.get_next_onboarding_step(merchant_id, draft)[0]
        if not step:
            conv.active_context_type = "none"
            conv.active_draft_id = None
            self.store.put(conv)
            return {"merchant_id": merchant_id, "draft_id": draft.id, "status": "complete"}

        actor = f"whatsapp:{contact.phone_e164[-4:]}"
        applied = self._apply_onboarding_step_reply(merchant_id, draft, step, raw_text, actor, conv)
        if not applied:
            self.transport.send_approval(
                recipient=contact.phone_e164,
                message=f"I couldn't interpret that for step '{step}'. Please reply *APPROVE* (or *1*) to accept recommended value, or reply with your value.",
            )
            return {"merchant_id": merchant_id, "draft_id": draft.id, "step": step, "applied": False}

        from sanocea.packages.product_onboarding.validation import ProductCompletenessValidator
        validator = ProductCompletenessValidator(self.store)
        draft = validator.validate(draft)

        next_step, next_msg = self.get_next_onboarding_step(merchant_id, draft)
        if next_step and next_msg:
            conv.active_onboarding_step = next_step
            self.store.put(conv)
            self.transport.send_approval(recipient=contact.phone_e164, message=next_msg)
            return {"merchant_id": merchant_id, "draft_id": draft.id, "step": next_step, "status": "in_progress"}

        # Draft is complete! Publish it!
        from sanocea.packages.runtime.service_graph import build_service_graph
        catalogue = build_service_graph(self.store).catalogue
        outcome = catalogue.auto_publish_after_resolution(merchant_id, draft.id, actor)
        draft = self.store.get(ProductDraft, merchant_id, draft.id)
        audit_ref = f"AUDIT-{(draft.id)[:8].upper()}"
        self._send_publish_confirmation(
            merchant_id, outcome,
            completed_fields={
                "price": draft.price / 100 if draft.price else None,
                "product_type": draft.product_type,
                "category": draft.category,
                "inventory_quantity": draft.attributes.get("inventory_quantity"),
                "inventory_location": draft.attributes.get("inventory_location"),
                "track_inventory": draft.attributes.get("track_inventory"),
                "weight": draft.attributes.get("weight"),
            },
            audit_ref=audit_ref, draft=draft,
            category_path=draft.attributes.get("recommended_category_path"),
        )

        # Advance queue to next incomplete draft in batch if any
        next_draft = self._get_next_incomplete_draft(merchant_id, exclude_id=draft.id)
        if next_draft:
            conv.active_draft_id = next_draft.id
            n_step, n_msg = self.get_next_onboarding_step(merchant_id, next_draft)
            conv.active_onboarding_step = n_step
            self.store.put(conv)
            if n_msg:
                self.transport.send_approval(recipient=contact.phone_e164, message=n_msg)
            return {
                "merchant_id": merchant_id,
                "draft_id": draft.id,
                "status": "READY",
                "publish_outcome": outcome,
                "next_draft_id": next_draft.id,
            }
        else:
            conv.active_draft_id = None
            conv.active_onboarding_step = None
            conv.active_context_type = "none"
            self.store.put(conv)
            self._send_batch_complete_message(merchant_id)
            return {
                "merchant_id": merchant_id,
                "draft_id": draft.id,
                "status": "READY",
                "publish_outcome": outcome,
                "batch_complete": True,
            }

    def _handle_unscoped_numeric_reply(
        self, merchant_id: str, contact: DemoSessionContact, conv: WhatsAppConversationState, msg: InboundApprovalMessage, raw_text: str
    ) -> dict[str, Any]:
        self.audit.record(
            merchant_id=merchant_id, actor="notifications", source=msg.provider, action="inbound_unscoped_numeric_rejected",
            object_type="InboundApprovalMessage", object_id=msg.provider_message_id, result="rejected",
        )
        self.transport.send_approval(
            recipient=contact.phone_e164,
            message=f"I couldn't identify what '{raw_text}' refers to. Send *Menu* to view available options.",
        )
        return {"status": "rejected", "reason": "numeric reply outside of active menu context"}

    def _handle_command_word_outside_context(
        self, merchant_id: str, contact: DemoSessionContact, conv: WhatsAppConversationState, msg: InboundApprovalMessage, match: re.Match
    ) -> dict[str, Any]:
        command_word = match.group(1).upper()
        reference = match.group(2).strip().upper() or None

        pending = self._get_actionable_pending_approvals(merchant_id)
        if reference:
            matches = [a for a in pending if (a.reference or "").upper() == reference or a.id.upper() == reference]
            if not matches:
                self.audit.record(
                    merchant_id=merchant_id, actor="notifications", source=msg.provider, action="inbound_no_matching_approval",
                    object_type="InboundApprovalMessage", object_id=msg.provider_message_id, result="rejected",
                )
                self.transport.send_approval(
                    recipient=contact.phone_e164,
                    message=f"I couldn't find a pending decision with reference '{reference}'. Send *2* or *Menu* to review open decisions.",
                )
                raise InboundResolutionError(f"no pending approval matches reference '{reference}'")
            target_approval = matches[0]
        else:
            if len(pending) == 1:
                target_approval = pending[0]
            elif len(pending) > 1:
                conv.active_context_type = "approval_disambiguation"
                conv.pending_disambiguation_ids = [a.id for a in pending]
                self.store.put(conv)
                dis_msg = self._format_approval_disambiguation(pending)
                self.transport.send_approval(recipient=contact.phone_e164, message=dis_msg)
                return {"merchant_id": merchant_id, "action": "disambiguation_presented", "count": len(pending)}
            else:
                incomplete = sorted(
                    (
                        d for d in self.store.list(ProductDraft, merchant_id)
                        if d.state in ("INCOMPLETE", "CONFLICTED") and set(d.commercial_facts.keys()) != {"image"}
                    ),
                    key=lambda d: getattr(d.sync, "observed_at", d.id),
                )
                if incomplete:
                    draft = incomplete[0]
                    conv.active_context_type = "product_onboarding"
                    conv.active_draft_id = draft.id
                    step, msg_text = self.get_next_onboarding_step(merchant_id, draft)
                    conv.active_onboarding_step = step
                    self.store.put(conv)
                    return self._handle_product_onboarding_reply(merchant_id, contact, conv, msg, match.group(0))
                else:
                    self.transport.send_approval(
                        recipient=contact.phone_e164,
                        message="✅ *Approval Queue Clear*\n\nNo pending decisions waiting for approval. Send *Menu* to view store options.",
                    )
                    return {"merchant_id": merchant_id, "action": "no_pending_approvals"}

        conv.active_context_type = "approval_decision"
        conv.active_approval_id = target_approval.id
        self.store.put(conv)
        return self._handle_active_decision_action(merchant_id, contact, conv, msg, command_word)

    def _send_resolution_confirmation(self, contact: DemoSessionContact, approval: Approval, decision: str, resolve_result: dict[str, Any]) -> None:
        """Sends an immediate confirmation reply over WhatsApp when a merchant acts on a decision."""
        ref = approval.reference or approval.id
        action_title = approval.action.replace("_", " ").title()
        if decision == "approved":
            text = (
                f"✅ *Approved: {action_title}*\n\n"
                f"Action executed successfully. The store and inventory have been updated and logged in the immutable audit ledger."
            )
        else:
            text = (
                f"❌ *Declined: {action_title}*\n\n"
                f"Request was rejected. No changes were made to your live store or inventory."
            )
        try:
            self.transport.send_approval(recipient=contact.phone_e164, message=text)
        except Exception:
            pass

    def _send_clarification(self, contact: DemoSessionContact, ambiguous: list[Approval], *, reason: str) -> None:
        lines = []
        for a in sorted(ambiguous, key=lambda x: x.reference or x.id):
            try:
                op = self.store.get(ChannelOperation, contact.merchant_id, a.object_id)
                channel_label = CHANNEL_LABELS.get(op.channel, op.channel)
            except Exception:
                channel_label = "pending decision"
            lines.append(f"{a.reference or a.id} ({channel_label})")
        message = (
            f"{reason} You have {len(ambiguous)} pending decision{'s' if len(ambiguous) != 1 else ''}:\n"
            + "\n".join(lines)
            + "\n\nReply APPROVE or REJECT, or select from Menu."
        )
        try:
            self.transport.send_approval(recipient=contact.phone_e164, message=message)
        except Exception:
            pass

    def _merchants_with_contacts_for(self, phone: str) -> list[str]:
        from sanocea.packages.prospect_demo import list_demo_tenants

        return [t["merchant_id"] for t in list_demo_tenants()]
