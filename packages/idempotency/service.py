from __future__ import annotations

from collections.abc import Callable
import time
from typing import TypeVar

from sanocea.packages.domain_contract.store import Phase0Store


T = TypeVar("T")


class IdempotencyService:
    def __init__(self, store: Phase0Store) -> None:
        self.store = store

    def run_once(self, scope: str, key: str, operation: Callable[[], T]) -> tuple[T, bool]:
        if not self.store.reserve_idempotency(scope, key):
            for _ in range(100):
                result = self.store.get_idempotency_result(scope, key)
                if result is not None:
                    return result, False
                time.sleep(0.05)
            return self.store.get_idempotency_result(scope, key), False
        try:
            result = operation()
        except BaseException:
            # Release the reservation so a genuine retry can actually re-attempt the operation, instead
            # of every future call polling for a completed result that will never arrive because this
            # attempt never reached complete_idempotency(). Without this, an operation that raises mid-
            # mutation permanently wedges this idempotency key.
            self.store.release_idempotency(scope, key)
            raise
        self.store.complete_idempotency(scope, key, result)
        return result, True
