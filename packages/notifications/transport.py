"""ApprovalNotificationTransport - the one interface every delivery channel (WhatsApp, email, and
whatever comes next) implements. SANOCEA's Approval/ApprovalService (packages/approvals/) stay
authoritative regardless of which transport is used: a transport only ever sends bytes out and hands
parsed inbound events back - it never owns approval status, expiry, or decision logic. This is what
makes swapping WhatsAppDemoTransport for a real MetaWhatsAppCloudTransport later a transport-layer
change only, never a rewrite of the approval/workflow engine (see DemoApprovalNotificationService).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

CHANNEL_LABELS = {"own_website": "Own Website", "amazon_in": "Amazon India", "flipkart": "Flipkart", "jiomart": "JioMart", "blinkit": "Blinkit"}


@dataclass
class DeliveryResult:
    delivered: bool
    provider_message_id: str | None = None
    error: str | None = None


@dataclass
class InboundApprovalMessage:
    """The transport-agnostic shape every provider's raw webhook/event is normalized into before
    DemoApprovalNotificationService ever sees it. `from_identifier` is the raw phone number/email as
    the provider reported it - callers must mask it before logging/display, never before comparing
    against a stored DemoSessionContact (masking is a DISPLAY concern only)."""

    provider: str  # "whatsapp_demo" | "whatsapp_cloud" | "email"
    provider_message_id: str  # for duplicate-webhook dedup - REQUIRED, never synthesized by us
    from_identifier: str
    raw_text: str
    received_at: datetime
    raw_event: dict[str, Any] = field(default_factory=dict)


def mask_phone(phone: str) -> str:
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) <= 4:
        return "*" * len(digits)
    return f"{'*' * (len(digits) - 4)}{digits[-4:]}"


def format_approval_message(
    *,
    merchant_display_name: str,
    channel: str,
    summary: str,
    evidence_line: str,
    recommendation: str,
    reference: str,
    likely_impact: str | None = None,
) -> str:
    """The structured exception alert shape for WhatsApp: states the issue, evidence, recommended action,
    likely commercial/operational impact, and interactive choices (Approve, Reject, Details, Later)."""
    impact_section = f"\n*Likely Impact:*\n{likely_impact}\n" if likely_impact else ""
    return (
        f"*SANOCEA — Policy Exception Alert*\n\n"
        f"*Merchant:* {merchant_display_name}\n"
        f"*Channel:* {CHANNEL_LABELS.get(channel, channel)}\n"
        f"*Issue:* {summary}\n\n"
        f"*Evidence:*\n{evidence_line}\n"
        f"{impact_section}\n"
        f"*Recommended Action:*\n{recommendation}\n\n"
        f"*Available Choices:*\n"
        f"• Reply *APPROVE {reference}* to execute\n"
        f"• Reply *REJECT {reference}* to dismiss\n"
        f"• Reply *DETAILS {reference}* for full breakdown\n"
        f"• Reply *LATER {reference}* to review later\n\n"
        f"_Action Reference: {reference}_"
    )


class ApprovalNotificationTransport(Protocol):
    name: str

    def send_approval(self, *, recipient: str, message: str) -> DeliveryResult: ...

    def parse_inbound(self, raw_event: dict[str, Any]) -> InboundApprovalMessage | None:
        """Returns None for an event that is real but not an approval-relevant message (e.g. a
        delivery receipt) - never raises for "not applicable", only for a malformed/untrusted event."""
        ...


class WhatsAppDemoTransport:
    """DEMO TRANSPORT — UNOFFICIAL WHATSAPP WEB. See
    docs/architecture/integrations/WHATSAPP_DEMO_TRANSPORT_COMPARISON.md for the full evaluation and
    the WAHA (NOWEB engine) recommendation. NEVER represented as a production SANOCEA integration, and
    never wired to Manpreet's personal number, SANOCEA's primary business number, or any
    customer-support production number - only a dedicated, disposable, recoverable demo number.

    The message-formatting and inbound-parsing logic below is real and independently testable today.
    The actual HTTP call to a running WAHA instance is deliberately NOT implemented - no WAHA instance
    exists yet (nothing has been provisioned), and this class must never fabricate a successful send.
    Provide `waha_base_url` (and provision the instance/session) before this can send anything real.
    """

    name = "whatsapp_demo"

    def __init__(self, waha_base_url: str | None = None, session: str = "default", api_key: str | None = None) -> None:
        self.waha_base_url = waha_base_url
        self.session = session
        self.api_key = api_key

    def send_approval(self, *, recipient: str, message: str) -> DeliveryResult:
        if not self.waha_base_url:
            raise NotImplementedError(
                "WhatsAppDemoTransport has no WAHA instance configured - a dedicated demo WhatsApp "
                "number and a running WAHA (NOWEB) session must be provisioned first. See "
                "docs/architecture/integrations/WHATSAPP_DEMO_TRANSPORT_COMPARISON.md."
            )
        digits = "".join(c for c in recipient if c.isdigit())
        body = json.dumps({"session": self.session, "chatId": f"{digits}@c.us", "text": message}).encode()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        req = urllib.request.Request(f"{self.waha_base_url}/api/sendText", data=body, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = json.loads(resp.read())
            return DeliveryResult(delivered=True, provider_message_id=raw.get("id") or raw.get("_data", {}).get("id", {}).get("id"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            return DeliveryResult(delivered=False, error=f"WAHA {exc.code}: {detail}")
        except (urllib.error.URLError, TimeoutError) as exc:
            return DeliveryResult(delivered=False, error=f"WAHA unreachable: {exc}")

    def download_media(self, url: str) -> bytes:
        """Fetches an inbound attachment's bytes from the URL WAHA's webhook payload reports at
        payload.media.url. Per WAHA's documented behavior this is typically a directly-fetchable HTTPS
        URL; the same X-Api-Key header used for outbound sends is included in case the instance is
        configured to require it for media access too - a harmless no-op if not."""
        headers = {}
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()

    def parse_inbound(self, raw_event: dict[str, Any]) -> InboundApprovalMessage | None:
        """Real parsing logic against WAHA's documented webhook event shape
        (event="message", payload={id, from, body, timestamp, fromMe}) - independently testable with
        synthetic, clearly-labeled-as-synthetic payloads shaped like WAHA's real documented contract,
        never against a live account until one is provisioned."""
        if raw_event.get("event") != "message":
            return None
        payload = raw_event.get("payload") or {}
        if payload.get("fromMe"):
            return None  # our own outbound echo, not an inbound reply
        message_id = payload.get("id")
        sender = payload.get("from")
        body = payload.get("body")
        # A document/image attachment can arrive with no caption at all (body is null or "") - only
        # a genuinely malformed event (missing id/sender, AND no body, AND no media) is rejected here.
        if not message_id or not sender or (body is None and not payload.get("hasMedia")):
            raise ValueError(f"malformed WAHA inbound event, missing required field(s): {raw_event!r}")
        timestamp = payload.get("timestamp")
        received_at = datetime.fromtimestamp(timestamp) if isinstance(timestamp, (int, float)) else datetime.now()
        # WhatsApp's current privacy-preserving addressing (confirmed live, Sept 2026): a direct
        # message's `from` can be a "LID" identifier ("<opaque id>@lid"), not the sender's real phone
        # number - WAHA still exposes the real phone-based JID separately, at
        # payload._data.key.remoteJidAlt ("<E164 digits>@s.whatsapp.net"). Falling back to the naive
        # "@c.us"-style split alone silently produces the WRONG identifier for every LID-addressed
        # sender, which is indistinguishable from a genuine wrong-number rejection downstream - this
        # was caught live, during physical certification, as exactly that failure mode.
        if sender.endswith("@lid"):
            alt = (((payload.get("_data") or {}).get("key") or {}).get("remoteJidAlt")) or ""
            phone = alt.split("@")[0] if alt else sender.split("@")[0]
        else:
            phone = sender.split("@")[0]
        return InboundApprovalMessage(
            provider=self.name, provider_message_id=str(message_id), from_identifier=phone,
            raw_text=str(body) if body is not None else "", received_at=received_at, raw_event=raw_event,
        )


class WebChatTransport:
    """Transport for the browser self-service chat demo - implements the SAME
    ApprovalNotificationTransport interface as WhatsAppDemoTransport, so DemoApprovalNotificationService's
    conversation engine (menu navigation, approval decisions, the AI explain fallback) runs completely
    unchanged regardless of which transport delivered/will deliver the reply. Where WhatsAppDemoTransport
    posts to WAHA, this one just accumulates the reply text in-process - the caller (the /chat API route)
    reads `sent` back out and returns it as the HTTP response. A real WAHA transport can be swapped in
    later for the same conversation layer without touching packages/notifications/resolution.py at all.
    Never persisted/shared across requests - construct one fresh per HTTP request."""

    name = "web_chat"

    def __init__(self) -> None:
        self.sent: list[str] = []

    def send_approval(self, *, recipient: str, message: str) -> DeliveryResult:
        self.sent.append(message)
        return DeliveryResult(delivered=True)

    def parse_inbound(self, raw_event: dict[str, Any]) -> InboundApprovalMessage | None:
        raise NotImplementedError("web chat messages are constructed directly by the API route, never parsed from a webhook event")


class EmailApprovalTransport:
    """Not implemented - no outbound email-send capability exists anywhere in this codebase (confirmed
    by audit; see docs/architecture/integrations/LIVE_DEMO_OPEN_SOURCE_AUDIT.md's ADOPT recommendation
    of stdlib smtplib, not yet wired). Present here only to prove the ApprovalNotificationTransport
    interface genuinely supports more than one provider without any change to ApprovalService/
    DemoApprovalNotificationService - see Section 8's "email transport adapter interface" requirement."""

    name = "email"

    def send_approval(self, *, recipient: str, message: str) -> DeliveryResult:
        raise NotImplementedError("no SMTP/email-send capability is wired in this codebase yet")

    def parse_inbound(self, raw_event: dict[str, Any]) -> InboundApprovalMessage | None:
        raise NotImplementedError("no inbound email parsing is wired in this codebase yet")
