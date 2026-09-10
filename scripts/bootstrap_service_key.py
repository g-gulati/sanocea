"""One-time deployment bootstrap: create the master 'service' API key used by the background
reconciliation worker and other internal jobs (e.g. issuing further operator keys via POST
/admin/api-keys). Run once per environment; the raw key is printed exactly once and is never
recoverable afterward (only its hash is stored).

Usage: SANOCEA_PG_DSN=... python -m sanocea.scripts.bootstrap_service_key
"""
from __future__ import annotations

import os

from sanocea.packages.domain_contract import PostgresStore


def main() -> None:
    dsn = os.environ["SANOCEA_PG_DSN"]
    store = PostgresStore(dsn)
    store.migrate()
    key_id, raw_key = store.create_api_key(merchant_id=None, role="service", label="bootstrap-service-key")
    print(f"key_id={key_id}")
    print(f"SANOCEA_SERVICE_API_KEY={raw_key}")
    print("# Store this raw key in your secret manager now - it cannot be displayed again.")


if __name__ == "__main__":
    main()
