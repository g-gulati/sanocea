# Ajanta Soya Multi-Channel Ecommerce Operations Audit

Date: 2026-09-16  
Mode: read-only, evidence-first, adversarial QA  
Purpose: commercial due diligence for SANOCEA  

## A. Executive Summary

This audit reviewed Ajanta Soya / Anchal's publicly observable ecommerce footprint without login, cart placement, account creation, contacting marketplaces, or bypassing access controls.

The operation is not visibly chaotic. The most reliable public evidence shows an active official Ajanta Soya website/store and active JioMart product pages. Amazon, Flipkart, and Blinkit presence is discoverable through search-engine and indexed marketplace evidence, but product-detail verification was limited by dynamic marketplace rendering and/or generic landing responses. BigBasket, Zepto, Swiggy Instamart, Meesho, and ONDC were not confirmed as active from reliable public product pages during this pass.

The audit identified 5 defensible official-site catalogue/control issues and 2 marketplace/public-data observations requiring internal verification. The strongest finding is that free-gift products are publicly exposed as in-stock, zero-price, purchasable products on the official WooCommerce catalogue; one free-gift page exposes both "Add to cart" and "Buy now" buttons for a zero-price product.

This does not prove human failure or employee incompetence. It does show the type of repetitive catalogue-control drift that can persist in a manually monitored multi-channel operation and that systematic monitoring could detect.

## B. Methodology

- Public web search across official site, Amazon India, Flipkart, BigBasket, Blinkit, Zepto, Swiggy Instamart, JioMart, Meesho, ONDC-visible search, and B2B references.
- Public official-site crawl through normal URLs.
- Public WooCommerce Store API extraction from `https://ajantasoya.com/wp-json/wc/store/products?per_page=100`.
- Public JioMart product-page fetch and structured-data extraction.
- No login, order placement, account creation, cart mutation, private API access, CAPTCHA bypass, rate-limit evasion, or contact with Ajanta/marketplaces.

Evidence saved under `docs/audits/ajanta_evidence/`:

- `official_wc_store_products_raw.json`
- `official_wc_store_products_summary.json`
- `official_page_fetch_summary.json`
- `jiomart_fetch_summary.json`
- raw official/JioMart HTML captures
- extracted JioMart JSON-LD files

Screenshot note: local browser screenshot tooling was not available (`playwright` was not installed). Raw HTML and JSON evidence were preserved instead.

## C. Channel Footprint

| Channel | Status | Control assessment | Evidence |
|---|---:|---|---|
| Official website / owned ecommerce store | CONFIRMED ACTIVE | Official/brand-controlled | `https://ajantasoya.com/`, official site states Ajanta Soya Limited and has Shop navigation; public shop page lists products and prices. |
| Amazon India | HISTORICAL / UNCERTAIN | Search-discovered; likely official merchant page, but direct product verification limited | Search results showed "Ajanta Soya Limited Store" and Anchal products; direct open returned generic Amazon shell. |
| Flipkart | HISTORICAL / UNCERTAIN | Search-discovered; seller/control not verified | Search results showed Anchal product pages for Soyabean 5L and Sunflower 1L. Direct product fields were not reliably extracted. |
| JioMart | CONFIRMED ACTIVE | Marketplace listing; Ajanta control not proven | Public product pages returned JioMart HTML and JSON-LD for Anchal Soyabean combo and Sunflower pack-of-6, both marked InStock. |
| Blinkit | HISTORICAL / UNCERTAIN | Search snippet only | Search result snippet referenced Anchal Refined Soyabean Oil, but opened page did not provide reproducible product details. |
| BigBasket | NOT FOUND | No confirmed active page | No reliable active Anchal/Ajanta product page found. |
| Zepto | NOT FOUND | No confirmed active page | No reliable active Anchal/Ajanta product page found. |
| Swiggy Instamart | NOT FOUND | No confirmed active page | No reliable active Anchal/Ajanta product page found. |
| Meesho | NOT FOUND | No confirmed active page | No reliable active Anchal/Ajanta product page found. |
| ONDC-visible stores | NOT FOUND | No confirmed active public page | No reliable public ONDC listing found. |
| IndiaMART / TradeIndia | HISTORICAL / UNCERTAIN | B2B/distributor-style reference, not retail channel proof | TradeIndia search result referenced Ajanta Soya Anchal mustard oil, not treated as retail marketplace defect evidence. |
| Instagram/Facebook | CONFIRMED BRAND PRESENCE | Marketing/social only | Public snippets reference Ajanta Oils and availability on Amazon/Flipkart/JioMart; used only as supporting footprint context. |

