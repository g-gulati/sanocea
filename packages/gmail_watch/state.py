"""Persistence for the Gmail push-notification edge's own state - the OAuth client registration, the
mailbox owner's refresh token, and Gmail's own change-cursor (historyId).

Deliberately NOT stored via packages/domain_contract/credentials.py's DurableEncryptedCredentialProvider:
that table's merchant_id column has a real FK to merchants(id), and this state is genuinely
mailbox-scoped, not merchant-scoped - one physical Gmail inbox (bigbrandloot@gmail.com) is shared across
every prospect demo tenant, and which merchant a given email belongs to is resolved LATER by SANOCEA's
own routing check (packages/email_ingress/service.py::resolve_merchant_from_routing), exactly as it was
under the n8n/IMAP transport this replaces. Forcing this into a merchant-scoped table would require an
artificial "system" merchant row that doesn't correspond to anything real.

Reuses the exact same AES-256-GCM primitive as DurableEncryptedCredentialProvider (same `cryptography`
library, same master-key-from-env convention) - see load_master_keys_from_env - so there is exactly one
encryption scheme in this codebase, not two; this module only avoids the merchant-scoped TABLE, not the
crypto itself.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime

import psycopg2
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from sanocea.packages.domain_contract.credentials import MissingMasterKeyError, load_master_keys_from_env

_ROW_ID = "default"  # single-row table - one Gmail mailbox for this whole demo deployment


@dataclass
class GmailWatchState:
    mailbox: str
    history_id: str | None
    watch_expiration: datetime | None
    oauth_client: dict | None  # {"client_id": ..., "client_secret": ..., "project_id": ...}
    refresh_token: str | None


class GmailWatchStateStore:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        keys, current = load_master_keys_from_env()
        if not current or current not in keys:
            raise MissingMasterKeyError(
                "SANOCEA_CRED_MASTER_KEY_CURRENT/SANOCEA_CRED_MASTER_KEY_<VERSION> must be set - "
                "gmail_watch_state encrypts the OAuth client and refresh token at rest using the same "
                "master key the rest of Sanocea's credential storage uses."
            )
        self._keys = keys
        self._current_version = current

    def _connect(self):
        return psycopg2.connect(self.dsn)

    def _encrypt(self, plaintext: str) -> tuple[bytes, bytes]:
        key = self._keys[self._current_version]
        nonce = os.urandom(12)
        ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
        return ciphertext, nonce

    def _decrypt(self, ciphertext: bytes, nonce: bytes, key_version: str) -> str:
        key = self._keys.get(key_version)
        if key is None:
            raise MissingMasterKeyError(f"no master key loaded for version {key_version!r}")
        try:
            return AESGCM(key).decrypt(bytes(nonce), bytes(ciphertext), None).decode("utf-8")
        except InvalidTag as exc:
            raise ValueError("gmail_watch_state decryption failed - wrong key or corrupted ciphertext") from exc

    def load(self) -> GmailWatchState | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT mailbox, history_id, watch_expiration, oauth_client_ciphertext, oauth_client_nonce, "
                "refresh_token_ciphertext, refresh_token_nonce, key_version FROM gmail_watch_state WHERE id = %s",
                (_ROW_ID,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        mailbox, history_id, watch_expiration, oc_ct, oc_nonce, rt_ct, rt_nonce, key_version = row
        import json

        oauth_client = json.loads(self._decrypt(bytes(oc_ct), bytes(oc_nonce), key_version)) if oc_ct else None
        refresh_token = self._decrypt(bytes(rt_ct), bytes(rt_nonce), key_version) if rt_ct else None
        return GmailWatchState(
            mailbox=mailbox, history_id=history_id, watch_expiration=watch_expiration,
            oauth_client=oauth_client, refresh_token=refresh_token,
        )

    def save_oauth_client(self, mailbox: str, oauth_client: dict) -> None:
        import json

        ct, nonce = self._encrypt(json.dumps(oauth_client))
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO gmail_watch_state (id, mailbox, history_id, oauth_client_ciphertext, oauth_client_nonce, key_version, updated_at)
                VALUES (%s, %s, '0', %s, %s, %s, now())
                ON CONFLICT (id) DO UPDATE SET
                  mailbox = EXCLUDED.mailbox, oauth_client_ciphertext = EXCLUDED.oauth_client_ciphertext,
                  oauth_client_nonce = EXCLUDED.oauth_client_nonce, key_version = EXCLUDED.key_version, updated_at = now()
                """,
                (_ROW_ID, mailbox, ct, nonce, self._current_version),
            )
            conn.commit()

    def save_refresh_token(self, refresh_token: str) -> None:
        ct, nonce = self._encrypt(refresh_token)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE gmail_watch_state SET refresh_token_ciphertext = %s, refresh_token_nonce = %s, "
                "key_version = %s, updated_at = now() WHERE id = %s",
                (ct, nonce, self._current_version, _ROW_ID),
            )
            conn.commit()

    def save_history_checkpoint(self, history_id: str, watch_expiration: datetime | None = None) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            if watch_expiration is not None:
                cur.execute(
                    "UPDATE gmail_watch_state SET history_id = %s, watch_expiration = %s, updated_at = now() WHERE id = %s",
                    (history_id, watch_expiration, _ROW_ID),
                )
            else:
                cur.execute(
                    "UPDATE gmail_watch_state SET history_id = %s, updated_at = now() WHERE id = %s",
                    (history_id, _ROW_ID),
                )
            conn.commit()
