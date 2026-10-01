"""Generic website publisher. It EXECUTES an already-authorised change; it never decides whether a change is allowed.

Flow:  Opportunity -> Decision -> Autonomy policy -> Eligibility gates -> Publisher.
The publisher refuses anything not backed by an ELIGIBLE decision whose digest is in the tenant's audit log, any action it does
not support, and any file outside the action's allowed paths (so it cannot touch redirects, nginx or pages).

Static-site mechanism (the site is a static build, no CMS): releases/<id>/ + an atomic `current` symlink served by nginx.
A publication NEVER edits the live release in place: it copies the current release to a NEW release directory, applies the
change there, proves exactly the allowed files differ, and switches the symlink atomically. The previous release is kept
untouched and is the rollback target. Initially supported: FIX_SITEMAP_ENTRY only."""

from __future__ import annotations

import difflib
import hashlib
import os
import shutil
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Protocol

from pydantic import BaseModel, Field

from packages.content_engine.seo.policy import PublishDecision, classify_action
from packages.content_engine.seo.store import SeoContentStore

# action -> the ONLY files it may change (relative to the release root)
ALLOWED_FILES: Dict[str, frozenset] = {"FIX_SITEMAP_ENTRY": frozenset({"sitemap.xml"})}
SUPPORTED_ACTIONS = frozenset(ALLOWED_FILES)


class PublisherError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


class PublishRequest(BaseModel):
    tenant_id: str
    opportunity_id: str
    change_id: str
    action: str
    target: str
    file_changes: Dict[str, str]  # relative path -> new full text
    before_sha256: str
    after_sha256: str
    expected_outcome: List[Dict] = Field(default_factory=list)  # from the action plan; what verification must observe
    source_path: Optional[str] = None  # repository source of the file, for the recorded source-sync patch


class ChangedFile(BaseModel):
    path: str
    before_sha256: str
    after_sha256: str


class PublishReceipt(BaseModel):
    change_id: str
    tenant_id: str
    action: str
    target: str
    status: str  # PUBLISHED | NOOP_ALREADY_PUBLISHED
    previous_release: str
    new_release: str
    changed_files: List[ChangedFile]
    published_at: str
    rollback_ref: str  # the previous release directory name
    opportunity_id: str = ""
    expected_outcome: List[Dict] = Field(default_factory=list)
    verification_required: bool = True
    source_sync_patch: str = ""  # the repository source must be updated or the next full build reverts this change


class RollbackResult(BaseModel):
    change_id: str
    restored_release: str
    live_sha256: str
    rolled_back_at: str


class WebsitePublisher(Protocol):
    def supports(self, action: str) -> bool: ...
    def publish(self, request: PublishRequest, decision: PublishDecision, store: SeoContentStore) -> PublishReceipt: ...
    def rollback(self, receipt: PublishReceipt, store: SeoContentStore) -> RollbackResult: ...


