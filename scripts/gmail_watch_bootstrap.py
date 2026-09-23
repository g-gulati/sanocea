#!/usr/bin/env python3
"""ONE-TIME setup for the Gmail push-notification email edge: stores the OAuth client registration,
runs the mailbox owner's one-time browser consent (opens a local browser - the mailbox owner approves
once, no password or App Password is ever entered), and registers the initial Gmail watch(). After this
succeeds, scripts/run_gmail_watch.py can be started (and restarted) indefinitely without repeating any
of this - see packages/gmail_watch/oauth.py's docstring.

Usage:
  python scripts/gmail_watch_bootstrap.py \
    --mailbox bigbrandloot@gmail.com \
    --client-id <...>.apps.googleusercontent.com \
    --client-secret <...> \
    --project-id sanocea-demo \
    --topic projects/sanocea-demo/topics/gmail-inbox-events
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
PARENT_DIR = ROOT_DIR.parent
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if not os.environ.get("SANOCEA_CRED_MASTER_KEY_CURRENT"):
    os.environ["SANOCEA_CRED_MASTER_KEY_CURRENT"] = "v1"
    os.environ["SANOCEA_CRED_MASTER_KEY_V1"] = base64.b64encode(b"\x2a" * 32).decode()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mailbox", required=True)
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--client-secret", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--topic", required=True, help="Full Pub/Sub topic path: projects/<id>/topics/<name>")
    args = parser.parse_args()

    dsn = os.environ.get("SANOCEA_PG_DSN", "postgresql://sanocea:sanocea@127.0.0.1:55432/sanocea_phase05")

    from sanocea.packages.gmail_watch import GmailWatchStateStore, WatchRegistrar, load_or_run_oauth_flow
    from sanocea.packages.gmail_watch.gmail_client import build_gmail_service

    store = GmailWatchStateStore(dsn)
    store.save_oauth_client(args.mailbox, {
        "client_id": args.client_id, "client_secret": args.client_secret, "project_id": args.project_id,
    })
    print(f"[BOOTSTRAP] OAuth client stored for {args.mailbox}.")

    print("[BOOTSTRAP] Opening your browser for one-time consent - approve as", args.mailbox, "...")
    creds = load_or_run_oauth_flow(store, args.mailbox)
    print("[BOOTSTRAP] Consent granted, refresh token stored (encrypted).")

    service = build_gmail_service(creds)
    registrar = WatchRegistrar(service, store, args.topic)
    history_id = registrar.register_now()
    print(f"[BOOTSTRAP] Gmail watch registered on {args.topic}, starting historyId={history_id}.")
    print("[BOOTSTRAP] Done. You can now run: python scripts/run_gmail_watch.py")


if __name__ == "__main__":
    main()