## D. Catalogue Map

Official WooCommerce Store API observed 9 product records:

| Product | Type | SKU | Public price/MRP representation | Availability |
|---|---|---:|---:|---|
| Anchal Kachi Ghani Mustard Oil | variable | `PKGMO-3` | From Rs 236; regular Rs 250; range up to Rs 1005 | purchasable, in stock |
| Anchal Refined Soyabean Oil | variable | `NRSO-2` | From Rs 136; regular Rs 150; range up to Rs 968 | purchasable, in stock |
| Anchal Refined Sunflower Oil | simple | `NRSO-4` | Rs 196; regular Rs 240 | purchasable, in stock |
| Buy 5L Mustard Oil Jar, Get 1L Soyabean Oil Bottle Free | simple | `NRSO-704` | Rs 1000; regular Rs 1500 | purchasable, in stock |
| Buy 5L Soyabean Oil Jar, Get 1L Mustard Oil Bottle Free | simple | `NRSO-702` | Rs 972; regular Rs 1450 | purchasable, in stock |
| Buy 5L Soyabean Oil Jar, Get 1L Sunflower Oil Bottle Free | simple | `NRSO-703` | Rs 996; regular Rs 1440 | purchasable, in stock |
| Mustard Oil Offer | simple/free gift | `PKGMO-1-1` | Rs 0 | API says purchasable, in stock |
| Soyaben Oil Offer | simple/free gift | `NRSO-1-1` | Rs 0 | API says purchasable, in stock |
| Sunflower Oil Offer | simple/free gift | `NRSO-1-2` | Rs 0 | page and API say purchasable, in stock |

Official variant records observed:

- Mustard: 1L Bottle, 5L Jar, plus malformed variation id `27952` with `Size = null`.
- Soyabean: 700gm Value Pack, 1L Bottle, 5L Jar.
- Sunflower: 1L Bottle.
- Combo/free-gift constructs: 6 simple offer records.

JioMart structured product records verified:

- Anchal Refined Soyabean Oil 5 Ltr Jar with 1 Ltr Bottle Combo.
- Anchal Refined Sunflower Oil 1 Litre Bottle, Pack of 6.

Additional marketplace records observed only through snippets/search indexing:

- Amazon: Anchal Dil Se Fit Refined Soyabean Oil 700g pouch pack-of-12; Anchal 1L bottle; Sunflower-related ASIN pages.
- Flipkart: Anchal Refined Soybean Oil 5L jar; Anchal Fortified Refined Sunflower Oil 1L.
- Blinkit: Anchal Refined Soyabean Oil snippet.

## E. Canonical Matching Strategy

Matching used deterministic fields only:

- Brand token: `Anchal` / Ajanta Soya context.
- Oil type: mustard / soyabean / sunflower.
- Pack form and quantity: 700g, 1L, 5L, pack-of-N, combo/free bottle.
- Official SKU only where exposed.
- Exact title and product-family matching where SKU/barcode was absent.

Confidence rules:

- HIGH: same brand, same oil type, same unit/pack, same role as standalone/combo, and direct page evidence.
- MEDIUM: same brand/product family but different multipack/combo arrangement or incomplete marketplace fields.
- LOW: search snippet only or reseller/control ambiguity.

No LOW-confidence match is used to claim a defect.

Cross-channel exact SKU matches: 0, because marketplace SKUs/GTINs were not exposed.  
High-confidence product-family matches: 2, official sunflower 1L family to JioMart sunflower pack-of-6; official soyabean 5L/1L family to JioMart soyabean combo.

## F. Findings

### AJ-WEB-001: Free-gift product exposed as a zero-price purchasable product

