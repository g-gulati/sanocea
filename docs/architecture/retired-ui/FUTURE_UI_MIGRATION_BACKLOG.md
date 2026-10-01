# Future UI migration backlog (capabilities that exist only as backend/API since the UI retirement)

Retired on 2026-10-01: the API-served `/ui` Command Centre (`apps/command_center/`) and the `/console.html` Operations
Console (`website/src/demo/`). `/demo.html` is the sole canonical SANOCEA UI (CLAUDE.md, "Canonical UI rule").

The backend endpoints behind these views were NOT removed. Nothing here is being migrated yet; this is a backlog, not a
commitment. Any item is built by extending `/demo.html` (`website/src/whatsapp-demo/`), never as a new surface.

| Capability (old UI) | Backend that remains | Notes |
|---|---|---|
| Operations overview: operator summary, management outcome, automation-impact benchmarks | `GET /merchants/{id}/operator/summary` | Dashboard shows static demo data today |
| Exceptions list with linked approvals | `GET /merchants/{id}/exceptions`, `/approvals` | |
| Conflict review: approve facts, resolve, publish draft, re-verify | `/merchants/{id}/catalogue/drafts/*`, `/catalogue/publications/*` | Only UI for catalogue drafts |
| Publication and channel operations | `/merchants/{id}/channel-operations`, `/catalogue/publications` | |
| Orders and multi-location inventory | `/merchants/{id}/orders`, `/inventory` | |
| Returns and refunds | `/merchants/{id}/returns`, `/refunds` | |
| Audit trail viewer | `GET /merchants/{id}/audit` | |
| Approve / reject an approval; send an approval to WhatsApp; attach a demo WhatsApp contact; live demo chat | `POST /merchants/{id}/approvals/{id}/resolve`, `/approvals/{id}/send-whatsapp`, `/demo/attach-whatsapp`, `/chat` | CORRECTION (2026-10-01): the current `/demo.html` WhatsApp Ops tab is a static simulation (no API calls). The real-API walkthrough that did this lives only in orphaned sources (see below) |
| Demo reset; ingest demo CSV | `POST /merchants/{id}/demo-reset`, `/demo/ingest-csv`, `scripts/reset_prospect_tenant.py` | Ops script path remains |
| Live email-ingress activity polling | email-ingress endpoints | |
| Read-only console views (orders, inventory, exceptions, approvals, reconciliation, channel operations) | same endpoints | Was `/console.html` |

Preserved sources: `command_center_app.js.working-copy-2026-10-01.js` and its uncommitted-changes patch (readable
location and channel labels, out-of-stock status, linked governance on exceptions, a longer order-flow approval list),
`console_main.jsx.working-copy-2026-10-01.jsx`, `console_demo.css.working-copy-2026-10-01.css` and
`console.html.copy-2026-10-01`. The committed `/ui` source remains in git history (before the retirement commit).

## Orphaned sources (not part of the current /demo.html import graph)

Found while inventorying the demo source on 2026-10-01. They are not needed to reproduce `/demo.html` and were NOT
committed or deleted as part of the retirement. They hold the earlier real-API WhatsApp/approval walkthrough flow:

- Tracked: `website/src/whatsapp-demo/Walkthrough.jsx` (modified), `chat.css` (modified), `walkthrough.css`
- Untracked: `DemoIntro.jsx`, `AjantaIntro.jsx`, `GoldenBirdIntro.jsx`, `ajantaScenario.js`, `goldenBirdScenario.js`,
  `demointro.css`, and `website/src/demo-control/` (its header comment points at the retired `/console.html`)

Decide separately whether to revive, migrate or delete them.
