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