| Field | Value |
|---|---|
| Channel | Official website |
| Product/SKU | Sunflower Oil Offer / `NRSO-1-2` |
| Category | Pricing / availability / catalogue control |
| Severity | HIGH |
| Confidence | HIGH |
| Publicly defensible | Yes |
| Evidence | `html__ajantasoya_com__product__buy-one-sunflower-oil-get-1l-free.html`; `official_wc_store_products_summary.json` |
| Observed values | Page title "Sunflower Oil Offer"; price "Free"; stock "109 in stock"; schema price `0.00`; availability `InStock`; visible "Add to cart" and "Buy now" buttons; API `is_purchasable: true`, price `0`. |
| Expected basis | Free-gift products should normally be gated by the qualifying paid bundle, not publicly purchasable as standalone zero-price products. |
| Why it matters | If checkout allows continuation, this can create free-order leakage, customer confusion, fulfilment exceptions, or promotional abuse. Even if downstream checkout blocks it, public catalogue state is misleading. |
| Likely detection method | Deterministic automation |
| Automated check | `price == 0` AND `is_purchasable == true` AND `availability == InStock` AND title contains offer/free-gift semantics |
| Exception generated | "Zero-price purchasable product requires promotion-rule review." |
| Human decision required | Yes, merchandising/commerce owner should confirm intended gating. |
| Recommended action | Hide free-gift simple products from public catalogue/search or enforce cart-rule-only availability; monitor zero-price purchasable SKUs daily. |

Related lower-confidence extension: `Mustard Oil Offer` and `Soyaben Oil Offer` are also zero-price and API-purchasable, but their direct product URLs redirected to the home page in this capture. They should be reviewed with the same control.

False-positive challenge: This could be deliberate WooCommerce promotion-engine setup. It remains a defensible public issue because one free-gift URL renders a public product page with stock, zero price, add-to-cart, and buy-now controls.

### AJ-WEB-002: Variable mustard product contains a malformed null-size variation

| Field | Value |
|---|---|
| Channel | Official website |
| Product/SKU | Anchal Kachi Ghani Mustard Oil / `PKGMO-3` |
| Category | Catalogue quality / variant structure |
| Severity | MEDIUM |
| Confidence | HIGH |
| Publicly defensible | Yes |
| Evidence | `official_wc_store_products_summary.json` lines containing variation id `27952`; official product page shows valid public options 1L Bottle and 5L Jar only. |
| Observed values | Variation id `27952` has attribute `Size: null`; same product also has valid 5L and 1L variations. |
| Expected basis | Every active variant on a variable product should have a valid, selectable pack-size attribute. |
| Why it matters | Null variants can create stale/orphan variants, wrong default behaviour, feed-export problems, channel sync errors, and approval/catalogue ambiguity. |
| Likely detection method | Deterministic automation |
| Automated check | For every variable product, reject or exception any active variation with null/blank variation-defining attributes. |
| Exception generated | "Malformed product variant: missing Size." |
| Human decision required | Usually no for detection; yes to delete/archive or repair. |
| Recommended action | Remove/archive variation `27952` or assign correct size after internal verification. |

False-positive challenge: The null variant may be a disabled/internal placeholder. The public Store API still exposes it as part of the product variation list, so it remains a legitimate catalogue-control finding.

### AJ-WEB-003: Variant-specific physical attributes are ambiguous on variable products

| Field | Value |
|---|---|
| Channel | Official website |
| Product/SKU | Mustard `PKGMO-3`; Soyabean `NRSO-2` |
| Category | Catalogue attributes / shipping data |
| Severity | MEDIUM |
| Confidence | MEDIUM |
| Publicly defensible | Yes, as a possible issue needing internal verification |
| Evidence | Official product pages and Store API. Mustard and Soyabean pages expose variants including 1L/700gm/5L, while parent product details show Weight `4550 g` and Dimensions `19 x 9.5 x 29 cm`. |
| Observed values | A parent variable product displays one physical weight/dimension set despite multiple pack sizes. |
| Expected basis | Physical shipping/compliance attributes should be variant-specific or clearly labelled as applying only to a selected/default variant. |
| Why it matters | Shipping cost, warehouse handling, marketplace feeds, customer expectations, and dimensional-weight calculations can be wrong if the parent value is exported for all variants. |
| Likely detection method | Rule-based monitoring |
| Automated check | For variable products with size terms representing materially different quantities, require variant-level weight/dimension fields or explicit default-labeling. |
| Exception generated | "Variable product has non-variant physical dimensions." |
| Human decision required | Yes, because internal WooCommerce variation records may still carry correct hidden values. |
| Recommended action | Verify variation-level weights/dimensions; expose or export only variant-specific values. |

