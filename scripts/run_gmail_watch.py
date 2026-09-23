#!/usr/bin/env python3
"""Long-running subscriber process for the Gmail push-notification email edge. Requires
scripts/gmail_watch_bootstrap.py to have been run once already (an OAuth client + refresh token +
initial watch must already be stored). Safe to restart at any time - refreshes the stored token silently
(no re-consent) and resumes from the last saved historyId checkpoint (see packages/gmail_watch/state.py
and subscriber.py's reliability notes for exactly what that guarantees and what it does not).

Usage:
  SANOCEA_SERVICE_API_KEY=sk_... python scripts/run_gmail_watch.py \
    --mailbox bigbrandloot@gmail.com \
    --topic projects/sanocea-demo/topics/gmail-inbox-events \
    --subscription projects/sanocea-demo/subscriptions/gmail-inbox-events-sub \
    --sanocea-url http://127.0.0.1:8080/demo/email-ingest
"""

from __future__ import annotations

import argparse
import base64
import logging
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mailbox", required=True)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--subscription", required=True, help="Full Pub/Sub subscription path")
    parser.add_argument("--sanocea-url", default="http://127.0.0.1:8080/demo/email-ingest")
    args = parser.parse_args()

    service_key = os.environ.get("SANOCEA_SERVICE_API_KEY")
    if not service_key:
        print("SANOCEA_SERVICE_API_KEY must be set", file=sys.stderr)
        sys.exit(1)

    dsn = os.environ.get("SANOCEA_PG_DSN", "postgresql://sanocea:sanocea@127.0.0.1:55432/sanocea_phase05")

    from sanocea.packages.domain_contract.credentials import build_production_credential_provider
    from sanocea.packages.domain_contract.postgres_store import PostgresStore
    from sanocea.packages.gmail_watch import GmailPushSubscriber, GmailWatchStateStore, WatchRegistrar, load_or_run_oauth_flow
    from sanocea.packages.gmail_watch.gmail_client import build_gmail_service
    from sanocea.packages.idempotency import IdempotencyService

    state_store = GmailWatchStateStore(dsn)
    creds = load_or_run_oauth_flow(state_store, args.mailbox)  # silent refresh - no browser unless never bootstrapped
    service = build_gmail_service(creds)

    state = state_store.load()
    registrar = WatchRegistrar(service, state_store, args.topic)
    if state is None or state.history_id is None:
        registrar.register_now()
    registrar.start_renewal_loop()

    domain_store = PostgresStore(dsn, credential_provider=build_production_credential_provider(dsn))
    idempotency = IdempotencyService(domain_store)

    def log_latency(report):
        print(f"[LATENCY] {report.as_dict()}")

    subscriber = GmailPushSubscriber(
        gmail_service=service, state_store=state_store, idempotency=idempotency,
        subscription_path=args.subscription, sanocea_ingest_url=args.sanocea_url,
        sanocea_service_key=service_key, pubsub_credentials=creds, on_latency=log_latency,
    )
    print(f"[RUN] Gmail push subscriber listening on {args.subscription} -> {args.sanocea_url}")
    subscriber.run_forever()


if __name__ == "__main__":
    main()
