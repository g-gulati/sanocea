from __future__ import annotations

import argparse
import os

from sanocea.packages.domain_contract import PostgresStore
from sanocea.packages.onboarding import MerchantOnboardingService


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--merchant-id", required=True)
    parser.add_argument("--display-name", required=True)
    args = parser.parse_args()
    dsn = os.environ["SANOCEA_PG_DSN"]
    store = PostgresStore(dsn)
    store.migrate()
    count = MerchantOnboardingService(store).onboard_phase1(args.merchant_id, args.display_name)
    print(f"configured {args.merchant_id} with approximately {count} values")


if __name__ == "__main__":
    main()

