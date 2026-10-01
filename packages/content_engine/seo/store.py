"""JSON-file store for SEO briefs and drafts (same convention as the existing engine's JSON records).

Kept OUT of website/marketing-ops/content on purpose: that directory is the social-dedup history and part of the public
website tree. Layout: <root>/<tenant_id>/<id>.json. A tenant can only ever read its own directory."""

from __future__ import annotations

import json
import os
import re
import tempfile
from typing import Optional

from packages.content_engine.seo.models import SeoBrief, SeoDraft

_TENANT = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_ID = re.compile(r"^(brief|draft)_[a-f0-9]{12}$")


def default_root() -> str:
    return os.environ.get("SANOCEA_SEO_CONTENT_DIR", "/opt/sanocea/shared/seo_content")


class SeoContentStore:
    def __init__(self, root: Optional[str] = None):
        self.root = root or default_root()

    def _dir(self, tenant_id: str) -> str:
        if not _TENANT.match(tenant_id or ""):
            raise ValueError("invalid tenant id")
        return os.path.join(self.root, tenant_id)

    def _path(self, tenant_id: str, item_id: str) -> str:
        if not _ID.match(item_id or ""):
            raise ValueError("invalid id")
        return os.path.join(self._dir(tenant_id), f"{item_id}.json")

    def _write(self, path: str, payload: dict) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, sort_keys=True)
            os.replace(tmp, path)  # atomic: a reader never sees a half-written record
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def _read(self, path: str) -> Optional[dict]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return None

    def save_brief(self, brief: SeoBrief) -> None:
        self._write(self._path(brief.tenant_id, brief.brief_id), json.loads(brief.model_dump_json()))

    def get_brief(self, tenant_id: str, brief_id: str) -> Optional[SeoBrief]:
        d = self._read(self._path(tenant_id, brief_id))
        return SeoBrief(**d) if d and d.get("tenant_id") == tenant_id else None

    def save_draft(self, draft: SeoDraft) -> None:
        self._write(self._path(draft.tenant_id, draft.draft_id), json.loads(draft.model_dump_json()))

    def get_draft(self, tenant_id: str, draft_id: str) -> Optional[SeoDraft]:
        d = self._read(self._path(tenant_id, draft_id))
        return SeoDraft(**d) if d and d.get("tenant_id") == tenant_id else None

    def list_drafts(self, tenant_id: str) -> list:
        d = self._dir(tenant_id)
        if not os.path.isdir(d):
            return []
        out = []
        for name in sorted(os.listdir(d)):
            if name.startswith("draft_") and name.endswith(".json"):
                item = self._read(os.path.join(d, name))
                if item and item.get("tenant_id") == tenant_id:
                    out.append(SeoDraft(**item))
        return out


    # ── audit trail and publication ledger (append-only / write-once) ──────────
    def append_audit(self, tenant_id: str, event_id: str, event: dict) -> bool:
        """Append one audit event; an event id already present is not written twice (idempotent). Returns True if written."""
        path = os.path.join(self._dir(tenant_id), "audit.jsonl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                if any(json.loads(line).get("event_id") == event_id for line in f if line.strip()):
                    return False
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"event_id": event_id, "tenant_id": tenant_id, **event}, sort_keys=True) + "\n")
        return True

    def audit_events(self, tenant_id: str) -> list:
        path = os.path.join(self._dir(tenant_id), "audit.jsonl")
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def _pub_path(self, tenant_id: str, key: str) -> str:
        import hashlib
        return os.path.join(self._dir(tenant_id), "publications", hashlib.sha1(key.encode()).hexdigest()[:16] + ".json")

    def get_publication(self, tenant_id: str, key: str) -> Optional[dict]:
        return self._read(self._pub_path(tenant_id, key))

    def record_publication(self, tenant_id: str, key: str, record: dict) -> None:
        """Write-once ledger entry for a published item (called by the future publisher). A second write for the same key is refused."""
        path = self._pub_path(tenant_id, key)
        if os.path.exists(path):
            raise FileExistsError("already published")
        self._write(path, {"key": key, "tenant_id": tenant_id, **record})
