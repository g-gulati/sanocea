"""Email-driven product ingestion for SANOCEA prospect demo tenants.

Deliberately thin: routing + security + timing/audit glue only. Every actual ingestion/validation/
provenance/exception/approval decision is made by the SAME certified engine every other ingestion path
already uses - packages.product_onboarding.workflow.ProductOnboardingWorkflow (services.catalogue) -
never duplicated or reimplemented here. n8n (or any other transport) is authoritative for NOTHING listed
in this module's docstring elsewhere as SANOCEA's own authority: canonical product state, provenance,
identity, validation, policy, approvals, exceptions, audit, publication. It only ever delivers bytes to
`ingest_email_attachment` below.
"""

from __future__ import annotations

import hashlib
import io
import re
import tempfile
import threading
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from sanocea.packages.audit import AuditLedger
from sanocea.packages.audit.context import reset_correlation_id, set_correlation_id
from sanocea.packages.domain_contract.models import Approval, ExceptionRecord, now_utc

MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024  # 10MB - generous for a demo product master, not a data lake
ALLOWED_EXTENSIONS = {".xlsx", ".csv"}
# Real Office Open XML zip container signature (PK\x03\x04) - the only way an .xlsx can honestly be one.
XLSX_MAGIC = b"PK\x03\x04"
DANGEROUS_ZIP_ENTRY_SUFFIXES = (".exe", ".dll", ".bat", ".cmd", ".sh", ".ps1", ".vbs", ".js", ".jar")
MACRO_ENTRY_MARKERS = ("vbaproject.bin",)
MAX_ZIP_UNCOMPRESSED_BYTES = 50 * 1024 * 1024  # zip-bomb guard - real demo workbooks are KB, not 50MB
MAX_ZIP_COMPRESSION_RATIO = 100  # a legitimate xlsx compresses maybe 5-10x; 100x is a bomb signature


class EmailRoutingError(ValueError):
    """Routing could not be resolved to exactly one known demo merchant - always fail closed, never
    guess. Raised before any ingestion is attempted; nothing is ever written to any merchant's data."""


class EmailIngestionError(ValueError):
    """Attachment failed a safety/format check, or the ingestion pipeline itself failed. Always raised
    before or instead of a partial/silent success - see PHASE L in the workflow spec this implements."""


# Deterministic email routing: Gmail's native plus-addressing (RFC 5233 subaddressing), not a bespoke
# mechanism. `bigbrandloot+demo-<slug>@gmail.com` requires zero mailbox-provider setup (no alias
# creation, no distribution list) and is inspectable by anyone reading the raw envelope - the exact
# property PHASE C's "trusted sender + subject token" and "dedicated recipient alias" options both aim
# for, without needing either a real alias or a hand-parsed subject convention.
ROUTING_SLUG_TO_MERCHANT = {
    "demo-ajanta": "prospect_ajanta_soya",
    "demo-healthvitals": "prospect_healthvitals",
    "demo-carzex": "prospect_carzex",
    "demo-premiumbasket": "prospect_premium_basket",
}
_PLUS_ADDRESS_RE = re.compile(r"^[^+@]+\+([^@]+)@", re.IGNORECASE)


def resolve_merchant_from_routing(to_addresses: list[str], sender: str, trusted_senders: set[str]) -> str:
    """FAIL CLOSED by construction: raises EmailRoutingError for anything not an exact, unambiguous
    match - an untrusted sender, zero matching recipients, more than one DIFFERENT matching recipient
    (genuinely ambiguous, never resolved by picking the first), or an unrecognized routing slug. Never
    infers a merchant from attachment contents, subject text, or any other unauthenticated signal."""
    if sender.strip().lower() not in trusted_senders:
        raise EmailRoutingError(f"sender {sender!r} is not a trusted demo sender")

    matched_merchants: set[str] = set()
    for addr in to_addresses:
        m = _PLUS_ADDRESS_RE.match(addr.strip())
        if not m:
            continue
        slug = m.group(1).strip().lower()
        merchant_id = ROUTING_SLUG_TO_MERCHANT.get(slug)
        if merchant_id:
            matched_merchants.add(merchant_id)

    if len(matched_merchants) == 0:
        raise EmailRoutingError(f"no recognized demo routing address among {to_addresses!r}")
    if len(matched_merchants) > 1:
        raise EmailRoutingError(f"ambiguous routing - matched more than one demo tenant: {matched_merchants!r}")
    return matched_merchants.pop()


