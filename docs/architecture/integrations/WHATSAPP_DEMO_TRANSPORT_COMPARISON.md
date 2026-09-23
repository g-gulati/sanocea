# WhatsApp demo transport — unofficial library comparison (Sept 2026)

Research only, for the CONTROLLED, LOCAL, DEMO-ONLY approval round-trip (real dedicated throwaway
number, one prospect meeting at a time, Windows dev machine). This is explicitly NOT a production
transport evaluation — see "Demo-only boundary" at the end. GitHub is discovery evidence here, never
authority on WhatsApp's own Terms of Service.

## Candidates evaluated

| | open-wa / wa-automate | whatsapp-web.js | Baileys | WPPConnect (lib) + WPPConnect Server | **WAHA** (devlikeapro) |
|---|---|---|---|---|---|
| Maintenance/activity | Active; commits/issues through Sept 2026 | Active; issues/PRs through Sept 2026, ongoing fixes for WhatsApp Web internal changes | Active (WhiskeySockets org); docs at baileys.wiki, ongoing migrations | Active; `server-cli` v1.3.35 released Sept 13 2026, Docker images current | Active; Docker image pushed within days, frequent releases |
| Licence | Historically split free/commercial tiers for some features — verify current terms before use, not fully confirmed this pass | Permissive OSS (widely cited as Apache-2.0-family) | Open source (WhiskeySockets fork is the maintained line after original author handed it off) | Open source (Apache-2.0-family), team-maintained | **As of v2026.6.1: 100% free, no paid tier, no license checks** — was previously Core/Plus/Pro split |
| Setup complexity | Medium — Node/Puppeteer, own session store | Medium — Node/Puppeteer, `LocalAuth` session store | Low-medium — pure WebSocket, no browser, but you build your own send/receive wrapper | Medium (lib) / **Low (Server)** — Server is a ready-to-use REST API, just run it | **Low** — `docker run` one container, REST API immediately live |
| QR/session persistence | Browser-session based, generally works but re-auth after long gaps is common | **Documented reliability issue**: multiple open GitHub issues on `LocalAuth` sessions not surviving a restart without re-scanning | WebSocket auth-state persisted to disk; widely reported as more restart-stable than browser-session approaches | Server persists tokens to a volume | Persists session per-engine; supports **pairing-code auth** (enter a phone number, no QR at all) as an alternative — friendlier for a live meeting |
| Send text | Yes | Yes | Yes | Yes | Yes (single REST call) |
| Receive text/events | Yes, via event listeners | Yes, via event listeners | Yes, via event listeners | Yes, via Server's own event system | **Yes — native webhook POST to a URL you configure**, no custom event-listener code needed |
| Webhooks | Not native — you wire listeners yourself | Not native — you wire listeners yourself | Not native — raw WebSocket events only | Server exposes its own webhook config | **Native, first-class** — this is WAHA's whole design point |
| Docker/self-host | Possible, not the primary packaging | Possible, not the primary packaging | Possible, not the primary packaging | **Server: yes, Docker is the primary distribution** | **Yes, Docker is the only distribution** |
| Windows suitability | OK (Node + Chromium) | OK (Node + Chromium) | Best — no browser dependency at all | OK via Server's Docker image (needs Docker Desktop on Windows) | OK via Docker Desktop on Windows; NOWEB/GOWS engines need no browser inside the container |
| Linux/VPS suitability (later, not now) | Good | Good | Best (lightest process) | Good | Good — same Docker image ports directly to a Linux VPS later |
| Reconnect behaviour | Manual handling needed in your own code | Manual handling needed in your own code | Documented reconnect/backoff patterns, still your own code | Server handles reconnect internally | Server handles reconnect internally, exposes session-status endpoint to poll |
| Session recovery | App-level responsibility | App-level responsibility, and see the LocalAuth issue above | App-level responsibility (community patterns exist) | Server-level, built in | Server-level, built in |
| API/server layer already included | No — you build it | No — you build it | No — you build it | **Yes (Server)** | **Yes** |
| n8n compatibility | Community nodes exist, less standardized | Community node exists (`n8n-nodes-wwebjs-api`, via a separate REST wrapper) | Community node exists (`n8n-nodes-bailey`) | Community integration possible via Server's REST API | **Native, first-party**: `devlikeapro/n8n-nodes-waha`, maintained by the same author, documented n8n workflow guide |
| Chatwoot compatibility | N/A | N/A | N/A | N/A | N/A — **Chatwoot's own WhatsApp channel is built on Meta's official Cloud API / Twilio / 360Dialog, not any of these unofficial libraries at all** — confirms Chatwoot must not be the WhatsApp path here regardless of which unofficial library is chosen |
| Ban/restriction risk | Real — same underlying mechanism as whatsapp-web.js (Puppeteer against WhatsApp Web) | Real — Meta's 2026 spam detection (ML + a 48h-unanswered-message counter over a rolling 30-day window) flags exactly the pattern of "proactive message to a number that hasn't messaged first," which is precisely what sending an approval request to a prospect's number is | Real — same category of risk; unofficial-protocol implementations are explicitly named by current 2026 sources as higher-risk than the official API regardless of transport mechanism | Real — same category | Real — same category (WAHA is a wrapper over these same unofficial mechanisms, inherits the same risk) |
| Custom SANOCEA code required | Build send + a webhook-shaped adapter yourself | Build send + a webhook-shaped adapter yourself | Build send + receive + your own delivery loop | Thin — call Server's REST API, receive its webhook | **Thinnest** — one HTTP POST to send, one FastAPI route to receive its webhook, matching the exact shape SANOCEA already uses for Chatwoot's `ingest_webhook` |

