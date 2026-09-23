# India quick-commerce direct-integration landscape — Step 9Q.6

Research only. No code, connector, simulator, domain change, or generic `MarketplaceConnector`/
`QuickCommerceConnector` change was made as a result of this step. See also
`quick-commerce-india-matrix.json` for the machine-readable version of the table in Part U.

## Evidence hierarchy used

LEVEL 1 = official developer/API documentation (platform-owned domain). LEVEL 2 = official vendor/seller
technical documentation. LEVEL 3 = official partner/onboarding documentation. LEVEL 4 = official
support/help material. LEVEL 5 = named mature integration-provider technical documentation (Unicommerce,
EasyEcom, Vinculum, Increff) — never promoted to a confirmed API contract. LEVEL 6 = other secondary
evidence (blogs, business-press coverage).

## Part B — the one cross-channel operating-model finding

**All six channels are vendor-PO-to-facility relationships, none is a marketplace-seller relationship.**
The merchant supplies bulk stock to a platform-designated dark store/facility via a purchase order the
*platform* issues; the platform controls facility allocation entirely; the platform's own riders/logistics
handle 100% of consumer-facing last-mile; no evidence anywhere of merchant involvement in consumer
returns; payment is against wholesale PO/invoice value (or, for Zepto, a hybrid with a category-dependent
commission layer — Level 6, unconfirmed at Level 5). This is confirmed directly for Blinkit, Zepto,
Swiggy Instamart, Flipkart Minutes, and BB Now; presumed but entirely unevidenced for Amazon Now. This is
the SAME role-inverted shape Step 9Q.2 first identified for Flipkart's HyperLocal program, now confirmed
across five independent channels — a real, load-bearing architectural fact, not a one-off.

## Channel-by-channel findings

### Blinkit — R5 (technical spec blocked despite real integration existing)

