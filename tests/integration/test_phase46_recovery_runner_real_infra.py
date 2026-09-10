from __future__ import annotations

import os
import threading
from uuid import uuid4

import pytest

from sanocea.packages.domain_contract import PostgresStore
from sanocea.packages.domain_contract.models import Merchant
from sanocea.scripts.run_recovery_worker import run_single_pass


pytestmark = pytest.mark.skipif(not os.environ.get("SANOCEA_PG_DSN"), reason="requires real Postgres DSN in SANOCEA_PG_DSN")


def test_advisory_lock_is_a_real_cross_connection_mutex():
    """Phase 4.6 item 4: two SEPARATE connections (not just two Python objects sharing one connection)
    racing for the SAME advisory lock name - only one may hold it at a time. This is the actual
    guarantee scripts/run_recovery_worker.py's overlapping-invocation protection depends on."""
    dsn = os.environ["SANOCEA_PG_DSN"]
    lock_name = f"test-lock-{uuid4().hex[:8]}"
    store_a = PostgresStore(dsn)
    store_b = PostgresStore(dsn)

    results: dict[str, bool] = {}
    holder_ready = threading.Event()
    release_holder = threading.Event()

    def hold():
        with store_a.advisory_lock(lock_name) as acquired:
            results["holder"] = acquired
            holder_ready.set()
            release_holder.wait(timeout=10)

    t = threading.Thread(target=hold)
    t.start()
    assert holder_ready.wait(timeout=10), "holder thread never acquired the lock"

    with store_b.advisory_lock(lock_name) as second_acquired:
        results["contender"] = second_acquired

    release_holder.set()
    t.join(timeout=10)

    assert results["holder"] is True
    assert results["contender"] is False, "a second connection must not acquire an advisory lock already held by another connection"

    # After the holder releases (thread exits its `with` block), a fresh attempt must succeed.
    with store_b.advisory_lock(lock_name) as after_release:
        assert after_release is True


def test_run_single_pass_against_real_postgres_with_real_merchant():
    """run_single_pass() deliberately processes EVERY merchant in the database (store.list_all_merchants
    is a genuine cross-tenant enumeration, by design - see its docstring). This dev database accumulates
    merchants across the whole session's history, some possibly missing config a later phase now
    expects, so this test only proves the new merchant it creates is reachable and the pass does not
    raise an UNHANDLED exception (a per-merchant failure is caught and counted, not fatal - see
    run_single_pass's own try/except) - it does not assert a clean 0 exit code against unrelated
    historical state this test does not control."""
    suffix = uuid4().hex[:8]
    dsn = os.environ["SANOCEA_PG_DSN"]
    store = PostgresStore(dsn)
    store.migrate()
    merchant_id = f"rw_real_mer_{suffix}"
    store.put(Merchant(id=merchant_id, merchant_id=merchant_id, legal_name="RW Real", display_name="RW Real"))
    all_merchants = store.list_all_merchants()
    assert any(m.id == merchant_id for m in all_merchants), "list_all_merchants() must include a merchant just created"
    run_single_pass(store)  # must not raise
