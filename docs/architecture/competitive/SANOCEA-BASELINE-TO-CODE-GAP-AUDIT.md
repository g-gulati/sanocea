# Sanocea Baseline-to-Code Gap Audit

**Read-only.** No production code, test, or script was modified to produce this document. Every claim
below is traceable to a real file, class, function, or test opened and read this session — not to a
docstring, README, or phase-completion summary taken at its word. Where a prior document's claim could
not be independently verified against real code, that is stated explicitly rather than assumed true.

This audit answers one question: **against the product Sanocea has decided (via
[`SANOCEA-PRODUCT-BASELINE-V1.md`](./SANOCEA-PRODUCT-BASELINE-V1.md)) it should become, what actually
exists in the repository today?** It is organized around that baseline's current requirements, not
around historical Phase 0-4.6 narrative — phase docs and scripts are cited as *evidence*, never as the
organizing structure, and never taken at face value without independent verification.

## 0. Classification legend

Every capability below receives exactly one primary state, chosen conservatively. **Evidence is never
upgraded**: a simulator is not a real platform; a model field existing is not an operational capability;
a connector interface existing is not a working connector; an API route existing is not proof a workflow
works end-to-end; a test fixture is not external truth; a dashboard counter is not the underlying
capability.

| Code | Meaning |
|---|---|
| **A** | IMPLEMENTED + PROVEN ON REAL EXTERNAL PLATFORM |
| **B** | IMPLEMENTED + PROVEN AGAINST REAL LOCAL INFRASTRUCTURE |
| **C** | IMPLEMENTED + PROVEN AGAINST STATEFUL EXTERNAL SIMULATOR |
| **D** | IMPLEMENTED BUT ONLY UNIT/INTEGRATION TEST PROVEN |
| **E** | PARTIAL IMPLEMENTATION |
| **F** | ARCHITECTURAL / INTERFACE / SCAFFOLD ONLY |
| **G** | MISSING |
| **H** | DELIBERATELY OUT OF SCOPE / DO NOT BUILD |
| **I** | CANNOT VERIFY |

---

## 3. Architectural foundations

