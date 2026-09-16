#!/usr/bin/env python3
"""SANOCEA Reference Merchant Deterministic Reset CLI.
Resets the 'ref_anchal_heritage' reference merchant tenant to its canonical baseline,
cleans existing records, seeds configuration, warehouse locations, initial inventory,
encrypted Shopify dev store credentials, and generates the messy merchant fixture pack.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Add workspace and parent directory to sys.path for robust module resolution
ROOT_DIR = Path(__file__).resolve().parent.parent
PARENT_DIR = ROOT_DIR.parent
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sanocea.packages.reference_merchant import reset_reference_merchant


def main() -> None:
    dsn = os.environ.get("SANOCEA_PG_DSN", "postgresql://sanocea:sanocea@127.0.0.1:55432/sanocea_phase05")
    fixtures_dir = ROOT_DIR / "tests" / "fixtures" / "reference_merchant"

    print(f"[RESET] Resetting Reference Merchant tenant (ref_anchal_heritage) against {dsn}...")
    result = reset_reference_merchant(dsn=dsn, fixtures_dir=fixtures_dir)
    print(json.dumps(result, indent=2))
    print("[RESET] Reference Merchant is now in canonical baseline demonstration state.")


if __name__ == "__main__":
    main()