## Recommendation: **WAHA** (`devlikeapro/waha`), NOWEB engine

Not chosen because it was the one mentioned by name — the case:

1. **Least custom code, by a clear margin.** Every other candidate requires SANOCEA to build its own event-listener-to-webhook bridge. WAHA already ships that bridge — `ApprovalNotificationTransport`'s `UnofficialWhatsAppDemoTransport` implementation becomes one outbound HTTP POST (`send_approval`) and one inbound FastAPI route (`receive_response`), the same shape as the already-existing `ChatwootConnector.ingest_webhook` pattern in this codebase.
2. **Native n8n node from the same maintainer**, if the demo later wants an n8n-mediated path instead of a direct HTTP integration — matches the repo's existing n8n toolset without adding a second, less-maintained community node.
3. **No browser dependency needed** if the NOWEB engine (WebSocket, Baileys-based under the hood) is selected — avoids Puppeteer/Chromium overhead and whatsapp-web.js's own documented `LocalAuth` session-restore issue, which is a real repeatable-demo risk: re-scanning a QR code minutes before a prospect meeting is exactly the kind of fragility this phase is trying to eliminate.
4. **Pairing-code auth** (phone-number entry instead of a QR scan) is a smoother one-time setup for a dedicated demo number.
5. **Fully free as of v2026.6.1** — no license-tier surprise mid-project.
6. Docker is the only distribution model, which fits this repo's existing Docker-based local tooling (n8n is already run this way) without introducing a new deployment pattern.

Baileys directly (without WAHA's wrapper) is the second choice if WAHA proves unreliable in testing — same underlying no-browser approach, marginally less to trust (one more layer removed), but requires SANOCEA to build the REST/webhook bridge itself.

## Demo-only boundary

- This is **DEMO TRANSPORT — UNOFFICIAL WHATSAPP WEB**, never described as a production SANOCEA integration in any UI copy, doc, or sales conversation.
- Must run against a **dedicated, disposable SANOCEA demo WhatsApp number** — never Manpreet's personal number, the primary SANOCEA business number, or any production support number.
- **Real ban/restriction risk exists and must be disclosed**: Meta's 2026 detection specifically flags proactive first-contact messages to non-opted-in numbers with low reply rates — which is structurally what a "send an approval to a prospect's freshly-entered number" flow looks like from Meta's side, even though the prospect consented in person. Expect the demo number to eventually get temporarily or permanently restricted; do not depend on long-term account survival, and have a replacement number ready.
- SANOCEA's `Approval` model and `ApprovalService` remain authoritative regardless of transport — WAHA (or any transport) only ever sends/receives raw messages and reports delivery metadata; it never owns approval state, expiry, or decision logic.
