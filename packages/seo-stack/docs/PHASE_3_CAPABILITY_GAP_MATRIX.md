# Phase 3: SANOCEA Commercial Client-Audit Engine — Capability Gap Matrix & Architecture Specification

**Document Version:** 1.0.0 · **Date:** 2026-09-29  
**Package:** `@sanocea/seo-stack` v1.0.0  
**Focus:** Transforming the verified Phase 1/2 engine into a commercial-grade, multi-domain client audit system with revenue impact quantification and closed-loop operational workflows.

---

## 1. Current State Assessment: Real Code vs. Architectural Stubs

Before expanding into Phase 3, we audited the current codebase in [`packages/seo-stack`](file:///opt/sanocea/repo/packages/seo-stack/src) to establish what is **genuinely working in source code** versus what was only sketched conceptually:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        CURRENT SEO-STACK AUDIT: IMPLEMENTATION AUDIT                   │
└────────────────────────────────────────────────────────────────────────────────────────┘

  1. GENUINELY IMPLEMENTED & TESTED (Production-Verified):
     ✔ Title typography pixel calculation (SERP Arial 20px kerning calibrated to 618px).
     ✔ Meta description length & pixel calculation (SERP Arial 14px calibrated to 985px).
     ✔ Server-Rendered H1 missing detection in static HTML before client-side hydration.
     ✔ Pages without internal static outlinks detection (root cause of SPA crawl failure).
     ✔ Meta robots & X-Robots-Tag indexability directives (noindex, nofollow).
     ✔ Canonical tag validation (missing, relative, multiple conflicting canonicals).
     ✔ Shopify collection product canonical dilution (/collections/*/products/*).
     ✔ Live stock vs InStock structured data conflict (The Waaree Discrepancy Rule).
     ✔ Product schema extraction (Offers, Price, Currency, GTIN/Barcode validation).
     ✔ /llms.txt live HTTP probing and GEO readiness observation (classified as INFO).
     ✔ Robots.txt AI crawler directive extraction (GPTBot, ClaudeBot, PerplexityBot, etc.).
     ✔ Closed-loop remediation engine (Apply → Approval Gate → Recrawl → Verify).
     ✔ Full evidence data contracts (ID, URL, Observed, Expected, Severity, Impact, Repro).

  2. PARTIALLY IMPLEMENTED (Functional but Basic):
     ~ Sitemaps: Regex extracts `<loc>` from raw XML strings, but lacks recursive 
       `<sitemapindex>` fetching, .xml.gz extraction, and sitemap vs crawl diffing.
     ~ Redirects: Fetch client follows redirects, but does not record the intermediate hop 
       chain (A → B → C), status 301 vs 302, redirect loops, or canonicals to 3xx URLs.
     ~ Internal Links: Discovers links and tracks depth, but does not construct a directed graph 
       G=(V,E), calculate inlinks/outlinks counts per page, or compute PageRank equity.
     ~ Security Headers: Handled via Nginx config, but observer only checks 5 basic headers.

  3. STILL MISSING (Target for Phase 3):
     ✗ Hreflang validation (language codes, return tags, x-default).
     ✗ Pagination rules (rel="next", rel="prev", canonical pointing to first page).
     ✗ Orphan page detection (URLs present in XML sitemap but with 0 internal links).
     ✗ Duplicate & thin content detection (word count threshold < 200, SimHash/MinHash).
     ✗ Image ALT & asset audit (missing alt, empty alt, WebP/AVIF format check, 404 images).
     ✗ Anchor text analysis (generic "click here", empty anchor text, repetitive anchors).
     ✗ Variant URL canonicalisation (?variant=123 not canonicalizing to root product).
     ✗ Category / Faceted navigation traps (indexable parameter bloat ?color=...&size=...).
     ✗ Performance & Core Web Vitals (LCP, INP, CLS, TTFB lab measurement, render-blocking JS).
     ✗ Entity & Organization schema completeness (Organization, logo, sameAs, contactPoint).
     ✗ Structured answerability (FAQ schema, definition/summary blocks for GEO).
     ✗ Client-facing Executive HTML Audit Dashboard with revenue impact & automation opportunities.
```

---

## 2. Phase 3 Capability Gap Matrix

| # | Capability Layer | Specific Check / Module | Current Status | Best Open-Source / Reference Implementation | License | SANOCEA Implementation Strategy | Priority |
|---|:---|:---|:---:|:---|:---:|:---|:---:|
| **1** | **Technical SEO** | **Crawlability & Indexability** | **Implemented** | Google Lighthouse (`is-crawlable.js`) | Apache-2.0 | Keep current Cheerio observer; add X-Robots-Tag header inheritance. | Core |
| **2** | Technical SEO | **Robots.txt Analysis** | **Implemented** | `samclarke/robots-parser` + Advertools | MIT | Enhance `parseRobotsTxt` with exact wildcard `*` and end-anchor `$` rule matching. | High |
| **3** | Technical SEO | **Recursive XML Sitemaps** | **Partial** | Advertools (`sitemap_to_df`) | Apache-2.0 | Build recursive `<sitemapindex>` fetcher supporting `.xml.gz` decompression. | High |
| **4** | Technical SEO | **Canonical Integrity** | **Implemented** | FreeCrawl canonical module | MIT | Keep current observer; add check for canonical pointing to 3xx or 404. | Core |
| **5** | Technical SEO | **Redirect Chain & Loop Tracing** | **Partial** | Sitespeed.io Coach (HAR waterfall) | MIT | Intercept HTTP redirect hops, record chain length ($A \to B \to C$), and flag 302 vs 301. | High |
| **6** | Technical SEO | **Broken Links (4xx/5xx)** | **Partial** | Apify Crawlee `RequestQueue` | Apache-2.0 | Maintain broken link registry with source URL, anchor text, and CSS selector. | High |
| **7** | Technical SEO | **Hreflang Internationalization** | **Missing** | Screaming Frog Hreflang rule dictionary | Reference | Parse `<link rel="alternate" hreflang="...">`, verify return tags and `x-default`. | Medium |
| **8** | Technical SEO | **Pagination Handling** | **Missing** | Yoast SEO / Google Search Central Guidelines | Reference | Audit `rel="next"` / `rel="prev"`, flag pagination loops and canonicalizing all pages to page 1. | Medium |
| **9** | Technical SEO | **Orphan Page Detection** | **Missing** | FreeCrawl internal link graph | MIT | Cross-reference discovered sitemap URLs with crawl link graph; flag in-degree $= 0$. | High |
| **10** | Technical SEO | **Duplicate URL Normalization** | **Implemented** | Apify Crawlee URL utils | Apache-2.0 | Current `normalizeUrl` is solid; add parameter sort order and case normalization. | Core |
| **11** | **On-Page SEO** | **SERP Title Pixel Width** | **Implemented** | Screaming Frog font metric standard | Reference | Retain calibrated Arial 20px metric (561px limit). | Core |
| **12** | On-Page SEO | **Meta Description Pixel Width** | **Implemented** | Screaming Frog font metric standard | Reference | Retain calibrated Arial 14px metric (985px limit / 155 chars). | Core |
| **13** | On-Page SEO | **Heading Hierarchy (H1/H2)** | **Partial** | Lighthouse `headings-order.js` | Apache-2.0 | Add check for H2 existence, empty headings, and heading level skips ($h_1 \to h_3$). | High |
| **14** | On-Page SEO | **Image Alt Text & Formats** | **Missing** | Sitespeed.io Coach-Core (`image.js`) | MIT | Check `img[alt]`: missing, empty, or filename in alt; flag legacy PNG/JPEG when WebP/AVIF suitable. | High |
| **15** | On-Page SEO | **Internal Link Equity Graph** | **Partial** | FreeCrawl link graph routines | MIT | Compute in-degree, out-degree, and click depth ($d$) from seed for all pages. | High |
| **16** | On-Page SEO | **Anchor Text Quality** | **Missing** | Google Lighthouse `link-text.js` | Apache-2.0 | Flag generic anchor text ("click here", "read more", URL as anchor, empty anchors). | Medium |
| **17** | On-Page SEO | **Thin & Duplicate Content** | **Missing** | `seomoz/simhash-py` / `ChenghaoMou/text-dedup` | MIT | Extract main body text, calculate word count (< 200 words), compute 64-bit SimHash for near-duplicates. | High |
| **18** | **Ecommerce SEO**| **Product & Offer Schema** | **Implemented** | Google `schema-dts` + Rich Results Validator | Apache-2.0 | Retain current JSON-LD extractor; add return policy & shipping schema checks. | Core |
| **19** | Ecommerce SEO | **Zero-Stock vs InStock Leak** | **Implemented** | SANOCEA Proprietary (Waaree Rule) | Proprietary | Retain current contradiction detector; expand to cover Flipkart/Amazon buy-box drift. | Core |
| **20** | Ecommerce SEO | **Shopify Collection URL Dilution**| **Implemented** | SANOCEA Proprietary (Shopify Rule) | Proprietary | Retain current `/collections/*/products/*` detector and Liquid remediation generator. | Core |
| **21** | Ecommerce SEO | **Variant Canonicalisation** | **Missing** | Shopify SEO Guidelines | Proprietary | Flag variant URLs (`?variant=...`) that lack canonical tags pointing to master product. | High |
| **22** | Ecommerce SEO | **SKU / GTIN / Brand Integrity** | **Partial** | GS1 Standard + Google Merchant Center Specs | Reference | Validate presence of `gtin13`/`upc`/`mpn`, `sku`, and `brand` consistency across catalog. | High |
| **23** | Ecommerce SEO | **Faceted Navigation Bloat** | **Missing** | Open SEO Crawler CMS patterns | MIT | Detect filter combinations (`?color=...&size=...`) causing exponential crawl budget waste. | High |
| **24** | **Performance** | **Core Web Vitals (LCP/CLS/INP)**| **Missing** | Google Lighthouse (`lighthouse-core`) | Apache-2.0 | Measure lab CWV metrics via Playwright DevTools protocol or Navigation Timing API. | High |
| **25** | Performance | **TTFB & Network Bottlenecks** | **Partial** | Sitespeed.io Coach-Core | MIT | Capture Time to First Byte (TTFB > 800ms) and uncompressed responses (missing gzip/brotli). | Medium |
| **26** | **GEO / AI** | **/llms.txt Discovery** | **Implemented** | Spronta Crawlie (`crawlie-core`) | MIT | Retain current probe and classification as `[GEO] GEO Readiness` observation (INFO). | Core |
| **27** | GEO / AI | **AI Crawler Directives** | **Implemented** | Spronta Crawlie | MIT | Retain parsing of `GPTBot`, `ClaudeBot`, `PerplexityBot`, `CCBot` in `robots.txt`. | Core |
| **28** | GEO / AI | **Entity & Organization Schema** | **Missing** | Schema.org Organization specification | Apache-2.0 | Audit `@type: Organization` for `name`, `logo`, `url`, `sameAs` (social proof), and `contactPoint`. | High |
| **29** | GEO / AI | **Structured Answerability** | **Missing** | Claude-SEO Prompt & Entity Engine | MIT | Check presence of FAQ schema, structured definition lists, and entity citation density. | High |
| **30** | **Evidence Engine**| **Evidence Contract & Receipts** | **Implemented** | SANOCEA Proprietary Contract | Proprietary | Retain finding data contract; add DOM selector paths and reproduction commands. | Core |
| **31** | **Remediation** | **Closed-Loop Verification** | **Implemented** | SANOCEA Proprietary Remediation Engine | Proprietary | Expand `ClosedLoopRemediator` to handle image alt, schema injection, and canonical tags. | Core |
| **32** | **Client Audit** | **Executive Dashboard & Report**| **Missing** | CrawlSEO Dashboard + Waaree Prospect Report | MIT / Prop | Generate standalone interactive HTML/Markdown client audit report with revenue impact. | High |

---

## 3. High-Leverage Open-Source Architectural Reuse Plan

To execute Phase 3 rapidly without bloat or legal risk:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        ARCHITECTURAL REUSE & LICENSING STRATEGY                        │
└────────────────────────────────────────────────────────────────────────────────────────┘

  1. ADOPT FROM SITESPEED.IO COACH-CORE (MIT License):
     - Extract DOM scripts for asset evaluation (`lib/dom/bestpractice/`, `lib/dom/performance/`).
     - Port image inspection logic: detects missing alt text, non-responsive images, and heavy formats.
     - Port TTFB and compression evaluation logic.

  2. ADOPT FROM SPRONTA CRAWLIE (MIT License):
     - Port Generative Engine Optimization (GEO) heuristics.
     - Add entity/authorship answerability heuristics for AI overview visibility.

  3. ADOPT FROM FREECRAWL (MIT License):
     - Port directed internal link graph calculations (inlink/outlink counting and click depth BFS).
     - Port orphan page detection logic (Sitemap URLs \ Discovered Crawl URLs).

  4. KEEP STRICTLY PROPRIETARY (SANOCEA IP):
     - The Evidence-First Data Contract (Finding → Evidence → Severity → Impact → Action → Receipt).
     - Ecommerce Exception Detection Engine (Shopify collection dilution, zero-stock vs InStock leaks, 
       marketplace Buy Box price erosion, GTIN/barcode catalog drift).
     - Closed-Loop Remediation Workflow (Human Approval Gate → Safe Code Fix → Independent Recrawl Verification).
     - WhatsApp Operations Alerting & Decision Routing layer.
```

---

## 4. Phase 3 Architecture: The 8-Layer Client Audit Pipeline

```
                                  ┌─────────────────────────────┐
                                  │   Client Seed URL / Store   │
                                  └──────────────┬──────────────┘
                                                 │
                                                 ▼
                                  ┌─────────────────────────────┐
                                  │  URL Discovery & Frontier   │
                                  │  (Sitemaps, Robots, Links)  │
                                  └──────────────┬──────────────┘
                                                 │
                                                 ▼
                                  ┌─────────────────────────────┐
                                  │  Dual-Engine Page Fetch     │
                                  │  (Fast HTTP + Playwright)   │
                                  └──────────────┬──────────────┘
                                                 │
                    ┌────────────────────────────┼────────────────────────────┐
                    ▼                            ▼                            ▼
         ┌─────────────────────┐      ┌─────────────────────┐      ┌─────────────────────┐
         │ 1. Technical SEO    │      │ 2. On-Page SEO      │      │ 3. Ecommerce SEO    │
         │ - Indexability      │      │ - Title / Meta SERP │      │ - Product Schema    │
         │ - Robots / Sitemaps │      │ - H1-H6 Hierarchy   │      │ - InStock vs OOS    │
         │ - Redirect Chains   │      │ - Image Alt / Format│      │ - Shopify Dilution  │
         │ - Orphan Pages      │      │ - Link Graph / Depth│      │ - Variant Canonicals│
         └──────────┬──────────┘      └──────────┬──────────┘      └──────────┬──────────┘
                    │                            │                            │
                    └────────────────────────────┼────────────────────────────┘
                                                 │
                    ┌────────────────────────────┴────────────────────────────┐
                    ▼                                                         ▼
         ┌─────────────────────┐                                   ┌─────────────────────┐
         │ 4. Performance CWV  │                                   │ 5. GEO / AI Engine  │
         │ - LCP, CLS, INP     │                                   │ - llms.txt Standard │
         │ - TTFB & Compression│                                   │ - AI Bot Directives │
         │ - Render Blocking JS│                                   │ - Entity Knowledge  │
         └──────────┬──────────┘                                   └──────────┬──────────┘
                    │                                                         │
                    └────────────────────────────┬────────────────────────────┘
                                                 │
                                                 ▼
                                  ┌─────────────────────────────┐
                                  │ 6. Evidence & Impact Engine │
                                  │ - Commercial Revenue Risk   │
                                  │ - Severity Classification   │
                                  │ - Exact DOM / XPath Proof   │
                                  └──────────────┬──────────────┘
                                                 │
                                                 ▼
                                  ┌─────────────────────────────┐
                                  │ 7. Closed-Loop Remediation  │
                                  │ - Automated PR / Code Diffs │
                                  │ - Human Sign-Off Gate       │
                                  │ - Independent Verification  │
                                  └──────────────┬──────────────┘
                                                 │
                                                 ▼
                                  ┌─────────────────────────────┐
                                  │ 8. Client Audit Dashboard   │
                                  │ - Executive HTML Report     │
                                  │ - WhatsApp Operations Alert │
                                  │ - Commercial Opportunity Map│
                                  └─────────────────────────────┘
```

---

## 5. Phase 3 Implementation Roadmap

### Milestone 3.1: Core Observer Expansion (Sprint 1)
* **Technical SEO:** Add recursive sitemap index parsing, redirect chain tracing, 404 broken link tracking with anchor text, and orphan page detection.
* **On-Page SEO:** Add Image Alt text validator, heading hierarchy validator ($h_1 \to h_6$), and main body word-count analyzer.
* **Ecommerce SEO:** Add variant canonicalization check (`?variant=...`), faceted parameter bloat check, and missing Brand/SKU validator.

### Milestone 3.2: Performance, GEO & Entity Intelligence (Sprint 2)
* **Performance:** Add TTFB measurement and uncompressed asset detection.
* **GEO & Entity:** Add Organization schema completeness validator (`name`, `logo`, `sameAs`) and structured FAQ answerability check.

### Milestone 3.3: Client-Facing Executive Audit Generator (Sprint 3)
* Build [`src/reporting/clientReportGenerator.ts`](file:///opt/sanocea/repo/packages/seo-stack/src/reporting/clientReportGenerator.ts):
  * Generates high-fidelity standalone HTML report and executive Markdown brief.
  * Calculates **Commercial Revenue at Risk** based on catalog size, organic traffic estimates, and suppressed listing risks.
  * Outlines **SANOCEA Automation Opportunities** mapping findings directly into SANOCEA platform modules.

### Milestone 3.4: Multi-Client Test Bench (Sprint 4)
* Run the expanded stack across 3 diverse storefronts:
  1. `sanocea.com` (Verified B2B baseline)
  2. `shop.waaree.com` (BigCommerce / enterprise solar ecommerce)
  3. A live Shopify fashion/jewellery storefront (e.g. Carzex or Golden Bird Jewels)
* Generate audit receipts and verify zero regression in existing test suites.