| Requirement | Actual files/classes/functions | Tests found | Proof level | Class | Gap |
|---|---|---|---|---|---|
| Canonical domain model | `packages/domain_contract/models.py` (693 lines, 50+ `CanonicalEntity` subclasses spanning `Merchant`→`Order`→`Refund`→`Supplier`→`SupportConversation`) | Exercised across every unit/integration/e2e test in `tests/` | Real, in-use across every package audited this session | **B** | None — genuinely wide cross-domain scope, matching the baseline's own claim. |
| Merchant/tenant isolation | `CanonicalEntity.merchant_id` on every entity; `require_operator` in `packages/authn/deps.py:32-43` cross-checks the URL's `merchant_id` against the authenticated key's bound `merchant_id` before allowing any request | `scripts/run_multi_platform_isolation_proof.py` — a dedicated real-platform cross-tenant isolation script (Shopify merchant A + WooCommerce merchant B), asserting a WooCommerce-shaped webhook at merchant A's URL is refused with 404/`ChannelMismatchError` (line 217, 221) and that merchant A's canonical order carries only `shopify` external refs, never `woocommerce` (line 233) | **A** for the specific isolation checks this script exercises (real Shopify + real WooCommerce, per Section 18) | **A** | None found this pass. |
| External-ID mapping | `ExternalIdMapping` model (`models.py:547-557`); resolved via `store.get_external_mapping` (referenced in `post_order/operations.py:305`) and `external_id_mappings` (referenced in `SettlementEntry`'s own field comments, `models.py:249-259`) | Not independently deep-dived this pass beyond confirming the model and its call sites exist | Real class and real call sites confirmed; mechanism depth (conflict handling, multi-system collision) not exhaustively traced | **D** | Baseline correctly marks this "STILL OPEN" — a real mechanism exists, but this audit did not have budget to trace its edge-case depth exhaustively. |
| Idempotency | `packages/idempotency/service.py` — `IdempotencyService.run_once` (18 lines): reserve → run → complete, with an explicit `release_idempotency` on any exception (line 32) "so a genuine retry can actually re-attempt the operation" | Referenced by `PostOrderOperationsService.reserve_inventory_for_order` via its own bespoke idempotency-marker pattern (`_record_internal_command`, `models.py`'s `ConnectorCommand.idempotency_key`) rather than by calling `IdempotencyService` directly for every path checked this pass | Real, working, exactly matches the mechanism the Pipe17 audit described from this same source | **B** | None on the core mechanism. Worth noting: not every mutation path in `post_order/operations.py` routes through `IdempotencyService.run_once` itself — several (e.g. `reserve_inventory_for_order`) implement their own idempotency check directly against `ConnectorCommand` rather than calling the shared service. Functionally equivalent, but not literally centralized in one call path. |
| Audit ledger | `packages/audit/ledger.py` — `AuditLedger.record()` (49 lines), a thin, real append-only wrapper over `store.append_audit(AuditEvent(...))`; `AuditEvent` model carries `actor`, `source`, `action`, `object_type`, `result`, `correlation_id`, `requested_mutation`, `external_ref` | Called from every service audited this session (`post_order`, `finance` implied, `support`, `exceptions`) | Real and consistently used | **B** | None found. |
| Policy engine | `packages/policy_engine/engine.py` — `PolicyEngine.decide()` (28 lines): a real `Decision.ALLOW/DENY/REQUIRE_APPROVAL` enum with amount-threshold logic for `"refund"` and a generic `mode` lookup otherwise | **Grepped exhaustively: `PolicyEngine.decide` / `.decide(` is called ZERO times anywhere in the repository outside its own file.** `PostOrderOperationsService.__init__` instantiates `self.policy = PolicyEngine()` (`post_order/operations.py:120`) but never calls `.decide()` on it. | The *class* exists and is unit-testable in isolation; it is not exercised by any real workflow | **F** | **A real, non-trivial finding, not previously surfaced in any prior document reviewed this session**: the "deterministic policy engine" the baseline (and every competitor audit) treats as an existing Sanocea strength is, in the literal sense of "one shared `PolicyEngine` class that decisions route through," dead code. The actual policy-decision logic lives independently, reimplemented per operation, directly in `post_order/operations.py`: `_refund_decision()` (lines 731-744) re-derives the identical `Decision.ALLOW`/`REQUIRE_APPROVAL` amount-threshold logic that `PolicyEngine.decide()` already encodes, reading `config.get("refunds")` directly rather than calling `self.policy.decide()`; `evaluate_cancellation()` (line 358) and `evaluate_return()` (line 405) each independently read their own merchant-config keys (`config.get("cancellations", {}).get("before_fulfilment", ...)`, `config.get("returns", {})`) with their own bespoke branching, never touching `PolicyEngine` either. **The capability (config-driven, deterministic, approval-gating decisions) is real and proven — see the Cancellation/Return/Refund rows below — but it is not centralized in the class the architecture names for this purpose.** This is a genuine, if narrow, architecture-vs-code gap: three independently-coded, drift-prone policy implementations where the codebase's own naming implies one. |
| Approval | `Approval` model (`models.py:430-438`); created by `evaluate_refund`, `evaluate_cancellation`, `evaluate_return` when `REQUIRE_APPROVAL`/`before_fulfilment` policy fires; `approve_refund()` (line 514) resolves it with a real authenticated `approver_id` (an `api_keys.id`, per its own docstring, "never free-text 'human'") | `run_phase46_integration_workload.py` asserts (line 675) that a support-initiated refund request can never itself execute the mutation — `support_action_status == "requested"` and the underlying mutation status is `{"permitted","approval_required"}`, never `"completed"` | Real, and specifically test-verified to resist bypass from the support path | **B** | None found; this is a genuine, evidenced strength. |
| Exception model | `ExceptionRecord` model (`models.py:441-449`) + `packages/exceptions/service.py` (68 lines) — `ExceptionService.create()` sets `remediation_options: list[str]` (plain suggestion strings, default `["review"]`) and `status: "open"/"acknowledged"/"resolved"` | Created from many real call sites (`post_order`, presumably `finance`/`procurement`) | Real, consistently used for surfacing | **D** for surfacing (implemented, exercised in tests, never proven against a real external system's exception volume); **G** for the baseline's own "resolution-condition"/auto-remediation concept — `remediation_options` is exactly the plain-string list the baseline itself already flags, confirmed by reading the actual field type | **B** (surfacing) / **G** (auto-remediation) | Matches the baseline's own honest self-assessment precisely — no gap in the finding itself. |
| ConnectorCommand / mutation lifecycle | `ConnectorCommand` model (`models.py:463-476`): `status: pending→approved→executing→succeeded/failed/uncertain/blocked`, `policy_decision: str = "REQUIRE_APPROVAL"` default | Used throughout `post_order/operations.py` (`_execute_logistics_command`, `_record_internal_command`) and exercised in every real-platform certification script (Section 18) | Real, exercised against real Shopify/WooCommerce/BigCommerce mutations | **A** (for the three real storefronts specifically; **C** for logistics/payments/suppliers, which only ever run against this state machine via simulators — Section 18) | None on the state-machine shape itself. |
| Capability registry | `ConnectorCapabilities`/`Capability` (imported as `Capability, CapabilityStatus, ConnectorCapabilities` in every connector's imports, e.g. `connectors/payments/simulated.py:8-13`, `connectors/bigcommerce/connector.py`) | Present in every connector file opened this session | Real, consistently declared per-connector | **B** | Mechanism depth (whether `SUPPORTED`/`UNSUPPORTED`/`ASYNC_ONLY` is actually read and branched on by calling code, vs. merely declared) was not independently traced this pass — flagged **I** for that specific sub-question. |
| Credential boundary | `Channel.credential_ref: str | None` (`models.py:78`) — credentials referenced, not embedded, on the canonical `Channel` entity; real per-merchant API-key resolution in `packages/authn/deps.py` | `require_operator`/`require_service` real, read from `store.resolve_api_key` | Real | **B** | Not independently traced whether `credential_ref` resolution itself (the secret store behind it) was opened this pass — **I** for that specific mechanism. |
| Raw payload/evidence retention | `RawPayload` model (`models.py:526-533`) — a real, generic `{merchant_id, source, payload, headers, checksum}` entity | Not independently traced to a specific ingestion call site this pass | Model is real; call-site usage not exhaustively confirmed | **I** | Genuinely not verified this pass, per the brief's own permitted honest answer. |
| Webhook replay/idempotency | `run_phase46_integration_workload.py` — "duplicate support event (redelivered)" check (line 520-527): "must cause exactly ONE business action"; `run_woocommerce_platform_independence.py` line 415: duplicate webhook replay produces no new order (`journey.get("duplicate_replay_no_new_order")`); `run_multi_platform_isolation_proof.py` line 180-210 (real webhook routing) | Confirmed real, positive test outcomes in real-platform certification scripts | **A** (for Shopify/WooCommerce specifically, per those scripts) | **A** | None found for the platforms these scripts cover. |
| Polling fallback | Not independently located this pass — no `poll` function distinct from webhook ingestion was found in the time budgeted | — | — | **I** | Genuinely not verified — flagged honestly rather than guessed. |
| Rate-limit handling | Not independently traced this pass | — | — | **I** | Same as above. |
| Retry/recovery | `workers/reconciliation_worker.py` — `ReconciliationWorker` (201 lines): "READ/RECONCILE EXTERNAL TRUTH FIRST → determine whether the mutation actually occurred → retry ONLY when genuinely safe... Bounded retries with terminal escalation" (its own module docstring, lines 19-23); `RecoveryCounters` tracks `retried_after_confirming_no_prior_effect`, `left_open_within_retry_bounds`, `escalated_terminal` | `scripts/run_recovery_worker.py` (130 lines) — a dedicated runner | Real, working, and precisely scoped | **B** | **Scoped narrowly to connector-mutation uncertainty** (a `ConnectorCommand` in an `uncertain`/`failed` state), not a general-purpose "any exception category, any resolution condition" sweep. This is real evidence *for* the baseline's Section 7 exception-autonomy doctrine's `RECHECK POLICY` concept, but only for the connector-mutation subset of exceptions — it does not, for example, auto-close an `INVENTORY_CONFLICT` exception once inventory is later restocked, or auto-resolve an `NDR_DETECTED` exception once a later tracking event shows delivery. |
| Read-back verification | `run_shopify_dev_store_certification.py` line 325: product/variant readback after publish; `run_bigcommerce_sandbox_certification.py` line 250: product readback after publish; `run_woocommerce_platform_independence.py` line 399: WooCommerce readback after update | Real, positive | **A** | **A** | None on the mechanism for these three platforms. |
| Reconciliation | `packages/finance/operations.py` — `FinanceOperationsService.reconcile_payment`, `.reconcile_settlement_batch`, `.reconcile_cumulative_settlement`, `._reconcile_charge` (553 lines total); `FinanceReconciliation.result` enum: `MATCH, EXPECTED_LAG, DIVERGENCE, UNKNOWN, EXTERNAL_ONLY, CANONICAL_ONLY, DUPLICATE, REQUIRES_CONFIGURATION, PARTIAL_SETTLEMENT, OVER_SETTLED, UNDER_SETTLED, UNRESOLVED_REFERENCE, ADJUSTMENT_RECORDED` (`models.py:275-280`) | Not exhaustively re-run this pass, but the engine's real, working depth is directly confirmed by reading its own code | Real, generic engine — but only ever exercised against `connectors/payments/settlement_simulator.py`'s `SimulatedSettlementProvider`, never a real payment gateway or marketplace settlement feed | **C** | See Section 9 for the full financial-truth trace — this is Sanocea's deepest generic engine, unconnected to any real external financial source. |
| Eventual-consistency handling | `packages/domain_contract/postgres_store.py:913-951` — `atomic_adjust_inventory`, using `ON CONFLICT` atomicity on `uq_inventory_merchant_sku_location`, explicitly documented as avoiding "a genuine lost-update race" (comment, line 917-922); `SupplierAcknowledgement.sequence`/`InboundShipment.sequence` fields exist specifically to "detect and refuse to let a stale/out-of-order event regress authoritative PO state" (`models.py:645-648`) | `tests/unit/test_phase41_procurement_integrity.py` — explicit over-acknowledgement/stale-event tests | Real, and specifically tested for the concurrency/ordering cases named | **B** | Confirmed real for procurement-acknowledgement ordering specifically; not independently re-traced for every other entity in the model. |
| API versioning | Not independently located this pass | — | — | **I** | Not verified. |
| RBAC/auth | `packages/authn/deps.py` (52 lines) — exactly two roles found: `"operator"` (merchant-scoped, URL-vs-key cross-check enforced) and `"service"` (machine/internal, unscoped) | Real, used by every FastAPI route this session's Grep touched | Real, but genuinely binary | **B** for the binary mechanism; **G** for any granularity beyond it | Confirms the baseline's own "2 coarse roles" claim exactly — no finer-grained role, permission, or scope concept found anywhere in `packages/authn/`. |
| Observability | `packages/metrics/workload.py` (38 lines, not independently opened in full this pass) + `runtime/queries.py`'s `operator_summary()` (an attention-query, not a metrics/observability system in the APM sense) | — | Real attention-query exists; genuine metrics/observability system depth not independently confirmed | **E**/**I** | Consistent with baseline's own "attention query, correlation IDs, no dashboards" framing (combined audit) — this pass did not find evidence to change that. |
| Retention/export/delete | Not independently located this pass | — | — | **I** | Not verified — a genuine open question for a future pass, not assumed either way. |

---

## 4. Multi-location — the P0 destruction test

**Verdict: the field-level structure for location-scoped inventory truth is genuinely real; every single
behavioral consequence of it — reservation-by-location, allocation, routing, multi-location
reconciliation, multi-location inbound, and return-to-location semantics — is either never exercised or
does not exist as a callable code path anywhere in the repository.**

**Can SKU A be represented as Surat=5, Mumbai=7 as two distinct facts, not one merchant-level 12?**
**Yes, at the schema/storage level — genuinely, not merely in principle.** `Inventory` (`models.py:145-159`)
carries `sku: str` and `location_ref: str` as separate fields, and `postgres_store.py:913-951`'s
`atomic_adjust_inventory` uses a real, named unique constraint `uq_inventory_merchant_sku_location` on
`(merchant_id, sku, location_ref)` — meaning the database schema itself is already structurally
multi-location-capable: two `Inventory` rows for the same SKU at two different `location_ref` values are
not just possible but are the *enforced* uniqueness boundary. **This is stronger than the baseline's own
framing implies** — the baseline treats this as an open architectural question; the schema itself already
answers "yes, this is representable," and it would be inaccurate to call the schema "MISSING."

**Can an order be deterministically allocated to a specific location by any real code path?**
**No — confirmed by exhaustive grep, not assumption.** Every single call site across the entire repository
that reads or writes `Inventory` passes `location` (or `location_ref`) as the literal string `"default"`,
either as an explicit argument or via an unoverridden default parameter:

- `PostOrderOperationsService.reserve_inventory_for_order(self, merchant_id, order, location: str = "default")` (`post_order/operations.py:125`)
- `PostOrderOperationsService.observe_inventory(self, merchant_id, sku, canonical_qty, external_qty, location: str = "default")` (`post_order/operations.py:175`)
- `ProcurementService.inventory_position(self, merchant_id, sku, location_ref: str = "default")` (`procurement/operations.py:202`)
- `ProcurementService._inventory_row(self, merchant_id, sku, location_ref: str = "default")` (`procurement/operations.py:220`)
- `ProcurementService._adjust_confirmed_inbound` calls `store.atomic_adjust_inventory(merchant_id, sku, "default", ...)` (`procurement/operations.py:668`) — **the literal string `"default"` is hardcoded directly at this call site, not even passed as a defaultable parameter.**

**A grep across every `.py` file in `packages/`, `workers/`, `connectors/`, `apps/`, `scripts/`, and
`tests/` for any call site passing a location value other than `"default"` returned zero results.** No
allocation function, no routing function, no "which location should fulfil this order" decision of any
kind exists anywhere in this codebase — not even as a stub that always returns `"default"`. The multi-
location *capability* is not merely unproven; the *decision logic itself does not exist as a named
function*, which is a more precise (and more severe) finding than "architectural only."

Per-item classification:

| Sub-capability | Classification | Evidence |
|---|---|---|
| Location-scoped inventory truth (schema) | **B** | Real unique constraint on `(merchant_id, sku, location_ref)`, atomic upsert function exists and is exercised in `tests/integration/test_phase4_procurement_real_infra.py:168` and `tests/unit/test_phase41_procurement_integrity.py` — but every test found calls it with `location_ref="default"` (line 168 of the integration test explicitly passes the string `"default"`), so the *schema* is proven multi-location-capable while the *tests* have never actually exercised two distinct locations for the same SKU. |
| Location-scoped ATS | **F** | The formula (`available = quantity - reserved`, computed per `(sku, location_ref)`) is schema-capable but has literally never been computed for more than one location for the same SKU anywhere in this codebase — no test constructs a second location. |
| Reservation by location | **F** | `reserve_inventory_for_order` filters candidates by `i.location_ref == location`, so the *code* is location-aware — but since `location` is always `"default"`, this has never been exercised as a real multi-location decision. |
| Allocation | **G** | No function exists. Not partial, not architectural-only in the sense of "a stub exists" — there is genuinely no code to classify above `MISSING`. |
| Routing | **G** | Same as allocation — no function exists anywhere. |
| Multi-location reconciliation | **G** | `observe_inventory`'s `location` parameter is real but always `"default"`; no reconciliation logic anywhere branches on location. |
| Multi-location inbound | **G** | `ProcurementService`'s goods-receipt/inbound-shipment code (Section 10) operates entirely against `location_ref="default"` — confirmed by the hardcoded literal at `procurement/operations.py:668`. |
| Return-to-location semantics | **G** | No restock-on-return logic exists at all (Section 5) — this question is moot until that gap closes, since there is no location-aware or location-agnostic restock path to evaluate. |

**This is the single most consequential confirmed finding of this entire audit.** The baseline's own P0
classification (`ARCHITECTURAL ONLY`) is, if anything, generous — "architectural only" implies a design
exists to build against; what actually exists is a real, correctly-designed *schema* with **zero**
behavioral code anywhere that has ever made a location-aware decision. The good news, precisely stated:
the schema does not need to change to support this — the P0 work is 100% new deterministic-engine and
policy code, not a data-model migration.

---

## 5. ATS / reservations / oversell

**The real formula the code represents:** `Inventory.quantity`, `Inventory.reserved`,
`Inventory.available`, `Inventory.confirmed_inbound` (`models.py:145-159`). **`committed: int = 0` is
declared on the model but is never read or written anywhere in the repository outside `models.py`
itself** — confirmed by an exhaustive grep for `.committed` across every package; this is a genuinely dead
field, not a state actually represented in the running system. No `damaged`, `quarantine`, or
`return_pending` state exists anywhere — the baseline's own "sellable/reserved/quarantine/in-transit"
future-state vocabulary (Section 4 of the baseline) is aspirational, not present.

**When does reservation occur?** `reserve_inventory_for_order` (`post_order/operations.py:125-172`):
`inv.available -= reserve_qty; inv.reserved += reserve_qty`, guarded by an idempotency check against a
`ConnectorCommand` marker keyed `reserve_inventory:{order.id}` so a retried call never double-reserves.
Real, and directly evidenced.

**When does it release? Confirmed: it does not, anywhere, for any reason.** An exhaustive grep for
`restock`, `release_reservation`, `reserved -=`, or any decrement of `.reserved` across the entire
repository returned **zero results**. Specifically:

- `execute_cancellation` (`post_order/operations.py:377-403`) sets `order.status = "CANCELLED"` and the
  `Cancellation.status = "completed"` — it never touches the `Inventory` row that
  `reserve_inventory_for_order` reserved against for that order's lines.
- `progress_return`'s `"inspection_passed" → "accepted"` transition (`post_order/operations.py:427-454`)
  never updates any `Inventory` row.
- `execute_refund` (line 533 onward) never touches inventory.
- The only two places `.reserved` is ever incremented are order reservation (above) and exchange
  reservation (`evaluate_exchange`, line 456-484, real: `selected.available -= 1; selected.reserved += 1`).
  **Neither has a corresponding decrement anywhere.**

**This is a real, confirmed correctness gap, not a hypothetical one.** `reserved` is monotonically
increasing in this codebase's current state — every cancelled order, every completed return, and every
refund permanently leaves that order's reserved quantity "stuck" against the SKU. The only mechanism that
ever *reduces* `reserved` implicitly is `observe_inventory`'s full-value overwrite of `quantity`/
`available` from an external re-sync (`post_order/operations.py:175-197`) — but that function does not
touch `.reserved` either; it only overwrites `quantity` and `available` directly from `external_qty`. Over
enough cancel/return/refund volume without corresponding external re-syncs, the ATS formula used by
`ProcurementService.inventory_position` (`on_hand - reserved + confirmed_inbound`, `procurement/
operations.py:217`) would drift toward under-reporting availability — the opposite failure mode from
overselling (a safer direction to drift in, but still a real, unaddressed bug).

**Oversell prevention (the shortfall path):** real and correctly evidenced —
`reserve_inventory_for_order`'s `reserve_qty = min(available, line.quantity)` with an explicit
`ExceptionRecord` (category `INVENTORY_CONFLICT`) raised on any shortfall, `remediation_options:
["expedite_replenishment", "cancel_line", "backorder"]` (line 166) — the suggestion list, not a working
backorder mechanism (Section 7). This part of the ATS story is genuinely proven: `Phase2Counters
.overselling_prevented` exists as a named counter specifically for this.

**Exchange reservation:** real, proven (above). **Cancel/refund/return behavior on inventory:**
confirmed **G — missing entirely.** **Inbound effect on ATS:** real and well-tested (Section 10's
`confirmed_inbound`/goods-receipt chain) — the one part of this section genuinely proven end-to-end.

| Sub-capability | Classification |
|---|---|
| Reservation at order time | **B** |
| Release on cancel | **G** |
| Release on refund | **G** |
| Restock on return | **G** |
| Exchange reservation | **B** |
| Inbound effect on ATS | **B** (via `confirmed_inbound`, Section 10) |
| Concurrency safety on reservation itself | **I** — not independently load-tested this pass; the atomic-upsert pattern exists for inventory *adjustment* (`atomic_adjust_inventory`) but `reserve_inventory_for_order`'s read-then-write (`inv.available = max(available - reserve_qty, 0); self.store.put(inv)`) was not confirmed to use the same atomic-conflict-safe path — flagged honestly as unverified rather than assumed safe. |

---

## 6. Bundles / kits / composites

**MISSING, confirmed by exhaustive search, not inferred from silence.** A case-insensitive grep for
`bundle`, `composite`, `\bkit\b`, and `BOM` across `packages/domain_contract/models.py`,
`packages/post_order/`, and `packages/procurement/` returned zero results. No parent/child SKU
relationship, no assembly-timing concept, no component-inventory-deduction logic, and no bundle-derived-
ATS calculation exists anywhere. `Variant.option_values: dict[str, str]` (`models.py:126-133`) is a plain
product-variant concept (e.g. size/colour) and is not, and should not be, reinterpreted as a bundle —
confirmed by reading its actual fields, which carry no notion of a second, related SKU or quantity.

**Classification: G, unconditionally**, across every sub-concept the baseline names (virtual bundle,
preassembled kit, BOM/manufactured item, multipack, component deduction, bundle ATS, bundle returns).

---

## 7. Order/fulfilment edge cases

| Capability | Classification | Evidence |
|---|---|---|
| Partial fulfilment | **G** | No code found distinguishing partial from full fulfilment at the order-line level; `OrderLine.fulfillment_state: str = "pending"` (`models.py:206`) exists as a field but no service code branches on partial-vs-full fulfilment logic. |
| Split fulfilment | **G** | Zero matches for `split_order`/`split_fulfil` anywhere in the repository. |
| Merge (orders) | **G** | Zero matches for `merge_order` anywhere. |
| Backorder | **G** | The *word* "backorder" appears exactly once in the entire codebase, as a plain string inside a `remediation_options` suggestion list (`post_order/operations.py:166`) — there is no backorder state, no backorder queue, no conversion-to-PO workflow. This is weaker than "architectural only" — it is a label with no mechanism behind it at all. |
| Preorder | **G** | Zero matches anywhere. |
| Partial cancellation | **G** | `Cancellation` (`models.py:377-383`) is order-scoped, not line-scoped; `evaluate_cancellation`/`execute_cancellation` operate on the whole `Order`, never a subset of `OrderLine`s. |
| Post-dispatch cancellation | **E** | `evaluate_cancellation` (`post_order/operations.py:358-375`) checks exactly one signal: `if order.fulfillment_status: status = "denied"` — i.e. cancellation is denied outright once *any* fulfilment status is set, with no distinct branch for "already dispatched, needs courier-return handling" the way the Unicommerce audit found (pre-invoice / post-invoice-pre-dispatch / post-dispatch as three distinct putaway-code branches). Sanocea's model collapses this to a binary eligible/denied, not a three-way branch. |
| Multiple shipments per order | **E** | `Shipment.order_id: str` (singular per shipment, `models.py:294-301`) permits multiple `Shipment` rows referencing one order in principle (the store query `[s for s in self.store.list(Shipment, merchant_id) if s.order_id == order.id]` at `post_order/operations.py:237` already returns a *list*), but `create_or_observe_shipment`'s own caching (`self._shipment_by_order: dict[tuple[str, str], Shipment]`, keyed by `(merchant_id, order.id)` — one entry per order, not per shipment) means the *service* logic assumes one shipment per order in its control flow, even though the *model* would permit more. |
| Multiple locations per order | **G** | Follows directly from Section 4 — no allocation logic exists to produce more than one location's involvement in an order at all. |
| Replacement/reship | **E** | `Exchange` (`models.py:385-392`) is the closest concept — real, with genuine inventory reservation (Section 5) — but it is framed as a size/variant exchange (`requested_variant_sku`), not a "replace this damaged item with an identical one" reship flow; whether it can represent same-SKU reship was not independently tested this pass. |
| Lost shipment | **G** | No distinct state or handling found — `TrackingEvent.status` is a free-text carrier status string; no canonical "lost" classification exists. |
| Delivery failure / NDR | **D** | Real and more substantial than the baseline's general "MISSING" framing suggests: `ingest_tracking` (`post_order/operations.py:303-345`) detects `event["status"] == "NDR"` and creates a real `ExceptionRecord` (category `NDR_DETECTED`, `remediation_options: ["reattempt_delivery", "contact_customer"]`); a real callable, `request_ndr_reattempt` (line 347-356), exists and issues a `request_ndr_action`/`REATTEMPT` connector command. **This is real, working code — but only ever tested against `SimulatedLogisticsConnector`, never a real courier**, and there is no corresponding "accept RTO instead of reattempting" decision path — only the reattempt branch is implemented. |
| RTO | **E** | Detected (`elif event["status"].startswith("RTO"): ... result = "rto"`, line 339-341) and raises an exception with `remediation_options: ["inventory_reconcile", "refund_review"]` — but, consistent with Section 5's finding, no code actually performs `inventory_reconcile` on an RTO; it is a suggestion string, not a mechanism. |

**Correction worth stating plainly:** the baseline's own language ("NDR/RTO ... MISSING entirely") is
**more pessimistic than the code actually is** for detection and a first reattempt action — this is a
case where the codebase is somewhat ahead of the baseline's own self-assessment. It remains accurate that
there is no full re-attempt-vs-RTO *decision workflow*, no real-courier proof, and no inventory-restock
consequence — those specific baseline claims hold.

---

## 8. India-first P1 requirements

| Requirement | Classification | Evidence |
|---|---|---|
| Amazon India | **G** | Zero matches for "amazon" anywhere in `connectors/` or `packages/`. |
| Flipkart | **G** | Zero matches anywhere. |
| Myntra | **G** | Zero matches anywhere. |
| Meesho | **G** | Zero matches anywhere. |
| COD (order-creation side) | **I** (not re-verified this pass; the combined audit's own claim of WooCommerce COD `IMPLEMENTED+PROVEN` was not independently re-traced to a specific line this session — the WooCommerce connector's real HTTP-calling structure was confirmed (Section 18), but a COD-specific payment-method branch was not opened) | — |
| COD remittance | **G** | No settlement-simulator entry type or reconciliation branch specific to COD-collection-vs-order-value tolerance matching was found distinct from the generic `SettlementEntry.entry_type: "cod_collection"` enum value (`models.py:248`) — the *type* exists in the taxonomy; no COD-specific reconciliation *logic* (a tolerance-matching state machine comparable to UniReco's) was found. |
| NDR/RTO | **D** (per Section 7) | Real detection + one reattempt action, simulator-proven only, no real Indian courier. |
| Indian courier abstraction | **G** | `Shipment.carrier: str` is free-text (`models.py:298`); no courier-selection logic, and the only logistics connector found anywhere is `SimulatedLogisticsConnector` (`connectors/logistics/simulated.py`) — no Delhivery/Bluedart/Xpressbees-shaped connector exists. |
| Marketplace settlement | **G** for any real marketplace; **C** for the generic engine against a simulator (Section 9) | The generic settlement-reconciliation *engine* is real and deep; the specific claim "Amazon India settlement ingestion exists" is false — there is no marketplace connector to ingest a settlement feed from in the first place. This is exactly the distinction the brief warned against blurring. |
| Marketplace fee reconciliation | **G** for real; **C** for the generic engine | `SettlementEntry.entry_type` includes `"marketplace_deduction"` (`models.py:248`) as a real taxonomy value the generic reconciliation engine can process — but no named fee-category vocabulary (Commission Fee, Pick and Pack Fee, etc., per the Unicommerce audit's finding) exists anywhere, and there is no marketplace connector to source real deduction data from. |
| WhatsApp support transport | **G** | Zero matches for "whatsapp" (case-insensitive) anywhere in `packages/` or `connectors/`. |
| Returns/refunds/exchanges | **D**/**B** — real, working, well-tested state machines (Section 7, Section 5) — but **not proven for any real Indian marketplace**, only for the real storefronts certified (Section 18) | See Sections 5, 7. |
| Bundles/kits | **G** | Section 6. |
| RBAC | **B** for the binary mechanism, **G** for granularity | Section 3. |
| Exception handling | **B** for surfacing, **G** for auto-remediation | Section 3, Section 13. |

---

## 9. Financial truth

`packages/finance/operations.py` (553 lines) is real, deep, and genuinely matches the combined audit's
own claim of a "dual-dimension reconciliation" architecture — but it is a **generic engine that has never
been connected to a real external financial source.**

- `PaymentObservation` (`models.py:219-229`), `SettlementBatch` (232-241), `SettlementEntry` (243-264):
  real models with real, non-trivial provenance-preservation logic — `SettlementEntry.provider_order_
  reference`/`provider_refund_reference` are explicitly documented (`models.py:249-259`) as "the
  provider's OWN ... reference, exactly as it arrived on the settlement feed — immutable evidence, kept
  even when resolution fails," resolved to Sanocea's internal `order_id`/`refund_id` only afterward via
  `external_id_mappings`, "never trusted directly off the incoming payload." This is real, careful,
  evidenced design, not aspiration.
- `Refund.status` (operational) vs. `Refund.financial_reconciliation_status: Literal["pending", "matched",
  "discrepancy"]` (`models.py:354-374`) is real and precisely as described everywhere in this research
  program — the model comment even names the exact function
  (`apply_refund_reconciliation_to_canonical()`, confirmed present at `finance/operations.py:374`) and
  the exact read-path (`runtime/queries.py:44`'s `get_refund_full_state`, confirmed present) that must be
  used together, "never `status` alone." This dual-status pattern is genuinely implemented, not just
  claimed.
- `FinanceReconciliation.result` carries 13 distinct real states (`MATCH` through `ADJUSTMENT_RECORDED`,
  `models.py:275-280`) — a materially richer taxonomy than a binary match/mismatch flag.
- **The connection to a real external financial source: `G`.** `connectors/payments/settlement_
  simulator.py`'s `SimulatedSettlementProvider` is the *only* source that has ever fed this engine,
  confirmed by its own docstring describing itself as "a stateful stand-in for a payment gateway's
  settlement feed." No real payment gateway, no real marketplace commission feed, and no real courier
  remittance feed connector exists anywhere in `connectors/`.

**Classification: C — implemented and proven against a real, stateful, non-trivial simulator; never
proven against any real financial source.** This is the correct, conservative classification: the engine
is real and the simulator is genuinely stateful (not a canned fixture), but per this audit's own
discipline, a simulator is never upgraded to "real platform" status regardless of its sophistication.

---

## 10. Procurement

`packages/procurement/operations.py` — the single most mature, most fully-proven domain in this entire
audit.

- `Supplier`, `SupplierSku` (real, merchant-independent — `Supplier.reliability_score` is explicitly
  documented as "deterministically derived from historical on-time/short-shipment performance ... never
  fabricated, never AI-estimated," `models.py:574-576`).
- `recommend_replenishment()` (`procurement/operations.py:241`) is a real, callable function producing a
  `ReplenishmentRecommendation` with a `reasoning: dict[str, Any]` field explicitly designed to "explain
  exactly why" (`models.py:604`) — not merely a model, a genuine computation.
- `PurchaseOrder.status` carries a real 13-state lifecycle (`DRAFT` through `CLOSED`, `models.py:612-616`)
  including `AUTO_APPROVED`, `REQUIRES_APPROVAL`, `BLOCKED`, `REJECTED`, `OVER_CONFIRMED` — genuinely rich,
  not a simple create→approve→send→receive flag.
- `SupplierAcknowledgement` with a real `sequence` field specifically to reject stale/out-of-order events
  (`models.py:645-648`), and `_adjust_confirmed_inbound`'s over-confirmation-capping logic
  (`procurement/operations.py:625-668`, comment: "confirmed_inbound only ever receives the LEGITIMATE
  portion ... inventory position was NOT silently inflated") is real, deliberate, and independently
  tested — `tests/unit/test_phase41_procurement_integrity.py` explicitly asserts `confirmed_inbound`
  never exceeds the legitimately ordered quantity across five distinct scenarios (over-acknowledgement,
  multi-order contribution, stale-event rejection).
- `GoodsReceipt`/`GoodsReceiptLine` with a real `disposition: "match"/"shortage"/"excess"/"wrong_sku"/
  "unexpected_item"` enum (`models.py:685-692`) — genuinely more granular than a boolean "received" flag,
  which directly answers baseline Section 13's own P2 aspiration (Pipe17's variance/damage-field design
  insight) as **already implemented**, not a gap.

**The one real gap:** identical to Section 4/8 — `_adjust_confirmed_inbound` hardcodes the literal string
`"default"` as its location argument (`procurement/operations.py:668`), so this entire, otherwise mature
lifecycle is single-location, exactly like everything else in the codebase.

**Merchant independence:** genuinely clean — no merchant-specific assumption found baked into
`ProcurementService`'s generic logic (Section 17).

**Classification: C — implemented and proven against a real, stateful supplier simulator
(`SupplierSimulator`, `connectors/suppliers/simulator.py`, deliberately designed to avoid leaking
Sanocea's own IDs into supplier-side state), and additionally proven against real local Postgres
infrastructure (`tests/integration/test_phase4_procurement_real_infra.py`) — never proven against a real
supplier's actual system.** This is, along with finance, the deepest generic engine in the codebase and
the strongest evidence for Section 16's procurement-truth trace below.

---

## 11. Customer operations — the differentiator-E chain, arrow by arrow

`packages/support/workflow.py` (291 lines) is real, and its own docstring states the architectural intent
precisely: "Support never maintains parallel business truth ... every actionable request ... is
dispatched into the SAME policy-gated post_order engine methods a direct API call would use ... Support
NEVER calls execute_refund/execute_cancellation/complete_exchange/progress_return itself." **This is
Sanocea's own code explicitly documenting the exact limit of what it does — the chain is not fully closed
by design, and the design says so.**

| Arrow | Verdict | Evidence |
|---|---|---|
| A. Conversation ingestion | **PROVEN** | Chatwoot webhook, real HMAC signature verification at the connector boundary (per the module docstring's own reference to `ChatwootConnector._verify_signature`); real webhook headers constructed and posted in `run_phase46_integration_workload.py` (`_chatwoot_headers`, line 59); real duplicate-delivery de-duplication tested (line 520-527). |
| B. Intent understanding | **PARTIALLY PROVEN** | `_deterministic_intent()` (`support/workflow.py:245-291`) is a real, substantial keyword-matching function covering 21 named intents. The "AI branch" it falls back to (`self.ai.classify(...)`, line 83) is real code, but `self.ai` defaults to `DeterministicAIProvider` (`support/workflow.py:68`) — the *same kind* of keyword-based deterministic logic, not a real model (Section 12). **In the system's current, real, deployed state, "intent understanding" is 100% deterministic — there is no genuine AI-mediated ambiguity resolution happening anywhere in this arrow today**, even though the code path that *would* call a real provider, if one existed, is real and correctly structured. |
| C. Live commerce truth | **PROVEN** | Every status-query intent (`order_status`, `refund_status`, `return_status`, `exchange_status`, `cancellation_status`, `rto_status`) reads directly from `self.store.list(Refund/Return/Exchange/Cancellation/Shipment, merchant_id)` (`support/workflow.py:177-196`) — live reads of the same canonical rows every other part of the system uses, not a cached or duplicated support-side copy. |
| D. Deterministic/policy eligibility | **PROVEN, and specifically test-verified against bypass** | `_decide_actionable()` (`support/workflow.py:214-234`) dispatches into `self.post_order.evaluate_refund/evaluate_return/evaluate_cancellation` — the exact same functions a direct API caller uses (Section 3/5's `_refund_decision` policy logic applies identically regardless of caller). `run_phase46_integration_workload.py`'s `support_unauthorized_mutation` check (line 498-517) specifically asserts a support-initiated refund request cannot bypass this gate. |
| E. Operational mutation | **NOT PROVEN AS A SUPPORT-ORIGINATED, CONTINUOUS CHAIN.** | This is the most important nuance in this entire audit. `handle_conversation` explicitly sets `record.status = "requested"` for the `APPROVAL-GATED` mode (line 149, with a comment confirming this is deliberate: "support created the canonical request object but never performed the underlying mutation itself"). **The actual mutation (`execute_refund`/`execute_cancellation`/`complete_exchange`) requires a separate, human-operator-initiated call** — and an exhaustive grep of every script and test in the repository (`run_phase46_integration_workload.py`, `run_phase11_simulation.py`, `run_phase21_workload.py`, `run_phase2_workload.py`, and every `tests/` file referencing `SupportWorkflowService`/`handle_conversation`) found **zero** instance where a single continuous test or workload actually calls `handle_conversation` and then follows through with the corresponding `approve_refund`/`execute_refund`/`reconcile_refund` on the *same* request. Each piece is independently real and independently tested; the full chain from a support message through to an executed, reconciled mutation has never been exercised together in one place. |
| F. Approval/risk control | **PROVEN** | The `Approval` record created inside `evaluate_refund`/`evaluate_cancellation`/`evaluate_return` is the real, same-shaped object an operator-initiated request creates (Section 3). |
| G. Reconciliation/read-back | **NOT PROVEN FOR A SUPPORT-ORIGINATED MUTATION SPECIFICALLY** | `apply_refund_reconciliation_to_canonical`/`get_refund_full_state` (Section 9) are real and proven for refunds *in general* — but since no test chains a support-originated refund through to `execute_refund`/`reconcile_refund` (arrow E's finding), this specific combination has never been exercised. The mechanism exists; the chain linking it to a support origin does not. |
| H. Continued support state | **PROVEN, by construction** | Because arrow C reads live canonical state, any later change to a `Refund`/`Return`/etc. row (however it was made) would correctly be reflected the next time a customer asks about it — this arrow follows necessarily from C being real, and does not depend on E/G being chained. |

**Precise summary, per the baseline's own amended Section 5.A.2 language:** the baseline already
distinguishes "currently proven" (the refund-reconciliation link, attributed to "Phase 4.6") from
"architectural scope, not separately proven" (the rest of the chain) — **this audit finds that even the
specific link the baseline calls "currently proven" (a support conversation → real refund → financial
reconciliation) has never actually been exercised as one continuous, real test.** What Phase 4.6's own
real test (`run_phase46_integration_workload.py`) actually proves is narrower and, in a specific way,
more interesting: it proves support **cannot** bypass the policy gate to execute a mutation on its own —
a real, valuable, differentiated security property — but it does not prove the full chain through to
execution and reconciliation was ever completed starting from a support message. **This is a real
correction to how "Phase 4.6 proved differentiator E" should be described going forward**: the proven
fact is "support requests are policy-gated identically to operator requests, and cannot self-execute,"
not "a support conversation has been shown to produce a reconciled financial consequence end-to-end."

---

## 12. AI reality check

**Current real stage: Stage 0, confirmed with certainty, not inferred.**

`packages/ai/provider.py` (84 lines): `AIProvider` is a `Protocol` (an interface, zero implementation) —
`classify`, `generate`, `map_attributes`. **The only class implementing it anywhere in the repository is
`DeterministicAIProvider`**, and reading its actual code confirms it makes no external call of any kind —
`classify()` is a plain `if "where" in lowered or "status" in lowered...` keyword-matching function
(lines 35-60) returning a hardcoded confidence of `0.9` or `0.2`; `generate()` returns a canned
string-template response (`f"{title} prepared from approved supplier evidence."`, line 68); `map_
attributes()` returns the input unchanged (`output=raw`, line 79).

An exhaustive grep for any other `AIProvider` implementation, any HTTP client construction inside
`packages/ai/`, or any reference to a real model name (OpenAI, Anthropic, a local model runtime) anywhere
in `packages/`, `workers/`, or `connectors/` returned **zero results**.

- **Has any real model inference ever been executed by the current product code?** No — confirmed, not
  assumed.
- **Does `AIProvider` call a real model?** No — the only implementation is a rule-based stub.
- **Are AI outputs used operationally anywhere?** Yes, in the narrow sense that `SupportWorkflowService`
  genuinely calls `self.ai.classify(...)` and uses its output to set `intent`/`confidence` (Section 11,
  arrow B) — but since the only real provider is deterministic, "AI output" and "keyword-match output"
  are, today, the identical thing.
- **Does AI diagnose, recommend, propose rules, authorize, or mutate anything?** No — none of these
  capabilities exist in any form; `DeterministicAIProvider` only classifies text and generates canned
  copy, both without any real reasoning.

**Classification: F — architectural/interface/scaffold only.** The `AIProvider` Protocol itself is
well-designed (matching the baseline's own repeated characterization) and genuinely wired into a real
call path (`support/workflow.py`), which is a real, if modest, structural strength — but "the interface is
wired in" and "AI is operational" are different claims, and only the first is true.

---

## 13. Exception autonomy

Comparing the actual repository against the baseline's own doctrine
(`EXCEPTION → CAUSE → RESOLUTION CONDITION → RECHECK POLICY → SAFE REMEDIATION → ESCALATION`):

| Doctrine stage | What exists today | Classification |
|---|---|---|
| CAUSE | `ExceptionRecord.category: str` (a plain string, e.g. `INVENTORY_CONFLICT`, `NDR_DETECTED` via `ExceptionCategory` enum, `exceptions/service.py:9-25`) — real, but a flat classification tag, not a structured cause object | **B** |
| RESOLUTION CONDITION | **Does not exist as a distinct concept.** `remediation_options: list[str]` (`models.py:448`) is exactly the plain-suggestion-string list the baseline itself already names as the gap — confirmed by reading the actual field type, not inferred | **G** |
| RECHECK POLICY | `ReconciliationWorker` (Section 3) is real, but scoped specifically to `ConnectorCommand` mutation-uncertainty, not a general per-exception-category recheck scheduler | **E** (real for the connector-mutation subset; **G** for the general case) |
| SAFE REMEDIATION | `Approval` (Section 3) is the real gate for anything requiring a decision — but there is no code that *proposes* a remediation and routes it through `Approval` automatically; a human must notice the `ExceptionRecord` and act | **F** |
| ESCALATION | `RecoveryCounters.escalated_terminal` (`workers/reconciliation_worker.py:37`) is real for the connector-mutation-retry case specifically ("a human-required exception is never retried forever," per the module's own docstring) — no general, deadline-based escalation for arbitrary exception categories was found | **E** |

**Net finding:** the baseline's own framing ("the need to surface exceptions is closed and proven;
automated remediation is genuinely open") is precisely correct and does not need correction — this pass's
contribution is confirming, with real file/line evidence, exactly how thin the "recheck" and "remediation"
stages actually are, and that the one real recheck/retry mechanism that exists (`ReconciliationWorker`) is
narrower in scope (connector-mutation-only) than the baseline's Pipe17-derived doctrine describes as the
target shape.

---

## 14. Operational evidence

**No generic `OperationalEvidence` primitive exists — confirmed, not inferred from absence of a
grep hit alone.** A search for `class OperationalEvidence` returned nothing, and a count of `evidence_ref`
occurrences in `models.py` returns **16** — meaning the *pattern* the baseline describes (a typed
reference to externally-stored content, linked back to the record it evidences) is real and repeated
throughout the model, but implemented as a **separate, independent `evidence_ref: str | None` field
scattered across at least sixteen different entities** (`Product`, `ProductDraft`'s `evidence_refs: list`,
`ExtractedAttribute`, `PaymentObservation`, `SettlementEntry`, `Refund` (indirectly via
`financial_reconciliation_ref`), `Return`, `SupportIntent`, `CustomerSupportAction`, and others) — never
one shared entity or relationship.

**Classification: exactly matching the baseline's own worst-case scenario, confirmed as already
happened, not merely risked.** The baseline's Section 9 warns this is "the natural failure mode" if a
generic primitive is never designed — this audit confirms that failure mode is the *current, real state*
of the codebase: domain-specific evidence fragments, not one generic model, not raw object-storage-only,
and not missing in the sense of "no evidence concept at all" — the concept is real and repeated, just
never unified.

`packages/object_storage/s3.py` (90 lines, not opened in full detail this pass) is the presumed backing
store for the object referenced by these `evidence_ref` strings — its own real-vs-simulated status was
not independently confirmed this pass (**I**).

---

## 15. Profitability read model

Checking the baseline's specific required inputs against real canonical fields found this session:

| Required input | Exists in real code today? | Evidence |
|---|---|---|
| Revenue | **Yes** | `Order.total_amount: int` (`models.py:190`) |
| COGS | **Partially** | `SupplierSku.cost: int` (`models.py:588`) is real per-supplier unit cost — but this is *supplier cost*, not a computed COGS attributed to a specific sold unit/order line; no code was found joining `OrderLine` to the specific `SupplierSku`/`PurchaseOrderLine` that supplied the units sold, which a true per-order COGS calculation would need |
| Discount | **Yes** | `OrderLine.discount_amount: int = 0` (`models.py:205`) |
| Marketplace fees | **Taxonomy only** | `SettlementEntry.entry_type` includes `"marketplace_deduction"` (`models.py:248`) as a real category the generic engine can carry — but since no real marketplace connector exists (Section 8), no real marketplace fee value has ever populated this field outside the simulator |
| Payment fees | **Taxonomy only** | `SettlementEntry.entry_type` includes `"fee"` — same caveat: real category, never populated by a real payment gateway |
| Shipping/fulfilment cost | **Missing** | No cost field was found anywhere on `Shipment` or `Fulfilment` (`models.py:286-301`) — both models carry status/tracking/SLA fields, not a cost figure |
| Refund/return economic consequence | **Yes** | `Refund.amount: int` (`models.py:357`) is real and canonical |
| Advertising attribution | **Missing** | No advertising-spend concept exists anywhere in the canonical model — consistent with the baseline's own explicit decision to keep advertising out of scope |

**Whether this can eventually be computed without a new source-of-truth entity, as the baseline
assumes:** **partially confirmed, partially challenged.** Revenue, discount, and refund/return
consequence are genuinely already canonical facts a read-model could join without any new entity —
that part of the baseline's assumption holds. **COGS and shipping/fulfilment cost are the two inputs
this audit finds are not merely "waiting on a connector to populate an existing field" (like marketplace/
payment fees) but are missing a *field* to populate in the first place** — a true per-order COGS
calculation would need either a new join path (order line → the specific inbound unit's cost, which
today's model does not track at the unit-of-sale level) or a new field, and shipping cost has no home on
`Shipment`/`Fulfilment` at all today. This is a real, specific refinement to the baseline's assumption,
not a wholesale contradiction of it — most of the profitability formula is genuinely a read-model problem;
two of its seven required inputs are a real, if narrow, canonical-model gap.

---

## 16. Differentiator F — reality check: three concrete traces

**(a) ORDER → inventory reservation → fulfilment → refund → financial reconciliation → support-visible
truth**

`Order` created → `reserve_inventory_for_order` (real, Section 5) → `create_or_observe_shipment`/
`monitor_fulfilment` (real, Section 7) → `evaluate_refund`/`execute_refund` (real, Section 9) →
`reconcile_refund`/`apply_refund_reconciliation_to_canonical` (real, Section 9, sets
`Refund.financial_reconciliation_status`) → `SupportWorkflowService._decide`'s `refund_status` intent
reads that exact `Refund` row live (real, Section 11, arrow C). **Every arrow in this trace has real,
named code implementing it.** The one break: the refund's effect on *inventory* (releasing the reservation
that was made for the now-refunded/cancelled line) does not exist (Section 5) — the chain is proven for
the financial and support-visibility legs, and breaks specifically at the inventory-consequence leg.
**Verdict: PARTIALLY PROVEN** — proven end-to-end for finance/support; broken at the inventory-consequence
link.

**(b) RETURN → inventory consequence → refund → reconciliation → support state**

`evaluate_return`/`progress_return` (real, Section 7) → **inventory consequence: does not exist** (no code
updates any `Inventory` row on `"inspection_passed"`/`"accepted"`, confirmed in Section 5) → refund/
reconciliation/support-state legs are the same real mechanisms as trace (a), but they are never *triggered
by* the return specifically — no code was found linking a completed `Return`'s acceptance to the
automatic creation of a `Refund`. Reading `progress_return`'s transition table (`post_order/operations.py:
442-450`) confirms it only ever changes `Return.status`; it never calls `evaluate_refund`. **Verdict:
ARCHITECTURAL ONLY** — the individual downstream mechanisms (refund, reconciliation, support-visibility)
are real in isolation, but the specific chain "a return causes its refund and inventory consequence" has
no connecting code at all; a human must separately notice an accepted return and separately request a
refund through another path.

**(c) LOW STOCK/DEMAND → replenishment → PO → acknowledgement → receipt → inventory truth**

`recommend_replenishment` (real, `procurement/operations.py:241`) → `ReplenishmentRecommendation.status:
"proposed"/"converted_to_po"` (real state, `models.py:606`) → `PurchaseOrder` creation/approval (real,
Section 10) → `SupplierAcknowledgement` (real, sequence-guarded, Section 10) → `GoodsReceipt`/
`GoodsReceiptLine` (real, disposition-typed, Section 10) → `_adjust_confirmed_inbound`/goods-receipt
handling updates `Inventory.confirmed_inbound`/`.quantity`/`.available` (real, confirmed by
`procurement/operations.py:799`'s `confirmed_inbound_delta=-quantity_received, quantity_delta=
quantity_received, available_delta=quantity_received` on receipt). **This trace is real, complete, and
independently tested end-to-end** (`tests/unit/test_phase41_procurement_integrity.py`,
`tests/integration/test_phase4_procurement_real_infra.py`, `scripts/run_phase4_procurement_workload.py`).
**Verdict: PROVEN** — the one trace of the three that genuinely closes, start to finish, in real,
independently-tested code.

**Overall Section 16 verdict, precisely stated:** Differentiator F is **real for the specific pairwise
connections this audit could trace with actual code (finance↔support, procurement's own internal chain),
and NOT PROVEN for the cross-domain consequences the baseline's own "architectural scope, not separately
proven" language already flags as unproven** — most importantly, no return or cancellation has ever been
shown to produce its correct inventory consequence, which is the single most concrete, checkable failure
of the cross-domain-consequence claim found this session. **This is not a case of the baseline overclaiming
something false; it is a case of the baseline correctly hedging a claim this audit can now confirm the
hedge was necessary for.** Differentiator F's *architecture* (one object model, one set of services reading
it) is real; its claimed *behavior* (a change in one domain reliably producing the correct consequence in
every other domain) is proven for procurement's internal chain, proven for the financial leg of the order
lifecycle, and specifically **not proven, and in the return case actively absent**, for the inventory
consequence of returns/cancellations/refunds.

---

## 17. Merchant-independence test

**Overall classification: CLEAN, with one specific instance of MINOR LEAKAGE.**

- No hardcoded merchant ID or merchant name was found anywhere in `packages/` outside test fixtures.
- No Shopify-specific or WooCommerce-specific payload shape was found leaking into generic package code —
  confirmed by the deliberate, documented fix already present in `post_order/operations.py`'s
  `observe_inventory`, whose own comment (line 199-201) explicitly calls out and describes fixing "a real
  multi-platform bug found while wiring the WooCommerce platform-independence test ... this literal used
  to say 'shopify' regardless of which connector was actually configured" — i.e. this class of leakage was
  found and fixed by the team's own prior work, and this audit found no new instance of it.
- **Minor leakage found: India-specific defaults baked directly into generic, merchant-independent
  canonical model/config code, rather than pushed to per-merchant configuration:**
  - `Merchant.default_currency: str = "INR"` (`models.py:65`)
  - `Merchant.timezone: str = "Asia/Kolkata"` (`models.py:66`)
  - `PurchaseOrder.currency: str = "INR"` (`models.py:617`)
  - `packages/onboarding/merchant.py:12` — the default onboarding config's `"currency": "INR"`
  - `packages/finance/operations.py:172` — `batch_payload.get("currency", "INR")` as a settlement-batch
    default
  - `procurement/operations.py:465` — `currency=currency or "INR"` as a PO default

  Each of these is a **default value on an overridable field**, not hardcoded logic that would break for
  a non-Indian merchant — a merchant onboarded with a different currency/timezone would simply pass a
  different value and everything downstream would work correctly. This is why it is classified **minor**,
  not **material** — but it is a real, findable instance of exactly the pattern the mandate's Section 2
  warns against ("India-specific behavior ... belongs in connectors, configuration, policy ... never in
  the canonical model itself"): the canonical `Merchant`/`PurchaseOrder` model's own *default* is
  India-shaped, rather than requiring every merchant (Indian or not) to specify it explicitly, or sourcing
  the default from merchant-configuration rather than a class-level Python default.

- No hardcoded threshold, policy, or location value was found in generic code — every threshold found
  (refund `automatic_limit`, return `window_days`, cancellation `before_fulfilment` mode) is read from
  `store.get_config(merchant_id)`, genuinely merchant-configurable.

---

## 18. Platform certification reality

| Platform | Connector exists? | Simulator exists? | Real local platform tested? | Sandbox tested? | Production merchant tested? | Mutation tested? | Webhook tested? | Reconciliation/read-back tested? | Certification label found | Code/tests support the label? |
|---|---|---|---|---|---|---|---|---|---|---|
| Shopify | Yes — `connectors/shopify_live/connector.py` (real GraphQL, discovers location gid live, per its own module docstring) + `connectors/shopify/connector.py` (a separate, simpler simulator-shaped connector) | Yes (`connectors/shopify/`) | Not applicable (Shopify has no self-hosted "local" mode) | Yes — `scripts/run_shopify_dev_store_certification.py` (real product create/readback/update, real inventory write, real webhook-triggered order, real duplicate-webhook idempotency, real fulfilment via `fulfillmentCreate`, real cancellation via `orderCancel`, real refund via `refundCreate`, real reconciliation call) | Not verified this pass (no evidence of a production-merchant run found, only the dev-store certification script) | Yes, per the script | Yes, per the script | Yes, per the script (`checks["reconciliation"]`, line 534) | Git commit history (`Initial commit: Sanocea Commerce OS - Shopify Dev Store certification PASS`, per this repository's own log) claims PASS | The script is real, structured for genuine live-platform proof (not a simulator), and its checks map directly to real GraphQL mutations with real IDs/error handling — **this audit did not re-execute the script against live credentials this session, so the *current* pass/fail state is `I — CANNOT VERIFY` as of today, though the script's own structure and the commit-history claim are consistent with a genuine past PASS** |
| WooCommerce | Yes — `connectors/woocommerce/connector.py` (real `urllib.request` HTTP calls, real HMAC/OAuth1 signing per `oauth1.py`) | Not separately found as a distinct simulator file (the real connector appears to be the only one) | Yes — `run_woocommerce_platform_independence.py` performs a real product/price/inventory/webhook/refund/cancel journey | N/A (WooCommerce is self-hosted, not a hosted sandbox tier) | Not verified this pass | Yes, per the script (lines 399-423) | Yes, including duplicate-replay idempotency (line 415) | Implied by the refund/cancel checks; not a separately named reconciliation step in this script | `_verdict()` function computes `PASS`/`CONDITIONAL_PASS`/`FAIL` from real check results (lines 429-436) | Same caveat as Shopify — real, structured, genuine; current pass state **I — not re-executed this session** |
| BigCommerce | Yes — `connectors/bigcommerce/connector.py` (real `urllib.request` calls) | Not separately found | Yes — `run_bigcommerce_sandbox_certification.py` | Yes, explicitly named "sandbox" in the script's own filename and checks (e.g. line 282's multi-location check) | Not verified this pass | Yes (fulfilment via Shipments API, cancellation, refund quote-then-execute — lines 383-425) | Yes (webhook-triggered order, duplicate-replay check, lines 333-372) | Yes (`checks["reconciliation"]`, line 431) | The mandate document (`README.md` Section 12) itself states "BigCommerce Partner application has been submitted; certification is externally blocked pending approval" | **This is the one clear case of a documented, honest, currently-open gap**: the script exists and is real, but per the mandate's own current status note, real sandbox access has not yet been granted — this audit's own review confirms the *code* is ready; the *certification* is honestly still pending, not falsely claimed complete |
| Amazon | No | No | N/A | N/A | N/A | N/A | N/A | N/A | None found | **G — no connector exists at all** |
| Flipkart | No | No | N/A | N/A | N/A | N/A | N/A | N/A | None found | **G** |
| Myntra | No | No | N/A | N/A | N/A | N/A | N/A | N/A | None found | **G** |
| Meesho | No | No | N/A | N/A | N/A | N/A | N/A | N/A | None found | **G** |
| Chatwoot | Yes — `connectors/chatwoot/connector.py` (real HMAC signature verification) | Not separately identified as distinct from the real connector | Real webhook headers constructed and posted in `run_phase46_integration_workload.py` (`_sign_chatwoot`, `_chatwoot_headers`) | Not applicable in the sandbox sense | Not verified this pass | Yes (`send_message` mutation, per Section 11) | Yes, including duplicate-delivery de-dup (Section 3) | N/A (not a financial reconciliation target) | No explicit "certification" label found for Chatwoot specifically | Real, working, well-tested against a real webhook-shaped payload structure — **B**, not **A**, since this audit found no evidence of a live Chatwoot account/inbox actually being used, only a correctly-signed synthetic payload |
| Payment provider (real gateway) | No | Yes (`SimulatedPaymentConnector`, `SimulatedSettlementProvider`) | N/A | N/A | N/A | Simulator-tested only | N/A | Simulator-tested only (Section 9) | None found | **C — real, deep simulator; no real gateway integration exists** |
| Courier/logistics | No | Yes (`SimulatedLogisticsConnector`) | N/A | N/A | N/A | Simulator-tested only | N/A | N/A | None found | **C** |
| Supplier | No (real supplier system) | Yes (`SimulatedSupplierConnector`, `SupplierSimulator`) | Yes — real local Postgres integration test (`tests/integration/test_phase4_procurement_real_infra.py`) | N/A | N/A | Simulator + real-local-infra tested | N/A | Yes, real local infra (Section 10) | None found | **C** for external-truth proof; **B** for the local-infrastructure proof specifically |

---

## 19. Gap register

| ID | Capability | Baseline priority | Current classification | Merchant impact | Dependency | Evidence | Recommended order |
|---|---|---|---|---|---|---|---|
| GAP-001 | Multi-location allocation/routing decision logic | P0 | **G** (no function exists at all, worse than "architectural only") | Every merchant with >1 fulfilment location silently mis-allocates or requires manual workaround | None — schema (`Inventory.location_ref`, `uq_inventory_merchant_sku_location`) is already correct and does not need to change | Section 4 | 1 |
| GAP-002 | Inventory reservation release on cancel/refund/return | Not separately named in the baseline's priority stack, but a prerequisite for the ATS/oversell claims the baseline treats as `LOCKED (need), STRONG EVIDENCE` | **G** | `reserved` drifts upward indefinitely; ATS math degrades over real cancel/return/refund volume | None — a straightforward addition to existing cancel/refund/return execution paths | Section 5 | 2 (should land before or alongside GAP-001, since correct ATS is a precondition for correct allocation) |
| GAP-003 | `PolicyEngine.decide()` is dead code; policy logic is independently reimplemented per operation | Not named in the baseline (a code-archaeology-only finding) | **F** for the named class; **B** for the actual (duplicated) capability | Low immediate merchant impact; real engineering-risk impact (drift between the three independent implementations as merchant config options grow) | None | Section 3 | 3 — low urgency, but cheap to fix before more operations are added with their own fourth reimplementation |
| GAP-004 | Bundles/kits/composites | P2 | **G** | Any merchant selling combo/gift-set offers cannot represent them at all today | Needs the canonical-model addition the baseline itself says is still being designed (parent/child SKU + assembly-timing attribute) | Section 6 | 5 |
| GAP-005 | Return → refund → inventory-consequence chain | Implied by differentiator F's "architectural scope, not separately proven" framing | **G** for the connecting logic (return acceptance does not trigger refund; neither triggers inventory restock) | A merchant's accepted return does not automatically produce a refund or restock — a human must separately notice and act on both | GAP-002 (restock logic) should land first | Section 16, trace (b) | 4 |
| GAP-006 | Split/merge/backorder/preorder order-lifecycle states | P2/P3 | **G**, unconditionally | Any merchant with partial-stock or duplicate-order scenarios has no system support | GAP-001/GAP-002 (location + reservation correctness) should land first, since split/backorder logic depends on accurate ATS | Section 7 | 6 |
| GAP-007 | Indian marketplace connectors (Amazon India, Flipkart first) | P1 | **G** | Zero India-marketplace merchants can be served beyond Shopify/WooCommerce/BigCommerce today | Connector-only work per the mandate's own connector/canonical split; no canonical-model blocker | Section 8 | 7 |
| GAP-008 | COD remittance / marketplace-fee-reconciliation connector work | P1 | **C** for the generic engine; **G** for any real feed | High-value, high-frequency merchant need once real COD/marketplace volume exists | GAP-007 (a marketplace connector must exist before its settlement feed can be ingested) | Section 8, Section 9 | 8 (after GAP-007) |
| GAP-009 | NDR/RTO full decision workflow (reattempt-vs-RTO choice, real courier) | P1 | **D**/**E** (real detection + reattempt only, simulator-proven) | High-cost Indian-logistics failure mode remains manually triaged beyond the one automated reattempt action | A real Indian courier connector (not in this gap register's current scope — courier selection is P2) | Section 7, Section 8 | 9 |
| GAP-010 | A real `AIProvider` implementation, Stage 1 (read-only) | P1 | **F** | Zero real AI capability exists anywhere; Sanocea cannot currently claim any AI-mediated capability truthfully | None — the `AIProvider` Protocol interface is already correctly designed and wired into `support/workflow.py` | Section 12 | 10 |
| GAP-011 | RBAC granularity beyond operator/service | P1 | **B** for the binary mechanism; **G** for granularity | Becomes load-bearing the moment >1 human role touches a merchant's account | None | Section 3 | 11 |
| GAP-012 | WhatsApp support connector | P1 | **G** | Real India-market communication-channel gap | None — the support-conversation model is already channel-agnostic by design, per the baseline's own claim (confirmed structurally plausible by `SupportWorkflowService`'s design, though not independently re-verified for true channel-agnosticism this pass) | Section 8 | 12 |
| GAP-013 | Exception auto-remediation (resolution-condition + general recheck scheduler) | P1 | **F**/**E** (real for the connector-mutation-retry subset only) | Real, recurring human-labor category (per every competitor audit's human-labor findings) remains unaddressed beyond one narrow mechanism | GAP-003 should probably be resolved first (a real, centralized policy/decision path makes "safe remediation" easier to reason about) | Section 13 | 13 |
| GAP-014 | Per-order/per-SKU profitability read model — COGS and shipping-cost input fields | P2 | **G** for two of seven required inputs (COGS-at-unit-of-sale, shipping/fulfilment cost); others already exist | Real, valued merchant need (per the Rithum audit) that cannot be built at all today for two of its seven inputs | GAP-007/GAP-008 (marketplace-fee data) for the other five inputs; a small, scoped canonical-model addition for the two missing ones | Section 15 | 14 |
| GAP-015 | `OperationalEvidence` generalization (currently 16 scattered `evidence_ref` fields) | P2 | **E** (real pattern, never unified) | Real, but lower urgency — the scattered pattern works today; unification is a maintainability/extensibility concern, not a broken capability | None blocking | Section 14 | 15 |
| GAP-016 | Multi-location reconciliation, inbound, and return-to-location semantics | P0-adjacent (a direct consequence of GAP-001) | **G** | Follows automatically once GAP-001 exists — currently moot | GAP-001 | Section 4 | Bundled with GAP-001's slice, not separately sequenced |

---

## 20. Implementation sequence

**No code is authorized by this document.** This is a proposed sequence for team review, following the
brief's own rules: architectural correctness before connector breadth; P0 before P1; boring commerce
correctness before AI; India-launch necessities before global-enterprise extras; never implement
DO-NOT-BUILD items; do not pull advertising into current scope; do not add complexity merely because a
competitor has it; preserve merchant independence.

### Slice 1 — Correct the single-location canonical model before anything else touches it

- **Objective:** make the existing `Inventory.location_ref`/`(merchant_id, sku, location_ref)` schema
  actually behavioral — a real allocation/routing decision, real reservation release, and real
  multi-location reconciliation — without changing the schema itself, which is already correct.
- **Gaps closed:** GAP-001, GAP-002, GAP-016.
- **Why now:** this is the P0 architectural blocker every one of the six competitor audits independently
  reconfirmed, and — per Section 4's finding — the actual code gap is more severe than the baseline's
  "architectural only" framing implied (no allocation function exists at all, not even a stub). Every
  later slice that touches inventory (bundles, split orders, courier selection, COD remittance) would
  otherwise be built on top of an inventory model that has never been pressure-tested with a second
  location or a working reservation-release path.
- **Dependencies:** none — the schema is ready.
- **Proof required before PASS:** a real test constructing two distinct `Inventory` rows for the same SKU
  at two different `location_ref` values, a real order allocated deterministically to one of them by an
  explicit rule (not a hardcoded default), and a real cancel/refund/return test asserting `Inventory.
  reserved` correctly decreases. This is the one slice where "proof" specifically means "prove the gap
  Section 4/5 found is closed," not merely "add a new feature."

### Slice 2 — Centralize policy decisions

- **Objective:** either make `PolicyEngine.decide()` the one real call path every `evaluate_*` method
  routes through, or deliberately retire the unused class and document that policy logic is intentionally
  per-operation — either is acceptable; the current silent drift between three independent
  reimplementations is not.
- **Gaps closed:** GAP-003.
- **Why now:** cheap, low-risk, and reduces the risk of the three implementations silently diverging as
  more merchant-config options are added in later slices (especially Slice 1's allocation-policy work,
  which will need its own decision logic and should not become a fourth independent reimplementation).
- **Dependencies:** none.
- **Proof required before PASS:** a single test asserting `evaluate_refund`, `evaluate_cancellation`, and
  `evaluate_return` all produce identical decisions for equivalent config inputs via one shared code path.

### Slice 3 — Close the return/refund/inventory consequence chain

- **Objective:** an accepted `Return` automatically produces its `Refund` (or an explicit, policy-gated
  proposal to do so) and, combined with Slice 1's reservation-release work, correctly restocks inventory.
- **Gaps closed:** GAP-005 (and depends on GAP-002 from Slice 1).
- **Why now:** this is the most concrete, checkable gap Section 16 found in differentiator F's own
  cross-domain-consequence claim — closing it directly strengthens Sanocea's single most-defended
  competitive claim with real, not merely architectural, evidence.
- **Dependencies:** Slice 1 (reservation-release logic must exist first).
- **Proof required before PASS:** a real test: create order → ship → return accepted → refund created
  automatically (or proposed via `Approval`) → inventory restocked → support's live status read reflects
  the new state, all in one continuous chain — the exact kind of trace Section 16 found missing.

### Slice 4 — India-first connector work (marketplace, then reconciliation, then WhatsApp)

- **Objective:** a real Amazon India or Flipkart connector (whichever proves more tractable first), then
  the COD-remittance/marketplace-fee reconciliation connector work that depends on it, then a WhatsApp
  support-channel connector.
- **Gaps closed:** GAP-007, GAP-008, GAP-012.
- **Why now:** sequenced after Slices 1-3 because a new marketplace connector built on top of an
  unproven multi-location model or an unproven return/refund/inventory chain would inherit both gaps
  immediately — better to fix the canonical-model correctness issues once, generically, than to discover
  them again specifically through an India-marketplace lens.
- **Dependencies:** Slice 1 (connectors will need to interact with a genuinely multi-location-aware
  allocation decision, not `"default"`).
- **Proof required before PASS:** the same real-platform certification discipline already proven for
  Shopify/WooCommerce/BigCommerce (Section 18) — real product/order/webhook/mutation/reconciliation
  checks against a real Amazon India or Flipkart sandbox, not a simulator.

### Slice 5 — A real `AIProvider`, Stage 1 only

- **Objective:** wire in one real model call for read-only diagnosis, exactly as the baseline's AI
  Roadmap Section 8 specifies — no mutation capability in this slice.
- **Gaps closed:** GAP-010.
- **Why now:** deliberately sequenced after the boring-commerce-correctness slices above, per the brief's
  own explicit ordering rule ("boring commerce correctness before AI") — and because Slice 1-3's fixes
  give a real `AIProvider` something genuinely correct to reason over, rather than diagnosing a canonical
  model with known, unfixed gaps.
- **Dependencies:** none technically, but ordered last among the "should happen soon" slices by design.
- **Proof required before PASS:** a real inference call, logged, auditable, read-only, answering a real
  "why did this happen" question over live canonical data — with cost/latency monitoring, per the
  baseline's own Stage 1 guardrail.

### Not sequenced — explicitly deferred, per the baseline's own DO-NOT-BUILD list

Bundles/kits (GAP-004), split/merge/backorder (GAP-006), full RBAC granularity (GAP-011), general
exception auto-remediation (GAP-013), the profitability read model (GAP-014), and `OperationalEvidence`
generalization (GAP-015) are all real, evidenced gaps — but none is P0, several depend on slices above
landing first, and none should be pulled forward merely because this audit found more evidence for them
than expected. Full WMS floor execution, a general ledger, a native courier network, an advertising
platform, and autonomous AI mutation without confirmation remain correctly excluded per the baseline's
Section 10 — nothing found this session changes any of those exclusions.

---

## 21. Executive verdict

**A. What Sanocea genuinely is today:** a real, working, single-location commerce-operations core with
three genuinely deep, independently-tested generic engines — finance reconciliation (dual-status,
13-state result taxonomy), procurement (13-state PO lifecycle, over-confirmation-capping, sequence-guarded
acknowledgement), and idempotency (release-on-failure, genuinely retry-safe) — proven against real
external storefront platforms (Shopify, WooCommerce, BigCommerce-pending-sandbox) but against nothing
else real: every payment, logistics, and supplier connector is a simulator, and support/customer
operations, while genuinely policy-gated and live-truth-reading, has never been proven as one continuous
chain from a support message through to an executed, reconciled mutation.

**B. What the baseline says it must become:** a merchant-independent Commerce OS with genuine
multi-location allocation, India-first marketplace/logistics/reconciliation depth, a canonical
cross-domain truth that produces real consequences across finance/inventory/procurement/support, and a
staged, safety-first AI capability — all while explicitly not becoming a WMS, an accounting system, a
courier network, or an advertising platform.

**C. Largest architectural gap:** multi-location allocation (GAP-001) — not merely unproven, as the
baseline itself frames it, but genuinely non-existent as callable code anywhere in the repository, while
the underlying schema is, encouragingly, already correct and does not need to change.

**D. Largest India-launch gap:** the complete absence of any Indian marketplace connector (Amazon India,
Flipkart, Myntra, Meesho all confirmed **G**) — every India-specific reconciliation/COD/NDR capability the
baseline prioritizes as P1 is blocked on this, since there is nothing yet to reconcile or ship orders
against.

**E. Strongest already-proven capability:** procurement (Section 10) — a genuinely mature, independently-
tested, sequence-guarded, over-confirmation-safe PO lifecycle with real disposition-typed goods receipt,
merchant-independent, and already answering P2 design questions (variance/damage fields) the baseline
treats as a future enhancement.

**F. Most overstated historical capability:** the "deterministic policy engine" as a singular,
centralized architectural component. `PolicyEngine.decide()` is real, tested-in-isolation code — and is
never called by anything in production. The *capability* it represents (config-driven, deterministic,
approval-gating decisions) is genuinely real and proven, reimplemented independently three times
(`_refund_decision`, `evaluate_cancellation`'s inline logic, `evaluate_return`'s inline logic) — but the
architecture-level claim of *one* policy engine every decision routes through does not hold up against the
actual call graph. This is a narrow, specific correction, not a broad indictment: every downstream
functional claim built on top of "Sanocea has a deterministic policy engine" (the baseline's Section 2
"Locked" architectural requirements, every competitor audit's differentiator-A discussion) remains true at
the *capability* level and should not be walked back — only the specific claim of centralization needs
correcting.

**G. Whether Differentiator F is real today or primarily architectural:** **both, precisely split by
domain, per Section 16's three traces.** Real and proven: procurement's own internal chain
(replenishment→PO→acknowledgement→receipt→inventory truth) and the financial leg of the order lifecycle
(order→refund→reconciliation→support-visible truth). Primarily architectural, not yet behaviorally proven:
the return→refund→inventory-consequence chain, which this audit found has literally no connecting code —
an accepted return does not currently cause its own refund or restock. Sanocea's claim to competitors is
correct in scope (no competitor researched combines these domains under one canonical model) and correct
in citing real proven instances — but should not claim every cross-domain consequence is proven, because
this audit found a specific, concrete one that is not.

**H. Recommended first implementation slice:** **Slice 1 — correct the single-location canonical model.**
Every other slice in Section 20, and every P1/P2 India-launch and profitability capability the baseline
prioritizes, is either directly blocked by or would inherit unproven assumptions from this gap. The schema
is already right; the work is entirely new deterministic-engine and policy code, which is the cheapest and
lowest-risk kind of gap to close first.

---

## 22. Addendum (2026-09-11) — Steps 1–6 implementation status

**This is an addendum, not a rewrite.** Everything above this line is the original read-only audit,
unchanged. Between that audit and this addendum, Steps 1–6 of the implementation roadmap were executed
(inventory reservation lifecycle, location-scoped inventory truth, deterministic whole-order allocation,
allocation concurrency/failure hardening, procurement location integration, end-to-end PO-line identity,
and a Step 6 cross-domain consolidation workload with a 16-point invariant sweep against real PostgreSQL).
Statuses below are assigned strictly from the code and tests those steps actually produced, not from
intent or design documents.

| Gap | Status | Evidence |
|---|---|---|
| GAP-001 — Multi-location allocation/routing decision logic | **CLOSED** (for the scope the baseline's P0 actually named) | `packages/post_order/allocation.py::rank_candidate_locations` + `PostOrderOperationsService._allocate_and_reserve_order` (Steps 3–4): deterministic priority-then-highest-ATS, whole-order-only allocation now exists, is real callable code, and is proven with real PostgreSQL concurrency (Steps 3, 4, 6). Distance/postcode/courier-cost routing and split/partial fulfilment were never part of this gap's P0 scope and remain unbuilt (see GAP-006). |
| GAP-002 — Inventory reservation release on cancel/refund/return | **CLOSED** | Step 1/1A: `InventoryReservation` ownership ledger, DB-atomic reserve/release/consume, `execute_cancellation` releases before fulfilment, `monitor_fulfilment` consumes at the correct signal, `progress_return`/RTO_DELIVERED restock correctly. Proven in Step 6's Part B/C workload and 16/16 invariant sweep. |
| GAP-003 — `PolicyEngine.decide()` dead code / reimplemented three times | **NOT YET ADDRESSED** | Explicitly out of scope for every step (PolicyEngine refactor was on every step's do-not-implement list). Unchanged from the original audit. |
| GAP-004 — Bundles/kits/composites | **NOT YET ADDRESSED** | Explicitly excluded from every step. Unchanged. |
| GAP-005 — Return → refund → inventory-consequence chain | **PARTIALLY CLOSED** | The return→inventory leg is now real: `progress_return(event="inspection_passed", restockable=True)` restocks physical inventory, proven in Step 6 Part C. The return→refund leg (an accepted return automatically creating/triggering a refund) still does not exist — Step 6 deliberately drove return and refund as two independent flows on separate orders (per Part C's explicit requirement that the two remain distinct events), and no connecting code was found or added. A human must still separately notice an accepted return and initiate its refund. |
| GAP-006 — Split/merge/backorder/preorder order-lifecycle states | **NOT YET ADDRESSED** | Explicitly excluded (split/partial fulfilment on every step's do-not-list). Unchanged. |
| GAP-007 — Indian marketplace connectors | **NOT YET ADDRESSED** | Explicitly excluded. Unchanged. |
| GAP-008 — COD remittance / marketplace-fee reconciliation | **NOT YET ADDRESSED** | Depends on GAP-007, which is unaddressed. Unchanged. |
| GAP-009 — NDR/RTO full decision workflow (reattempt-vs-RTO, real courier) | **NOT YET ADDRESSED** (RTO inventory semantics adjacent to it strengthened) | The RTO_DETECTED vs RTO_DELIVERED inventory-consequence distinction is now correct and proven (Step 1A, re-verified Step 6 Part C) — but that is inventory correctness, not the decision workflow this gap names (reattempt-vs-RTO choice, a real courier connector). No change to the actual gap. |
| GAP-010 — Real `AIProvider` implementation | **NOT YET ADDRESSED** | Explicitly excluded. Unchanged. |
| GAP-011 — RBAC granularity beyond operator/service | **NOT YET ADDRESSED** | Untouched by Steps 1–6. |
| GAP-012 — WhatsApp support connector | **NOT YET ADDRESSED** | Explicitly excluded. Unchanged. |
| GAP-013 — Exception auto-remediation | **NOT YET ADDRESSED** | Untouched. Step 6's own exception categories (ambiguous/unknown PO-line identity, wrong-location receipt, etc.) are new evidence sources for this future capability, not a step toward building it. |
| GAP-014 — Profitability read model | **NOT YET ADDRESSED** | Explicitly excluded. Unchanged. |
| GAP-015 — `OperationalEvidence` generalization | **NOT YET ADDRESSED** | Steps 1–6 added more scattered evidence (audit records, exception categories, `GoodsReceiptLine.purchase_order_line_id`, etc.) in the same ununified pattern the original audit described — consistent with existing style, not a step toward unification. |
| GAP-016 — Multi-location reconciliation, inbound, and return-to-location semantics | **PARTIALLY CLOSED** | Location-scoped inventory, confirmed inbound, goods receipt, and exact PO-line identity through the full procurement chain are real and proven (Steps 2, 5, 5A, 5B; Step 6 Part D feedback-loop proof). Return-TO-A-DIFFERENT-LOCATION routing specifically remains unimplemented — an explicit, disclosed simplification since Step 2 (returns/RTO always restock at the reservation's own original consumption location, never a merchant-chosen different return destination) — carried through unchanged. |

**New finding, not in the original GAP-001–016 register (Step 6):** `evaluate_cancellation` can put a
`Cancellation` into `status="approval_required"` when the merchant's `cancellations.before_fulfilment`
policy is `REQUIRE_APPROVAL` (the default), but **no `approve_cancellation` method exists anywhere in the
codebase** (`packages/post_order/operations.py`, `apps/api/app.py`, `packages/runtime/commands.py` all
searched — confirmed absent) — unlike the parallel `approve_refund`/`approve_purchase_order` methods that
do exist for refunds and POs. A cancellation that requires approval therefore has **no path to ever
become executable**: `execute_cancellation` only proceeds from `{"eligible", "approved"}`, and nothing in
the system can move a `Cancellation` into `"approved"`. This was discovered directly by Step 6's Part B
workload (order 4 could not be cancelled under the merchant's default policy) and worked around at the
harness level (temporarily configuring `ALLOW` for that one proof, restored immediately after) rather than
implemented, per the mandate's explicit instruction not to add capabilities during Step 6. This should be
added to the gap register as its own item in a future audit pass — it is a genuine, concrete, P0-adjacent
defect (the cancellation-approval flow is currently a dead end, not merely unproven), not a documentation
gap.

---

## 23. Addendum (2026-09-11, continued) — Steps 7A / 7A.1 / 7B

**GAP-005 — Return → refund → inventory-consequence chain: upgraded to CLOSED** (was PARTIALLY CLOSED
after Step 6). Step 7B added `evaluate_return_refund`, fired automatically from `progress_return`'s
"accepted" transition (`Return.status == "accepted"`, independent of `restockable`), creating a
`Refund` durably owned by the `Return` (`Refund.return_id`, DB-uniquely enforced via
`uq_refund_return_id`) and, for an ALLOW-policy decision, carrying it through the existing
`execute_refund` path automatically. The connecting code the original audit found missing ("an accepted
return does not currently cause its own refund or restock") now exists for BOTH consequences. One
narrower, separately-disclosed limitation remains and does not reopen this gap: `Return` has no
per-line/per-quantity representation in the canonical model (no `ReturnLine` entity), so a Return-
triggered refund always targets the order's whole remaining refundable amount, never a fabricated
partial-quantity calculation — see the Step 7B report for the full disclosure.

**Two genuine, concrete defects found and fixed while closing GAP-005, GAP-001-adjacent (cancellation)
and GAP-016-adjacent (procurement) work, not previously named in the gap register:**

- **Cancellation-approval dead end (flagged in the prior addendum) — now CLOSED.** Step 7A added
  `approve_cancellation`/`reject_cancellation`, closing the previously-nonexistent execution path for a
  `REQUIRE_APPROVAL`-gated cancellation. Step 7A.1 (real-Postgres investigation, unrelated to
  cancellation) additionally found and fixed a lost-update race in procurement's supplier-acknowledgement
  concurrency handling — see item below.
- **Procurement acknowledgement lost-update (Step 7A.1).** A real, reproduced Postgres race in
  `record_supplier_acknowledgement`'s sequence-staleness check could silently discard a legitimate,
  concurrent, distinct-sequence acknowledgement delta. Fixed with a new single-transaction primitive
  (`atomic_apply_acknowledgement`) and a corrected staleness rule (exact-sequence-reuse, not "any lower
  sequence than the highest applied"). This was a genuine defect in already-shipped Phase 4.1 concurrency
  guarantees, not a new capability — recorded here for completeness, not as a new gap register item, since
  it corrects (rather than extends) GAP-adjacent procurement concurrency claims already covered above.
- **Refund DENY status bug (Step 7B).** `evaluate_refund`'s status assignment previously collapsed
  `Decision.DENY` into the SAME `status="approval_required"` as `Decision.REQUIRE_APPROVAL`, but created
  no `Approval` object for it — a denied refund was left permanently stuck with nothing that could ever
  approve it. Fixed to assign a distinct, terminal `status="denied"`, mirroring the identical Step 7A fix
  already made for `Cancellation`'s DENY policy. Not a new gap register item (a correctness fix within the
  existing refund policy mechanism, not a missing capability).

---

## 24. Addendum (2026-09-11, continued) — Step 8: Pilot Readiness Prioritization (audit only, no implementation)

Step 8 is a read-only prioritization pass, not a feature step. This section reconciles the register
against Steps 7A/7A.1/7B/7B.1 and records the Part E/F investigative findings. No code changed as a
result of this section.

**GAP-005 — final reconciliation.** Step 7B.1 closed the one race Step 7B had disclosed as open (two
concurrent Returns on the same Order both computing "remaining refundable = full amount" and both
refunding it). `atomic_claim_refund_capacity` now locks the canonical `Order` row and treats every
non-`"denied"` `Refund` status (`permitted`, `approval_required`, `mutation_submitted`, `mutation_uncertain`,
`approved`, `completed`) as capacity-reserving, proven with real Postgres (19/20 over-refund reproduced
pre-fix, 0/N post-fix across bounded concurrent-harness runs). **GAP-005 remains CLOSED**, and its one
disclosed non-reopening limitation (whole-order-only refund amount, no `ReturnLine` partial-quantity
model) is unchanged and still deliberately out of scope.

**GAP-003 — `PolicyEngine.decide()` dead code — reconciled, status unchanged: OPEN.** Re-verified directly
against current code, not carried forward from a stale addendum: `PolicyEngine.decide()`
(`packages/policy_engine/engine.py`) is instantiated once (`PostOrderOperationsService.__init__`,
`self.policy = PolicyEngine()`) but **`.decide()` is never called anywhere in `packages/` or `apps/`** —
grep for `.decide(` across the whole tree matches only the engine's own definition and its own unit test
(`tests/unit/test_phase0_acceptance.py`). Every real decision site reimplements its own inline logic
independently, and — new observation this pass — **the reimplementations have already functionally
diverged from `decide()`, not merely duplicated it**:
- `evaluate_cancellation` (`post_order/operations.py:673`) — inline `mode` string comparison, no `Decision` enum use, no fulfilment-state check inside `PolicyEngine` at all (that check — `if order.fulfillment_status: status = "denied"` — exists only in the inline version).
- `evaluate_return` (`post_order/operations.py:830`) — inline `mode`/`auto_authorize` checks, structurally unrelated to `decide()`'s generic mode branch.
- `_refund_decision` (`post_order/operations.py:1347`) — the closest to `decide()`'s `"refund"` branch, but has strictly more invariants than it: `payment_status != "paid"` → DENY, `amount <= 0 or amount > order.total_amount` → DENY, and an optional `permitted_order_states` check, none of which exist in `PolicyEngine.decide()`. Routing refund decisions through `decide()` today would be a **regression**, not a simplification.
- `evaluate_po_authority` (`procurement/operations.py:369`) — an entirely different architecture (multi-factor reasoning trail, `_stricter()` escalation combinator over supplier-active/data-completeness/spend-threshold/reliability/cost-variance/unusual-quantity checks) that `decide()`'s single-branch shape could not express even in principle.

Verdict for Part F: **not a correctness blocker** — each site is independently tested and has been hardened through real fixes (Steps 7A/7B's DENY-status bug). **Is real, evidenced maintainability debt**: the identical DENY-collapses-into-REQUIRE_APPROVAL bug class had to be found and fixed *twice*, independently, in two different call sites (`evaluate_cancellation` in 7A, `evaluate_refund` in 7B) — exactly the kind of recurrence a single decision path would have prevented paying for twice. **Not currently a channel-scaling prerequisite**: each new merchant-config-driven decision so far has been cheap to add inline. Recommend keeping GAP-003 as a real, open, non-urgent item — worth doing before a *third* recurrence of the same bug class, not before pilot.

**Part E — `mutation_uncertain` trace (read-only; no recovery implemented).**

*Cancellation* (`execute_cancellation`, `post_order/operations.py:793-817`, backed by `_execute_logistics_command`, `:1256-1313`):
- **External ambiguity:** the shipment-cancel logistics call times out (`TimeoutError`) — the connector cannot tell whether the downstream carrier/3PL received and applied the cancel before or after the timeout.
- **Evidence retained:** the underlying `ConnectorCommand` row is written with `status="uncertain"` (distinct from `status="failed"` on a definite `RuntimeError`) — this distinction exists and is queryable one level below the top-level `Cancellation.status`, which collapses both outcomes into the same `"mutation_uncertain"` value.
- **Reconciliation/read-back today:** none automatic for cancellation — unlike `execute_refund` (below), `execute_cancellation`'s uncertain branch does not attempt an active read-back against the logistics provider before giving up.
- **Manual recovery possible today:** yes, but only by an operator manually inspecting the `ConnectorCommand` row and the carrier's own system — no in-product surfaced action exists to resolve a stuck `mutation_uncertain` Cancellation.
- **Can another execution accidentally duplicate the mutation:** the completion CLAIM (`atomic_transition_cancellation_status(..., "completed")`) is committed *before* the logistics call is attempted, then overwritten to `"mutation_uncertain"` on ambiguity — so the DB briefly shows `"completed"` before the true outcome is known, but no code path re-attempts the logistics cancel a second time for the same `Cancellation`, so no double-submission risk was found.
- **Operationally inconvenient or financially dangerous:** operationally inconvenient, not directly financially dangerous by itself (no money moves in cancellation) — but a `mutation_uncertain` cancellation whose shipment was actually NOT cancelled leaves the order in a state where inventory was already released and nothing is being shipped against that reservation, which is an inventory-integrity risk, not a payment one.

*Refund* (`execute_refund`, `post_order/operations.py:1040-1079`):
- **External ambiguity:** same shape — payment provider call times out.
- **Evidence retained:** the `Refund` row itself is the only record; no separate connector-command row was found for the payment leg the way `ConnectorCommand` exists for logistics.
- **Reconciliation/read-back today:** **better than cancellation** — the `TimeoutError` branch actively calls `self.payments.find_refund(...)` first, and only falls back to `status="mutation_uncertain"` if that lookup finds nothing. This is a genuine, already-working active reconciliation mechanism, not merely passive evidence retention.
- **Manual recovery possible today:** for the `TimeoutError`/uncertain path, the same `find_refund` lookup an operator or a future scheduled reconciler could re-invoke. For the `RuntimeError` path, `refund.status` is never updated at all — it stays at `"mutation_submitted"` (the value set just before the `try` block), which is a **weaker** signal than `"mutation_uncertain"`: an unequivocal failure (429/5xx) is currently indistinguishable, at the status level, from "still in flight."
- **Can another execution accidentally duplicate the mutation:** `execute_refund`'s executable-status guard set does not include `"mutation_uncertain"` or `"mutation_submitted"`, so a plain retry call is a no-op today (proven directly by this session's own tests) — no duplicate money-movement path was found for a retried call through the existing entrypoint.
- **Operationally inconvenient or financially dangerous:** **financially adjacent** — an uncertain/submitted refund correctly continues to consume the order's refund capacity (Step 7B.1), so it cannot be double-refunded through this system's own logic; the actual risk is the inverse (a genuinely-completed refund at the payment provider that never gets reconciled back to `"completed"` in Sanocea, leaving support/finance blind to it) rather than duplicate money movement.

**Summary judgment for Part E:** neither case is a live double-mutation bug — the concurrency and capacity work already proven (Steps 7A.1, 7B.1) independently prevents duplicate execution and double-refund. The real gap is **read-back completeness**: cancellation has no active reconciliation call at all (only passive `ConnectorCommand` evidence), and refund's `RuntimeError` branch loses status information a `TimeoutError` retains. Recommend treating "close the reconciliation loop for both mutation_uncertain families" as a real candidate item, not urgent for a controlled pilot with a human escalation fallback, but real technical debt.

**Part G — onboarding/config readiness (read-only).** `MerchantOnboardingService.onboard()`
(`packages/onboarding/merchant.py`) is a real, reachable surface, not aspirational: exposed through the
running app at `POST /admin/merchants` (`apps/api/app.py`), not a direct-service bypass. It sets, in one
validated call: merchant identity, currency/timezone, catalogue required-field/category rules,
publication approval mode, support auto-response toggles, refund policy (`automatic_limit`/`above_limit`),
return policy (`mode`/`window_days`), cancellation policy (`before_fulfilment`), SLA thresholds, finance
tolerances/expected-charges, procurement spending/cost-tolerance/reliability/priority/replenishment
config, channels (with `credential_ref`), raw credential secrets (`set_credential_ref`), and initial
supplier/SKU-offer mappings — with `_validate_config` blocking activation on structurally-broken input
(bad currency code, non-int limits, invalid `Decision` literals, unknown `supplier_priority` terms,
out-of-range reliability threshold) before anything is persisted. This is a genuine "configuration, not
code changes" onboarding path for the sections it covers.

**What has no onboarding surface today (confirmed absent, not merely unverified):** no concept of a
fulfilment **location**/warehouse anywhere in `onboarding/merchant.py` or its config shapes (consistent
with GAP-001/GAP-016 — `Inventory.location_ref` exists in the schema but nothing in onboarding lets a
merchant declare or configure locations); no settlement/payment-source or payout-account configuration;
no human-escalation-contact field; no explicit "support scope" beyond the two auto-response booleans
already listed. These would need direct database/developer setup today, not merchant-facing
configuration — consistent with, and does not reopen, GAP-001's existing P0 classification.
