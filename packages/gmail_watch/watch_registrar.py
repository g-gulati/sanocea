"""Registers and renews the Gmail watch() subscription. Google documents watch() as expiring after at
most 7 days regardless of activity (https://developers.google.com/gmail/api/guides/push) - if nothing
renews it, push notifications silently stop with no error surfaced anywhere else in this system, which
is exactly the kind of silent loss this whole replacement was built to eliminate. Deliberately a small,
dedicated mechanism (a background thread with a daily check) rather than another workflow engine - see
the user's explicit 'do not introduce another workflow engine' instruction.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from .gmail_client import register_watch
from .state import GmailWatchStateStore

logger = logging.getLogger("sanocea.gmail_watch")

RENEWAL_MARGIN = timedelta(days=1)  # renew a full day before the 7-day expiry, never cutting it close
CHECK_INTERVAL_SECONDS = 3600  # hourly check is cheap; renewal itself only actually fires ~once/6 days


class WatchRegistrar:
    def __init__(self, service, state_store: GmailWatchStateStore, topic_name: str) -> None:
        self.service = service
        self.state_store = state_store
        self.topic_name = topic_name
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def register_now(self) -> str:
        """Registers (or re-registers) the watch immediately and persists the fresh checkpoint. Returns
        the historyId to start listening from - the caller must NOT reuse an old historyId across a
        watch re-registration, since Gmail resets its own retention window on each watch() call."""
        result = register_watch(self.service, self.topic_name)
        history_id = result["historyId"]
        expiration_ms = int(result["expiration"])
        expiration = datetime.fromtimestamp(expiration_ms / 1000, tz=timezone.utc)
        self.state_store.save_history_checkpoint(history_id, watch_expiration=expiration)
        logger.info("gmail watch registered, expires %s, historyId=%s", expiration.isoformat(), history_id)
        return history_id

    def start_renewal_loop(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True, name="gmail-watch-renewal")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                state = self.state_store.load()
                if state and state.watch_expiration:
                    if datetime.now(timezone.utc) >= state.watch_expiration - RENEWAL_MARGIN:
                        logger.info("gmail watch approaching expiry (%s) - renewing", state.watch_expiration.isoformat())
                        self.register_now()
            except Exception:  # noqa: BLE001 - a renewal-loop crash must never take down the subscriber
                logger.exception("gmail watch renewal check failed - will retry on next interval")
            self._stop.wait(CHECK_INTERVAL_SECONDS)
