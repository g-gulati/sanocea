#!/usr/bin/env python3
"""Mints ONE internal-operator API key, explicitly authorized for the Reference Merchant plus every
configured prospect demo tenant (see packages/prospect_demo/registry.py::list_demo_tenants) - the fix
for the Command Center's "re-prompt for a new key on every merchant switch" UX problem.

This does NOT rotate or revoke any existing single-merchant operator key (Anchal's own key, or any
individual prospect key minted by scripts/reset_prospect_tenant.py, remain valid and unaffected) - it
creates one additional, purely additive key.

All five tenants must already exist as Merchant rows (run scripts/reset_reference_merchant.py and
scripts/reset_prospect_tenant.py --all at least once first) - api_key_merchants has a real foreign key
to merchants(id), so minting against a merchant that doesn't exist yet fails loudly rather than silently
creating a dangling authorization.
"""

from __future__ import annotations

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

from sanocea.packages.domain_contract.credentials import build_production_credential_provider
from sanocea.packages.domain_contract.postgres_store import PostgresStore
from sanocea.packages.prospect_demo import list_demo_tenants


def main() -> None:
    dsn = os.environ.get("SANOCEA_PG_DSN", "postgresql://sanocea:sanocea@127.0.0.1:55432/sanocea_phase05")
    cred_provider = build_production_credential_provider(dsn)
    store = PostgresStore(dsn, credential_provider=cred_provider)
    store.migrate()

    merchant_ids = [t["merchant_id"] for t in list_demo_tenants()]
    key_id, raw_key = store.create_api_key(
        merchant_id=None, role="operator", label="internal-operator-demo-switcher",
        allowed_merchants=merchant_ids,
    )
    print(f"[MINT] Internal operator key {key_id} authorized for: {merchant_ids}")
    if os.environ.get("SANOCEA_PRINT_DEMO_OPERATOR_KEYS") == "1":
        print(f"[MINT] api_key={raw_key}")
    else:
        print("[MINT] raw key not printed by default - set SANOCEA_PRINT_DEMO_OPERATOR_KEYS=1 to print it")


if __name__ == "__main__":
    main()