False-positive challenge: The storefront may display the selected default variant's attributes. Because static public HTML/API does not prove channel exports are wrong, this is classified as possible issue requiring internal verification, not a high-risk defect.

### AJ-WEB-004: Soyabean product gallery/API includes sunflower-labelled image metadata

| Field | Value |
|---|---|
| Channel | Official website |
| Product/SKU | Anchal Refined Soyabean Oil / `NRSO-2` |
| Category | Content / image metadata |
| Severity | LOW |
| Confidence | HIGH |
| Publicly defensible | Yes |
| Evidence | `official_wc_store_products_summary.json` product `Anchal Refined Soyabean Oil` image list includes image name and alt: "Anchal Sunflower oil is rich in omega-6 and is lightweight." |
| Observed values | Soyabean product has sunflower-labelled image metadata. |
| Expected basis | Product-gallery image names/alt text should match the product identity. |
| Why it matters | Accessibility, SEO, feed enrichment, image selection automation, and marketplace content exports can drift when image metadata references a different product. |
| Likely detection method | AI-assisted review plus deterministic product-token comparison |
| Automated check | Product type token `soyabean` conflicts with image metadata token `sunflower`. |
| Exception generated | "Image metadata may reference another product." |
| Human decision required | Yes, review whether the image itself is wrong or only metadata is wrong. |
| Recommended action | Correct image metadata or remove wrong image from soyabean gallery. |

False-positive challenge: Could be a shared brand image rather than product image. Still public metadata conflicts with the product identity and is safe to discuss as content-quality drift.

### AJ-WEB-005: Repeated public spelling/catalogue hygiene issues

| Field | Value |
|---|---|
| Channel | Official website |
| Product/SKU | Multiple official products |
| Category | Content quality |
| Severity | LOW |
| Confidence | HIGH |
| Publicly defensible | Yes |
| Evidence | Official product pages show `Coutry of Origin`; product/API records include `Soyaben Oil Offer`; mustard image metadata includes `Byu Mustard Oil 1L Bottle`. |
| Observed values | Repeated typos in product-detail labels and product/media names. |
| Expected basis | Public product catalogue labels and offer names should be clean and professionally spelled. |
| Why it matters | Low direct commercial risk, but indicates catalogue-maintenance drift and can affect customer trust, SEO, and feed exports. |
| Likely detection method | AI-assisted review and dictionary/token checks |
| Automated check | Known-field labels and product/media names scanned for likely typos. |
| Exception generated | "Catalogue text hygiene issue." |
| Human decision required | Usually no for obvious spelling corrections; yes before changing product names. |
| Recommended action | Correct public labels and media titles; add a spelling/content lint check before publishing. |

False-positive challenge: Some terms may be brand/internal names. `Coutry` and `Byu` are sufficiently likely typos; `Soyaben` may be an internal typo or intentional shorthand, so it should be corrected only after confirmation.

### AJ-MKT-001: JioMart structured product data has empty price fields despite InStock availability

| Field | Value |
|---|---|
| Channel | JioMart |
| Product/SKU | Anchal Soyabean combo; Anchal Sunflower pack-of-6 |
| Category | Marketplace structured data / price representation |
| Severity | INFO |
| Confidence | MEDIUM |
| Publicly defensible | Yes as observation, not Ajanta-controlled defect |
| Evidence | Extracted JioMart JSON-LD files under `docs/audits/ajanta_evidence/`; JSON-LD shows `availability: https://schema.org/InStock` while `price` and `priceCurrency` are empty in first Product block. |
| Observed values | Public structured data marks products InStock but leaves price fields blank. |
| Expected basis | Product structured data normally includes price and currency where publicly sellable. |
| Why it matters | SEO/merchant-feed quality and price monitoring may be less reliable. |
| Likely detection method | Rule-based monitoring |
| Automated check | Marketplace product JSON-LD has `InStock` with empty `offers.price`. |
| Exception generated | "Marketplace structured price absent." |
| Human decision required | Yes, determine whether seller or marketplace controls this field. |
| Recommended action | Use only as monitoring signal; do not accuse Ajanta without internal channel-control confirmation. |

False-positive challenge: Marketplace may intentionally omit price from server-rendered JSON-LD and hydrate price client-side or by location. This is therefore INFO only.