Re-verified directly this step. Unicommerce's own KB, re-fetched: "Supports Purchase Order (PO) sync via
PDF (.pdf) files only" [Level 5] — but ALSO confirms a real ASN mechanism: "ASN is generated post
dispatch (manifest closure). Blinkit will consider this as an acknowledgement of PO fulfillment" [Level
5] — real, but transport/schema unconfirmed. EasyEcom's competing claim (EDI + configurable webhook)
could not be re-verified this step (its KB page 404'd) — the discrepancy from Step 9Q.1 remains
unresolved, not newly confirmed either way. `partners.blinkit.com` is a real, Blinkit-owned domain
(confirmed) but login-gated (403) — its content (whether it offers an independent technology-partner
tier distinct from vendor-account access) could not be verified. Facility mapping: static vendor-JSON
[Level 5]. Settlement/GRN: explicitly none — "No status updates are triggered between UC and the
channel, or vice versa" [Level 5, re-confirmed]. **R5, not R3**: a partner-facing domain existing doesn't
establish that a usable technical spec becomes available even after onboarding — unlike Myntra (Step
9Q.5), where the official portal itself named specific, real business rules.

### Zepto — R6 (no direct route evidenced)

Re-fetched directly. Unicommerce, unchanged and re-confirmed: "No PO acknowledgment mechanism," "No ASN
functionality," "No status updates are triggered... in either direction" [Level 5]. No developer portal,
partner program, or any Zepto-owned technical documentation found on any domain. Facility mapping: same
static-JSON pattern [Level 5]. Operating model: Zepto issues POs from its own demand forecast against
vendor-committed capacity (a replenishment arrangement, not per-order) [Level 5]; payment is a
category-dependent commission (8-15%) on a weekly cycle [Level 6, unconfirmed at higher level] — this is
the one channel showing a possible hybrid PO+commission payment mechanic rather than a clean wholesale
invoice, worth re-confirming if this channel is ever pursued.

### Swiggy Instamart — R6 for vendor operations (best public developer program of any channel, but on the wrong side of the business)

Re-fetched directly. Unicommerce: PO delivery PDF-only; self-shipped ("shipping will be handled by the
seller"); seller-side cancellation explicitly not allowed; returns "designated for future implementation"
[Level 5]. One genuine positive finding, real and specific: **Instamart pushes cancellations INTO the
OMS** — the only confirmed inbound (channel→integrator) status-push behavior found across any of the six
channels researched [Level 5]. Swiggy's own public developer platform ("Builders Club," OAuth 2.1+PKCE,
named partner managers, enterprise SLAs) is real and technically mature [Level 3/4] but is confirmed
consumer-facing (AI agents ordering as a customer) — must never be read as vendor/seller-API evidence,
per the explicit caution carried forward from Step 9Q.1.

### Flipkart Minutes — R3 (partner onboarding required, for the unimplemented leg only)

**Do not assume the existing Flipkart connector's HyperLocal implementation covers Minutes end to end —
it covers exactly one leg of it, correctly.** Fresh research this step confirmed the operating model
directly: "Selected sellers are mapped to the nearest Flipkart Minutes dark stores... inventory PO is
raised at SKU level," "sellers dispatch stock to Flipkart Minutes dark stores with inwarding fees...
SLA of 48 hours from PO to dispatch" [Level 5/6]. This CONFIRMS the HyperLocal catalogue/inventory/pricing
endpoints already implemented in `connectors/flipkart/connector.py` (Step 9Q.2, Level 1 confirmed:
`/listings/v3/hyperlocal`, `/hyperlocal/update`, `/hyperlocal/update/inventory`, `/hyperlocal/update/price`)
represent the **replenishment-declaration leg** of a vendor-PO relationship — a vendor telling Flipkart
what/how much it can supply to a specific dark-store location — not a live marketplace listing the way
main-Flipkart-Seller-API listings work. **We do not accidentally possess the order/fulfilment/GRN/
settlement leg** — no HyperLocal-specific order, dispatch-confirmation, GRN, or settlement endpoint was
ever found (Step 9Q.2 marked these UNCONFIRMED, and nothing in this step's research changed that). That
leg would need the same role-inverted architecture as Blinkit/Zepto/Instamart, not a reuse of the main
Flipkart connector's `sync_orders`/`OrderLine` methods (which read CONSUMER marketplace orders via
`/sellers/v3/shipments/filter` — the wrong shape/direction entirely for a PO-driven replenishment flow).
Access route for the missing leg: the same Flipkart Partner Dashboard registration already used for the
main Seller API (Step 9Q.2) — no evidence of a SEPARATE Minutes-specific partner tier.

### Amazon Now — R6 (no evidence found anywhere; confirmed NOT covered by the existing Amazon connector)

No Amazon Now-specific technical surface was found, official or secondhand, beyond one unverifiable
"Amazon Today" mention in a single integrator's marketing page (Step 9Q.1, never independently
confirmed). This step found and directly confirmed a real, separate, official Amazon program — **Vendor
Direct Fulfillment (VDF)** — `getOrders`/`getOrder`/`submitAcknowledgement` endpoints
(developer-docs.amazon.com/sp-api/docs/vendor-direct-fulfillment-orders-api, Level 1) — a genuine
PO-received/ack-required vendor pattern, structurally exactly the shape this step's target chain
describes. **Directly confirmed from its own official documentation that VDF is NOT Amazon Now** — no
mention of dark stores, local fulfilment, or rapid delivery anywhere; it is a general B2B drop-ship
vendor program. **No capability from the existing Amazon SP-API connector (Step 9Q.3) is reusable for
Amazon Now** — the connector's entire surface (Listings Items, Orders v0, FBA Inventory, Notifications,
Feeds, Reports, Finances) is built for the marketplace-seller relationship, categorically different from
whatever Amazon Now's (unevidenced) vendor-PO relationship would require. VDF is worth remembering as a
*pattern reference* (real evidence that Amazon's own vendor-ack contract shape exists somewhere in their
ecosystem) should Amazon Now's real contract ever surface, but it is not that contract.

### BigBasket (main) — R6; BB Now — R6

No technical documentation of any kind was found for BigBasket's main (non-quick-commerce) business —
not even a secondhand OMS-integrator page. The ONE real technical document found — Unicommerce's "BigBasket
| QuickCommerce" KB page [Level 5] — covers **BB Now specifically** ("Bigbasket is available in Uniware
under Quick Commerce service"), not the main business. BB Now: PO delivery via email + Excel to
Unicommerce's own parsing inbox; B2B/COD order type; self-shipped; catalogue sync explicitly not
automatic; no PO ack, ASN, or GRN ("No status updates are triggered... in either direction"); facility
mapping is the same static-JSON pattern; access is gated at **Unicommerce's own Enterprise Seller tier**
— a restriction on Unicommerce's customer tier, not evidence of a BigBasket-side partner program Sanocea
could approach directly. BB Now is confirmed (Level 6, business press) to reuse BigBasket's existing
warehouse/dark-store network and last-mile fleet operationally, and to repurpose other Tata retail
outlets (Croma, 1mg) as additional dark stores — but whether the *vendor integration mechanism* is shared
with BigBasket-main remains unconfirmed either way, since no main-business integration documentation
exists at all to compare against.

