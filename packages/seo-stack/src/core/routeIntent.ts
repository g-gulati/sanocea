/**
 * SANOCEA SEO Stack — Route Intent Classification Engine
 * Eliminates false positives by distinguishing Transactional/Utility/Search/Simulator routes
 * from Public Search Landing Pages.
 */

import { RouteIntent } from './types.js';

const SYSTEM_PATTERNS = [
  /\.xml(\.gz)?$/i,
  /robots\.txt$/i,
  /llms\.txt$/i,
  /sitemap.*\.php$/i,
  /\/feed\/?$/i
];

const UTILITY_PATTERNS = [
  /\/cart(\/|$|\?)/i,
  /\/checkout(\/|$|\?)/i,
  /\/my-account(\/|$|\?)/i,
  /\/account(\/|$|\?)/i,
  /\/login(\/|$|\?)/i,
  /\/signin(\/|$|\?)/i,
  /\/register(\/|$|\?)/i,
  /\/signup(\/|$|\?)/i,
  /\/wishlist(\/|$|\?)/i,
  /\/orders(\/|$|\?)/i,
  /\/track-order(\/|$|\?)/i,
  /\/password(\/|$|\?)/i,
  /\/reset-password(\/|$|\?)/i,
  /\/privacy-policy(\/|$|\?)/i,
  /\/terms(\/|$|\?)/i,
  /\/refund-policy(\/|$|\?)/i,
  /\/shipping-policy(\/|$|\?)/i,
  /\/cookie-policy(\/|$|\?)/i,
  /\/contact-us(\/|$|\?)/i,
  /\/auth(\/|$|\?)/i
];

const SIMULATOR_PATTERNS = [
  /\/demo(\.html|\/|$)/i,
  /\/calculator(\.html|\/|$)/i,
  /\/simulator(\.html|\/|$)/i,
  /\/sandbox(\.html|\/|$)/i,
  /\/tool(s)?(\.html|\/|$)/i,
  /\/portal(\.html|\/|$)/i,
  /\/app(\.html|\/|$)/i
];

const SEARCH_QUERY_KEYS = ['s', 'q', 'search', 'query', 'keyword', 'k'];

const FACET_PREFIXES = ['filter.', 'filter_', 'facet.', 'pf_', 'f_'];
const FACET_PARAMS = ['sort', 'sort_by', 'order', 'orderby', 'view', 'grid', 'limit', 'page', 'p', 'dir'];

const PDP_PATTERNS = [
  /\/products\/[^/]+/i,
  /\/product\/[^/]+/i,
  /\/p\/[^/]+/i,
  /\/item\/[^/]+/i
];

const PLP_PATTERNS = [
  /\/collections\/[^/]+/i,
  /\/category\/[^/]+/i,
  /\/c\/[^/]+/i,
  /\/shop\/?$/i,
  /\/catalog\/?$/i
];

/**
 * Classifies a URL into its functional ecommerce/web architecture intent
 */
export function classifyRouteIntent(urlStr: string): RouteIntent {
  try {
    const parsed = new URL(urlStr, 'https://sanocea.internal');
    const path = parsed.pathname;
    const searchParams = parsed.searchParams;

    // 1. System Files (.xml, robots.txt, llms.txt, etc.)
    for (const pat of SYSTEM_PATTERNS) {
      if (pat.test(path)) return 'SYSTEM_FEED';
    }

    // 2. Interactive Simulators & Diagnostic Tools
    for (const pat of SIMULATOR_PATTERNS) {
      if (pat.test(path)) return 'UTILITY_SIMULATOR';
    }

    // 3. Transactional, Account & Checkout Endpoints
    for (const pat of UTILITY_PATTERNS) {
      if (pat.test(path)) return 'TRANSACTIONAL_UTILITY';
    }

    // 4. Internal Search Results (e.g. ?s=shoes, ?q=solar, /search?q=inverter, /catalogsearch/result/?q=battery)
    if (path.includes('/search') || path.includes('/catalogsearch')) {
      return 'INTERNAL_SEARCH';
    }
    for (const key of SEARCH_QUERY_KEYS) {
      if (searchParams.has(key)) {
        return 'INTERNAL_SEARCH';
      }
    }

    // 5. Faceted Navigation & Filter Query Parameters
    let hasFacetParam = false;
    for (const [key] of searchParams.entries()) {
      const lowerKey = key.toLowerCase();
      if (FACET_PREFIXES.some(prefix => lowerKey.startsWith(prefix)) || FACET_PARAMS.includes(lowerKey)) {
        hasFacetParam = true;
        break;
      }
    }

    // 6. PDP Patterns
    for (const pat of PDP_PATTERNS) {
      if (pat.test(path)) {
        return hasFacetParam ? 'FACETED_FILTER' : 'PRODUCT_DISPLAY_PAGE';
      }
    }

    // 7. PLP / Collection Patterns
    for (const pat of PLP_PATTERNS) {
      if (pat.test(path)) {
        return hasFacetParam ? 'FACETED_FILTER' : 'COLLECTION_PAGE';
      }
    }

    // 8. Editorial & Blog Articles
    if (path.includes('/blog/') || path.includes('/news/') || path.includes('/article/') || path.includes('/post/')) {
      return 'EDITORIAL_ARTICLE';
    }

    // If faceted parameters on generic path
    if (hasFacetParam) {
      return 'FACETED_FILTER';
    }

    return 'MARKETING_LANDING_PAGE';
  } catch {
    return 'MARKETING_LANDING_PAGE';
  }
}

/**
 * Checks whether a `noindex` directive is standard and expected for this route.
 * Transactional endpoints, internal search, simulators, and faceted filter URLs
 * SHOULD have noindex to prevent index bloat and search result cannibalization.
 */
export function isExpectedNoindex(urlStr: string): boolean {
  const intent = classifyRouteIntent(urlStr);
  return isUtilityOrNonIndexableIntent(intent);
}

/**
 * Checks whether the route intent is considered utility or non-indexable by standard design
 */
export function isUtilityOrNonIndexableIntent(intent: RouteIntent): boolean {
  return (
    intent === 'TRANSACTIONAL_UTILITY' ||
    intent === 'SYSTEM_FEED' ||
    intent === 'INTERNAL_SEARCH' ||
    intent === 'UTILITY_SIMULATOR' ||
    intent === 'FACETED_FILTER'
  );
}