### AJ-MKT-002: Search-discovered channel records require live verification before use as defect evidence

| Field | Value |
|---|---|
| Channel | Amazon, Flipkart, Blinkit |
| Product/SKU | Multiple Anchal products |
| Category | Footprint verification |
| Severity | INFO |
| Confidence | LOW to MEDIUM depending channel |
| Publicly defensible | Yes as limitation/footprint observation |
| Evidence | Search snippets/direct URLs for Amazon merchant/store, Flipkart product pages, Blinkit snippet. |
| Observed values | Product presence appears indexed, but direct product fields could not be consistently reproduced in static fetch. |
| Expected basis | Defect claims should rely on direct product evidence, not snippets alone. |
| Why it matters | Prevents false positives and protects the discussion with Ajanta. |
| Likely detection method | Browser/live monitor with location context |
| Automated check | Scheduled channel crawler with location/session metadata and screenshot capture. |
| Exception generated | "Channel presence discovered; product verification incomplete." |
| Human decision required | Yes, decide whether to run a consented/live channel verification pass. |
| Recommended action | Treat Amazon/Flipkart/Blinkit as footprint leads, not findings, until product pages are captured directly. |

## G. Internal Channel Audit

Official website:

- Active ecommerce shop with product pages, variants, prices, add-to-cart controls, cart links, free shipping messaging, and WooCommerce Store API.
- Catalogue quality issues found: null-size variant, free-gift products publicly exposed, ambiguous variable product physical attributes, product/media typos, mismatched image metadata.
- Pricing arithmetic on official visible prices is internally plausible:
  - Sunflower: Rs 196 vs regular Rs 240.
  - Mustard: from Rs 236 vs regular Rs 250.
  - Soyabean: from Rs 136 vs regular Rs 150.
  - Combo offers show significant discounting but no deterministic impossibility from public data alone.
- Availability: official pages/API show in-stock/purchasable status. The free-gift availability is the primary concern.

JioMart:

- Two direct pages provided structured product data and InStock signals.
- Price fields in one JSON-LD block were empty; treated as marketplace structured-data observation only.
- No strong Ajanta-caused defect was established.

Amazon/Flipkart/Blinkit:

- Presence signals exist, but direct product content was not reliable enough to compare attributes or allege defects.

## H. Cross-Channel Consistency Audit

High-confidence exact SKU comparison was not possible because marketplace SKUs/GTINs were not exposed.

Product-family comparisons:

| Product family | Channels | Match confidence | Result |
|---|---|---:|---|
| Anchal Refined Sunflower Oil 1L | Official site vs JioMart pack-of-6 | HIGH product-family, not exact pack | No verified inconsistency. Different pack-of-6 listing is expected channel variation. |
| Anchal Refined Soyabean Oil 5L/1L combo | Official combo family vs JioMart soyabean combo | MEDIUM | No verified inconsistency. Combo composition differs across listings and may be legitimate. |
| Anchal Soyabean / Sunflower on Amazon/Flipkart/Blinkit | Official vs search snippets | LOW | Not used for defect claims. |

No HIGH-risk cross-channel product identity conflict was established from defensible public evidence.

## I. Pack-Size / Price Mathematics

Programmatic visible-price extraction from official Store API:

| Product | Price | Regular/MRP representation | Deterministic anomaly? |
|---|---:|---:|---|
| Sunflower Oil Offer | Rs 0 | Rs 0 | Yes: zero-price purchasable free gift; see AJ-WEB-001. |
| Mustard Oil Offer | Rs 0 | Rs 0 | Needs internal review; API-purchasable free gift. |
| Soyaben Oil Offer | Rs 0 | Rs 0 | Needs internal review; API-purchasable free gift. |
| Anchal Refined Sunflower Oil 1L | Rs 196 | Rs 240 | No. |
| Anchal Kachi Ghani Mustard Oil | from Rs 236 | from Rs 250 | No. |
| Anchal Refined Soyabean Oil | from Rs 136 | from Rs 150 | No. |
| Mustard 5L + Soyabean 1L combo | Rs 1000 | Rs 1500 | No deterministic issue. |
| Soyabean 5L + Mustard 1L combo | Rs 972 | Rs 1450 | No deterministic issue. |
| Soyabean 5L + Sunflower 1L combo | Rs 996 | Rs 1440 | No deterministic issue. |

