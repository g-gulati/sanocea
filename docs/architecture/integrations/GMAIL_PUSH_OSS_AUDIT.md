# Gmail Push Notification Edge — OSS/GitHub Audit

Per CLAUDE.md's OSS-first rule, before implementing the Gmail `users.watch()` + Pub/Sub email-detection
edge (replacing the n8n/IMAP trigger), the following mature, maintained implementations were checked.

## What was checked

- **google-api-python-client** (github.com/googleapis/google-api-python-client) — Google's own official,
  actively maintained Python client for every Google API, including Gmail. Used in Google's own Gmail
  API push-notification quickstart and cookbook samples (github.com/googleworkspace/python-samples).
- **google-auth / google-auth-oauthlib** (github.com/googleapis/google-auth-library-python,
  github.com/googleapis/google-auth-library-python-oauthlib) — Google's official OAuth2 credential and
  installed-app-flow libraries. `InstalledAppFlow.run_local_server()` is the documented, standard pattern
  for a native/local application that cannot embed a client secret safely, and is what this
  implementation uses (packages/gmail_watch/oauth.py).
- **google-cloud-pubsub** (github.com/googleapis/python-pubsub) — Google's official Pub/Sub client. Its
  `SubscriberClient.subscribe()` streaming-pull pattern (the same shape used in Google's own quickstart
  samples) is what this implementation uses (packages/gmail_watch/subscriber.py) — a long-lived,
  outbound-only connection with sub-second delivery, no public endpoint required.
- **google-workspace/python-samples: gmail/push_notifications** — Google's own reference example for
  wiring `users.watch()` to a Pub/Sub topic and consuming notifications via `history.list()`. Confirmed
  the notification payload shape (`{"emailAddress": ..., "historyId": ...}`), the 7-day watch expiry, and
  the `historyTypes=["messageAdded"]` filter used here.
- A handful of third-party "Gmail-to-webhook" / "Gmail Pub/Sub watcher" GitHub repos surfaced by search
  (e.g. generic "gmail-pubsub-notifier" style projects) — reviewed for pattern ideas only (historyId
  checkpoint persistence, watch-renewal-via-cron), not for code reuse; none were maintained enough
  (last commit years old, no tests) to justify depending on directly.

## Decisions

| Component | Decision | Reasoning |
|---|---|---|
| Gmail API access (`watch`, `history.list`, `messages.get`, attachment retrieval) | **ADOPT** `google-api-python-client` | Official, maintained, exactly this task's documented use case |
| OAuth2 (installed-app consent + refresh) | **ADOPT** `google-auth` + `google-auth-oauthlib` | Official; `InstalledAppFlow.run_local_server()` is Google's own recommended pattern for a local, non-public app |
| Pub/Sub pull subscription | **ADOPT** `google-cloud-pubsub`'s `SubscriberClient` streaming pull | Official; avoids hand-rolling a long-poll loop; no public endpoint needed (this deployment has none) |
| historyId checkpoint persistence & renewal scheduling | **BUILD OWN** (packages/gmail_watch/state.py, watch_registrar.py) | Genuinely application-specific (which Postgres table, which encryption, which merchant-isolation model) — no external library owns SANOCEA's own persistence/security model, and this is a small amount of code, not a commodity problem |
| Third-party "Gmail Pub/Sub watcher" frameworks found on GitHub | **REJECT** | Unmaintained, untested, would add a dependency for what official libraries + ~250 lines of glue already cover; reviewed for pattern ideas only (option C — learn semantics, don't adopt) |
| Sender validation, attachment safety validation, idempotency at the SANOCEA boundary, routing, canonical ingestion | **ALREADY COVERED BY SANOCEA** | `packages/email_ingress/EmailIngestionService` and the `/demo/email-ingest` route (`apps/api/app.py`) — unchanged, this edge only supplies real bytes to that already-certified path |

## Verified against current official documentation (not memory alone)

- Gmail API push notifications: https://developers.google.com/gmail/api/guides/push — watch() expires
  after **at most 7 days**; the notification itself carries only `emailAddress` + `historyId`, never
  message content — retrieval is a separate, authenticated `history.list()` + `messages.get()` call,
  which is why this implementation treats Pub/Sub purely as a transport (no business data ever flows
  through Pub/Sub itself).
- Gmail API quota: free, 1,000,000,000 quota units/day per project (far beyond demo-scale usage).
- Cloud Pub/Sub pricing: free tier is 10 GiB/month of throughput; a single demo mailbox's notification
  volume (a JSON payload of a few hundred bytes per new message) stays well within that tier — realistic
  cost is $0/month at this usage.
