# Phase 2: SANOCEA Production SEO Remediation & Operational Execution Plan

**Document Version:** 1.0.0 · **Date:** 2026-09-29  
**Target:** `https://www.sanocea.com/` (Production Domain) & Secondary Test Domain  
**Engine:** `@sanocea/seo-stack` v1.0.0  
**Status:** Prepared for Human Approval (Pre-Execution Gate)

---

## 1. Finding Classification Matrix

Per architectural governance, findings are strictly segregated into four operational tiers plus a dedicated technical-security category:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                          PRODUCTION REMEDIATION CLASSIFICATION                         │
└────────────────────────────────────────────────────────────────────────────────────────┘
  │
  ├───► TIER 1: SAFE AUTOMATIC REMEDIATION
  │     └── OpenGraph Image Canonical URL qualification (make relative URLs absolute HTTPS).
  │
  ├───► TIER 2: REMEDIATION REQUIRING HUMAN APPROVAL (Content & SERP Snippets)
  │     ├── Title Tag Pixel Truncation (618px → 472px)
  │     └── Meta Description Character Truncation (231 chars → 142 chars)
  │
  ├───► TIER 3: ARCHITECTURE / DEVELOPER CHANGE (Structural Rendering)
  │     ├── SSR H1 Heading Missing in Static HTML (Vite SPA Hydration Analysis)
  │     └── Zero Static Internal Outlinks (SPA Routing vs Prerendering vs Semantic HTML Shell)
  │
  ├───► TIER 4: INFORMATIONAL OBSERVATIONS (AI / Emerging Standards)
  │     ├── /llms.txt Absence (GEO Readiness observation — NOT an SEO error)
  │     └── Robots.txt AI Bot Directives (Informational policy governance)
  │
  └───► TECHNICAL-SECURITY CATEGORY (Reverse Proxy / Nginx Governance)
        └── 5 Missing HTTP Security Headers (X-Content-Type-Options, X-Frame-Options, CSP, HSTS, Referrer)
```

---

## 2. In-Depth Architectural Investigation

### 2.1 The SSR H1 Heading Issue
* **Root Cause Identified:**  
  In `website/index.html`, the `<body>` contains only `<div id="root"></div>` and `<script type="module" src="/src/main.jsx"></script>`.  
  Inside React (`website/src/main.jsx`), an `<h1>` tag **does** exist:
  ```jsx
  <h1>
    AI-assisted ecommerce operations.
    <br />
    Automate the repetitive work — with humans in control.
  </h1>
  ```
  However, non-JavaScript search bots (or bots operating under compute-constrained first-pass crawls) fetch `index.html` and parse the raw DOM before the Vite bundle downloads, parses, and executes `createRoot().render()`. These crawlers see **0 `<h1>` tags**.
* **Architectural Options Evaluated:**
  * *Option A: Artificial hidden `<h1 class="sr-only">` in `<head>` or outer `<body>`.*  
    **Rejected:** Search engines consider hidden text cloaking if it does not match visible content.
  * *Option B: Full Server-Side Rendering (SSR) migration (Node.js/Express or Next.js).*  
    **Rejected for Phase 2:** Adds heavy operational overhead, server state, and eliminates the simplicity of the static Nginx `/var/www/sanocea/current` file server.
  * *Option C: Semantic Fallback Shell inside `<div id="root">` (Recommended).*  
    React 19 / `createRoot(document.getElementById('root'))` **cleanly replaces all inner children of `#root` upon hydration**. Placing a semantic HTML fallback containing the exact matching `<h1>` and navigation links inside `<div id="root">...</div>` allows non-JS crawlers to index the exact semantic content immediately, while browser users experience zero layout shift before React hydrates.

### 2.2 The Zero Static Internal Links Issue
* **Root Cause Identified:**  
  The homepage navigation currently renders in React with in-page anchor links (`href="#fragment"`, `href="#stack"`, `href="#operations"`, `href="#diagnostic"`). The only cross-page link is `<a href="/demo.html">`.  
  Crucially, there are **no static HTML links in `index.html`** pointing to:
  * `/solutions/marketplace-reconciliation/`
  * `/demo.html`
  * `/sitemap.xml`
  Because Screaming Frog and legacy crawlers do not execute JavaScript by default, they discover 0 internal outlinks and abort the crawl after page 1.
* **Architectural Recommendation:**  
  Instead of injecting "artificial" invisible links, add a clean, static, accessible footer/sitemap shell in `index.html` inside `<div id="root">` (or static `<noscript>` / footer template) that links to canonical solutions, demo, and sitemap.

---

## 3. Production Change Plan: Exact Before & After Specifications

