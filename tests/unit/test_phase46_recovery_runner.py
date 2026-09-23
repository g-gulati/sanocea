from __future__ import annotations

from sanocea.packages.domain_contract.models import Merchant
from sanocea.scripts.run_recovery_worker import main, run_single_pass


def test_advisory_lock_prevents_overlapping_holders(phase0):
    store, *_ = phase0
    with store.advisory_lock("test-lock") as first:
        assert first is True
        with store.advisory_lock("test-lock") as second:
            assert second is False, "a second concurrent holder of the SAME lock name must not acquire it"
    with store.advisory_lock("test-lock") as third:
        assert third is True, "the lock must be released after the first holder's `with` block exits"


def test_advisory_lock_different_names_are_independent(phase0):
    store, *_ = phase0
    with store.advisory_lock("lock-a") as a:
        with store.advisory_lock("lock-b") as b:
            assert a is True and b is True


def test_run_single_pass_with_no_merchants_is_a_noop_success(phase0):
    store, *_ = phase0
    assert run_single_pass(store) == 0


def test_run_single_pass_processes_every_merchant_without_error(phase0):
    store, *_ = phase0
    store.put(Merchant(id="rw_mer_1", merchant_id="rw_mer_1", legal_name="RW1", display_name="RW1"))
    store.put(Merchant(id="rw_mer_2", merchant_id="rw_mer_2", legal_name="RW2", display_name="RW2"))
    assert run_single_pass(store) == 0


def test_run_single_pass_skips_when_lock_already_held(phase0):
    store, *_ = phase0
    store.put(Merchant(id="rw_mer_locked", merchant_id="rw_mer_locked", legal_name="RW", display_name="RW"))
    with store.advisory_lock("sanocea_reconciliation_worker") as acquired:
        assert acquired is True
        # A second pass attempted while the lock is held must skip (return 0), not block or raise.
        assert run_single_pass(store) == 0


def test_main_once_mode_exits_cleanly(monkeypatch, phase0):
    store, *_ = phase0
    store.put(Merchant(id="rw_mer_cli", merchant_id="rw_mer_cli", legal_name="RW", display_name="RW"))
    monkeypatch.setenv("SANOCEA_USE_IN_MEMORY_STORE", "1")
    # main() builds its own store from env, not the fixture's - this test only proves the CLI plumbing
    # (argument parsing, --once short-circuit, clean exit code) works, not cross-instance state.
    assert main(["--once"]) == 0
