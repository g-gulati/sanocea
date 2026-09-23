"""Pull-based Pub/Sub subscriber - the event-transport half of the Gmail push edge. A PULL subscription
(not push/webhook) is deliberate: this deployment runs on a developer machine with no public HTTPS
endpoint, and Pub/Sub's own streaming-pull client (the same mechanism Google's own quickstart samples
use) delivers messages with sub-second latency over an outbound-only connection - no ngrok, no public
exposure, and no change to the target architecture's meaning of "Pub/Sub is only the event transport."

Reliability posture (see the user's explicit list): duplicate notifications, duplicate Gmail messages,
out-of-order delivery, multiple messages close together, a stale/expired historyId, and a mid-message
crash are all handled below - see the inline notes at each point. What is NOT claimed: exactly-once
delivery (Pub/Sub itself is at-least-once by design; this module makes redelivery safe via idempotency,
it does not pretend redelivery cannot happen).
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass

import requests
from google.api_core.exceptions import GoogleAPICallError, NotFound
from google.cloud import pubsub_v1

from sanocea.packages.idempotency import IdempotencyService

from .gmail_client import fetch_message, list_history
from .state import GmailWatchStateStore

logger = logging.getLogger("sanocea.gmail_watch")


@dataclass
class LatencyReport:
    message_id: str
    t0_email_arrived_ms: int
    t1_notification_received: float
    t2_message_identified: float
    t3_attachment_retrieved: float
    t4_ingestion_begins: float
    t4_ingestion_status: int

    def as_dict(self) -> dict:
        t0_s = self.t0_email_arrived_ms / 1000
        return {
            "message_id": self.message_id,
            "t0_email_arrived": t0_s,
            "t1_minus_t0_seconds": round(self.t1_notification_received - t0_s, 3),
            "t2_minus_t1_seconds": round(self.t2_message_identified - self.t1_notification_received, 3),
            "t3_minus_t2_seconds": round(self.t3_attachment_retrieved - self.t2_message_identified, 3),
            "t4_minus_t3_seconds": round(self.t4_ingestion_begins - self.t3_attachment_retrieved, 3),
            "total_t4_minus_t0_seconds": round(self.t4_ingestion_begins - t0_s, 3),
            "sanocea_ingestion_status": self.t4_ingestion_status,
        }


class GmailPushSubscriber:
    def __init__(
        self, gmail_service, state_store: GmailWatchStateStore, idempotency: IdempotencyService,
        subscription_path: str, sanocea_ingest_url: str, sanocea_service_key: str,
        pubsub_credentials=None, on_latency: "callable | None" = None,
    ) -> None:
        self.gmail_service = gmail_service
        self.state_store = state_store
        self.idempotency = idempotency
        self.subscription_path = subscription_path
        self.sanocea_ingest_url = sanocea_ingest_url
        self.sanocea_service_key = sanocea_service_key
        self.pubsub_credentials = pubsub_credentials
        self.on_latency = on_latency
        # A single, process-wide lock around "read checkpoint -> advance checkpoint" - Pub/Sub's
        # streaming-pull client delivers messages via its own thread pool, so two notifications can
        # arrive concurrently; without this lock two callbacks could both read the SAME stale
        # history_id and race to process/advance it, corrupting the checkpoint.
        self._checkpoint_lock = threading.Lock()

    def run_forever(self) -> None:
        subscriber = pubsub_v1.SubscriberClient(credentials=self.pubsub_credentials)
        future = subscriber.subscribe(self.subscription_path, callback=self._on_pubsub_message)
        logger.info("listening on %s", self.subscription_path)
        try:
            future.result()
        except KeyboardInterrupt:
            future.cancel()
            future.result()

    def _on_pubsub_message(self, message: "pubsub_v1.subscriber.message.Message") -> None:
        t1 = time.time()
        # Pub/Sub is at-least-once: the SAME message.message_id can be redelivered (network hiccup
        # before our ack reached Google, a redelivery after the ack deadline, etc). Dedup on Pub/Sub's
        # own unique message id BEFORE touching Gmail at all - a pure replay must be a true no-op.
        def _process() -> dict:
            return self._handle_notification(message, t1)

        try:
            result, created = self.idempotency.run_once("gmail_pubsub_notification", message.message_id, _process)
            if not created:
                logger.info("duplicate Pub/Sub notification %s - already processed, ack only", message.message_id)
            message.ack()
        except _TransientGmailError as exc:
            # A real, temporary failure (Gmail API hiccup, SANOCEA temporarily unreachable) - nack so
            # Pub/Sub redelivers with backoff, rather than silently losing the notification.
            logger.warning("transient failure processing notification %s: %s - will redeliver", message.message_id, exc)
            message.nack()
        except Exception:  # noqa: BLE001
            # An unexpected, non-transient failure. Acking here (not nacking) is deliberate: an
            # infinite redelivery loop of a message that will never succeed is its own reliability
            # failure (it starves the subscriber of capacity for genuinely new mail) - the exception is
            # logged loudly instead, a real operator-visible signal, never a silent drop.
            logger.exception("permanent failure processing notification %s - acking to avoid infinite redelivery", message.message_id)
            message.ack()

    def _handle_notification(self, message: "pubsub_v1.subscriber.message.Message", t1: float) -> dict:
        payload = json.loads(message.data.decode("utf-8"))
        notification_history_id = str(payload["historyId"])
        with self._checkpoint_lock:
            state = self.state_store.load()
            if state is None or state.history_id is None:
                raise RuntimeError("gmail_watch_state has no history_id checkpoint - register a watch first")
            start_history_id = state.history_id
            try:
                message_ids, latest_history_id = list_history(self.gmail_service, start_history_id)
            except NotFound as exc:
                # Gmail's history retention window has passed (typically ~7 days, sometimes sooner on a
                # very active mailbox) - our stored checkpoint is now unusable. This is a genuine GAP:
                # any mail that arrived between start_history_id and now whose history entry has already
                # rolled off is UNRECOVERABLE by definition (Gmail itself no longer has the delta). The
                # honest, fail-loud response is to resync forward from THIS notification's own
                # historyId, never to silently pretend nothing was missed.
                logger.error(
                    "gmail history gap: checkpoint %s has expired (%s) - resyncing to notification's "
                    "historyId %s; any mail in between may have been missed and is NOT recoverable",
                    start_history_id, exc, notification_history_id,
                )
                self.state_store.save_history_checkpoint(notification_history_id)
                return {"gap_resync": True}
            except GoogleAPICallError as exc:
                raise _TransientGmailError(str(exc)) from exc

            results = []
            for gmail_message_id in message_ids:
                results.append(self._process_one_message(gmail_message_id, t1))
            # Only advance the checkpoint after every message in this batch has been handled (even a
            # "no attachment, skipped" outcome counts as handled) - if the process crashes mid-batch,
            # restart resumes from the OLD checkpoint and safely reprocesses the whole batch, each
            # message individually deduped by its own message_id below.
            self.state_store.save_history_checkpoint(latest_history_id or notification_history_id)
            return {"processed": results}

    def _process_one_message(self, gmail_message_id: str, t1: float) -> dict:
        # Dedup at the actual Gmail message identity - the level that matters regardless of how many
        # times Pub/Sub redelivers the notification or how history-range overlaps might resurface the
        # same message id across two separate notifications.
        def _process() -> dict:
            return self._ingest_one_message(gmail_message_id, t1)

        result, created = self.idempotency.run_once("gmail_message_processed", gmail_message_id, _process)
        if not created:
            logger.info("gmail message %s already processed - skipping", gmail_message_id)
        return result

    def _ingest_one_message(self, gmail_message_id: str, t1: float) -> dict:
        try:
            gmail_message = fetch_message(self.gmail_service, gmail_message_id)
        except GoogleAPICallError as exc:
            raise _TransientGmailError(f"fetch_message failed: {exc}") from exc
        t2 = time.time()
        if not gmail_message.attachments:
            logger.info("gmail message %s (%r) has no attachment - nothing to forward", gmail_message_id, gmail_message.subject)
            return {"skipped": "no_attachment", "subject": gmail_message.subject, "from": gmail_message.sender}
        attachment = gmail_message.attachments[0]
        sha256 = hashlib.sha256(attachment.content).hexdigest()
        t3 = time.time()
        content_base64 = base64.b64encode(attachment.content).decode("ascii")
        payload = {
            "message_id": gmail_message.message_id,
            "sender": gmail_message.sender,
            "to_addresses": gmail_message.to_addresses,
            "subject": gmail_message.subject,
            "filename": attachment.filename,
            "content_base64": content_base64,
        }
        t4 = time.time()
        try:
            resp = requests.post(
                self.sanocea_ingest_url, json=payload,
                headers={"Authorization": f"Bearer {self.sanocea_service_key}", "Content-Type": "application/json"},
                timeout=90,
            )
        except requests.RequestException as exc:
            raise _TransientGmailError(f"POST to SANOCEA failed: {exc}") from exc
        report = LatencyReport(
            message_id=gmail_message.message_id, t0_email_arrived_ms=gmail_message.internal_date_ms,
            t1_notification_received=t1, t2_message_identified=t2, t3_attachment_retrieved=t3,
            t4_ingestion_begins=t4, t4_ingestion_status=resp.status_code,
        )
        logger.info("ingested gmail message %s: sha256=%s status=%s latency=%s", gmail_message_id, sha256, resp.status_code, report.as_dict())
        if self.on_latency:
            self.on_latency(report)
        return {"sha256": sha256, "status_code": resp.status_code, "subject": gmail_message.subject, "sender": gmail_message.sender}


class _TransientGmailError(Exception):
    """Distinguishes a retry-worthy failure (nack -> Pub/Sub redelivers) from a permanent one (ack ->
    logged, never silently retried forever)."""