def validate_attachment_safety(filename: str, content: bytes) -> None:
    """Untrusted input (PHASE N). Every check here fails closed with a specific, non-generic reason -
    never a silent pass-through. Deliberately does NOT execute anything to check it - no formula
    evaluation, no macro execution, no archive extraction to disk outside the caller's own controlled
    temp file."""
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise EmailIngestionError(f"unsupported attachment type {suffix!r} - only {sorted(ALLOWED_EXTENSIONS)} accepted")
    if len(content) == 0:
        raise EmailIngestionError("attachment is empty")
    if len(content) > MAX_ATTACHMENT_BYTES:
        raise EmailIngestionError(f"attachment exceeds {MAX_ATTACHMENT_BYTES} byte limit")

    if suffix == ".xlsx":
        if not content.startswith(XLSX_MAGIC):
            raise EmailIngestionError("attachment named .xlsx but is not a real Office Open XML zip container (extension/content mismatch)")
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                total_uncompressed = 0
                for info in zf.infolist():
                    name_lower = info.filename.lower()
                    # Path traversal / absolute-path guard - a legitimate xlsx entry is always a plain
                    # relative name like "xl/worksheets/sheet1.xml".
                    if info.filename.startswith("/") or ".." in Path(info.filename).parts:
                        raise EmailIngestionError(f"unsafe zip entry path: {info.filename!r}")
                    if name_lower.endswith(DANGEROUS_ZIP_ENTRY_SUFFIXES):
                        raise EmailIngestionError(f"attachment contains disallowed executable-shaped entry: {info.filename!r}")
                    if any(marker in name_lower for marker in MACRO_ENTRY_MARKERS):
                        raise EmailIngestionError("macro-enabled workbook rejected (vbaProject.bin present) - only plain .xlsx accepted")
                    total_uncompressed += info.file_size
                if total_uncompressed > MAX_ZIP_UNCOMPRESSED_BYTES:
                    raise EmailIngestionError("attachment uncompressed size exceeds safety limit (possible zip bomb)")
                if len(content) > 0 and total_uncompressed / max(len(content), 1) > MAX_ZIP_COMPRESSION_RATIO:
                    raise EmailIngestionError("attachment compression ratio exceeds safety limit (possible zip bomb)")
        except zipfile.BadZipFile as exc:
            raise EmailIngestionError("attachment is not a valid zip/xlsx container") from exc
    elif suffix == ".csv":
        try:
            content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise EmailIngestionError("attachment is not valid UTF-8 text CSV") from exc


@dataclass
class EmailIngestionResult:
    run_id: str
    merchant_id: str
    message_id: str
    filename: str
    idempotent_replay: bool
    email_received_at: str
    ingestion_started_at: str
    ingestion_completed_at: str
    validation_completed_at: str
    workflow_completed_at: str
    elapsed_seconds: float
    records_received: int
    records_ready: int
    records_requiring_attention: int
    exception_ids: list[str] = field(default_factory=list)
    approval_ids: list[str] = field(default_factory=list)
    channel_operations_started: int = 0
    channels_engaged: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id, "merchant_id": self.merchant_id, "message_id": self.message_id,
            "filename": self.filename, "idempotent_replay": self.idempotent_replay,
            "email_received_at": self.email_received_at, "ingestion_started_at": self.ingestion_started_at,
            "ingestion_completed_at": self.ingestion_completed_at,
            "validation_completed_at": self.validation_completed_at,
            "workflow_completed_at": self.workflow_completed_at, "elapsed_seconds": self.elapsed_seconds,
            "records_received": self.records_received, "records_ready": self.records_ready,
            "records_requiring_attention": self.records_requiring_attention,
            "exception_ids": self.exception_ids, "approval_ids": self.approval_ids,
            "channel_operations_started": self.channel_operations_started, "channels_engaged": self.channels_engaged,
        }