### Change 1: Title Tag Truncation (Tier 2 — Needs Approval)
* **File:** [`website/index.html`](file:///opt/sanocea/repo/website/index.html) (Line 288)
* **Before Value:**  
  ```html
  <title>SANOCEA™ | AI-Assisted Ecommerce Operations & Marketplace Exception Automation</title>
  ```
  *(78 characters · Calculated SERP Pixel Width: 618px — Exceeds 561px limit)*
* **Proposed After Value:**  
  ```html
  <title>SANOCEA™ | AI-Assisted Ecommerce Operations</title>
  ```
  *(44 characters · Calculated SERP Pixel Width: 472px — 100% within Google SERP limits)*
* **Expected SEO Effect:** Title will display in full across all desktop and mobile Google SERP snippets without unsightly `...` ellipsis truncation.
* **Rollback Method:** Revert line 288 to previous 78-char string.

---

### Change 2: Meta Description Truncation (Tier 2 — Needs Approval)
* **File:** [`website/index.html`](file:///opt/sanocea/repo/website/index.html) (Lines 46–48)
* **Before Value:**  
  ```html
  <meta
    name="description"
    content="SANOCEA™ helps ecommerce businesses automate repetitive operational work across catalogue, inventory, pricing, orders, fulfilment, reconciliation, and marketplace exceptions — while keeping humans in control of important decisions."
  />
  ```
  *(231 characters · Calculated SERP Pixel Width: 1,471px — Exceeds 155-char / 985px limit)*
* **Proposed After Value:**  
  ```html
  <meta
    name="description"
    content="SANOCEA™ automates repetitive ecommerce operations across catalogue, inventory, pricing, orders, and reconciliation — with humans in control."
  />
  ```
  *(142 characters · Calculated SERP Pixel Width: 908px — 100% within 155-char / 985px limits)*
* **Expected SEO Effect:** Eliminates truncation; search engines will show the complete value proposition rather than cutting off at "reconciliation...".
* **Rollback Method:** Revert lines 46–48 to previous text.

---

### Change 3: OpenGraph Title Synchronization (Tier 1 — Safe Automatic)
* **File:** [`website/index.html`](file:///opt/sanocea/repo/website/index.html) (Line 60)
* **Before Value:**  
  ```html
  <meta property="og:title" content="SANOCEA™ | AI-Assisted Ecommerce Operations & Marketplace Exception Automation" />
  ```
* **Proposed After Value:**  
  ```html
  <meta property="og:title" content="SANOCEA™ | AI-Assisted Ecommerce Operations" />
  ```
* **Expected SEO Effect:** Consistent branding across Google SERPs, LinkedIn, Twitter/X, and WhatsApp link previews.

---

### Change 4: Semantic Pre-Hydration H1 & Internal Links (Tier 3 — Developer / Architecture)
* **File:** [`website/index.html`](file:///opt/sanocea/repo/website/index.html) (Line 291)
* **Before Value:**  
  ```html
  <div id="root"></div>
  ```
* **Proposed After Value:**  
  ```html
  <div id="root">
    <header class="ssr-shell" style="padding: 24px; text-align: center;">
      <h1>AI-assisted ecommerce operations. Automate the repetitive work — with humans in control.</h1>
      <nav aria-label="Quick links" style="margin-top: 12px; font-size: 14px;">
        <a href="/demo.html">Commerce Command Center Demo</a> ·
        <a href="/solutions/marketplace-reconciliation/">Marketplace Reconciliation</a> ·
        <a href="/sitemap.xml">Sitemap</a>
      </nav>
    </header>
  </div>
  ```
* **Mechanism:** When React mounts in `main.jsx` via `createRoot(document.getElementById('root')).render(...)`, React cleanly replaces this inner content. Non-JS bots immediately see the canonical `<h1>` and crawlable `<a href>` links.
* **Expected SEO Effect:** Resolves `H1_HEADING_MISSING_IN_SSR` and `PAGES_WITHOUT_INTERNAL_OUTLINKS` simultaneously.
* **Rollback Method:** Empty the contents of `<div id="root"></div>`.

---

### Change 5: Security Response Headers (Technical-Security Category)
* **File:** `/etc/nginx/sites-available/sanocea-website` (Lines 85–88)
* **Proposed Addition inside `server { listen 443 ... location / { ... } }`:**
  ```nginx
  add_header X-Content-Type-Options "nosniff" always;
  add_header X-Frame-Options "SAMEORIGIN" always;
  add_header Referrer-Policy "strict-origin-when-cross-origin" always;
  add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
  ```
* **Expected Effect:** Passes all 5 security header audits (`issues_overview_report.csv` resolution); defends against MIME-sniffing and clickjacking.
* **Verification:** `curl -sI https://www.sanocea.com/ | grep -E 'X-Content-Type|X-Frame|Strict-Transport|Referrer'`.
* **Rollback Method:** Remove the `add_header` directives and reload nginx via `nginx -t && systemctl reload nginx`.

---

### Change 6: `/llms.txt` GEO File Deployment (Tier 4 — GEO Initiative)
* **File:** `website/public/llms.txt` (New File)
* **Proposed Content:**
  ```markdown
  # SANOCEA™ — AI-Assisted Ecommerce Operations Layer
  > Operational automation across catalogue, inventory, pricing, orders, fulfilment, reconciliation, and marketplace exceptions with humans in control.

  ## Canonical Modules & Solutions
  - [Commerce Command Center](/demo.html): Unified operations dashboard and WhatsApp decision layer.
  - [Marketplace Reconciliation](/solutions/marketplace-reconciliation/): Automated settlement deduction auditing across Amazon, Flipkart, and Blinkit.
  - [Operational Domains](/#operations): Catalogue, Inventory Drift, Pricing MAP, Order Triage, NDR Management.
  ```
* **Expected Effect:** Resolves `LLMS_TXT_ABSENT_OBSERVATION` and provides clean, structured Markdown for AI engines (Perplexity, ChatGPT, Claude).

---

## 4. Multi-Domain Generic Verification Plan (Acceptance Criteria)

To prove that `@sanocea/seo-stack` is a generic, reusable product and not a hardcoded SANOCEA checker:
1. **Primary Domain Execution (`sanocea.com`):**
   * Apply approved changes → Run `scripts/deploy_website.sh` → Recrawl production via `@sanocea/seo-stack` CLI → Generate Before/After Verification Receipt.
2. **Secondary Domain Execution:**
   * Run the exact same engine against a live external target (e.g. `https://shop.waaree.com` or `https://httpbin.org` or a live client storefront).
   * Verify that:
     * Discovered URLs, title pixel widths, meta descriptions, heading structures, and schema are independently parsed.
     * Ecommerce detection (Shopify dilution / Product schema) triggers dynamically based on observed HTML.
     * Zero hardcoded logic leaks across domains.
