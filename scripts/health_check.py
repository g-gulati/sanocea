from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request

"""Step P0.2 - bounded post-deployment health verification, called by scripts/deploy.sh after
restarting services and before declaring the deployment a PASS.

/health (apps/api/app.py) ALWAYS returns HTTP 200 with a status dict - api is unconditional; postgres,
temporal, object_storage each only appear if their own env var is configured, and each independently
reports "ok" or "error:<ExceptionType>" without ever affecting the other keys or the HTTP status code.
This script is what turns that raw dict into a deployment PASS/FAIL decision, and it draws the line the
mandate requires:

  APPLICATION HEALTH  - the API process is up and answering at all (transport-level success).
  INFRASTRUCTURE HEALTH - api == "ok" AND every infra key actually PRESENT in the response == "ok".
                          A configured-but-unreachable Postgres/Temporal/object-storage is a real
                          deployment failure; an unconfigured one is simply not checked (matches
                          production-configuration.md's OPTIONAL classification for Temporal/S3).
  CONNECTOR HEALTH   - deliberately NOT checked here. No merchant/channel credential state is queried
                       by /health today, and this script must never be extended to require one - a
                       missing Flipkart/Amazon/Meesho merchant credential must not fail a Sanocea
                       deployment (Part M).

Bounded retry: polls at a fixed interval up to a fixed deadline, then stops - never an unbounded/manual
polling loop.
"""


def poll_health(url: str, timeout_seconds: float, interval_seconds: float) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                import json

                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
            last_error = exc
            time.sleep(interval_seconds)
    raise TimeoutError(f"API did not respond within {timeout_seconds}s at {url}: {last_error}")


def evaluate(status: dict) -> tuple[bool, list[str]]:
    problems: list[str] = []
    if status.get("api") != "ok":
        problems.append(f"api={status.get('api')!r} (APPLICATION HEALTH failure)")
        return False, problems
    for key in ("postgres", "temporal", "object_storage"):
        if key in status and not str(status[key]).startswith("ok"):
            problems.append(f"{key}={status[key]!r} (INFRASTRUCTURE HEALTH failure)")
    return (len(problems) == 0), problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded post-deployment health verification.")
    parser.add_argument("--url", default="http://127.0.0.1:8010/health")
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument("--interval-seconds", type=float, default=2.0)
    args = parser.parse_args()

    try:
        status = poll_health(args.url, args.timeout_seconds, args.interval_seconds)
    except TimeoutError as exc:
        print(f"HEALTH CHECK FAILED: {exc}", file=sys.stderr)
        return 1

    print(f"raw /health response: {status}")
    healthy, problems = evaluate(status)
    if not healthy:
        print(f"HEALTH CHECK FAILED: {'; '.join(problems)}", file=sys.stderr)
        return 1
    print("HEALTH CHECK PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