class EmailIngestionService:
    def __init__(self, store, services, idempotency) -> None:
        self.store = store
        self.services = services  # packages.runtime.Services - services.catalogue is the SAME
        # ProductOnboardingWorkflow every other ingestion path (UI upload, API) already uses.
        self.idempotency = idempotency
        self.audit = AuditLedger(store)

    def ingest_email_attachment(
        self, *, merchant_id: str, message_id: str, filename: str, content: bytes,
        sender: str, subject: str, received_at=None,
    ) -> EmailIngestionResult:
        validate_attachment_safety(filename, content)

        content_hash = hashlib.sha256(content).hexdigest()
        # Idempotent per (merchant, message_id, attachment content hash) - reuses the SAME
        # IdempotencyService/reserve-complete-release primitive the Shopify webhook path already relies
        # on (connectors/shopify_live/connector.py::ingest_webhook). A replayed identical email/attachment
        # (retry, duplicate delivery) collapses to one ingestion; a REVISED attachment under the same
        # message_id gets a different hash and is genuinely (correctly) reprocessed.
        scope = f"{merchant_id}:email_ingest"
        idem_key = f"{message_id}:{content_hash}"
        run_id = f"email:{message_id}:{content_hash[:12]}"

        def _do_ingest() -> dict[str, Any]:
            email_received_at = (received_at or now_utc()).isoformat()
            token = set_correlation_id(run_id)
            try:
                self.audit.record(
                    merchant_id=merchant_id, actor="email_ingress", source="gmail", action="email_received",
                    object_type="EmailMessage", object_id=message_id, result="received",
                    correlation_id=run_id,
                )
                self.audit.record(
                    merchant_id=merchant_id, actor="email_ingress", source="gmail", action="attachment_received",
                    object_type="EmailMessage", object_id=message_id, result=filename, correlation_id=run_id,
                )
                self.audit.record(
                    merchant_id=merchant_id, actor="email_ingress", source="gmail", action="file_validated",
                    object_type="EmailMessage", object_id=message_id, result="safety_checks_passed", correlation_id=run_id,
                )

                ingestion_started_at = now_utc().isoformat()
                self.audit.record(
                    merchant_id=merchant_id, actor="email_ingress", source="gmail", action="ingestion_started",
                    object_type="EmailMessage", object_id=message_id, result="started", correlation_id=run_id,
                )

                suffix = Path(filename).suffix or ".csv"
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                    tmp.write(content)
                    tmp_path = Path(tmp.name)
                try:
                    drafts = self.services.catalogue.ingest_file(merchant_id, tmp_path, "application/octet-stream" if suffix == ".xlsx" else "text/csv")
                finally:
                    tmp_path.unlink(missing_ok=True)

                ingestion_completed_at = now_utc().isoformat()
                self.audit.record(
                    merchant_id=merchant_id, actor="email_ingress", source="gmail", action="ingestion_completed",
                    object_type="EmailMessage", object_id=message_id, result=f"{len(drafts)} records", correlation_id=run_id,
                )

                for draft in drafts:
                    self.audit.record(
                        merchant_id=merchant_id, actor="email_ingress", source="gmail", action="record_extracted",
                        object_type="ProductDraft", object_id=draft.id, result=draft.sku or draft.title or "unknown",
                        correlation_id=run_id,
                    )

                # Empirically verified against the real validator (not assumed): a freshly-ingested new
                # product identity normally lands in NEEDS_APPROVAL - a routine, one-click governance
                # sign-off (policy.publication.require_approval), NOT a data problem. Only
                # CONFLICTED/INCOMPLETE/INVALID represent a genuine defect the real validator actually
                # detected (e.g. a barcode collision, a missing mandatory field) - those, not
                # NEEDS_APPROVAL, are what "requires attention" means here.
                attention_states = {"CONFLICTED", "INCOMPLETE", "INVALID"}
                attention = [d for d in drafts if d.state in attention_states]
                ready = [d for d in drafts if d.state not in attention_states]
                for draft in ready:
                    self.audit.record(
                        merchant_id=merchant_id, actor="email_ingress", source="gmail", action="product_ready",
                        object_type="ProductDraft", object_id=draft.id, result="clean", correlation_id=run_id,
                    )

                validation_completed_at = now_utc().isoformat()
                self.audit.record(
                    merchant_id=merchant_id, actor="email_ingress", source="gmail", action="validation_completed",
                    object_type="EmailMessage", object_id=message_id,
                    result=f"{len(ready)} ready / {len(attention)} require attention", correlation_id=run_id,
                )

                # ingest_file() already created the real ExceptionRecord/Approval rows for
                # CONFLICTED/INCOMPLETE/INVALID/NEEDS_APPROVAL drafts (ProductOnboardingWorkflow's own
                # logic, reused unchanged) - just collect their ids for this run's own summary/response.
                # Approvals are collected from ALL drafts this run touched (routine NEEDS_APPROVAL
                # sign-offs are real approvals too, even though they are not "attention" - see above);
                # exceptions only ever exist for genuine attention-state drafts.
                all_draft_ids = {d.id for d in drafts}
                exception_ids = [
                    e.id for e in self.store.list(ExceptionRecord, merchant_id)
                    if e.object_id in {d.id for d in attention} and e.correlation_id == run_id
                ]
                approval_ids = [
                    a.id for a in self.store.list(Approval, merchant_id)
                    if a.object_id in all_draft_ids
                ]
                for aid in approval_ids:
                    self.audit.record(
                        merchant_id=merchant_id, actor="email_ingress", source="gmail", action="approval_required",
                        object_type="Approval", object_id=aid, result="pending", correlation_id=run_id,
                    )

                # PHASE (Sept 2026 multi-channel live demo #2): clean records continue automatically into
                # Channel Operations - no separate manual trigger. Runs in a BACKGROUND THREAD rather than
                # inline: real marketplace/channel operations are genuinely asynchronous work, and running
                # them synchronously inside this HTTP request would force every channel to finish (or fail)
                # before the response even returns - the exact "everything resolves in lockstep" artifact
                # that makes a demo look scripted rather than like real, independently-paced channel work.
                # A channel-operations failure must never retroactively fail the ingestion itself (the
                # products WERE genuinely ingested/validated); per-operation failures are already caught
                # and recorded as FAILED ChannelOperation rows by the service itself, never raised here.
                # store.put()/get() open a FRESH connection per call by default (no shared-connection reuse
                # unless SANOCEA_PG_REUSE_CONNECTION=1 - see PostgresStore.connect()), so handing the same
                # store instance to a background thread is safe: the two threads never share one connection.
                config_for_channels = self.store.get_config(merchant_id)
                known_channels = (config_for_channels.get("demo") or {}).get("known_channels") or []
                from sanocea.packages.channel_ops.service import CANONICAL_CHANNELS as _CANONICAL_CHANNELS

                channels_engaged = [c for c in _CANONICAL_CHANNELS if c in known_channels]
                channel_ops_started = len(channels_engaged) * len(ready)
                if channel_ops_started:
                    self.audit.record(
                        merchant_id=merchant_id, actor="email_ingress", source="gmail",
                        action="channel_operations_queued", object_type="EmailMessage", object_id=message_id,
                        result=f"{channel_ops_started} operations queued across {len(channels_engaged)} channels",
                        correlation_id=run_id,
                    )

                    def _run_channel_ops_in_background(store=self.store, mid=merchant_id, rid=run_id, draft_ids=[d.id for d in ready]) -> None:
                        from sanocea.packages.channel_ops import ChannelOperationService

                        try:
                            ChannelOperationService(store).run_for_email_ingestion(mid, rid, draft_ids)
                        except Exception as bg_exc:  # noqa: BLE001 - visible via audit, never crashes the (already-returned) request
                            AuditLedger(store).record(
                                merchant_id=mid, actor="email_ingress", source="gmail",
                                action="channel_operations_failed", object_type="EmailMessage", object_id=message_id,
                                result="error", error=str(bg_exc), correlation_id=rid,
                            )

                    threading.Thread(target=_run_channel_ops_in_background, daemon=True).start()

                workflow_completed_at = now_utc().isoformat()
                self.audit.record(
                    merchant_id=merchant_id, actor="email_ingress", source="gmail", action="workflow_completed",
                    object_type="EmailMessage", object_id=message_id,
                    result=f"received={len(drafts)} ready={len(ready)} attention={len(attention)}",
                    correlation_id=run_id,
                )

                elapsed = (now_utc() - datetime.fromisoformat(ingestion_started_at)).total_seconds()
                return EmailIngestionResult(
                    run_id=run_id, merchant_id=merchant_id, message_id=message_id, filename=filename,
                    idempotent_replay=False,
                    email_received_at=email_received_at, ingestion_started_at=ingestion_started_at,
                    ingestion_completed_at=ingestion_completed_at, validation_completed_at=validation_completed_at,
                    workflow_completed_at=workflow_completed_at, elapsed_seconds=round(max(elapsed, 0.0), 3),
                    records_received=len(drafts), records_ready=len(ready), records_requiring_attention=len(attention),
                    exception_ids=exception_ids, approval_ids=approval_ids,
                    channel_operations_started=channel_ops_started, channels_engaged=channels_engaged,
                ).as_dict()
            finally:
                reset_correlation_id(token)

        result_dict, created = self.idempotency.run_once(scope, idem_key, _do_ingest)
        result = EmailIngestionResult(**{**result_dict, "idempotent_replay": not created})
        if not created:
            self.audit.record(
                merchant_id=merchant_id, actor="email_ingress", source="gmail", action="duplicate_email_ignored",
                object_type="EmailMessage", object_id=message_id, result="idempotent_replay",
            )
        return result
