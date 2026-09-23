from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from uuid import uuid4

from sanocea.packages.audit.context import reset_correlation_id, set_correlation_id
from sanocea.packages.domain_contract.postgres_store import PostgresStore
from sanocea.packages.domain_contract.store import Phase0Store
from sanocea.packages.runtime import build_service_graph
from sanocea.workers.reconciliation_worker import RecoveryCounters, ReconciliationWorker

"""Phase 4.6 item 4: a production-shaped, portable runner for ReconciliationWorker.run_once() -
suitable for a systemd service (long-running loop), a systemd timer or cron entry (--once), or a
container process (either mode). Deliberately NOT deployed by this phase - see docs/architecture/
phase4.6-commerce-core-completion.md for the deployment steps this leaves to Phase 5+/ops.

Portability: no Windows Task Scheduler, no PowerShell - pure stdlib (argparse/logging/signal/time),
identical on Linux and this Windows dev host. Locking: a single Postgres advisory lock
(store.advisory_lock, non-blocking) held for the duration of one pass over all merchants, so two
overlapping invocations of this runner (a systemd timer firing again before the previous run finished,
a stray cron entry beside a running systemd service, two container replicas both scheduled) can never
process the same work concurrently - the second one logs and exits/skips rather than racing the first.
Graceful shutdown: SIGTERM/SIGINT sets a flag checked between merchants and between loop iterations;
in-flight per-merchant work always finishes before exit. Bounded execution: --once gives a single,
naturally-bounded pass (the cron/timer-friendly shape); --max-iterations bounds the loop mode for
supervised/restart-based deployment patterns instead of a truly eternal process.
"""

LOCK_NAME = "sanocea_reconciliation_worker"


def _build_store():
    if os.environ.get("SANOCEA_USE_IN_MEMORY_STORE") == "1":
        return Phase0Store()
    dsn = os.environ.get("SANOCEA_PG_DSN")
    if not dsn:
        raise RuntimeError("SANOCEA_PG_DSN is required (or set SANOCEA_USE_IN_MEMORY_STORE=1 for local/test runs)")
    store = PostgresStore(dsn)
    store.migrate()
    return store


def run_single_pass(store, *, max_attempts: int = 5) -> int:
    """Runs ReconciliationWorker.run_once() for every merchant, inside the advisory lock. Returns a
    process-exit-code-shaped int: 0 on success (including "no merchants" / "lock held elsewhere" - both
    are normal, not failures), 1 if any merchant's pass raised."""
    correlation_id = f"recovery-pass-{uuid4().hex}"
    token = set_correlation_id(correlation_id)
    try:
        with store.advisory_lock(LOCK_NAME) as acquired:
            if not acquired:
                logging.warning("recovery_worker: another instance holds the lock (%s) - skipping this pass", LOCK_NAME)
                return 0
            merchants = store.list_all_merchants()
            if not merchants:
                logging.info("recovery_worker: no merchants to process")
                return 0
            failures = 0
            totals = RecoveryCounters()
            for merchant in merchants:
                try:
                    graph = build_service_graph(store)
                    worker = ReconciliationWorker(store, graph.services, supplier_connector=graph.suppliers, payment_connector=graph.payments, max_attempts=max_attempts)
                    counters = worker.run_once(merchant.id)
                    logging.info("recovery_worker: merchant=%s counters=%s", merchant.id, counters.as_dict())
                    for field_name in totals.__dataclass_fields__:
                        setattr(totals, field_name, getattr(totals, field_name) + getattr(counters, field_name))
                except Exception:
                    failures += 1
                    logging.exception("recovery_worker: pass failed for merchant=%s", merchant.id)
            logging.info("recovery_worker: pass complete merchants=%d failures=%d totals=%s", len(merchants), failures, totals.as_dict())
            return 1 if failures else 0
    finally:
        reset_correlation_id(token)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sanocea reconciliation/recovery worker runner (Phase 4.6)")
    parser.add_argument("--once", action="store_true", help="run a single pass over all merchants then exit (cron/timer-friendly)")
    parser.add_argument("--interval-seconds", type=int, default=300, help="seconds to wait between passes in loop mode (default 300)")
    parser.add_argument("--max-iterations", type=int, default=None, help="bound the number of passes in loop mode, then exit cleanly (default: unbounded)")
    parser.add_argument("--max-attempts", type=int, default=5, help="ReconciliationWorker's own bounded-retry ceiling per exception (default 5)")
    parser.add_argument("--log-level", default=os.environ.get("SANOCEA_LOG_LEVEL", "INFO"))
    args = parser.parse_args(argv)

    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)

    stop = {"flag": False}

    def _handle_signal(signum, _frame) -> None:
        logging.info("recovery_worker: received signal %s - will exit gracefully after the current pass", signum)
        stop["flag"] = True

    try:
        import signal

        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT, _handle_signal)
    except (ImportError, ValueError):
        # ValueError: signal handlers can only be set in the main thread - acceptable to skip when
        # embedded (e.g. imported into a test), not when run as the actual process entrypoint.
        pass

    store = _build_store()

    if args.once:
        return run_single_pass(store, max_attempts=args.max_attempts)

    iterations = 0
    exit_code = 0
    while not stop["flag"]:
        exit_code = run_single_pass(store, max_attempts=args.max_attempts)
        iterations += 1
        if args.max_iterations is not None and iterations >= args.max_iterations:
            logging.info("recovery_worker: reached --max-iterations=%d - exiting", args.max_iterations)
            break
        for _ in range(args.interval_seconds):
            if stop["flag"]:
                break
            time.sleep(1)
    logging.info("recovery_worker: shutdown complete after %d iteration(s)", iterations)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
