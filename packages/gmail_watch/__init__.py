"""Gmail API push-notification email edge - replaces the n8n/IMAP trigger for the same job (detect a
new email, hand its real attachment bytes to SANOCEA's already-certified /demo/email-ingest). See
state.py's module docstring for why this is mailbox-scoped, not merchant-scoped, and gmail_watch_state's
own docstring in the migration for the storage rationale.

SANOCEA remains authoritative for everything downstream of "here are the real bytes": routing, sender
validation, attachment validation, idempotency, canonical data, channel operations, approvals,
execution, readback, audit. This package's only job is detecting a new message reliably and retrieving
its real content - it deliberately contains zero business logic.
"""

from .oauth import load_or_run_oauth_flow
from .state import GmailWatchState, GmailWatchStateStore
from .subscriber import GmailPushSubscriber
from .watch_registrar import WatchRegistrar

__all__ = [
    "GmailPushSubscriber",
    "GmailWatchState",
    "GmailWatchStateStore",
    "WatchRegistrar",
    "load_or_run_oauth_flow",
]
