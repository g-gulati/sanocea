/**
 * SANOCEA SEO Stack — Test Fixtures
 * Matches the exact live DOM state of https://www.sanocea.com/ and Shopify patterns
 */

export const SANOCEA_BASELINE_HTML = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="theme-color" content="#f6fbff" />
    <meta
      name="description"
      content="SANOCEA™ helps ecommerce businesses automate repetitive operational work across catalogue, inventory, pricing, orders, fulfilment, reconciliation, and marketplace exceptions — while keeping humans in control of important decisions."
    />
    <meta
      name="keywords"
      content="AI-assisted ecommerce operations, ecommerce operations automation, marketplace operations"
    />
    <meta name="robots" content="index, follow" />
    <link rel="canonical" href="https://www.sanocea.com/" />
    <link rel="icon" href="/sanocea-wordmark.png" />
    <meta property="og:site_name" content="SANOCEA™" />
    <meta property="og:type" content="website" />
    <meta property="og:url" content="https://www.sanocea.com/" />
    <meta property="og:title" content="SANOCEA™ | AI-Assisted Ecommerce Operations & Marketplace Exception Automation" />
    <meta
      property="og:description"
      content="Automate repetitive operational work across catalogue, inventory, pricing, orders, fulfilment, reconciliation, and marketplace exceptions — while keeping humans in control of important decisions."
    />
    <meta property="og:image" content="/sanocea-wordmark.png" />
    <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": "SANOCEA™",
        "legalName": "Sanocea",
        "url": "https://www.sanocea.com/",
        "logo": "https://www.sanocea.com/sanocea-wordmark.png"
      }
    </script>
    <script type="module" src="/src/main.jsx"></script>
    <title>SANOCEA™ | AI-Assisted Ecommerce Operations & Marketplace Exception Automation</title>
  </head>
  <body>
    <!-- Client-side hydrated SPA: Note empty root container and 0 static <h1> tags -->
    <div id="root"></div>
  </body>
</html>`;

export const SANOCEA_ROBOTS_TXT = `User-agent: *
Disallow: /admin/
Disallow: /private/
`;

export const SHOPIFY_TEST_STORE_HTML = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>Solar Hybrid Inverter 3kW — Clean Energy Direct</title>
    <meta name="description" content="Commercial grade 3kW single-phase solar inverter with MPPT charge controller." />
    <link rel="canonical" href="https://store.example.com/products/solar-hybrid-inverter-3kw" />
    <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Solar Hybrid Inverter 3kW",
        "sku": "INV-3KW-01",
        "offers": {
          "@type": "Offer",
          "price": "85000",
          "priceCurrency": "INR",
          "availability": "https://schema.org/InStock"
        }
      }
    </script>
  </head>
  <body>
    <header>
      <nav>
        <!-- Shopify Collection URL Canonical Dilution Bug -->
        <a href="/collections/inverters/products/solar-hybrid-inverter-3kw">Solar Hybrid Inverter 3kW</a>
        <a href="/collections/all-products/products/solar-hybrid-inverter-3kw">Inverter Featured</a>
      </nav>
    </header>
    <main>
      <h1>Solar Hybrid Inverter 3kW</h1>
      <!-- Real Stock Contradiction: Storefront says Out of Stock while Schema said InStock -->
      <div class="stock-status">Out of Stock</div>
      <button disabled>Add to cart</button>
    </main>
  </body>
</html>`;