No selling-price-greater-than-MRP issue was found in the verified official catalogue.

## J. Website Technical QA

Checked:

- homepage, shop page, product pages
- public WooCommerce Store API
- product JSON-LD/schema on free-gift page
- product availability and add-to-cart controls
- basic product schema/metadata
- official shop enumeration

Not performed:

- checkout completion
- account login/registration
- payment/cart mutation beyond static page inspection
- CAPTCHA or access-control bypass
- full mobile rendered-DOM screenshots due missing local screenshot tooling

Technical observations:

- Official site is WordPress/WooCommerce with NitroPack/static optimization.
- Public Store API exposes product, price, stock, variation, image, and add-to-cart metadata.
- Free-gift products are exposed through shop page quick-view cards and API; one free-gift page is directly accessible with add-to-cart/buy-now controls.
- Product schema for the free-gift page advertises an InStock zero-price offer.
- Some image alt/title metadata is blank, stale, or mismatched.

## K. Human-Operations Failure Patterns

The verified issues are consistent with the following repetitive-control patterns:

- Promotional/free-gift SKU exposed outside intended bundle logic.
- Old/orphan product variation left attached to active variable product.
- Parent/variant attribute ambiguity when pack sizes change or expand.
- Media metadata copied across product families.
- Catalogue text not linted before publication.
- Marketplace structured data requiring monitoring but not necessarily seller-controlled.

This audit does not prove humans caused these issues. It shows issues that can persist when catalogue QA relies on manual spot-checks across products and channels.

## L. Automation Control Mapping

| Finding | Detection method | Automated check | Exception generated | Human action |
|---|---|---|---|---|
| AJ-WEB-001 | Deterministic automation | zero price + purchasable + in stock + offer/free semantics | Zero-price purchasable SKU | Confirm intended promotion gating; hide or gate SKU. |
| AJ-WEB-002 | Deterministic automation | variable product variation attribute null/blank | Malformed variant | Delete/archive or repair variant. |
| AJ-WEB-003 | Rule-based monitoring | variable product has materially different sizes but shared parent dimensions | Variant physical data review | Verify internal variant weights/dimensions. |
| AJ-WEB-004 | AI-assisted review + token rules | product family token conflicts with image metadata token | Image metadata mismatch | Correct image/media metadata. |
| AJ-WEB-005 | AI-assisted review + dictionary rules | known-field label typo/product-media typo | Catalogue text hygiene issue | Correct public labels/names. |
| AJ-MKT-001 | Rule-based monitoring | InStock structured data with empty price | Marketplace structured data incomplete | Determine seller vs marketplace control. |
| AJ-MKT-002 | Rule-based crawler | search-discovered product but no reproducible product detail | Channel verification gap | Run live channel/browser verification. |

## M. Management Reporting Opportunity

Weekly operations report structure:

- Listings checked: official 9 product records + marketplace pages/snippets discovered.
- Channels checked: 12.
- Channels with verified active product evidence: 2.
- New discrepancies: 5 official-site findings + 2 marketplace observations.
- Resolved discrepancies: not measured in read-only audit.
- Unresolved exceptions: all findings open pending Ajanta/internal review.
- Pricing anomalies: 1 high-confidence official free-gift purchasable issue.
- Catalogue inconsistencies: null variant, image metadata mismatch, typo/hygiene issues.
- Stock/availability inconsistencies: free-gift product in stock and purchasable.
- Stale listings: not proven.
- High-priority exceptions: AJ-WEB-001.
- Recurring issue categories: promotion gating, variant integrity, content hygiene.

Monthly management report structure:

- Total operational events monitored.
- Exception rate.
- Resolution rate.
- Ageing exceptions.
- Channel-wise defect rate.
- Recurring defect categories.
- Catalogue health trend.
- Pricing/promotion health.
- Inventory/availability health.
- Estimated manual checks avoided.
- Items requiring management authority.

No Ajanta-specific weekly/monthly trend numbers were invented.

## N. Employee vs Automated Control - Evidence Only

Human-led model:

