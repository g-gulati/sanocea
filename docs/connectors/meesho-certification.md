# Meesho connector — certification status

**Overall state: SIMULATED EXTERNAL PLATFORM + REAL LOCAL INFRASTRUCTURE, and thinner than that for
every business capability — this connector implements AUTH ONLY.** No real Meesho credentials, sandbox,
or supplier account have been used at any point in this step. Do not describe this connector as
certified, live, or feature-complete.

## Access blocker classification

**Not** an access blocker — direct, per-supplier credential issuance from Meesho itself is evidenced
and available to Sanocea (email-based, no formal partner-approval process found). **Is** a
**DOCUMENTATION blocker**: no Meesho-owned primary source describing any business-operation
request/response schema was reachable during this step's research (see `docs/connectors/meesho.md` for
every source attempted and why each failed). This is a narrower, more specific finding than "Meesho is
unreachable" — Sanocea can very likely obtain real credentials by emailing Meesho directly; what
Sanocea cannot currently do is implement schema-accurate business logic against material that has never
been publicly documented.

## Capability-by-capability breakdown

| Capability | Capability status | Verification level | Notes |
|---|---|---|---|
| `auth` | SUPPORTED | IMPLEMENTED (not TESTED_SIMULATED against a real endpoint — there is no confirmed endpoint to test against; tested only for header-construction correctness, credential isolation, and the documented no-op `invalidate()` behavior) | Level 5 evidence (two independent integrators agree on header names/base URLs). The `security` header's derivation is genuinely unknown and not guessed at. |
| `catalogue_read`/`catalogue_write` | UNCONFIRMED | — | "Catalog sync is available" (Unicommerce) is a capability claim, not a contract. No endpoint path or field name found anywhere. |
| `inventory_read`/`inventory_write` | UNCONFIRMED | — | Facility-wise inventory sync is mentioned (Unicommerce); no schema. |
| `order_ingest` | UNCONFIRMED | — | Real and non-optional per Unicommerce ("Manual Order Sync would not work for now" — implying the API path is mandatory, not portal-only) — but no order object schema, endpoint, or pagination contract found. |
| `order_confirmation` | UNCONFIRMED | — | EasyEcom's KB names this as a feature; ambiguous whether it's a real API call or EasyEcom automating Meesho's own portal on the seller's behalf — "another OMS having access != Sanocea being eligible for that access" applies directly. |
| `fulfilment_update` | UNCONFIRMED | — | Confirmed FACT (not schema): Meesho generates shipping labels itself; the integrator only fetches the Meesho-generated label. No fetch endpoint/schema. |
| `cancellation` | UNCONFIRMED | — | Confirmed FACT: seller-initiated cancellation is possible only *before* order confirmation, and becomes fully disabled after API integration is turned on (EasyEcom KB, specific and disclosed) — but no request schema. |
| `return_refund` | UNCONFIRMED | — | Returns/RTO sync exists as status-visibility only (Unicommerce); no seller-initiated return or refund action documented anywhere — Meesho likely owns the financial action outright, consistent with quick-commerce-vendor findings elsewhere in this codebase, but not independently confirmed for Meesho. |
| `settlement_ingest` | UNCONFIRMED | — | **Strongest possible negative finding**: no settlement/payment API, report, or downloadable file was found in ANY source reached this step — absence across every source checked, not merely "not searched." |
| `order_notifications` | UNCONFIRMED | — | One secondhand mention of "order status updates via webhook" with zero registration/payload/signature detail — insufficient to implement anything against. |
| `fetch`/`search` | UNCONFIRMED | — | Gate every read; both refuse before reaching any entity-type branching (`test_fetch_and_search_refuse_before_touching_any_entity_type`). |

## Rate limits / idempotency / retry / readback

**No evidence found for any of these** — not documented by any source reached. This connector inherits
`MarketplaceConnector`'s generic 429/5xx retry handling structurally (unused today, since no mutation
is implemented to exercise it), but no Meesho-specific rate-limit numbers or idempotency-key convention
were ever found to configure it against.

## Finance/settlement behavior

Not implemented — no evidence of any settlement source (API, report, or file) exists. This is a
disclosed gap, not a silent omission: Sanocea's existing `SettlementBatch`/`SettlementEntry`/
`FinanceReconciliation` models remain the correct target once real evidence exists (per Part H's
instruction to map into existing Phase 3 structures, never a parallel subsystem) — there is simply
nothing to map yet.

## Known gaps

- Every business operation beyond auth — see the matrix above.
- The `security` header's exact derivation.
- Whether "order confirmation"/"cancellation"/"label generation" described by EasyEcom's KB are real
  API operations or portal automation performed on the seller's behalf.
- Whether a webhook mechanism genuinely exists, and if so its registration/payload/signature contract.

## What would need to happen for REAL_ACCOUNT_CERTIFIED (or even TESTED_SIMULATED beyond auth)

1. A real onboarded Meesho supplier relationship (see `docs/connectors/meesho.md`'s access section and
   Part M's exact next steps) — email Meesho, receive real `client-id`/`secret-key`/`supplier_identifier`.
2. **Obtain Meesho's actual technical documentation directly from Meesho during that onboarding** — this
   is the real prerequisite blocking any further implementation, not merely credentials.
3. Confirm the `security` header derivation.
4. Only then implement catalogue/order/fulfilment/returns/settlement against real, Meesho-confirmed
   schemas — never secondhand vendor-integration summaries.

Until step 2 above happens, this connector should not be expanded beyond auth, per "do not fabricate a
contract to make the connector appear complete."