def _sha_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _tree_hashes(root: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for d, _, files in os.walk(root):
        for n in files:
            p = os.path.join(d, n)
            out[os.path.relpath(p, root)] = "symlink" if os.path.islink(p) else _sha_file(p)
    return out


class StaticSiteReleasePublisher:
    def __init__(self, www_root: str, tenant_id: str, health_check: Optional[Callable[[str], bool]] = None, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.root, self.tenant_id, self.health_check, self.clock = www_root, tenant_id, health_check, clock

    # ── paths ────────────────────────────────────────────────────────────────
    @property
    def current_link(self) -> str:
        return os.path.join(self.root, "current")

    def current_release(self) -> str:
        return os.path.realpath(self.current_link)

    def live_file(self, rel: str) -> str:
        with open(os.path.join(self.current_release(), rel), "r", encoding="utf-8") as f:
            return f.read()

    def supports(self, action: str) -> bool:
        return action in SUPPORTED_ACTIONS and classify_action(action) in ("A", "B")

    def _switch(self, release_dir: str) -> None:
        tmp = self.current_link + ".tmp"
        if os.path.lexists(tmp):
            os.unlink(tmp)
        os.symlink(release_dir, tmp)
        os.replace(tmp, self.current_link)  # atomic rename over the symlink: readers see the old or the new release, never neither

    # ── guard: the publisher cannot bypass policy ────────────────────────────
    def _authorise(self, req: PublishRequest, dec: PublishDecision, store: SeoContentStore) -> None:
        if req.action not in SUPPORTED_ACTIONS or not self.supports(req.action):
            raise PublisherError("UNSUPPORTED_ACTION", f"{req.action} is not enabled in the publisher (supported: {sorted(SUPPORTED_ACTIONS)}).")
        if req.tenant_id != self.tenant_id or dec.tenant_id != self.tenant_id:
            raise PublisherError("TENANT_MISMATCH", "The request or decision belongs to a different tenant.")
        if not (dec.eligible and dec.status == "ELIGIBLE") or dec.blocked_by:
            raise PublisherError("NOT_ELIGIBLE", f"The decision is not eligible: {dec.blocked_by}.")
        if dec.draft_id != req.change_id or dec.action != req.action or dec.action_class not in ("A", "B"):
            raise PublisherError("DECISION_MISMATCH", "The decision does not match this change.")
        digest = hashlib.sha1(f"{req.change_id}|{req.action}|{sorted(dec.blocked_by)}|{req.before_sha256}|{req.after_sha256}".encode()).hexdigest()[:16]
        ev = [e for e in store.audit_events(self.tenant_id) if e.get("event_id") == "evt_" + digest and e.get("eligible") is True and e.get("change_id") == req.change_id]
        if not ev:
            raise PublisherError("NO_AUDITED_DECISION", "No audited eligibility decision matches this change; a decision object alone is not authority.")
        extra = set(req.file_changes) - ALLOWED_FILES[req.action]
        if extra or not req.file_changes:
            raise PublisherError("PATH_NOT_ALLOWED", f"{req.action} may only change {sorted(ALLOWED_FILES[req.action])}; refused {sorted(extra)}.")

    # ── publish ──────────────────────────────────────────────────────────────
    def publish(self, req: PublishRequest, dec: PublishDecision, store: SeoContentStore) -> PublishReceipt:
        self._authorise(req, dec, store)
        prior = store.get_publication(self.tenant_id, req.change_id)
        if prior:  # idempotent: the same change is never applied twice
            return PublishReceipt(**{**{k: v for k, v in prior.items() if k not in ("key", "tenant_id_")}, "status": "NOOP_ALREADY_PUBLISHED"})
        prev = self.current_release()
        for rel in req.file_changes:
            if _sha_file(os.path.join(prev, rel)) != req.before_sha256:
                raise PublisherError("STALE_BEFORE_STATE", f"The live {rel} changed since this change was planned; re-plan instead of overwriting.")
        now = self.clock()
        new = os.path.join(self.root, "releases", f"{now.strftime('%Y-%m-%dT%H-%M-%SZ')}-{req.change_id}")
        if os.path.exists(new):
            raise PublisherError("RELEASE_EXISTS", "The release directory for this change already exists.")
        shutil.copytree(prev, new, symlinks=True)  # NEW release; the live one is never edited in place
        try:
            for rel, text in req.file_changes.items():
                dest = os.path.join(new, rel)
                tmp = dest + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(text)
                os.replace(tmp, dest)
            before, after = _tree_hashes(prev), _tree_hashes(new)
            changed = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))
            if set(changed) != set(req.file_changes):
                raise PublisherError("UNEXPECTED_DIFF", f"Release differs in {changed}, expected exactly {sorted(req.file_changes)}.")
            if after["sitemap.xml"] != req.after_sha256:
                raise PublisherError("AFTER_HASH_MISMATCH", "The written file does not match the planned after-state.")
        except Exception:
            shutil.rmtree(new, ignore_errors=True)  # nothing was switched; live release untouched
            raise
        self._switch(new)
        if self.health_check and not self.health_check(new):
            self._switch(prev)
            raise PublisherError("HEALTH_CHECK_FAILED", "The new release failed its health check; switched back to the previous release.")
        patch = "".join(difflib.unified_diff(open(os.path.join(prev, "sitemap.xml")).read().splitlines(True), req.file_changes["sitemap.xml"].splitlines(True), "a/" + (req.source_path or "sitemap.xml"), "b/" + (req.source_path or "sitemap.xml")))
        receipt = PublishReceipt(change_id=req.change_id, tenant_id=self.tenant_id, action=req.action, target=req.target, status="PUBLISHED", previous_release=os.path.basename(prev), new_release=os.path.basename(new),
                                 changed_files=[ChangedFile(path=p, before_sha256=before[p], after_sha256=after[p]) for p in changed], published_at=now.isoformat(), rollback_ref=os.path.basename(prev), source_sync_patch=patch, opportunity_id=req.opportunity_id, expected_outcome=req.expected_outcome)
        store.record_publication(self.tenant_id, req.change_id, receipt.model_dump())
        store.append_audit(self.tenant_id, "evt_pub_" + req.change_id, {"type": "SITEMAP_PUBLISHED", "change_id": req.change_id, "opportunity_id": req.opportunity_id, "action": req.action, "actor_type": "AUTONOMOUS_AGENT",
                                                                       "previous_release": receipt.previous_release, "new_release": receipt.new_release, "before_sha256": req.before_sha256, "after_sha256": req.after_sha256, "at": receipt.published_at})
        return receipt

    # ── rollback ─────────────────────────────────────────────────────────────
    def rollback(self, receipt: PublishReceipt, store: SeoContentStore) -> RollbackResult:
        """Restores the exact previous release the change recorded. Refuses if anything was published since (it would undo that too)."""
        prev = os.path.join(self.root, "releases", receipt.rollback_ref)
        if self.current_release() != os.path.join(self.root, "releases", receipt.new_release):
            raise PublisherError("ROLLBACK_CONFLICT", "The live release is no longer the one this change created; refusing to undo later changes.")
        if not os.path.isdir(prev):
            raise PublisherError("PREVIOUS_RELEASE_MISSING", "The previous release no longer exists.")
        for c in receipt.changed_files:
            if _sha_file(os.path.join(prev, c.path)) != c.before_sha256:
                raise PublisherError("PREVIOUS_RELEASE_ALTERED", f"{c.path} in the previous release no longer matches its recorded before-state.")
        self._switch(prev)
        live = _sha_file(os.path.join(self.current_release(), receipt.changed_files[0].path))
        now = self.clock().isoformat()
        store.append_audit(self.tenant_id, "evt_rb_" + receipt.change_id, {"type": "SITEMAP_ROLLED_BACK", "change_id": receipt.change_id, "restored_release": receipt.rollback_ref, "live_sha256": live, "at": now})
        return RollbackResult(change_id=receipt.change_id, restored_release=receipt.rollback_ref, live_sha256=live, rolled_back_at=now)
