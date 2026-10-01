/**
 * SANOCEA SEO Stack — Track A: Core Technical SEO & On-Page Observer
 * Hardened with Route Intent Classification
 */

import { staticVisibleText, countWords } from '../core/staticText.js';
import { RETIRED_RICH_RESULTS } from '../core/retiredRichResults.js';
import { PageAuditContext, SeoFinding } from '../core/types.js';
import { calculateTitlePixelWidth, calculateMetaDescPixelWidth, GOOGLE_SERP_LIMITS } from '../core/pixelWidth.js';
import { estimateCommercialRisk } from '../core/businessImpact.js';
import { classifyRouteIntent, isUtilityOrNonIndexableIntent } from '../core/routeIntent.js';

export function runTechnicalSeoObserver(context: PageAuditContext): SeoFinding[] {
  const findings: SeoFinding[] = [];
  const { page, $ } = context;
  const now = new Date().toISOString();
  const routeIntent = classifyRouteIntent(page.url);

  // ── 1. Page Title Checks ──────────────────────────────────────────
  const titleTags = $('title');
  const titleText = titleTags.first().text().trim();

  if (titleTags.length === 0 || !titleText) {
    if (routeIntent !== 'SYSTEM_FEED') {
      const risk = estimateCommercialRisk('TITLE_TAG_MISSING', page.url);
      findings.push({
        findingId: `SAN-SEO-TIT-MISSING-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
        url: page.url,
        routeIntent,
        detectionRule: 'TITLE_TAG_MISSING',
        track: 'TRACK_A_CORE_SEO',
        category: 'Technical SEO',
        severity: 'CRITICAL',
        evidenceClass: '[O] Observed',
        observedValue: titleTags.length === 0 ? '0 <title> tags found' : 'Empty <title>',
        expectedValue: 'Descriptive title between 30 and 60 characters (<= 561px)',
        exactEvidence: {
          htmlSnippet: titleTags.length > 0 ? titleTags.prop('outerHTML') : undefined,
          domSelector: 'head > title'
        },
        reproductionMethod: `curl -sL '${page.url}' | grep -i '<title>'`,
        businessImpact: 'Search engines fail to determine page topic; causes severe organic ranking penalty.',
        commercialRisk: risk.commercialRisk,
        automationOpportunity: risk.automationOpportunity,
        recommendedRemediation: 'Add a concise, unique <title> tag inside the <head> element.',
        automaticallyFixable: true,
        requiredAccess: 'HTML / Template source code',
        remediationStatus: 'ACTION_REQUIRED',
        beforeEvidence: null,
        afterEvidence: null,
        verificationResult: null,
        timestamp: now
      });
    }
  } else {
    const charLen = titleText.length;
    const pixelWidth = calculateTitlePixelWidth(titleText);

    if (pixelWidth > GOOGLE_SERP_LIMITS.TITLE_MAX_PIXELS) {
      const risk = estimateCommercialRisk('TITLE_PIXEL_WIDTH_EXCEEDED', page.url);
      findings.push({
        findingId: `SAN-SEO-TIT-OVERFLOW-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
        url: page.url,
        routeIntent,
        detectionRule: 'TITLE_PIXEL_WIDTH_EXCEEDED',
        track: 'TRACK_A_CORE_SEO',
        category: 'Technical SEO',
        severity: 'HIGH',
        evidenceClass: '[O] Observed',
        observedValue: `${pixelWidth}px (${charLen} chars)`,
        expectedValue: `≤ ${GOOGLE_SERP_LIMITS.TITLE_MAX_PIXELS}px (≤ 60 chars)`,
        exactEvidence: {
          htmlSnippet: `<title>${titleText}</title>`,
          domSelector: 'head > title',
          pixelWidth,
          charLength: charLen
        },
        reproductionMethod: `Calculate Arial 20px width of title string: "${titleText}"`,
        businessImpact: 'Google SERP truncates title with an ellipsis (...), cutting off primary branding and value proposition.',
        commercialRisk: risk.commercialRisk,
        automationOpportunity: risk.automationOpportunity,
        recommendedRemediation: `Shorten title to <= 561px (<= 60 chars) while preserving primary search keywords.`,
        automaticallyFixable: true,
        requiredAccess: 'HTML / Template source code',
        remediationStatus: 'ACTION_REQUIRED',
        beforeEvidence: titleText,
        afterEvidence: null,
        verificationResult: null,
        timestamp: now
      });
    }
  }

  // ── 2. Meta Description Checks ────────────────────────────────────
  const metaDescTag = $('meta[name="description"]');
  const metaDescText = metaDescTag.attr('content')?.trim();

  if (!metaDescText && !isUtilityOrNonIndexableIntent(routeIntent)) {
    const risk = estimateCommercialRisk('META_DESCRIPTION_MISSING', page.url);
    findings.push({
      findingId: `SAN-SEO-METADESC-MISSING-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
      url: page.url,
      routeIntent,
      detectionRule: 'META_DESCRIPTION_MISSING',
      track: 'TRACK_A_CORE_SEO',
      category: 'Technical SEO',
      severity: 'MEDIUM',
      evidenceClass: '[O] Observed',
      observedValue: 'Missing meta description',
      expectedValue: 'Compelling snippet between 70 and 155 characters (<= 985px)',
      exactEvidence: {
        domSelector: 'head > meta[name="description"]'
      },
      reproductionMethod: `curl -sL '${page.url}' | grep -i 'name="description"'`,
      businessImpact: 'Search engines generate random page text excerpts in search results, reducing click-through rate (CTR).',
      commercialRisk: risk.commercialRisk,
      automationOpportunity: risk.automationOpportunity,
      recommendedRemediation: 'Provide a targeted meta description that clearly states the page value proposition.',
      automaticallyFixable: true,
      requiredAccess: 'HTML / Template source code',
      remediationStatus: 'ACTION_REQUIRED',
      beforeEvidence: null,
      afterEvidence: null,
      verificationResult: null,
      timestamp: now
    });
  } else if (metaDescText) {
    const charLen = metaDescText.length;
    const pixelWidth = calculateMetaDescPixelWidth(metaDescText);

    if (charLen > GOOGLE_SERP_LIMITS.META_DESC_MAX_CHARS || pixelWidth > GOOGLE_SERP_LIMITS.META_DESC_MAX_PIXELS) {
      const risk = estimateCommercialRisk('META_DESCRIPTION_LENGTH_EXCEEDED', page.url);
      findings.push({
        findingId: `SAN-SEO-METADESC-OVERFLOW-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
        url: page.url,
        routeIntent,
        detectionRule: 'META_DESCRIPTION_LENGTH_EXCEEDED',
        track: 'TRACK_A_CORE_SEO',
        category: 'Technical SEO',
        severity: 'MEDIUM',
        evidenceClass: '[O] Observed',
        observedValue: `${charLen} characters (${pixelWidth}px)`,
        expectedValue: `70–${GOOGLE_SERP_LIMITS.META_DESC_MAX_CHARS} characters (≤ ${GOOGLE_SERP_LIMITS.META_DESC_MAX_PIXELS}px)`,
        exactEvidence: {
          htmlSnippet: `<meta name="description" content="${metaDescText}">`,
          domSelector: 'head > meta[name="description"]',
          pixelWidth,
          charLength: charLen
        },
        reproductionMethod: `Inspect length of: "${metaDescText.slice(0, 60)}..."`,
        businessImpact: 'Meta description is truncated with an ellipsis in SERP snippets, losing important conversion copy.',
        commercialRisk: risk.commercialRisk,
        automationOpportunity: risk.automationOpportunity,
        recommendedRemediation: `Refine meta description to within 150 characters to prevent truncation.`,
        automaticallyFixable: true,
        requiredAccess: 'HTML / Template source code',
        remediationStatus: 'ACTION_REQUIRED',
        beforeEvidence: metaDescText,
        afterEvidence: null,
        verificationResult: null,
        timestamp: now
      });
    }
  }

  // ── 3. Heading Hierarchy (H1) Checks ──────────────────────────────
  const h1Tags = $('h1');
  if (!isUtilityOrNonIndexableIntent(routeIntent)) {
    if (h1Tags.length === 0) {
      const risk = estimateCommercialRisk('H1_HEADING_MISSING_IN_SSR', page.url);
      findings.push({
        findingId: `SAN-SEO-H1-MISSING-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
        url: page.url,
        routeIntent,
        detectionRule: 'H1_HEADING_MISSING_IN_SSR',
        track: 'TRACK_A_CORE_SEO',
        category: 'Content & Headings',
        severity: 'CRITICAL',
        evidenceClass: '[O] Observed',
        observedValue: '0 <h1> tags found in static server-rendered HTML',
        expectedValue: 'Exactly 1 <h1> tag representing the primary page topic',
        exactEvidence: {
          rawContext: 'Raw HTML contains empty root container without static <h1> tag',
          domSelector: 'h1'
        },
        reproductionMethod: `curl -sL '${page.url}' | grep -c '<h1'`,
        businessImpact: 'Search crawlers that do not execute heavy client-side JavaScript perceive a missing primary page heading, degrading ranking ability.',
        commercialRisk: risk.commercialRisk,
        automationOpportunity: risk.automationOpportunity,
        recommendedRemediation: 'Render a semantic <h1> tag server-side in the initial HTML response rather than relying entirely on client-side JS hydration.',
        automaticallyFixable: true,
        requiredAccess: 'Server-side HTML / React SSR template',
        remediationStatus: 'ACTION_REQUIRED',
        beforeEvidence: 'Zero <h1> in static HTML',
        afterEvidence: null,
        verificationResult: null,
        timestamp: now
      });
    } else if (h1Tags.length > 1) {
      findings.push({
        findingId: `SAN-SEO-H1-MULTIPLE-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
        url: page.url,
        routeIntent,
        detectionRule: 'MULTIPLE_H1_HEADINGS',
        track: 'TRACK_A_CORE_SEO',
        category: 'Content & Headings',
        severity: 'LOW',
        evidenceClass: '[O] Observed',
        observedValue: `${h1Tags.length} <h1> tags found`,
        expectedValue: 'Exactly 1 primary <h1> per document',
        exactEvidence: {
          htmlSnippet: h1Tags.map((_idx: number, el: any) => $(el).prop('outerHTML')).get().join(' | ')
        },
        reproductionMethod: `curl -sL '${page.url}' | grep -o '<h1[^>]*>.*</h1>'`,
        businessImpact: 'Multiple H1s dilute page topical focus across competing headlines.',
        recommendedRemediation: 'Consolidate page structure into 1 primary <h1> and demote secondary headers to <h2>.',
        automaticallyFixable: true,
        requiredAccess: 'Template source code',
        remediationStatus: 'ACTION_REQUIRED',
        beforeEvidence: null,
        afterEvidence: null,
        verificationResult: null,
        timestamp: now
      });
    }
  }

  // Heading order check (detect skipped levels e.g. H1 followed directly by H3 without H2)
  const headings: { level: number; text: string }[] = [];
  $('h1, h2, h3, h4, h5, h6').each((_: number, el: any) => {
    const tagName = el.tagName?.toLowerCase();
    if (tagName) {
      const level = parseInt(tagName.replace('h', ''), 10);
      headings.push({ level, text: $(el).text().trim() });
    }
  });

  for (let i = 0; i < headings.length - 1; i++) {
    const current = headings[i].level;
    const next = headings[i + 1].level;
    if (next > current + 1) {
      findings.push({
        findingId: `SAN-SEO-HDG-SKIP-${Buffer.from(page.url).toString('base64').slice(0, 8)}-${i}`,
        url: page.url,
        routeIntent,
        detectionRule: 'HEADING_LEVEL_SKIPPED',
        track: 'TRACK_A_CORE_SEO',
        category: 'Content & Headings',
        severity: 'LOW',
        evidenceClass: '[O] Observed',
        observedValue: `<h${current}> followed directly by <h${next}>`,
        expectedValue: `Sequential heading hierarchy (e.g. <h${current}> followed by <h${current + 1}>)`,
        exactEvidence: {
          skippedHeading: `<h${current}>: "${headings[i].text.slice(0, 40)}" -> <h${next}>: "${headings[i + 1].text.slice(0, 40)}"`,
          domSelector: `h${next}`
        },
        reproductionMethod: `Inspect DOM heading order on ${page.url}`,
        businessImpact: 'Impaired document outline parsing for screen readers and semantic search engines.',
        recommendedRemediation: `Adjust <h${next}> to <h${current + 1}> or introduce intermediate sub-heading.`,
        automaticallyFixable: true,
        requiredAccess: 'HTML / Component templates',
        remediationStatus: 'ACTION_REQUIRED',
        beforeEvidence: `<h${current}> -> <h${next}>`,
        afterEvidence: null,
        verificationResult: null,
        timestamp: now
      });
      break;
    }
  }

  // ── 4. Image ALT & Asset Integrity ────────────────────────────────
  const images = $('img');
  let missingAltCount = 0;
  let emptyAltCount = 0;
  let sampleBrokenImage: string | undefined;

  images.each((_: number, el: any) => {
    const src = $(el).attr('src') || '';
    const alt = $(el).attr('alt');

    if (alt === undefined) {
      missingAltCount++;
      if (!sampleBrokenImage) sampleBrokenImage = src;
    } else if (alt.trim() === '') {
      emptyAltCount++;
    }
  });

  if (missingAltCount > 0 && !isUtilityOrNonIndexableIntent(routeIntent)) {
    findings.push({
      findingId: `SAN-SEO-IMG-ALT-MISSING-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
      url: page.url,
      routeIntent,
      detectionRule: 'IMAGE_ALT_TAGS_MISSING',
      track: 'TRACK_A_CORE_SEO',
      category: 'Image & Media',
      severity: 'MEDIUM',
      evidenceClass: '[O] Observed',
      observedValue: `${missingAltCount} images without alt attribute`,
      expectedValue: 'Descriptive alt attribute on all content images',
      exactEvidence: {
        brokenSrc: sampleBrokenImage,
        domSelector: 'img:not([alt])'
      },
      reproductionMethod: `curl -sL '${page.url}' | grep -o '<img[^>]*>' | grep -v 'alt='`,
      businessImpact: 'Images cannot be indexed in Google Image Search; fails accessibility (WCAG 2.1 AA) compliance.',
      commercialRisk: {
        riskType: 'SERP_CTR_LEAK',
        title: 'Image Search Discoverability Deficit',
        estimatedMonthlyLossInr: 15000,
        currency: 'INR',
        confidence: '[ESTIMATED]',
        source: 'industry_benchmark_estimate',
        severityScore: 2,
        calculationFormula: 'Lost image search clicks: ₹15,000/mo'
      },
      recommendedRemediation: 'Add contextual, keyword-relevant alt attributes to all <img> tags.',
      automaticallyFixable: true,
      requiredAccess: 'HTML / Asset templates',
      remediationStatus: 'ACTION_REQUIRED',
      beforeEvidence: `${missingAltCount} images missing alt`,
      afterEvidence: null,
      verificationResult: null,
      timestamp: now
    });
  }

  // Missing explicit width/height dimensions (CLS Prevention)
  let missingDimensionsCount = 0;
  let sampleMissingDimImage: string | undefined;

  images.each((_: number, el: any) => {
    const widthAttr = $(el).attr('width');
    const heightAttr = $(el).attr('height');
    const styleAttr = $(el).attr('style') || '';
    const hasStyleDimensions = /width\s*:\s*\d+/i.test(styleAttr) && /height\s*:\s*\d+/i.test(styleAttr);
    const hasAspectRatio = /aspect-ratio\s*:/i.test(styleAttr);

    if (!widthAttr && !heightAttr && !hasStyleDimensions && !hasAspectRatio) {
      missingDimensionsCount++;
      if (!sampleMissingDimImage) sampleMissingDimImage = $(el).attr('src') || $(el).prop('outerHTML');
    }
  });

  if (missingDimensionsCount > 0 && !isUtilityOrNonIndexableIntent(routeIntent)) {
    findings.push({
      findingId: `SAN-SEO-IMG-NODIM-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
      url: page.url,
      routeIntent,
      detectionRule: 'IMAGE_MISSING_EXPLICIT_DIMENSIONS',
      track: 'TRACK_A_CORE_SEO',
      category: 'Image & Media',
      severity: 'MEDIUM',
      evidenceClass: '[O] Observed',
      observedValue: `${missingDimensionsCount} image(s) lack explicit width and height dimensions`,
      expectedValue: 'Explicit width and height HTML attributes or CSS aspect-ratio on all <img> tags',
      exactEvidence: {
        brokenSrc: sampleMissingDimImage,
        domSelector: 'img:not([width]):not([height])'
      },
      reproductionMethod: `Inspect <img> elements on ${page.url} for missing width/height attributes`,
      businessImpact: 'Causes layout instability (Cumulative Layout Shift / CLS) while assets render, degrading Core Web Vitals and organic search rank.',
      commercialRisk: {
        riskType: 'CONVERSION_FRICTION',
        title: 'CLS Visual Instability & Core Web Vitals Ranking Penalty',
        estimatedMonthlyLossInr: 12000,
        currency: 'INR',
        confidence: '[ESTIMATED]',
        source: 'industry_benchmark_estimate',
        severityScore: 3,
        calculationFormula: 'Modeled Core Web Vitals conversion friction penalty: ₹12,000/mo'
      },
      recommendedRemediation: 'Add explicit width and height HTML attributes or aspect-ratio CSS to <img> tags in template code.',
      automaticallyFixable: true,
      requiredAccess: 'HTML / Component templates',
      remediationStatus: 'ACTION_REQUIRED',
      beforeEvidence: `${missingDimensionsCount} images missing dimensions`,
      afterEvidence: null,
      verificationResult: null,
      timestamp: now
    });
  }

  // Legacy format detection (PNG/JPG where WebP/AVIF next-gen is appropriate)
  let legacyFormatCount = 0;
  let sampleLegacyImage: string | undefined;

  images.each((_: number, el: any) => {
    const src = ($(el).attr('src') || '').trim();
    if (!src || src.startsWith('data:')) return;

    // Skip tracking pixels or icons <= 16px
    const widthAttr = parseInt($(el).attr('width') || '100', 10);
    const heightAttr = parseInt($(el).attr('height') || '100', 10);
    if (widthAttr <= 16 || heightAttr <= 16 || src.includes('favicon') || src.includes('tracking')) {
      return;
    }

    const isLegacy = /\.(jpe?g|png)(\?.*)?$/i.test(src);
    if (isLegacy) {
      // Check if enclosed in <picture> with webp or avif <source>
      const parent = $(el).parent();
      const hasPictureWebp = parent.is('picture') && parent.find('source[type*="webp"], source[type*="avif"]').length > 0;
      if (!hasPictureWebp) {
        legacyFormatCount++;
        if (!sampleLegacyImage) sampleLegacyImage = src;
      }
    }
  });

  if (legacyFormatCount > 0 && !isUtilityOrNonIndexableIntent(routeIntent)) {
    findings.push({
      findingId: `SAN-SEO-IMG-LEGACY-FMT-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
      url: page.url,
      routeIntent,
      detectionRule: 'IMAGE_LEGACY_FORMAT_NOT_NEXTGEN',
      track: 'TRACK_A_CORE_SEO',
      category: 'Image & Media',
      severity: 'LOW',
      evidenceClass: '[O] Observed',
      observedValue: `${legacyFormatCount} raster image(s) served in legacy PNG/JPG format without WebP/AVIF alternatives`,
      expectedValue: 'Next-generation image formats (WebP/AVIF) served via <picture> or CDN image optimization',
      exactEvidence: {
        brokenSrc: sampleLegacyImage,
        domSelector: 'img[src$=".png"], img[src$=".jpg"], img[src$=".jpeg"]'
      },
      reproductionMethod: `curl -sL '${page.url}' | grep -iE '\\.(png|jpg|jpeg)'`,
      businessImpact: 'Legacy formats generate 25-50% larger payloads, degrading Largest Contentful Paint (LCP) and inflating mobile data usage.',
      commercialRisk: {
        riskType: 'CONVERSION_FRICTION',
        title: 'Largest Contentful Paint Latency via Uncompressed Raster Assets',
        estimatedMonthlyLossInr: 8000,
        currency: 'INR',
        confidence: '[ESTIMATED]',
        source: 'industry_benchmark_estimate',
        severityScore: 2,
        calculationFormula: 'Modeled mobile bounce rate increase from unoptimized images: ₹8,000/mo'
      },
      recommendedRemediation: 'Convert raster assets to modern WebP/AVIF via build pipeline (e.g. Sharp / Next.js Image) or dynamic CDN optimization (e.g. Cloudflare Polish). Note: Autonomous template editing cannot safely convert binary image assets.',
      automaticallyFixable: false,
      requiredAccess: 'CDN / Image build pipeline',
      remediationStatus: 'ACTION_REQUIRED',
      beforeEvidence: `${legacyFormatCount} legacy PNG/JPG images`,
      afterEvidence: null,
      verificationResult: null,
      timestamp: now
    });
  }

  // Oversized image payload detection
  let oversizedCount = 0;
  let sampleOversizedImage: string | undefined;

  images.each((_: number, el: any) => {
    const src = $(el).attr('src') || '';
    const widthAttr = parseInt($(el).attr('width') || '0', 10);
    const dataSize = parseInt($(el).attr('data-size') || '0', 10);
    const hasSrcset = !!$(el).attr('srcset');

    // Check width >= 1600px without responsive srcset, or explicit data-size > 150KB (153600 bytes), or query params indicating huge dimensions
    const isHeavyQuery = /[?&](w|width)=(2[0-9]{3}|[3-9][0-9]{3})/i.test(src);
    if (dataSize > 153600 || (widthAttr >= 1600 && !hasSrcset) || isHeavyQuery) {
      oversizedCount++;
      if (!sampleOversizedImage) sampleOversizedImage = src || $(el).prop('outerHTML');
    }
  });

  if (oversizedCount > 0 && !isUtilityOrNonIndexableIntent(routeIntent)) {
    findings.push({
      findingId: `SAN-SEO-IMG-OVERSIZED-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
      url: page.url,
      routeIntent,
      detectionRule: 'IMAGE_OVERSIZED_PAYLOAD',
      track: 'TRACK_A_CORE_SEO',
      category: 'Image & Media',
      severity: 'MEDIUM',
      evidenceClass: '[O] Observed',
      observedValue: `${oversizedCount} image(s) exceed 150KB or display width >= 1600px without responsive srcset`,
      expectedValue: 'Responsive images with srcset breakpoints and compressed payloads < 150KB',
      exactEvidence: {
        brokenSrc: sampleOversizedImage,
        domSelector: 'img'
      },
      reproductionMethod: `Inspect image dimensions and asset payload sizes on ${page.url}`,
      businessImpact: 'Massive hero and banner images block main-thread rendering and inflate mobile page load times.',
      commercialRisk: {
        riskType: 'CONVERSION_FRICTION',
        title: 'High Page Weight LCP Degradation',
        estimatedMonthlyLossInr: 15000,
        currency: 'INR',
        confidence: '[ESTIMATED]',
        source: 'industry_benchmark_estimate',
        severityScore: 3,
        calculationFormula: 'Modeled mobile conversion drop from high asset weight: ₹15,000/mo'
      },
      recommendedRemediation: 'Resize images to maximum required display dimensions, supply responsive srcset attributes, and compress below 150KB via CDN/asset pipeline. Note: Requires asset build/CDN processing.',
      automaticallyFixable: false,
      requiredAccess: 'Asset pipeline / CDN',
      remediationStatus: 'ACTION_REQUIRED',
      beforeEvidence: `${oversizedCount} oversized images`,
      afterEvidence: null,
      verificationResult: null,
      timestamp: now
    });
  }

  // ── 5. Thin Content / Word Count Audit ─────────────────────────────
  if (!isUtilityOrNonIndexableIntent(routeIntent)) {
    const cleanBodyText = staticVisibleText($);
    const wordCount = countWords(cleanBodyText);

    if (wordCount < 100 && page.status === 200) {
      findings.push({
        findingId: `SAN-SEO-THIN-CONTENT-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
        url: page.url,
        routeIntent,
        detectionRule: 'THIN_CONTENT_DETECTED',
        track: 'TRACK_A_CORE_SEO',
        category: 'Content & Headings',
        severity: 'HIGH',
        evidenceClass: '[O] Observed',
        observedValue: `${wordCount} words of primary visible text`,
        expectedValue: '≥ 250 words of descriptive, authoritative topical content',
        exactEvidence: {
          thinWordCount: wordCount,
          rawContext: cleanBodyText.slice(0, 150)
        },
        reproductionMethod: `Count visible text words on ${page.url} excluding navigation/footer`,
        businessImpact: 'Pages with thin content are classified as low quality by Google Panda/Helpful Content system, depressing domain authority.',
        recommendedRemediation: 'Expand primary page copy with structured product/solution details, specifications, and FAQs.',
        automaticallyFixable: false,
        requiredAccess: 'Copywriting / CMS',
        remediationStatus: 'ACTION_REQUIRED',
        beforeEvidence: `${wordCount} words`,
        afterEvidence: null,
        verificationResult: null,
        timestamp: now
      });
    }
  }

  // ── 6. Anchor Text Quality Audit ──────────────────────────────────
  const GENERIC_ANCHORS = new Set(['click here', 'read more', 'here', 'link', 'learn more', 'this', 'view', 'more']);
  const genericLinksFound: { href: string; text: string }[] = [];

  $('a[href]').each((_: number, el: any) => {
    const text = $(el).text().trim().toLowerCase();
    const href = $(el).attr('href') || '';
    if (GENERIC_ANCHORS.has(text) && !href.startsWith('#') && !href.startsWith('mailto:')) {
      genericLinksFound.push({ href, text });
    }
  });

  if (genericLinksFound.length > 0 && !isUtilityOrNonIndexableIntent(routeIntent)) {
    findings.push({
      findingId: `SAN-SEO-ANCHOR-GENERIC-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
      url: page.url,
      routeIntent,
      detectionRule: 'GENERIC_ANCHOR_TEXT_DETECTED',
      track: 'TRACK_A_CORE_SEO',
      category: 'Internal Linking',
      severity: 'LOW',
      evidenceClass: '[O] Observed',
      observedValue: `${genericLinksFound.length} links using non-descriptive anchor text (e.g. "${genericLinksFound[0].text}")`,
      expectedValue: 'Descriptive, keyword-rich anchor text conveying target destination topic',
      exactEvidence: {
        genericAnchorText: genericLinksFound.map(g => `[${g.text}] -> ${g.href}`).slice(0, 3).join(' | '),
        domSelector: 'a'
      },
      reproductionMethod: `Inspect anchor texts of links on ${page.url}`,
      businessImpact: 'Fails to pass topical relevance signals through internal link equity to destination pages.',
      recommendedRemediation: `Replace "${genericLinksFound[0].text}" with descriptive target page topic keywords.`,
      automaticallyFixable: true,
      requiredAccess: 'HTML / Component templates',
      remediationStatus: 'ACTION_REQUIRED',
      beforeEvidence: genericLinksFound[0].text,
      afterEvidence: null,
      verificationResult: null,
      timestamp: now
    });
  }

  // ── 7. Internal Outlinks & Orphan Discovery ───────────────────────
  const internalOutlinks = page.discoveredUrls.filter(u => u.source === 'internal_link');
  if (internalOutlinks.length === 0 && !isUtilityOrNonIndexableIntent(routeIntent)) {
    const risk = estimateCommercialRisk('PAGES_WITHOUT_INTERNAL_OUTLINKS', page.url);
    findings.push({
      findingId: `SAN-SEO-NO-INTERNAL-OUTLINKS-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
      url: page.url,
      routeIntent,
      detectionRule: 'PAGES_WITHOUT_INTERNAL_OUTLINKS',
      track: 'TRACK_A_CORE_SEO',
      category: 'Internal Linking',
      severity: 'HIGH',
      evidenceClass: '[O] Observed',
      observedValue: '0 internal HTML <a href> links discovered in static HTML',
      expectedValue: 'Navigational links to internal solutions, pricing, and demo pages in static HTML',
      exactEvidence: {
        rawContext: 'Page does not expose static HTML <a href="..."> links to internal routes; links are client-rendered or handled via JS event listeners'
      },
      reproductionMethod: `curl -sL '${page.url}' | grep -o '<a[^>]*href=\"/[^\"]*\"'`,
      businessImpact: 'Root cause why standard crawlers (like Screaming Frog) fail to discover subpages. Internal link equity cannot flow through client-rendered JS buttons.',
      commercialRisk: risk.commercialRisk,
      automationOpportunity: risk.automationOpportunity,
      recommendedRemediation: 'Include standard HTML <a href="..."> tags in header/footer navigation for key landing pages.',
      automaticallyFixable: true,
      requiredAccess: 'HTML navigation templates',
      remediationStatus: 'ACTION_REQUIRED',
      beforeEvidence: '0 internal <a href> in static HTML',
      afterEvidence: null,
      verificationResult: null,
      timestamp: now
    });
  }

  // Check Crawl Graph if available: is this page an orphan?
  if (context.crawlGraph && !isUtilityOrNonIndexableIntent(routeIntent)) {
    const node = context.crawlGraph.get(page.url);
    if (node && node.isOrphan) {
      findings.push({
        findingId: `SAN-SEO-ORPHAN-PAGE-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
        url: page.url,
        routeIntent,
        detectionRule: 'ORPHAN_PAGE_DETECTED',
        track: 'TRACK_A_CORE_SEO',
        category: 'Internal Linking',
        severity: 'HIGH',
        evidenceClass: '[O] Observed',
        observedValue: '0 internal in-links pointing to this page from the site crawl graph',
        expectedValue: 'At least 1-3 contextual in-links from category or navigation pages',
        exactEvidence: {
          inDegree: node.inDegree,
          outDegree: node.outDegree,
          rawContext: 'Page is discovered in XML sitemap but receives 0 navigational links from any other crawled page'
        },
        reproductionMethod: `Inspect crawl graph in-degree for ${page.url}`,
        businessImpact: 'Orphan pages receive minimal crawl frequency from search engines and suffer from zero distributed PageRank.',
        recommendedRemediation: 'Add internal contextual links to this page from relevant parent categories or articles.',
        automaticallyFixable: false,
        requiredAccess: 'Navigation / CMS',
        remediationStatus: 'ACTION_REQUIRED',
        beforeEvidence: 'in-degree: 0',
        afterEvidence: null,
        verificationResult: null,
        timestamp: now
      });
    }
  }

  // ── 8. Performance Heuristics: Render-Blocking Resources ──────────
  const blockingScripts = $('head > script:not([async]):not([defer]):not([type="application/ld+json"]):not([type="module"])');
  if (blockingScripts.length > 2 && !isUtilityOrNonIndexableIntent(routeIntent)) {
    findings.push({
      findingId: `SAN-SEO-PERF-BLOCKING-JS-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
      url: page.url,
      routeIntent,
      detectionRule: 'RENDER_BLOCKING_SCRIPTS_IN_HEAD',
      track: 'TRACK_A_CORE_SEO',
      category: 'Performance',
      severity: 'MEDIUM',
      evidenceClass: '[O] Observed',
      observedValue: `${blockingScripts.length} synchronous script tags in <head>`,
      expectedValue: 'All <head> scripts should use defer, async, or type="module"',
      exactEvidence: {
        htmlSnippet: blockingScripts.first().prop('outerHTML'),
        domSelector: 'head > script:not([defer]):not([async])'
      },
      reproductionMethod: `curl -sL '${page.url}' | grep '<head>' -A 30 | grep '<script'`,
      businessImpact: 'Blocks HTML parser and delays First Contentful Paint (FCP) and Largest Contentful Paint (LCP).',
      recommendedRemediation: 'Add defer or async attribute to external script tags or move scripts before </body>.',
      automaticallyFixable: true,
      requiredAccess: 'HTML / Bundle config',
      remediationStatus: 'ACTION_REQUIRED',
      beforeEvidence: `${blockingScripts.length} blocking scripts`,
      afterEvidence: null,
      verificationResult: null,
      timestamp: now
    });
  }

  // ── 9. Organization & Extended Structured Data ───────────────────
  const jsonLdScripts = $('script[type="application/ld+json"]');
  const allJsonLdEntities: any[] = [];
  let orgSchemaFound = false;

  jsonLdScripts.each((_: number, el: any) => {
    try {
      const parsed = JSON.parse($(el).html() || '{}');
      const entities = Array.isArray(parsed) ? parsed : (parsed['@graph'] ? parsed['@graph'] : [parsed]);
      for (const ent of entities) {
        if (ent && typeof ent === 'object') {
          allJsonLdEntities.push(ent);
          if (['Organization', 'Corporation', 'LocalBusiness', 'WebSite'].includes(ent['@type'])) {
            orgSchemaFound = true;
          }
        }
      }
    } catch {}
  });

  const urlObj = new URL(page.url);
  const isHomepage = urlObj.pathname === '/' || urlObj.pathname === '';
  if (isHomepage && !orgSchemaFound) {
    findings.push({
      findingId: `SAN-SEO-SCHEMA-ORG-MISSING-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
      url: page.url,
      routeIntent,
      detectionRule: 'ORGANIZATION_SCHEMA_MISSING',
      track: 'TRACK_A_CORE_SEO',
      category: 'Technical SEO',
      severity: 'MEDIUM',
      evidenceClass: '[O] Observed',
      observedValue: 'No Organization or WebSite schema declared in JSON-LD',
      expectedValue: 'Schema.org Organization markup with name, url, logo, and sameAs profiles',
      exactEvidence: {
        domSelector: 'script[type="application/ld+json"]'
      },
      reproductionMethod: `curl -sL '${page.url}' | grep 'application/ld+json'`,
      businessImpact: 'Impairs Google Knowledge Graph entity recognition and brand search panel qualification.',
      recommendedRemediation: 'Inject schema.org/Organization with authoritative brand profiles (LinkedIn, Twitter, Crunchbase).',
      automaticallyFixable: true,
      requiredAccess: 'HTML template source code',
      remediationStatus: 'ACTION_REQUIRED',
      beforeEvidence: 'Missing Organization schema',
      afterEvidence: null,
      verificationResult: null,
      timestamp: now
    });
  }

  // 9a. WebSite + SearchAction Structured Data (Google Sitelinks Searchbox)
  const websiteEntity = allJsonLdEntities.find(ent => ent['@type'] === 'WebSite');
  const hasSearchAction = websiteEntity && websiteEntity.potentialAction && (
    (websiteEntity.potentialAction['@type'] === 'SearchAction' && !!(websiteEntity.potentialAction.target || websiteEntity.potentialAction['target'])) ||
    (Array.isArray(websiteEntity.potentialAction) && websiteEntity.potentialAction.some((a: any) => a['@type'] === 'SearchAction' && !!(a.target || a['target'])))
  );

  if (isHomepage && !hasSearchAction && !isUtilityOrNonIndexableIntent(routeIntent)) {
    findings.push({
      findingId: `SAN-SEO-SCHEMA-WEBSITE-SEARCH-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
      url: page.url,
      routeIntent,
      detectionRule: 'WEBSITE_SEARCH_ACTION_SCHEMA_MISSING',
      track: 'TRACK_A_CORE_SEO',
      category: 'Structured Data',
      severity: 'INFO',
      evidenceClass: '[O] Observed',
      observedValue: websiteEntity ? 'WebSite schema found but missing SearchAction potentialAction' : 'No WebSite schema found on homepage',
      expectedValue: 'None required: Google no longer shows a sitelinks search box, so this markup has no Google rich-result effect',
      exactEvidence: {
        domSelector: 'script[type="application/ld+json"]',
        schemaType: 'WebSite'
      },
      reproductionMethod: `curl -sL '${page.url}' | grep -i 'SearchAction'`,
      businessImpact: `No measurable Google impact. ${RETIRED_RICH_RESULTS.SITELINKS_SEARCH_BOX.retired}. ${RETIRED_RICH_RESULTS.SITELINKS_SEARCH_BOX.stillUseful}`,
      recommendedRemediation: `No action needed for Google. Source: ${RETIRED_RICH_RESULTS.SITELINKS_SEARCH_BOX.source}`,
      automaticallyFixable: false,
      requiredAccess: 'HTML template source code',
      remediationStatus: 'INFORMATIONAL',
      beforeEvidence: websiteEntity ? 'WebSite schema missing SearchAction' : 'Missing WebSite schema',
      afterEvidence: null,
      verificationResult: null,
      timestamp: now
    });
  }

  // 9b. FAQPage Structured Data Validation & Missing Detection
  const faqContainer = $('.faq, .faqs, .faq-item, .faq-section, [data-faq], .accordion-item, dl.faq');
  const hasFaqHeading = $('h1, h2, h3, h4').filter((_: number, el: any) => Boolean(/frequently asked questions|\bfaqs?\b/i.test($(el).text()))).length > 0;
  const detailsSummaryCount = $('details summary').length;
  const hasFaqInDom = faqContainer.length > 0 || hasFaqHeading || detailsSummaryCount >= 2;

  const faqEntity = allJsonLdEntities.find(ent => ent['@type'] === 'FAQPage');

  if (hasFaqInDom && !faqEntity && !isUtilityOrNonIndexableIntent(routeIntent)) {
    findings.push({
      findingId: `SAN-SEO-SCHEMA-FAQ-MISSING-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
      url: page.url,
      routeIntent,
      detectionRule: 'FAQPAGE_SCHEMA_MISSING',
      track: 'TRACK_A_CORE_SEO',
      category: 'Structured Data',
      severity: 'INFO',
      evidenceClass: '[O] Observed',
      observedValue: 'Visible FAQ content detected on page without Schema.org/FAQPage JSON-LD',
      expectedValue: 'None required: Google no longer shows FAQ rich results',
      exactEvidence: {
        domSelector: '.faq, details, [data-faq]',
        schemaType: 'FAQPage'
      },
      reproductionMethod: `Inspect ${page.url} for visible FAQ content and grep application/ld+json for FAQPage`,
      businessImpact: `No measurable Google impact. ${RETIRED_RICH_RESULTS.FAQ.retired}. ${RETIRED_RICH_RESULTS.FAQ.stillUseful}`,
      recommendedRemediation: `No action needed for Google. Keep the visible FAQ text; it is what readers and AI answer engines read. Source: ${RETIRED_RICH_RESULTS.FAQ.source}`,
      automaticallyFixable: false,
      requiredAccess: 'HTML template source code',
      remediationStatus: 'INFORMATIONAL',
      beforeEvidence: 'FAQ content present without FAQPage schema',
      afterEvidence: null,
      verificationResult: null,
      timestamp: now
    });
  } else if (faqEntity) {
    const mainEntity = faqEntity.mainEntity;
    const questions = Array.isArray(mainEntity) ? mainEntity : (mainEntity ? [mainEntity] : []);
    const malformedQuestions = questions.filter((q: any) => {
      const hasQuestionName = q && q.name && typeof q.name === 'string' && q.name.trim().length > 0;
      const answerText = q?.acceptedAnswer?.text || q?.acceptedAnswer?.name;
      const hasAnswer = typeof answerText === 'string' && answerText.trim().length > 0;
      return !hasQuestionName || !hasAnswer;
    });

    if (questions.length === 0 || malformedQuestions.length > 0) {
      findings.push({
        findingId: `SAN-SEO-SCHEMA-FAQ-MALFORMED-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
        url: page.url,
        routeIntent,
        detectionRule: 'FAQPAGE_SCHEMA_MALFORMED',
        track: 'TRACK_A_CORE_SEO',
        category: 'Structured Data',
        severity: 'INFO',
        evidenceClass: '[O] Observed',
        observedValue: `FAQPage schema contains ${malformedQuestions.length} malformed Question/Answer entities (empty name or text)`,
        expectedValue: 'Every Question entity must have non-empty "name" and acceptedAnswer with non-empty "text"',
        exactEvidence: {
          domSelector: 'script[type="application/ld+json"]',
          schemaType: 'FAQPage'
        },
        reproductionMethod: `Validate schema.org/FAQPage JSON-LD syntax on ${page.url}`,
        businessImpact: `Markup is invalid, but there is no Google rich-result consequence. ${RETIRED_RICH_RESULTS.FAQ.retired}.`,
        recommendedRemediation: 'Optional: fix the empty name/text, or remove the unused FAQPage markup. No Google rich-result benefit either way.',
        automaticallyFixable: false,
        requiredAccess: 'HTML template source code',
        remediationStatus: 'INFORMATIONAL',
        beforeEvidence: JSON.stringify(faqEntity).slice(0, 120),
        afterEvidence: null,
        verificationResult: null,
        timestamp: now
      });
    }
  }

  // 9c. Article / BlogPosting Structured Data Validation & Missing Detection
  const isEditorial = routeIntent === 'EDITORIAL_ARTICLE' || 
                      /\/(blog|articles?|posts?|news)(\/|$)/i.test(urlObj.pathname) || 
                      ($('article').length > 0 && $('body').text().length > 300);

  const articleEntity = allJsonLdEntities.find(ent => 
    ['Article', 'NewsArticle', 'BlogPosting'].includes(ent['@type'])
  );

  if (isEditorial && !articleEntity && !isUtilityOrNonIndexableIntent(routeIntent)) {
    findings.push({
      findingId: `SAN-SEO-SCHEMA-ARTICLE-MISSING-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
      url: page.url,
      routeIntent,
      detectionRule: 'ARTICLE_SCHEMA_MISSING',
      track: 'TRACK_A_CORE_SEO',
      category: 'Structured Data',
      severity: 'HIGH',
      evidenceClass: '[O] Observed',
      observedValue: 'Editorial article route missing Schema.org Article / BlogPosting structured data',
      expectedValue: 'Schema.org/Article or BlogPosting JSON-LD with headline, author, datePublished, and image',
      exactEvidence: {
        domSelector: 'article, script[type="application/ld+json"]',
        schemaType: 'BlogPosting'
      },
      reproductionMethod: `Inspect ${page.url} application/ld+json for Article or BlogPosting entity`,
      businessImpact: 'Prevents article from appearing in Google Top Stories, Google Discover, and enhanced editorial SERP cards.',
      commercialRisk: {
        riskType: 'SERP_CTR_LEAK',
        title: 'Google Discover & Top Stories Ineligibility',
        estimatedMonthlyLossInr: 25000,
        currency: 'INR',
        confidence: '[ESTIMATED]',
        source: 'industry_benchmark_estimate',
        severityScore: 4,
        calculationFormula: 'Modeled lost organic editorial discovery visits: ₹25,000/mo'
      },
      recommendedRemediation: 'Inject Schema.org/BlogPosting JSON-LD declaring headline, author, datePublished, and image.',
      automaticallyFixable: true,
      requiredAccess: 'Editorial CMS / Template code',
      remediationStatus: 'ACTION_REQUIRED',
      beforeEvidence: 'Missing Article schema',
      afterEvidence: null,
      verificationResult: null,
      timestamp: now
    });
  } else if (articleEntity && !isUtilityOrNonIndexableIntent(routeIntent)) {
    const missingProps: string[] = [];
    if (!articleEntity.headline || typeof articleEntity.headline !== 'string') missingProps.push('headline');
    if (!articleEntity.author) missingProps.push('author');
    if (!articleEntity.datePublished) missingProps.push('datePublished');
    if (!articleEntity.image) missingProps.push('image');

    if (missingProps.length > 0) {
      findings.push({
        findingId: `SAN-SEO-SCHEMA-ARTICLE-INCOMPLETE-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
        url: page.url,
        routeIntent,
        detectionRule: 'ARTICLE_SCHEMA_INCOMPLETE',
        track: 'TRACK_A_CORE_SEO',
        category: 'Structured Data',
        severity: 'MEDIUM',
        evidenceClass: '[O] Observed',
        observedValue: `Article schema is missing recommended properties: ${missingProps.join(', ')}`,
        expectedValue: 'Article / BlogPosting schema must include headline, author, datePublished, and image',
        exactEvidence: {
          domSelector: 'script[type="application/ld+json"]',
          schemaType: articleEntity['@type'],
          missingSchemaProperties: missingProps
        },
        reproductionMethod: `Validate Article JSON-LD properties on ${page.url}`,
        businessImpact: 'Incomplete article structured data prevents qualification for rich editorial search appearances.',
        commercialRisk: {
          riskType: 'SERP_CTR_LEAK',
          title: 'Editorial Rich Feature Disqualification',
          estimatedMonthlyLossInr: 15000,
          currency: 'INR',
          confidence: '[ESTIMATED]',
          source: 'industry_benchmark_estimate',
          severityScore: 3,
          calculationFormula: 'Modeled CTR loss from missing author/image rich cards: ₹15,000/mo'
        },
        recommendedRemediation: `Populate missing Article structured data properties: ${missingProps.join(', ')}.`,
        automaticallyFixable: true,
        requiredAccess: 'Editorial CMS / Template code',
        remediationStatus: 'ACTION_REQUIRED',
        beforeEvidence: `Missing: ${missingProps.join(', ')}`,
        afterEvidence: null,
        verificationResult: null,
        timestamp: now
      });
    }
  }

  // ── 10. Security Response Headers ─────────────────────────────────
  const headers = page.headers;
  const securityChecks = [
    {
      header: 'x-content-type-options',
      rule: 'SECURITY_MISSING_X_CONTENT_TYPE_OPTIONS',
      expected: 'nosniff',
      severity: 'LOW' as const,
      impact: 'Browsers may MIME-sniff response content, opening cross-site scripting vulnerabilities.'
    },
    {
      header: 'x-frame-options',
      rule: 'SECURITY_MISSING_X_FRAME_OPTIONS',
      expected: 'DENY or SAMEORIGIN',
      severity: 'LOW' as const,
      impact: 'Allows malicious third-party websites to embed the page inside iframes, enabling clickjacking attacks.'
    },
    {
      header: 'content-security-policy',
      rule: 'SECURITY_MISSING_CONTENT_SECURITY_POLICY',
      expected: 'Valid Content-Security-Policy directive',
      severity: 'LOW' as const,
      impact: 'Leaves site exposed to cross-site scripting (XSS) and unauthorized resource injection.'
    },
    {
      header: 'strict-transport-security',
      rule: 'SECURITY_MISSING_HSTS',
      expected: 'max-age=31536000; includeSubDomains',
      severity: 'LOW' as const,
      impact: 'Browsers may make unencrypted HTTP requests prior to redirecting to HTTPS, vulnerable to man-in-the-middle attacks.'
    },
    {
      header: 'referrer-policy',
      rule: 'SECURITY_MISSING_REFERRER_POLICY',
      expected: 'strict-origin-when-cross-origin',
      severity: 'LOW' as const,
      impact: 'Full URLs including sensitive query parameters may leak to external third-party sites during external navigation.'
    }
  ];

  for (const check of securityChecks) {
    if (!headers[check.header]) {
      findings.push({
        findingId: `SAN-SEO-SEC-${check.rule}-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
        url: page.url,
        routeIntent,
        detectionRule: check.rule,
        track: 'TRACK_A_CORE_SEO',
        category: 'Security Headers',
        severity: check.severity,
        evidenceClass: '[O] Observed',
        observedValue: `Missing '${check.header}' header`,
        expectedValue: check.expected,
        exactEvidence: {
          headerValue: undefined,
          rawContext: `Server response headers did not include ${check.header}`
        },
        reproductionMethod: `curl -sI '${page.url}' | grep -i '${check.header}'`,
        businessImpact: check.impact,
        recommendedRemediation: `Configure reverse proxy (nginx/Caddy) to supply '${check.header}: ${check.expected}'.`,
        automaticallyFixable: true,
        requiredAccess: 'Web server / reverse proxy config',
        remediationStatus: 'ACTION_REQUIRED',
        beforeEvidence: null,
        afterEvidence: null,
        verificationResult: null,
        timestamp: now
      });
    }
  }

  // ── 11. OpenGraph Image Validation ────────────────────────────────
  const ogImage = $('meta[property="og:image"]').attr('content')?.trim();
  if (ogImage && !ogImage.startsWith('http://') && !ogImage.startsWith('https://')) {
    findings.push({
      findingId: `SAN-SEO-OG-IMAGE-RELATIVE-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
      url: page.url,
      routeIntent,
      detectionRule: 'OPENGRAPH_IMAGE_NOT_ABSOLUTE',
      track: 'TRACK_A_CORE_SEO',
      category: 'Technical SEO',
      severity: 'MEDIUM',
      evidenceClass: '[O] Observed',
      observedValue: ogImage,
      expectedValue: 'Fully-qualified absolute URL (https://...)',
      exactEvidence: {
        htmlSnippet: `<meta property="og:image" content="${ogImage}">`,
        domSelector: 'meta[property="og:image"]'
      },
      reproductionMethod: `curl -sL '${page.url}' | grep 'property="og:image"'`,
      businessImpact: 'Social platforms (LinkedIn, Twitter, WhatsApp) fail to render preview cards when image URL is relative.',
      recommendedRemediation: `Prepend the canonical origin to provide an absolute HTTPS image URL.`,
      automaticallyFixable: true,
      requiredAccess: 'HTML template source code',
      remediationStatus: 'ACTION_REQUIRED',
      beforeEvidence: ogImage,
      afterEvidence: null,
      verificationResult: null,
      timestamp: now
    });
  }

  // ── 12. Outbound External Link Probe & Dead Link Audit ────────────
  if (page.outboundLinks && page.outboundLinks.length > 0) {
    for (const link of page.outboundLinks) {
      if (link.isDead) {
        findings.push({
          findingId: `SAN-SEO-OUTBOUND-BROKEN-${Buffer.from(link.url).toString('base64').slice(0, 8)}`,
          url: page.url,
          routeIntent,
          detectionRule: 'OUTBOUND_BROKEN_LINK_DETECTED',
          track: 'TRACK_A_CORE_SEO',
          category: 'Internal Linking',
          severity: 'MEDIUM',
          evidenceClass: '[O] Observed',
          observedValue: `Outbound link to ${link.url} returned ${link.status ? 'HTTP ' + link.status : link.error || 'Connection Failed'} (Anchor: "${link.anchorText}")`,
          expectedValue: 'Active, reachable 200 OK external destination',
          exactEvidence: {
            brokenOutboundUrl: link.url,
            outboundStatusCode: link.status,
            outboundError: link.error,
            genericAnchorText: link.anchorText,
            domSelector: `a[href="${link.url}"]`
          },
          reproductionMethod: `curl -sI '${link.url}'`,
          businessImpact: 'Dead external links degrade user experience and signal stale, unmaintained editorial content to search engine quality algorithms.',
          commercialRisk: {
            riskType: 'CONVERSION_FRICTION',
            title: 'Broken Outbound Destination & Content Hygiene Penalty',
            estimatedMonthlyLossInr: 5000,
            currency: 'INR',
            confidence: '[ESTIMATED]',
            source: 'industry_benchmark_estimate',
            severityScore: 2,
            calculationFormula: 'Modeled user friction penalty for dead external references: ₹5,000/mo'
          },
          recommendedRemediation: `Inspect dead external link target (${link.url}) and update href to current active destination or remove anchor. Autonomous deletion is suppressed to prevent breaking editorial intent.`,
          automaticallyFixable: false, // Explicitly detection-only to protect editorial intent
          requiredAccess: 'Editorial CMS / Content templates',
          remediationStatus: 'ACTION_REQUIRED',
          beforeEvidence: `Dead link: ${link.url} (${link.status || link.error})`,
          afterEvidence: null,
          verificationResult: null,
          timestamp: now
        });
      }
    }
  }

  return findings;
}
