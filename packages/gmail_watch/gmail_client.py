"""Thin wrapper around the official Gmail API client (googleapiclient) - the mature, Google-maintained
library, not a hand-rolled HTTP client. Every method here does exactly one Gmail API call; no business
logic (routing, validation, ingestion) lives here - see packages/gmail_watch/__init__.py's docstring.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


@dataclass
class GmailAttachment:
    filename: str
    content: bytes  # real, decoded attachment bytes - never a placeholder


@dataclass
class GmailMessage:
    message_id: str
    sender: str
    to_addresses: list[str]
    subject: str
    internal_date_ms: int  # Gmail's own arrival timestamp - T0 for latency measurement
    attachments: list[GmailAttachment]


def build_gmail_service(creds: Credentials):
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def register_watch(service, topic_name: str, mailbox: str = "me") -> dict[str, Any]:
    """https://developers.google.com/gmail/api/reference/rest/v1/users/watch - must be renewed within 7
    days (Google's own documented expiry) or push notifications silently stop; see watch_registrar.py
    for the renewal mechanism. Returns {"historyId": ..., "expiration": <epoch ms string>}."""
    return service.users().watch(userId=mailbox, body={"topicName": topic_name, "labelIds": ["INBOX"]}).execute()


def list_history(service, start_history_id: str, mailbox: str = "me") -> tuple[list[str], str | None]:
    """Returns (new_message_ids, latest_history_id). Gmail's history API is itself the durable,
    at-least-once-friendly primitive here: replaying the SAME start_history_id after a crash/restart
    re-derives the identical set of messages added since then - no separate dedup bookkeeping is needed
    for THIS step (message-level idempotency still happens at SANOCEA's own /demo/email-ingest, exactly
    as it always has). Raises googleapiclient.errors.HttpError(404) if start_history_id has expired past
    Gmail's own retention window - the caller must treat that as a hard resync (see subscriber.py)."""
    message_ids: list[str] = []
    latest = start_history_id
    page_token = None
    while True:
        resp = service.users().history().list(
            userId=mailbox, startHistoryId=start_history_id, historyTypes=["messageAdded"],
            pageToken=page_token,
        ).execute()
        for record in resp.get("history", []):
            latest = record.get("id", latest)
            for added in record.get("messagesAdded", []):
                msg_id = added.get("message", {}).get("id")
                if msg_id:
                    message_ids.append(msg_id)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return message_ids, resp.get("historyId", latest)


def fetch_message(service, message_id: str, mailbox: str = "me") -> GmailMessage:
    """Retrieves the real message content and every attachment's real, decoded bytes - never a
    placeholder or a re-derivation. A message with no attachment returns attachments=[] (the caller
    decides whether that's expected, e.g. an unrelated newsletter - exactly the same shape of decision
    the n8n Code node used to make)."""
    msg = service.users().messages().get(userId=mailbox, id=message_id, format="full").execute()
    headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
    sender = _extract_address(headers.get("from", ""))
    to_addresses = [_extract_address(a) for a in headers.get("to", "").split(",") if a.strip()]
    subject = headers.get("subject", "")
    attachments = list(_iter_attachments(service, mailbox, message_id, msg["payload"]))
    return GmailMessage(
        message_id=message_id, sender=sender, to_addresses=to_addresses, subject=subject,
        internal_date_ms=int(msg.get("internalDate", "0")), attachments=attachments,
    )


def _iter_attachments(service, mailbox: str, message_id: str, part: dict[str, Any]):
    filename = part.get("filename") or ""
    body = part.get("body", {})
    if filename and body.get("attachmentId"):
        att = service.users().messages().attachments().get(
            userId=mailbox, messageId=message_id, id=body["attachmentId"],
        ).execute()
        # Gmail's attachment payload is URL-safe base64 without padding - base64.urlsafe_b64decode
        # tolerates the missing padding via the trailing '=' pad-out below.
        raw = base64.urlsafe_b64decode(att["data"] + "=" * (-len(att["data"]) % 4))
        yield GmailAttachment(filename=filename, content=raw)
    for sub in part.get("parts", []) or []:
        yield from _iter_attachments(service, mailbox, message_id, sub)


def _extract_address(header_value: str) -> str:
    """RFC5322 'Name <addr@example.com>' or a bare address - the Gmail API returns raw header strings,
    same shape n8n's IMAP 'simple' format did, so the same extraction logic applies (see the equivalent
    fix in integrations/n8n/demo/email_ingress_workflow.json's Code node, now retired)."""
    header_value = header_value.strip()
    if "<" in header_value and header_value.endswith(">"):
        return header_value[header_value.rindex("<") + 1 : -1].strip()
    return header_value
