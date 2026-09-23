"""OAuth 2.0 for the Gmail push-notification edge. Uses Google's own official client libraries
(google-auth-oauthlib, google-auth) - see docs/architecture/integrations/GMAIL_PUSH_OSS_AUDIT.md for the
GitHub/OSS audit this followed. No password or App Password is ever requested from the mailbox owner -
a one-time browser consent (InstalledAppFlow.run_local_server, a local, non-public redirect - the
Desktop-app OAuth client type Google's own docs recommend for exactly this: a native/local application
that cannot securely embed a client secret) grants a refresh token, which is the only long-lived
credential ever stored (encrypted - see state.py).
"""

from __future__ import annotations

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from .state import GmailWatchStateStore

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    # The SAME consenting principal (the mailbox owner) also pulls from the Pub/Sub subscription -
    # avoids standing up a separate service account purely to authenticate the subscriber half of one
    # local demo process. Requires the mailbox owner to hold at least "Pub/Sub Subscriber" IAM on the
    # subscription/project (a real Cloud IAM grant, not an OAuth scope alone - scope says WHAT this
    # token can ask for, IAM says whether the account is ALLOWED to).
    "https://www.googleapis.com/auth/pubsub",
]


def run_oauth_consent(oauth_client: dict, mailbox: str) -> str:
    """Opens the mailbox owner's local browser for a one-time consent. Returns the refresh token - the
    caller is responsible for persisting it (see load_or_run_oauth_flow). Never logs the token or the
    client secret."""
    client_config = {
        "installed": {
            "client_id": oauth_client["client_id"],
            "client_secret": oauth_client["client_secret"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    # login_hint steers the Google account picker toward the mailbox actually being watched - the
    # consenting human must be the mailbox owner, not whoever happens to be signed into the browser.
    creds = flow.run_local_server(port=0, login_hint=mailbox, access_type="offline", prompt="consent")
    if not creds.refresh_token:
        raise RuntimeError(
            "Google did not return a refresh token - this happens when the same client/account already "
            "has a live consent grant with no way to force a fresh one; revoke prior access at "
            "https://myaccount.google.com/permissions and retry."
        )
    return creds.refresh_token


def load_or_run_oauth_flow(state_store: GmailWatchStateStore, mailbox: str) -> Credentials:
    """Returns valid, ready-to-use Credentials. Runs the one-time browser consent ONLY if no refresh
    token is stored yet - every subsequent call (including after a SANOCEA restart) silently refreshes
    the existing token instead, exactly as the reliability requirements demand (no re-consent on
    restart)."""
    state = state_store.load()
    if state is None or state.oauth_client is None:
        raise RuntimeError("no OAuth client registered - call state_store.save_oauth_client() first")
    if state.refresh_token is None:
        refresh_token = run_oauth_consent(state.oauth_client, mailbox)
        state_store.save_refresh_token(refresh_token)
    else:
        refresh_token = state.refresh_token
    creds = Credentials(
        token=None, refresh_token=refresh_token, token_uri="https://oauth2.googleapis.com/token",
        client_id=state.oauth_client["client_id"], client_secret=state.oauth_client["client_secret"],
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return creds
