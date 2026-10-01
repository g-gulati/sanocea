/**
 * SANOCEA SEO Stack — Generative Engine Optimization (GEO) & AI Readiness Observer
 * 
 * Strict User Directive:
 * Classify /llms.txt and AI crawler directives as GEO/AI-readiness observations,
 * NOT automatically as SEO errors. Do not create an error/remediation merely because the asset is absent.
 */

import { PageAuditContext, SeoFinding } from '../core/types.js';
import { classifyRouteIntent } from '../core/routeIntent.js';
import { AiBotDirective } from '../core/aiCrawlerPolicy.js';

export interface GeoObserverOptions {
  llmsTxtStatus?: {
    checked: boolean;
    present: boolean;
    url: string;
    content?: string;
  };
  aiBotDirectives?: Record<string, AiBotDirective>;
}

export function runGeoObserver(context: PageAuditContext, options: GeoObserverOptions = {}): SeoFinding[] {
  const findings: SeoFinding[] = [];
  const { page } = context;
  const now = new Date().toISOString();
  const routeIntent = classifyRouteIntent(page.url);

  // ── 1. /llms.txt Discovery & AI Context Readiness ─────────────────
  if (options.llmsTxtStatus?.checked) {
    if (options.llmsTxtStatus.present) {
      findings.push({
        findingId: `SAN-GEO-LLMSTXT-PRESENT-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
        url: options.llmsTxtStatus.url,
        routeIntent: 'SYSTEM_FEED',
        detectionRule: 'LLMS_TXT_DISCOVERED',
        track: 'GEO_READINESS',
        category: 'GEO / AI Readiness',
        severity: 'INFO',
        evidenceClass: '[GEO] GEO Readiness',
        observedValue: '/llms.txt is present and accessible',
        expectedValue: 'Documented /llms.txt standard for AI search engines',
        exactEvidence: {
          rawContext: (options.llmsTxtStatus.content || '').slice(0, 200)
        },
        reproductionMethod: `curl -sL '${options.llmsTxtStatus.url}'`,
        businessImpact: 'Positive readiness for Generative Engines (ChatGPT, Perplexity, Claude); provides clean markdown context on business modules.',
        recommendedRemediation: 'Maintain updated system/product summaries in /llms.txt.',
        automaticallyFixable: false,
        requiredAccess: 'Public web root',
        remediationStatus: 'INFORMATIONAL',
        beforeEvidence: 'Present',
        afterEvidence: null,
        verificationResult: 'Validated',
        timestamp: now
      });
    } else {
      findings.push({
        findingId: `SAN-GEO-LLMSTXT-OBSERVATION-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
        url: options.llmsTxtStatus.url,
        routeIntent: 'SYSTEM_FEED',
        detectionRule: 'LLMS_TXT_ABSENT_OBSERVATION',
        track: 'GEO_READINESS',
        category: 'GEO / AI Readiness',
        severity: 'INFO',
        evidenceClass: '[GEO] GEO Readiness',
        observedValue: '/llms.txt not deployed (HTTP 404)',
        expectedValue: 'Optional /llms.txt file to guide AI scrapers and answer engines',
        exactEvidence: {
          rawContext: `HTTP 404 response on ${options.llmsTxtStatus.url}`
        },
        reproductionMethod: `curl -I '${options.llmsTxtStatus.url}'`,
        businessImpact: 'Neutral for traditional Google/Bing SEO. Adopting /llms.txt is an emerging GEO strategy to ensure LLMs ingest clean domain summaries rather than unstructured DOM.',
        recommendedRemediation: 'Consider deploying a standard /llms.txt file describing SANOCEA products, documentation, and key URLs for generative engines.',
        automaticallyFixable: false,
        requiredAccess: 'Public web root / content team',
        remediationStatus: 'INFORMATIONAL',
        beforeEvidence: 'Absent',
        afterEvidence: null,
        verificationResult: null,
        timestamp: now
      });
    }
  }

  // ── 2. AI Bot Directives in robots.txt ─────────────────────────────
  // The impact wording depends on what the crawler is FOR: blocking a training crawler does not stop the same
  // vendor's search/citation crawler, and user-triggered fetchers are not always governed by robots.txt.
  if (options.aiBotDirectives) {
    const bots = Object.entries(options.aiBotDirectives);
    for (const [botName, status] of bots) {
      findings.push({
        findingId: `SAN-GEO-BOT-${botName.toUpperCase()}-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
        url: `${new URL(page.url).origin}/robots.txt`,
        routeIntent: 'SYSTEM_FEED',
        detectionRule: `AI_BOT_DIRECTIVE_${botName.toUpperCase()}`,
        track: 'GEO_READINESS',
        category: 'GEO / AI Readiness',
        severity: 'INFO',
        evidenceClass: '[GEO] GEO Readiness',
        observedValue: describeObserved(botName, status),
        expectedValue: 'Intentional policy decision on whether AI models may crawl site content',
        exactEvidence: {
          rawContext: status.rules.join(' | ') || 'No explicit disallows'
        },
        reproductionMethod: `curl -sL '${new URL(page.url).origin}/robots.txt' | grep -i -B2 -A4 '${botName}'`,
        businessImpact: describeImpact(botName, status),
        recommendedRemediation: status.purpose === 'SEARCH_CITATION' && !status.allowed
          ? 'Confirm this is intended: blocking a search crawler removes the site from that product\'s answers.'
          : 'Confirm this matches the intended AI-crawler policy.',
        automaticallyFixable: false,
        requiredAccess: 'robots.txt configuration',
        remediationStatus: 'INFORMATIONAL',
        beforeEvidence: status.rules.join(' | '),
        afterEvidence: null,
        verificationResult: null,
        timestamp: now
      });
    }
  }

  return findings;
}

const PURPOSE_LABEL: Record<string, string> = {
  SEARCH_CITATION: 'search / citation crawler',
  TRAINING: 'model-training crawler',
  USER_TRIGGERED: 'user-triggered fetcher'
};

function state(status: AiBotDirective): string {
  if (!status.allowed) return 'blocked from the whole site';
  if (status.access === 'PARTIAL') return `restricted on some paths (${status.rules.join(', ')})`;
  return 'allowed';
}

function describeObserved(bot: string, status: AiBotDirective): string {
  const kind = status.purpose ? ` (${PURPOSE_LABEL[status.purpose]}, ${status.operator})` : '';
  const via = status.inherited ? ' via the User-agent: * group (no rule names it)' : '';
  return `${bot}${kind} is ${state(status)}${via}`;
}

function describeImpact(bot: string, status: AiBotDirective): string {
  const op = status.operator ?? 'its operator';
  const caveat = status.basis === 'REPORTED' ? ' (purpose per public reporting, not yet checked against the vendor page)' : '';
  if (status.purpose === 'SEARCH_CITATION') {
    return (status.allowed
      ? `${bot} may read the pages it is allowed to, so ${op}'s search product can cite them.`
      : `${op}'s search product cannot read these pages, so they will not be cited there.`) + caveat;
  }
  if (status.purpose === 'TRAINING') {
    return `Controls whether ${op} may collect content for model training only. It does not decide whether ${op}'s search product can cite the site; that crawler is controlled separately.` + caveat;
  }
  if (status.purpose === 'USER_TRIGGERED') {
    return `Fetches pages when a person asks ${op}'s assistant about them. Vendors may not apply robots.txt to these requests, so this rule may have no effect.` + caveat;
  }
  return status.allowed ? `${bot} is not blocked.` : `${bot} is blocked from the site.`;
}