## Part C/G/H/I — cross-channel facility, GRN, settlement, and returns findings

- **Facility model:** every channel with any evidence at all shows the identical pattern — a static,
  vendor-maintained pincode/supplier-code→facility-code JSON, entered once, never fetched live from a
  platform API (Flipkart Minutes' `location.id`, obtained once via a separate Onboarding API, is the one
  partial exception — still not a live per-call lookup). **This validates Sanocea's existing
  `Inventory.location_ref` + `ExternalIdMapping` model rather than breaking it** — no new first-class
  `Location`/`Facility` entity is evidenced as necessary; the existing free-string `location_ref` +
  external-mapping pattern already represents exactly what every evidenced channel actually does.
- **GRN: zero evidence across all six channels.** No platform anywhere was found to expose goods-receipt,
  accepted/rejected/shortage/damage quantities, or discrepancy reasons programmatically.
- **Settlement: zero API evidence across all six channels.** The single strongest cross-channel finding
  of this entire step. Where anything exists at all (BigBasket's vendor portal), it is a finance/
  procurement self-service portal (payment status, e-invoice upload), not a settlement data feed.
- **Returns/RTV: essentially unevidenced everywhere.** Instamart's explicit "designated for future
  implementation" is the only concrete statement found anywhere across all six channels.

## Part R — architecture gap audit (no code changed)

| Sanocea concept | Classification | Reasoning |
|---|---|---|
| `Product`/`Variant` | REUSABLE AS-IS | Catalogue identity is channel-neutral regardless of vendor-PO vs marketplace model. |
| `ExternalIdMapping` | REUSABLE AS-IS | Validated by the consistent facility/vendor-code mapping pattern across every evidenced channel. |
| `Inventory.location_ref` / multi-location truth | REUSABLE AS-IS | Directly validated — see facility-model finding above. Quick commerce confirms, does not break, the existing multi-location architecture. |
| `PurchaseOrder` | ROLE-INVERTED | Confirmed across five of six channels: the merchant is the VENDOR receiving a PO, not the buyer issuing one — same finding as Step 9Q.2, now reconfirmed at category scale. |
| `SupplierAcknowledgement` | ROLE-INVERTED | Modeled as "the supplier's ack of a PO we sent" — the mirror image (our ack of a PO the platform sent us) is needed, not this entity directly. |
| `InboundShipment`/`GoodsReceipt` | ROLE-INVERTED | These model goods coming INTO the merchant from a supplier; the quick-commerce ASN/GRN direction is OUTBOUND (merchant→platform), and the GRN is recorded BY THE PLATFORM — the merchant may never see a formal GRN object at all, only its downstream settlement consequence. |
| `Order`/`OrderLine` | GENERIC QUICK-COMMERCE GAP / UNKNOWN UNTIL SPEC | No channel evidences a vendor-visible consumer order at all — once GRN'd, the platform fulfils from its own facility-level stock with zero merchant visibility into the individual consumer order. The vendor-side interaction may never touch a consumer-order concept at all; it may be entirely replenishment-PO-shaped end to end. Cannot be resolved without a real contract. |
| `Fulfilment`/`Shipment` | ADAPTER-LOCAL (tentative) | Plausibly reusable for the vendor's own outbound dispatch-to-facility leg (conceptually similar to existing `Shipment`, destination is a platform facility not a consumer address) — not confirmed, no schema exists yet to test the fit against. |
| `Return`/`RTO` | UNKNOWN UNTIL SPEC | Almost no evidence anywhere; cannot classify. |
| `PaymentObservation`/`SettlementBatch`/`SettlementEntry`/`FinanceReconciliation` | GENERIC QUICK-COMMERCE GAP (model shape, not code, is fine) | The existing batch+entry+reconciliation shape is structurally adequate for whatever settlement data eventually surfaces — there is simply nothing evidenced to map into it yet for any of the six channels. |
| `ConnectorCommand`/`ExceptionRecord`/`AuditEvent` | REUSABLE AS-IS | Channel-neutral infrastructure; no mismatch found. |

**No canonical domain change is proposed or was made.** The one open architectural question worth
naming precisely (not resolving): whether a future `ChannelPurchaseOrder`/`VendorOrder`-shaped canonical
object is needed for the platform-issues-PO-to-merchant-as-vendor direction, or whether a sufficiently
role-aware adapter over the *existing* `PurchaseOrder` shape (flipping which party plays which role) would
suffice — this cannot be decided without a real contract for at least one channel's PO/ack/ASN/GRN
lifecycle, and is explicitly deferred, per this step's "no domain change" instruction.

## Part S — connector-family decision: D (defer)

Neither a `MarketplaceConnector` subclass (the semantics are categorically different — PO-received vs.
order-received, ack vs. no ack, platform-controlled facility allocation vs. seller-controlled listings)
nor a new generic `QuickCommerceConnector` (would be built from evidence that is mostly absent — five of
six channels have essentially no confirmed contract at all) is justified right now. Flipkart Minutes'
already-implemented catalogue/inventory/pricing leg sits fine as an extension of the *existing*
`FlipkartConnector` — proving that even where quick commerce DOES have a real contract, it hasn't needed
a new abstraction to be represented correctly. Building a generic abstraction now would violate
"abstraction follows evidence." **Build directly against whichever channel's real contract arrives
first, once one does.**

## Part T — truthful Medconic answer

- **CAN HANDLE NOW:** nothing, for any of the six channels' quick-commerce vendor operations.
- **CAN HANDLE WITH MERCHANT ACCESS + CONFIGURATION:** Flipkart Minutes catalogue/inventory/pricing sync
  only, if the merchant has (or obtains) HyperLocal-enabled Flipkart Partner credentials — genuinely
  ready today, already built and tested (Step 9Q.2).
- **REQUIRES NEW CONNECTOR ENGINEERING:** the full PO/ASN/GRN/settlement lifecycle, for every one of the
  six channels, once a real contract exists for any one of them.
- **REQUIRES CHANNEL APPROVAL/SPEC:** Blinkit (resolve the partner-account/PDF-vs-EDI ambiguity),
  Flipkart Minutes (the order/fulfilment/GRN/settlement leg specifically — same Partner Dashboard route
  as the existing connector).
- **MUST REMAIN HUMAN/PORTAL FOR NOW:** Zepto, Swiggy Instamart, Amazon Now, BigBasket/BB Now in full,
  and settlement/reconciliation for every one of the six channels without exception — this is the
  category's single biggest, most consistent gap.

## Part V — ranked implementation priority and recommendation

1. **Flipkart Minutes** — partial contract already proven and implemented; smallest remaining gap of
   any channel.
2. **Blinkit** — best-evidenced unimplemented channel (real ASN mechanism, real partner-facing domain);
   R5, one clarifying conversation away from R2/R3.
3. **Amazon Now** — a real vendor-ack pattern (VDF) exists somewhere in Amazon's ecosystem to learn from,
   even though it doesn't apply directly; worth a direct question to Amazon once Amazon Now matures publicly.
4. **BigBasket/BB Now** — real vendor-PO relationship confirmed, but zero bidirectional machine interface
   and access gated behind a third party's own customer tier.
5. **Zepto** — no official documentation of any kind; weaker than Blinkit/BigBasket on every dimension.
6. **Swiggy Instamart** — ironically has the most technically mature PUBLIC developer program of the six,
   but confirmed to be the wrong side of the business (consumer, not vendor) — do not mistake platform
   sophistication for vendor-API depth.

**Recommendation: NONE — no channel has a complete, legitimately obtainable technical contract for the
PO/ASN/GRN/settlement lifecycle.** Implementing any of the six now would repeat exactly the fabrication
risk this research track exists to prevent (the lesson carried forward explicitly from Step 9Q.4's
Meesho outcome).

**Exact next access/spec action:** pursue Blinkit partner-account access via `partners.blinkit.com`,
specifically to resolve the PDF-vs-EDI/webhook PO-transport discrepancy and confirm whether a vendor's
webhook target is genuinely third-party-configurable — **in parallel**, ask Flipkart (through the same
channel that already yielded the confirmed HyperLocal contract) for the Minutes-specific order/
fulfilment/GRN/settlement endpoints, since the catalogue/inventory/pricing leg is already proven and this
is the smallest remaining gap of any channel researched. Either path converts a partial R3/R5 into R1/R2
faster than starting fresh with any R6 channel. No email has been sent as part of this step.
