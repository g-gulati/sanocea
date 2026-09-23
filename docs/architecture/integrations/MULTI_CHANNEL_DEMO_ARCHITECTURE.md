# Multi-channel live demo #2 — architecture note

Sept 2026. Covers Flow A (Email → Channel Operations) only — increments A–D of the certification
order in the spec. Flow B (Channel Assurance) and the WhatsApp/email approval transport are not yet
built; see the end of this note for exact status.

## Why the five channels are NOT five identical simulators

Each channel's controlled-demo model is shaped by what was actually found in two prior, dedicated
research passes (`docs/architecture/channel-research/quick-commerce-india-direct-access.md` and the
Ajanta multi-channel operations audit), never invented for this build:

- **Own Website (WooCommerce)** — real, contract-built connector
  (`connectors/woocommerce/connector.py`). Controlled demo = the SAME connector class, subclassed only
  to override its one HTTP seam (`_request_with_headers`) with deterministic canned responses — every
  other line (payload building, capability declarations, response normalization) is the real,
  credentialed-path code. This channel deliberately carries the demo's one **owner-approval** case: a
  brand-new SKU with no prior public price history is not auto-published straight to the storefront the
  public sees immediately.
- **Amazon India** — real SP-API connector, same subclass-and-override pattern. Preserves Amazon's real
  async contract exactly: `put_listing` always returns `MutationResult(status="accepted")` (the HTTP
  request was accepted, never "the mutation applied") — whether the listing was actually accepted or
  rejected only shows up in the embedded `issues[]`, which `ChannelOperationService` inspects itself,
  matching how a real caller of this connector already has to behave (see
  `docs/connectors/amazon-certification.md`'s "async operations" section). This channel carries the
  demo's **strongest auto-resolution case**: a submission missing `country_of_origin` is rejected,
  investigated, and resubmitted with a value inferred from the merchant's own registered profile
  (GSTIN if present, else its registered INR operating currency) — never a guess.
- **Flipkart** — real Seller API connector, same pattern. Deliberately the "nothing dramatic happens"
  channel — clean submit, clean readback, VERIFIED — since Flipkart's own contract-tested field shapes
  are the least uncertain of the three real connectors and nothing about this demo needed to manufacture
  drama here.
- **JioMart** — **no connector class exists**, by design, matching the audit's explicit finding that no
  confirmed JioMart seller-API contract exists anywhere. Its `ChannelOperation` is driven entirely
  inside `ChannelOperationService._run_jiomart` with no connector object at all — a generic internal
  submission/response pair, always stamped `SYNTHETIC_DEMO`. Its auto-resolution case (a small listed-
  price delta) is evaluated through the real `PolicyEngine`'s new `channel_price_correction` action
  (a genuine, general threshold-based decision, mirroring the existing `refund` policy pattern — not
  demo-only logic), not a hardcoded if/else.
- **Blinkit** — **no connector class**, and deliberately **not shaped like a listing submission at
  all**. The channel-research audit found Blinkit to be a vendor-PO/dark-store relationship with no
  confirmed self-serve write API. Its `ChannelOperation` is modeled as vendor-catalogue onboarding
  (declaring a case-pack/supply unit for future PO sizing), not "publish a listing" — the one channel
  whose demo lifecycle looks structurally different from the other four on purpose.

## Why `ProductPublicationService` isn't reused

`ProductPublicationService.publish()` hardcodes `action="publish_product"`. Amazon's real, Level-1-
confirmed capability name is `put_listing`/`patch_listing`, not `publish_product` — reusing that service
unchanged would silently fail for Amazon. Extending it to be action-name-aware per connector would touch
code the certified Shopify path also depends on, which this build must never modify. Instead,
`ChannelOperationService` drives each connector's real `execute_mutation()`/`fetch()` directly with the
correct action name — same `MutationRequest`/`MutationResult` contract, same audit+idempotency wrapper,
same connector classes; only the one method that happens to be Amazon-incompatible is bypassed.
`Publication`/`PublicationAttempt`/`ListingVerification` remain exclusively the real Shopify-certification
path's model, completely untouched by this build.

## Demo truth boundary

Every `ChannelOperation` this build creates is stamped `demo_provenance = "SYNTHETIC_DEMO"`. No real
Amazon/Flipkart/WooCommerce/JioMart/Blinkit credential is read, stored, or required anywhere in
`packages/channel_ops/demo_connectors.py` — the controlled-demo connector subclasses never open a real
socket. The Command Center's existing prospect-demo disclosure banner remains unchanged and continues to
cover this. What IS real: the ERP workflow, the policy engine's authority decision, the approval object
and its idempotent resolution, the audit trail, and the Command Center's live rendering of all of it.

## Status (certification order A–H)

- **A — Email → Channel Operations: built, verified** (direct backend test + real HTTP + real browser,
  zero console errors). Clean records continue automatically, no manual trigger.
- **B — Per-channel lifecycle UI: built, verified.** Publication & Channel Operations tab: executive
  grid (per-channel Verified/Resolving/Attention counts, all backend-sourced) + click-through per-product
  lifecycle drilldown.
- **C — Routine auto-resolution: built, verified.** Amazon (missing attribute), JioMart (price
  rounding), Blinkit (case-pack quantity) all auto-resolve via the real `PolicyEngine`, no owner asked.
- **D — Owner approval pause/resume: built, verified.** Own Website's new-SKU-no-price-history case
  pauses with full evidence/recommendation/alternative, resolves via `POST .../approvals/{id}/resolve`
  (idempotent — a second resolve returns `already_resolved: True`), resumes the paused
  `ChannelOperation`, executes the real connector call, verifies, and the Command Center reflects it
  without a page reload.
- **E/F — WhatsApp transport / real phone round-trip: not built.** Requires a real external Meta
  WhatsApp Business Cloud API setup — see the OSS/architecture audit
  (`docs/architecture/integrations/LIVE_DEMO_OPEN_SOURCE_AUDIT.md`) for the exact external
  account/number/webhook requirements this needs from Manpreet before it can be built and certified.
- **G — Channel Assurance (Flow B): not built.**
- **H — Full end-to-end sales certification: not attempted** (depends on E/F/G).