- Can operate a catalogue successfully, especially at moderate SKU/channel counts.
- Has finite checking capacity.
- Repetitive full-catalogue checks consume working hours.
- Monitoring frequency depends on available capacity and checklists.
- Process knowledge can reside with individuals.
- More SKUs, promotions, and channels increase checking workload.
- Management reporting may itself require manual preparation.

Automated-control model:

- Can systematically check every known SKU/channel on a schedule.
- Applies the same rules consistently.
- Routes exceptions to humans instead of asking humans to inspect everything.
- Keeps an evidence trail of observed values and changes.
- Can report operational health from event history.
- Still requires integration maintenance, rule maintenance, human judgement, and infrastructure cost.

The evidence supports a "systematic monitoring plus human judgement" case, not an "AI replaces employees" claim.

## O. False-Positive Review

Findings challenged against:

- different SKU/product/formulation
- different pack or combo structure
- reseller-controlled listing
- marketplace-specific promotion
- location-dependent availability
- stale cache or search-index artifact
- dynamic pricing
- tax-inclusive vs tax-exclusive display
- legitimate channel-specific content
- old packaging still in circulation
- temporary stock state

Outcomes:

- Free-gift purchasable page survived challenge because official page and schema expose a zero-price InStock product with add-to-cart/buy-now controls.
- Null-size variant survived challenge because official public API exposes it.
- Physical attribute issue was downgraded to possible issue requiring internal verification.
- Image metadata and typo findings stayed LOW because they are real but low operational severity.
- Amazon/Flipkart/Blinkit snippets were not converted into defect claims.
- JioMart empty-price structured data was kept INFO because marketplace rendering/location can explain it.

False positives removed/downgraded: 6 candidate issues were downgraded or excluded, including search-snippet-only marketplace price/availability differences and JioMart URL-slug quantity hints.

## P. Final Numbers

| Metric | Count |
|---|---:|
| Channels discovered/researched | 12 |
| Channels verified with direct active product evidence | 2 |
| Channels with footprint signals but incomplete product verification | 3 |
| Official products/offer records observed | 9 |
| Marketplace product records directly structured-data verified | 2 |
| Search-snippet marketplace records observed but not used as defects | 5 |
| Products/listing records observed overall | 16 |
| Variants/pack constructs observed | 13 |
| Exact SKU cross-channel matches | 0 |
| High/medium-confidence product-family matches | 2 |
| Total cited observations | 31 |
| Verified defects / official-site findings | 5 |
| Critical | 0 |
| High | 1 |
| Medium | 2 |
| Low | 2 |
| Info observations | 2 |
| Possible issues requiring internal data | 3 |
| False positives removed/downgraded | 6 |
| Automatable checks | 7 |
| Human-decision items | 5 |

## Q. Strongest 5 Defensible Discussion Points

1. Official free-gift product publicly exposed as zero-price, InStock, add-to-cart, and buy-now.
   - Defensible because it is Ajanta's official site, direct product URL, public HTML/schema/API, not marketplace/reseller evidence.

2. Official Store API exposes a null-size variant on Anchal Kachi Ghani Mustard Oil.
   - Defensible because the public Store API exposes variation id `27952` with `Size = null` while valid variants are 1L and 5L.

3. Official variable products show shared parent physical attributes despite materially different pack sizes.
   - Defensible as a review item because the public page/API visibly combine 700gm/1L/5L variants with one parent weight/dimension representation; not overstated as proven fulfilment error.

4. Soyabean product includes sunflower-labelled image metadata.
   - Defensible because it is in the official public product API and affects catalogue/content quality.

5. Repeated official-site spelling/catalogue hygiene issues.
   - Defensible because the typos are visible in official product pages/API and are low-risk, factual observations rather than accusations.

## R. Recommended Next Steps

1. Review official WooCommerce promotion/free-gift configuration immediately.
2. Remove/archive malformed null-size variation or repair it after checking order/feed dependencies.
3. Verify variant-level weights/dimensions for 700gm, 1L, and 5L products; ensure feeds export variant-specific values.
4. Clean media metadata and obvious product-page typos.
5. Run a consented live-browser verification pass for Amazon, Flipkart, Blinkit, and any quick-commerce channel Ajanta confirms as active.
6. Implement recurring monitoring rules for zero-price purchasable SKUs, null variants, image/product token mismatches, missing price fields, and cross-channel pack-size drift.

Stop point: audit complete. No SANOCEA ERP production/business logic was modified.
