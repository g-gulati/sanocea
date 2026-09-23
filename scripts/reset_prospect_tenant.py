#!/usr/bin/env python3
"""SANOCEA Prospect Demo Tenant Deterministic Reset CLI.

Resets ONE prospect demo tenant (see packages/prospect_demo/tenants.py::PROSPECT_TENANTS) to its
canonical baseline: real, publicly-verified products + a synthetic operational scenario. Never touches
the Reference Merchant (ref_anchal_heritage) or any other prospect tenant.

Usage:
    python scripts/reset_prospect_tenant.py <merchant_id>
    python scripts/reset_prospect_tenant.py --all
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
PARENT_DIR = ROOT_DIR.parent
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sanocea.packages.prospect_demo import PROSPECT_TENANTS, reset_prospect_tenant


def main() -> None:
    dsn = os.environ.get("SANOCEA_PG_DSN", "postgresql://sanocea:sanocea@127.0.0.1:55432/sanocea_phase05")
    if len(sys.argv) < 2:
        print("usage: python scripts/reset_prospect_tenant.py <merchant_id> | --all")
        print(f"known tenants: {list(PROSPECT_TENANTS.keys())}")
        sys.exit(1)

    targets = list(PROSPECT_TENANTS.keys()) if sys.argv[1] == "--all" else [sys.argv[1]]
    for merchant_id in targets:
        print(f"[RESET] Resetting prospect demo tenant ({merchant_id}) against {dsn}...")
        result = reset_prospect_tenant(merchant_id, dsn=dsn)
        printable = {k: v for k, v in result.items() if k != "operator_api_key"}
        print(json.dumps(printable, indent=2))
        print(f"[RESET] {merchant_id} operator_api_key_id={result['operator_key_id']} (raw key not printed to stdout by default)")
        if os.environ.get("SANOCEA_PRINT_DEMO_OPERATOR_KEYS") == "1":
            print(f"[RESET] {merchant_id} operator_api_key={result['operator_api_key']}")
    print("[RESET] Done.")


if __name__ == "__main__":
    main()
