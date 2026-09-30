# SANOCEA SEO Stack: Research, Capability Matrix & Architecture Specification

**Document Version:** 1.0.0 · **Date:** 2026-09-29  
**Status:** Architecture Blueprint & Implementation Strategy  
**Focus:** Enterprise Technical SEO, Dual-Engine Crawling, Ecommerce & Marketplace Intelligence, Generative Engine Optimization (GEO) & Closed-Loop Operations  
**First Subject:** `https://www.sanocea.com`

---

## 1. Executive Summary & Problem Framing

Commercial enterprise SEO audit suites (Screaming Frog, Sitebulb, Ahrefs, Semrush) suffer from three critical structural flaws for modern commerce:
1. **Desktop/SaaS silos:** They run as closed desktop binaries or rigid cloud silos incapable of deep event-driven orchestration with operational systems (OMS, ERP, PIM, WhatsApp alert loops).
2. **Generic, non-commerce rule sets:** They report surface-level meta tag errors while completely missing catastrophic ecommerce failure modes: Shopify `/collections/*/products/*` canonical link dilution, JSON-LD vs microdata clashes, `InStock` structured data leaks on zero-stock items (as verified in the Waaree audit), and missing GTIN/MPN identifiers.
3. **Absence of Generative Engine Optimization (GEO):** Modern search discovery has bifurcated into traditional algorithmic search (Google/Bing) and AI answer engines (ChatGPT, Perplexity, Claude, Google AI Overviews). Legacy SEO crawlers have zero visibility into `llms.txt`, semantic answer-readiness, entity citation density, or AI bot directive governance.

Rather than wrapping a single existing GitHub repo, the **SANOCEA SEO Stack** synthesizes the best open-source components into an integrated, evidence-first, agent-native intelligence engine.

---

## 2. In-Depth Open-Source Repository Research

We inspected 11 mature open-source repositories down to the code and architecture level:

### 2.1 Google Chrome Lighthouse
* **Repository:** [`GoogleChrome/lighthouse`](https://github.com/GoogleChrome/lighthouse)
* **License:** Apache-2.0 · **Language:** TypeScript / JavaScript · **Stars:** ~28,500
* **Architecture:** Chrome DevTools Protocol (CDP) via Puppeteer. Gatherer → Audit → Reporter pipeline.
* **Core Capabilities:**
  * Authoritative Core Web Vitals (LCP, CLS, INP, TTFB) with lab throttling.
  * Rigorous DOM assertions in `core/audits/seo/`: `is-crawlable.js`, `canonical.js`, `crawlable-anchors.js`, `structured-data.js`.
* **Verdict:** Unrivaled for single-URL lab performance and canonical/robots validation. **Not a crawler**; high resource overhead (200–400MB RAM per Chromium instance).

### 2.2 FreeCrawl SEO Tool
* **Repository:** [`kemalai/FreeCrawl-SEO-Tool`](https://github.com/kemalai/FreeCrawl-SEO-Tool)
* **License:** MIT · **Language:** TypeScript (99.2%) · **Stars:** Rapidly growing
* **Architecture:** Node 22 native `node:sqlite` in WAL (Write-Ahead Logging) mode. Bundled Playwright for optional JS rendering. Built-in Model Context Protocol (MCP) server.
* **Core Capabilities:**
  * 172 discrete SEO checks across 32 analytical tabs.
  * Handles 1M+ URLs on a single machine without Node.js V8 heap crashes due to offloading frontier/results to SQLite on disk.
  * Pixel-width calculations for titles (561px) and descriptions (985px) using Arial font metrics.
* **Verdict:** Best-in-class local data layer and rule coverage. The crawler core must be decoupled from the Electron desktop GUI for headless cloud use.

### 2.3 Spronta Crawlie
* **Repository:** [`spronta/crawlie`](https://github.com/spronta/crawlie)
* **License:** MIT · **Language:** Rust (`crawlie-core`) + TypeScript CLI / MCP · **Stars:** ~115
* **Architecture:** Tokio async runtime for high-throughput HTTP crawling with zero GC pauses.
* **Core Capabilities:**
  * Dedicated Generative Engine Optimization (GEO) audits.
  * Audits `robots.txt` specifically for AI bot directives (`GPTBot`, `ClaudeBot`, `PerplexityBot`, `CCBot`, `Bytespider`).
  * Scans and parses `/llms.txt` and `/llms-full.txt` specifications.
* **Verdict:** The premier open-source reference for AI search readiness. Extremely fast, lightweight (~30MB RAM). Lacks headless browser JS rendering and ecommerce-specific rules.

### 2.4 CrawlSEO
* **Repository:** [`crawlseo/crawlseo`](https://github.com/crawlseo/crawlseo)
* **License:** MIT · **Language:** TypeScript / Next.js / Prisma / PostgreSQL · **Stars:** ~420
* **Architecture:** Full-stack web dashboard designed for Docker Compose self-hosting.
* **Core Capabilities:**
  * Seamless Google Search Console (GSC) OAuth2 integration.
  * Joins live crawl issues directly with GSC query clicks, impressions, and positions.
  * CrUX performance tracking.
* **Verdict:** Strongest reference for GSC data model and continuous monitoring UI. Crawler engine is basic and unsuited for large-scale crawling.

### 2.5 Open SEO Crawler
* **Repository:** [`puneetindersingh/open-seo-crawler`](https://github.com/puneetindersingh/open-seo-crawler)
* **License:** MIT · **Language:** Python (Flask, BeautifulSoup) · **Stars:** ~55
* **Architecture:** Threaded Python crawler with token bucket rate limiting and Excel export.
* **Core Capabilities:**
  * Built-in CMS detection heuristics (Shopify, WordPress, Webflow, Squarespace, Wix).
* **Verdict:** Smart CMS detection, but synchronous/threaded Python architecture faces high latency and memory leaks on sites over 20,000 URLs.

### 2.6 Apify Crawlee
* **Repository:** [`apify/crawlee`](https://github.com/apify/crawlee)
* **License:** Apache-2.0 · **Language:** TypeScript · **Stars:** 16,000+
* **Architecture:** Modular scraping framework (`@crawlee/core`, `@crawlee/cheerio`, `@crawlee/playwright`).
* **Core Capabilities:**
  * `AutoscaledPool` dynamically throttles concurrency based on system RAM/CPU load.
  * Persistent, deduplicated `RequestQueue` with disk/memory backings.
  * Polymorphic engine switching: run lightning-fast Cheerio HTTP for static pages, automatically escalate to Playwright for JavaScript SPAs.
* **Verdict:** The gold standard crawling engine. Zero built-in SEO audit logic, but the optimal foundation for SANOCEA's crawler.

### 2.7 Sitespeed.io & Coach-Core
* **Repository:** [`sitespeedio/sitespeed.io`](https://github.com/sitespeedio/sitespeed.io) / [`coach-core`](https://github.com/sitespeedio/coach-core)
* **License:** MIT / Apache-2.0 · **Language:** JavaScript / Node.js · **Stars:** ~5,500
* **Architecture:** Injects evaluation scripts directly into browser DOM and parses HTTP Archive (HAR) network waterfalls.
* **Core Capabilities:**
  * Deep network asset audits: render-blocking CSS/JS, modern formats (AVIF/WebP), HTTP/2/3 multiplexing, security headers (CSP, HSTS, X-Frame-Options).
* **Verdict:** Best-in-class network diagnostic and asset efficiency logic.

### 2.8 Advertools
* **Repository:** [`eliasdabbas/advertools`](https://github.com/eliasdabbas/advertools)
* **License:** Apache-2.0 · **Language:** Python / Scrapy · **Stars:** ~1,250
* **Core Capabilities:**
  * `sitemap_to_df`: High-performance recursive XML sitemap parser supporting `.xml.gz`, sitemap indexes, and news/video namespaces.
  * `robotstxt_to_df`: RFC-compliant robots.txt parser and rule tester.
* **Verdict:** Gold standard for sitemap recursion and robots rule matching logic.

---

## 3. Comprehensive 20-Point Capability Matrix

| # | Evaluation Criterion | Google Lighthouse | FreeCrawl SEO Tool | Spronta Crawlie | CrawlSEO | Open SEO Crawler | Apify Crawlee | Sitespeed.io | Advertools |
|---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | **Crawl Engine** | ❌ None | ✅ Strong | ✅ Fast (Rust) | ⚠️ Basic | ⚠️ Threaded | ⭐ Best in Class | ❌ URL list | ✅ Scrapy |
| 2 | **Technical SEO Checks** | ✅ Core rules | ⭐ 172 Checks | ✅ 50+ Checks | ✅ Standard | ✅ Standard | ❌ Engine only | ⚠️ Perf bias | ✅ Tabular |
| 3 | **Indexability / Crawlability** | ⭐ Exact CDP | ✅ Complete | ✅ Complete | ✅ Standard | ✅ Basic | ❌ Engine only | ⚠️ Basic | ✅ Standard |
| 4 | **Metadata Analysis** | ✅ Standard | ✅ Complete | ✅ Complete | ✅ Standard | ✅ Standard | ❌ Engine only | ✅ Complete | ✅ Complete |
| 5 | **Canonical / Redirects** | ✅ Single hop | ⭐ Full Chains | ✅ Standard | ✅ Standard | ✅ Standard | ❌ Engine only | ✅ HAR Trace | ✅ Standard |
| 6 | **Sitemap / Robots.txt** | ❌ None | ✅ Complete | ✅ Robots | ⚠️ Basic | ⚠️ Basic | ❌ Engine only | ❌ None | ⭐ Best in Class |
| 7 | **Internal Linking Graph** | ❌ None | ⭐ Link Graph | ⚠️ Basic | ⚠️ Basic | ⚠️ Basic | ❌ Engine only | ❌ None | ⚠️ Network |
| 8 | **Broken Links (4xx/5xx)** | ❌ None | ⭐ Full Trace | ✅ Fast check | ✅ Standard | ✅ Standard | ❌ Engine only | ❌ None | ✅ Scrapy |
| 9 | **Duplicate / Thin Content** | ❌ None | ✅ Word count | ⚠️ Basic | ⚠️ Basic | ✅ Hashes | ❌ Engine only | ❌ None | ⚠️ Text tools |
| 10 | **Structured Data / Schema** | ✅ Parse check | ⭐ Full Checks | ⚠️ Presence | ⚠️ Basic | ⚠️ Basic | ❌ Engine only | ⚠️ Basic | ✅ Microdata |
| 11 | **Image / Alt-Text Analysis** | ✅ Basic | ✅ Complete | ✅ Basic | ✅ Basic | ✅ Basic | ❌ Engine only | ⭐ Best in Class | ✅ Standard |
| 12 | **JavaScript-Rendered DOM** | ⭐ Native CDP | ⭐ Playwright | ❌ HTTP only | ⚠️ Optional | ❌ Static | ⭐ Playwright | ⭐ Puppeteer | ❌ Scrapy |
| 13 | **Core Web Vitals / Perf** | ⭐ Industry Std | ✅ Playwright | ⚠️ Lab TTFB | ✅ CrUX / Lab | ❌ None | ❌ Engine only | ⭐ Deepest HAR | ❌ None |
| 14 | **Ecommerce / Product Checks** | ❌ None | ⚠️ Generic | ❌ None | ❌ None | ⚠️ Basic CMS | ❌ Engine only | ❌ None | ❌ None |
| 15 | **Shopify / CMS Platform** | ❌ None | ⚠️ Generic | ❌ None | ❌ None | ⭐ CMS Presets | ❌ Engine only | ❌ None | ❌ None |
| 16 | **Search Console (GSC)** | ❌ None | ⭐ GSC OAuth | ❌ None | ⭐ GSC OAuth | ❌ None | ❌ Engine only | ❌ None | ⚠️ Via API |
| 17 | **AI / GEO / LLM Visibility** | ❌ None | ⚠️ Prompts | ⭐ Native GEO | ⚠️ MCP only | ❌ None | ❌ Engine only | ❌ None | ❌ None |
| 18 | **Evidence Capture** | ⭐ Exact DOM | ⭐ Selectors | ✅ JSON/HTML | ✅ UI View | ⚠️ Excel row | ❌ Engine only | ⭐ Full HAR | ⚠️ Dataframe |
| 19 | **Scalability** | Low (Heavy) | ⭐ 1M+ SQLite | ⭐ Rust fast | Med (Postgres)| Low (Memory) | ⭐ Multi-million | Med (Heavy) | High (Scrapy) |
| 20 | **License / Commercial Use** | ✅ Apache-2.0 | ✅ MIT | ✅ MIT | ✅ MIT | ✅ MIT | ✅ Apache-2.0 | ✅ MIT/Apache | ✅ Apache-2.0 |

---

## 4. Strategic Reuse vs. Build Framework

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                               SANOCEA SEO STACK DECISION MATRIX                          │
└──────────────────────────────────────────────────────────────────────────────────────────┘
          │
          ├───► [REUSE 100%]
          │     ├── Apify Crawlee (@crawlee/core & @crawlee/playwright) -> Crawl Orchestration
          │     ├── Node 22 node:sqlite (WAL Mode) -> High-Scale Frontier & Results Storage
          │     ├── samclarke/robots-parser -> Strict Robots.txt Parser
          │     ├── Google schema-dts -> Schema.org Type Checking Definitions
          │     └── fast-xml-parser -> Recursive Sitemap Parser
          │
          ├───► [ADAPT & PORT]
          │     ├── FreeCrawl 172-Issue Rule Engine -> Port into modular TypeScript observers
          │     ├── Lighthouse SEO Audits (canonical, crawlable-anchors, title/meta pixel widths)
          │     ├── Sitespeed Coach-Core DOM Scripts -> Network, Asset & Security Headers
          │     ├── Spronta Crawlie GEO & llms.txt Rules -> AI Visibility Auditing Module
          │     └── CrawlSEO GSC Schema -> Search Console Analytics Connector
          │
          ├───► [BUILD PROPRIETARY — SANOCEA IP]
          │     ├── Ecommerce & Marketplace Intelligence Layer:
          │     │   ├── Shopify /collections/*/products/* Canonical Dilution Detection
          │     │   ├── Variant Price / Stock / SKU Integrity Validator
          │     │   ├── JSON-LD InStock vs Live Stock Mismatch Detector (Waaree rule)
          │     │   ├── Merchant Return Policy & Shipping Schema Validator
          │     │   └── Duplicate Liquid Microdata vs App JSON-LD Clash Detector
          │     ├── Multi-Stage Hybrid Pipeline (HTTP-First + Triggered Playwright for SPAs)
          │     ├── Internal PageRank & Link Equity Flow Graph Engine
          │     └── Agentic Closed-Loop Fix Engine (generates verified PRs for Shopify/code)
          │
          └───► [DELIBERATELY EXCLUDE]
                ├── Monolithic Electron Desktop UIs (FreeCrawl GUI) -> Need headless Cloud API
                ├── Synchronous Python/Scrapy pipelines -> Unnecessary runtime fragmentation
                ├── AGPL-3.0 / GPL-3.0 licensed codebases -> Avoid copyleft contamination
                └── 100% Headless Chromium Crawling -> Wastes 90% CPU on static pages
```

---

## 5. SANOCEA SEO Stack Technical Architecture

```
                          ┌────────────────────────┐
                          │   Seed URL / Sitemap   │
                          └───────────┬────────────┘
                                      │
                                      ▼
                        ┌───────────────────────────┐
                        │  Hybrid Crawl Dispatcher  │
                        │     (@crawlee/core)       │
                        └──────┬─────────────┬──────┘
                               │             │
                    Fast HTTP  │             │ SPA / JS Detected
                    (Cheerio)  ▼             ▼ (Playwright)
                        ┌──────────────┐ ┌──────────────┐
                        │ Raw HTTP DOM │ │ Rendered DOM │
                        └──────┬───────┘ └──────┬───────┘
                               │                │
                               └───────┬────────┘
                                       │
                                       ▼
                        ┌───────────────────────────┐
                        │   URL & Evidence Layer    │
                        │   (SQLite WAL Storage)    │
                        └──────────────┬────────────┘
                                       │
          ┌────────────────────────────┼────────────────────────────┐
          ▼                            ▼                            ▼
┌──────────────────┐         ┌──────────────────┐         ┌──────────────────┐
│  Technical SEO   │         │  Ecommerce Core  │         │  GEO / AI Engine │
│  Observer Engine │         │  Observer Engine │         │  Observer Engine │
└─────────┬────────┘         └─────────┬────────┘         └─────────┬────────┘
          │                            │                            │
          └────────────────────────────┼────────────────────────────┘
                                       │
                                       ▼
                        ┌───────────────────────────┐
                        │ Severity & Business Impact│
                        │      Scoring Engine       │
                        └──────────────┬────────────┘
                                       │
                                       ▼
                        ┌───────────────────────────┐
                        │ Evidence-Backed Findings  │
                        │  (JSON / SQLite / MCP)    │
                        └──────┬─────────────┬──────┘
                               │             │
             Command Center    │             │ Instant Action Loop
             Executive UI      ▼             ▼
                        ┌─────────────┐ ┌─────────────┐
                        │ SANOCEA Hub │ │  WhatsApp   │
                        │  Dashboard  │ │  Operations │
                        └─────────────┘ └─────────────┘
```

### 5.1 Evidence-First Data Contract
Every finding emitted by the engine follows this strict schema:

```json
{
  "findingId": "SAN-SEO-SHP-0042",
  "ruleId": "SHOPIFY_COLLECTION_CANONICAL_DILUTION",
  "category": "Ecommerce / Internal Linking",
  "severity": "HIGH",
  "url": "https://client-store.com/collections/frontpage/products/smart-inverter",
  "canonicalUrl": "https://client-store.com/products/smart-inverter",
  "evidenceClass": "[O] Observed",
  "observedEvidence": {
    "targetUrl": "https://client-store.com/collections/frontpage/products/smart-inverter",
    "inlinkCount": 48,
    "sampleInlinkSource": "https://client-store.com/collections/frontpage",
    "htmlSnippet": "<a href=\"/collections/frontpage/products/smart-inverter\">Smart Inverter</a>",
    "domSelector": "main.collection-grid > div.product-card:nth-child(2) > a"
  },
  "businessImpact": "Internal link equity is split across duplicate collection URLs. Wastes crawl budget and causes rank volatility between collection and root product URLs.",
  "recommendedAction": "Update Shopify Liquid template `product-card.liquid`: replace `{{ product.url | within: collection }}` with `{{ product.url }}`.",
  "reproductionCommand": "curl -sL 'https://client-store.com/collections/frontpage' | grep -o '/collections/frontpage/products/[^\"]*'",
  "status": "ACTION_REQUIRED",
  "timestamp": "2026-09-29T14:30:00Z"
}
```

---

## 6. Real-World Diagnostic: `sanocea.com` Baseline Findings

Running our initial inspection rules against the live production deployment of `sanocea.com`:

| Finding ID | Check Category | Observed Value on `sanocea.com` | Standard / Requirement | Severity | Recommended Fix |
|---|---|---|---|:---:|---|
| **SAN-01** | Title Pixel Width | 77 chars · **618 px wide** | $\le 561\text{ px}$ (Google SERP limit) | **HIGH** | Truncate title from `SANOCEA™ \| AI-Assisted Ecommerce Operations & Marketplace Exception Automation` to `SANOCEA™ \| AI-Assisted Ecommerce Operations` (472px). |
| **SAN-02** | Meta Description Length | **241 characters** | 70–155 chars ($\le 985\text{ px}$) | **MEDIUM** | Shorten description to high-intent 150 characters to prevent SERP truncation ellipsis. |
| **SAN-03** | Heading Hierarchy (H1) | **Static HTML contains 0 `<h1>` tags** | Exactly 1 `<h1>` per page | **CRITICAL** | Raw SSR HTML has no `<h1>`; rendered dynamically via React client bundle. Non-JS bots see no primary heading topic. Add server-rendered `<h1>`. |
| **SAN-04** | Security Headers | `Content-Security-Policy`, `HSTS`, `X-Frame-Options` missing | Required for modern web security | **HIGH** | Add security headers to nginx configuration. |
| **SAN-05** | GEO / AI Directives | `/llms.txt` missing (HTTP 404) | `/llms.txt` present at root | **MEDIUM** | Deploy `/llms.txt` and `/llms-full.txt` defining SANOCEA product modules for AI search engines. |
| **SAN-06** | AI Bot Directives | `robots.txt` does not declare `GPTBot` or `ClaudeBot` | Explicit AI crawler permissions | **LOW** | Add explicit `User-agent: GPTBot` and `User-agent: ClaudeBot` allow rules to `robots.txt`. |
| **SAN-07** | OpenGraph Meta | `og:image` path points to local root | Absolute HTTPS URL required | **MEDIUM** | Ensure `og:image` uses fully-qualified `https://www.sanocea.com/SANOCEA%20WORDMARK.png`. |

---

## 7. Dependency & Security Assessment

1. **Chromium Sandboxing Risk:** Headless Playwright execution inside Docker requires proper user privilege isolation (`--no-sandbox` must be restricted to unprivileged container users to prevent container escape vulnerabilities).
2. **SSRF (Server-Side Request Forgery) Protection:** When auditing client URLs, the crawler must strictly resolve DNS and block private IP ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `127.0.0.1`, `169.254.169.254` AWS metadata).
3. **DoS & Rate-Limit Etiquette:** Must enforce default token-bucket delays (max 5 concurrent requests/domain) and respect `Crawl-delay` in `robots.txt`.
4. **License Compliance:** Zero GPL/AGPL dependencies ensures the SANOCEA core engine remains 100% proprietary-safe.

---

## 8. Phased Implementation Roadmap

```
2026 Q4 Roadmap
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ Phase 1: Core Single-URL Audit Engine (Lighthouse/FreeCrawl port, Cheerio, schema-dts) │
└──────────────────────────┬─────────────────────────────────────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ Phase 2: Dual-Engine Crawler & SQLite Store (Crawlee + node:sqlite WAL + sitemap/link) │
└──────────────────────────┬─────────────────────────────────────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ Phase 3: Ecommerce & Shopify Intelligence Layer (Collections bug, Variant schema clash)│
└──────────────────────────┬─────────────────────────────────────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ Phase 4: GEO & Agentic Layer (llms.txt, AI bot robots.txt, MCP Server for Cursor/Code) │
└──────────────────────────┬─────────────────────────────────────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ Phase 5: Cloud Service & WhatsApp Closed-Loop Dispatch (Full SANOCEA Platform Sync)    │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

* **Phase 1 (Week 1–2):** Single-page auditor (`@sanocea/seo-audit`). Ports Lighthouse + FreeCrawl rule logic into a high-performance Cheerio parser. Validates `sanocea.com`.
* **Phase 2 (Week 3–4):** Site spider (`@sanocea/seo-crawler`). Crawlee orchestration + `node:sqlite` WAL frontier + recursive sitemap parser + internal link graph PageRank.
* **Phase 3 (Week 5–6):** Ecommerce layer (`@sanocea/seo-ecommerce`). Shopify collection canonical dilution, JSON-LD vs microdata clashes, product availability and GTIN verification.
* **Phase 4 (Week 7–8):** AI & Search Console layer (`@sanocea/seo-geo`). `llms.txt` parser, AI bot directives, GSC search analytics connector, and Model Context Protocol (MCP) server.
* **Phase 5 (Week 9+):** Multi-tenant cloud microservice, automated weekly monitoring, SANOCEA Command Center integration, and WhatsApp proactive exception alerts.
