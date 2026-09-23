# Prospect-Specific Demo Tenants — Architecture

**Status:** Implemented, tested locally. Not deployed. Reference Merchant (`ref_anchal_heritage`) unchanged.

## What this is

One SANOCEA ERP, one Command Center, multiple tenant-scoped demo datasets. Manpreet can switch the
Command Center between the certified Reference Merchant and any configured prospect (Ajanta Soya, Dr.
J's HealthVitals, Carzex, The Premium Basket) so a prospect sees their own real products inside a live
demonstration of the platform, without a separate mock site per prospect.

## Why it required no new backend surface

Auditing the existing system (`apps/api/app.py`) found every merchant-scoped route already keyed on
`{merchant_id}` from the URL path, with tenant boundary enforcement already done centrally
(`packages/authn/deps.py::require_operator` - an operator API key is bound to exactly one `merchant_id`
at mint time; the dependency 403s if the URL's merchant_id doesn't match the key's). Nothing about
multi-tenancy needed to be built - the gap was entirely on the seeding/config side (one config that
existed, `ref_anchal_heritage`) and the frontend side (Command Center hardcoded `merchantId:
'ref_anchal_heritage'` as a JS constant). Both gaps were closed additively.

## Components

- `packages/prospect_demo/tenants.py` - `PROSPECT_TENANTS`, one config dict per prospect: merchant_id,
  display_name, currency, `public_products` (real, sourced, dated), `public_catalogue_sources`,
  `known_channels`, `prospect_provided_context`, `enabled_scenarios`, `policy_profile`,
  `deterministic_seed`. Adding a fifth prospect means adding an entry here - research + configuration,
  never a new Python module of business logic.
- `packages/prospect_demo/reset.py` - `reset_prospect_tenant(merchant_id)`, one generic function driving
  every entry in `PROSPECT_TENANTS`. Reuses `packages/reference_merchant/reset.py`'s own
  `_REF_TABLES_TO_CLEAR` table list (imported, not duplicated) and the same Merchant/Channel/Config/
  Inventory/operator-API-key seeding pattern already established there. Refuses to run against
  `ref_anchal_heritage` by construction.
- `packages/prospect_demo/scenarios.py` - one seeder function per `enabled_scenarios` value
  (`reconciliation`, `order_monitoring`, `returns_reconciliation`, `catalogue_operations`), each calling
  the SAME production service classes the certified Reference Merchant lifecycle uses
  (`FinanceOperationsService`, `PostOrderOperationsService`, `ExceptionService`) against the real seeded
  products - never hand-crafted rows that bypass that business logic.
- `packages/prospect_demo/registry.py` - `list_demo_tenants()`, display metadata only (id + name) for
  the Command Center's merchant switcher. Grants no access by itself.
- `scripts/reset_prospect_tenant.py` - CLI, mirrors `scripts/reset_reference_merchant.py`'s shape.
- Command Center (`apps/command_center/`) - `STATE.merchantId` is now switchable via a `<select>` in the
  header (`app.js::switchMerchant`), never a hardcoded constant. Every existing API call already read
  `STATE.merchantId` dynamically, so no per-tab rendering code needed to change - switching merchants
  re-fetches all 7 tabs' data from that tenant's own authoritative backend state.

## Data classification (Phase D discipline)

- **PUBLIC_VERIFIED** - every `public_products` entry, sourced and dated, obtained from the prospect's
  own official website/store or a real, identifiable marketplace listing. Never invented; a field
  genuinely not publicly visible is `None`, never guessed. Seeded into `ProductDraft.commercial_facts`
  with `classification="EXTERNALLY_VERIFIED"` - the existing `ProvenanceClassification` enum value
  closest in meaning to PUBLIC_VERIFIED, reused rather than adding a new member to a certified enum.
- **PROSPECT_PROVIDED** - what the prospect told Sanocea directly during outreach/discovery (channel
  mix, stated pain points). Stored in each tenant's `prospect_provided_context`, surfaced via
  `GET /merchants/{id}/profile`'s `config.demo.prospect_provided_context` - never presented as
  independently verified.
- **SYNTHETIC_DEMO** - every order, payment observation, return, refund, exception, and approval the
  scenario seeders create. Never claimed as the prospect's real operational numbers.
- **Disclosure** - `config.demo.disclosure` (`"Tailored demonstration using public catalogue information
  and simulated operational events."`) is set once per tenant in `reset.py`, read by the Command Center
  and rendered as a banner (`updateDemoDisclosureBanner()`) - never hardcoded per merchant in the
  frontend, so it cannot drift from what was actually seeded.

## What was deliberately not built this task

- No prospect-facing external session/URL (Phase I explicitly deferred this and forbade deploying public
  access). The existing per-merchant operator-key scoping already structurally supports it later: handing
  a prospect only their own merchant-scoped key would already produce the "cannot enumerate other
  merchants" property this task required, with no new session architecture needed - but no such key was
  issued or exposed to any prospect in this task.
- No publication of prospect products to the live Shopify dev store (Phase J). Prospect channels are
  seeded with `type="demo_<channel>"`, which matches no entry in `StorefrontConnectorRegistry` - no
  connector is ever instantiated for them, so publish/mutate actions are structurally unavailable, not
  merely discouraged.
- The Reference Merchant's own adversarial-ingestion/conflict-detection certification story
  (`packages/reference_merchant/generator.py`) was not generalized or reused - none of the four prospect
  scenarios (Phase E) call for it, and reusing it would have meant fabricating a "messy ingestion" event
  that never happened for these real companies.
