import test from 'node:test';
import assert from 'node:assert/strict';
import { SeoDatabase } from '../src/persistence/seoDb.js';
import { SeoMonitoringWorker } from '../src/worker/seoMonitoringWorker.js';
import { AgentRosterManager } from '../src/agents/agentRoster.js';
import { KeywordIntelligenceEngine, DataForSeoKeywordAdapter } from '../src/search-intel/keywordIntelligence.js';
import { AeoIntelligenceEngine, UnconfiguredAeoProvider } from '../src/search-intel/aeoIntelligence.js';
import { GeoCitationEngine, UnconfiguredGeoProvider } from '../src/search-intel/geoCitationEngine.js';
import { CompetitorIntelligenceEngine } from '../src/search-intel/competitorWorker.js';
import { parseRobotsTxt } from '../src/core/urlDiscovery.js';
import { resolveAiCrawlerAccess, isPathAllowed, parseRobotsGroups } from '../src/core/aiCrawlerPolicy.js';
import { findRetiredSchemaTypes, retiredFeatureForRule } from '../src/core/retiredRichResults.js';
import { runGeoObserver } from '../src/observers/geoObserver.js';
import { fakeFetch, urlset } from './helpers/fakeHttp.js';

// ── robots.txt: RFC 9309 groups and effective access ─────────────────────────

test('robots: consecutive User-agent lines share one rule group (previously only the last agent got the rule)', () => {
  const r = parseRobotsTxt('User-agent: GPTBot\nUser-agent: ClaudeBot\nDisallow: /\n');
  assert.equal(r.aiBotDirectives['gptbot'].allowed, false, 'GPTBot is in the group and must be blocked');
  assert.equal(r.aiBotDirectives['claudebot'].allowed, false);
  assert.deepEqual(r.disallowRules['gptbot'], ['/']);
});

test('robots: a bot with no group inherits `*`; a blocked wildcard blocks every AI crawler, an open one reports nothing', () => {
  const blocked = parseRobotsTxt('User-agent: *\nDisallow: /\n');
  assert.equal(blocked.aiBotDirectives['oai-searchbot'].allowed, false);
  assert.equal(blocked.aiBotDirectives['oai-searchbot'].inherited, true);
  const open = parseRobotsTxt('User-agent: *\nAllow: /\n');
  assert.deepEqual(open.aiBotDirectives, {}, 'inheriting an open wildcard is not a finding');
  assert.deepEqual(parseRobotsTxt('').aiBotDirectives, {});
});

test('robots: longest match wins and Allow beats Disallow on ties; partial restriction is not "blocked"', () => {
  const g = parseRobotsGroups('User-agent: gptbot\nDisallow: /\nAllow: /public/\n');
  assert.equal(isPathAllowed(g[0].rules, '/'), false);
  assert.equal(isPathAllowed(g[0].rules, '/public/x'), true);
  assert.equal(isPathAllowed([{ type: 'allow', path: '/a' }, { type: 'disallow', path: '/a' }], '/a'), true);
  assert.equal(isPathAllowed([{ type: 'disallow', path: '/*.pdf$' }], '/x/y.pdf'), false);
  assert.equal(isPathAllowed([{ type: 'disallow', path: '/*.pdf$' }], '/x/y.pdfs'), true);
  assert.equal(isPathAllowed([{ type: 'disallow', path: '' }], '/'), true, 'empty Disallow allows everything');
  const partial = resolveAiCrawlerAccess('User-agent: *\nDisallow: /admin/\n').find(c => c.token === 'gptbot')!;
  assert.equal(partial.access, 'PARTIAL');
  assert.equal(partial.basis_of_access, 'INHERITED_WILDCARD');
});

test('robots: blocking a training crawler is reported as training-only and does not claim search citations are lost', () => {
  const dir = parseRobotsTxt('User-agent: GPTBot\nDisallow: /\n').aiBotDirectives;
  assert.equal(dir['gptbot'].purpose, 'TRAINING');
  const page: any = { url: 'https://www.sanocea.com/' };
  const f = runGeoObserver({ page } as any, { aiBotDirectives: dir }).find(x => x.detectionRule === 'AI_BOT_DIRECTIVE_GPTBOT')!;
  assert.match(f.businessImpact, /training only/);
  assert.match(f.businessImpact, /search product can cite the site; that crawler is controlled separately/);
  assert.doesNotMatch(f.businessImpact, /search answers/);
  const s = runGeoObserver({ page } as any, { aiBotDirectives: parseRobotsTxt('User-agent: OAI-SearchBot\nDisallow: /\n').aiBotDirectives })[0];
  assert.match(s.businessImpact, /will not be cited/);
});

// ── retired Google features ──────────────────────────────────────────────────

test('retired registry: FAQ and sitelinks-search-box rules are recognised; HowTo markup is flagged', () => {
  assert.equal(retiredFeatureForRule('FAQPAGE_SCHEMA_MISSING')?.feature, 'FAQ rich result');
  assert.equal(retiredFeatureForRule('WEBSITE_SEARCH_ACTION_SCHEMA_MISSING')?.feature, 'Sitelinks search box');
  assert.equal(retiredFeatureForRule('TITLE_TAG_MISSING'), undefined);
  assert.deepEqual(findRetiredSchemaTypes(['Product', 'HowTo', 'FAQPage']).map(r => r.type).sort(), ['FAQPage', 'HowTo']);
  assert.deepEqual(findRetiredSchemaTypes(['Product', 'Organization']), []);
});

// ── AI Content Auditor: real published-page evidence, no score ───────────────

const HTML_EMPTY_SHELL = '<html><head><title>x</title></head><body><div id="root"></div><script>app()</script></body></html>';
const HTML_RICH = `<html><head><script type="application/ld+json">{"@type":"HowTo"}</script></head><body><h1>Title</h1><main>${'word '.repeat(150)}</main></body></html>`;

function rosterWith(db: SeoDatabase, fetchImpl: typeof fetch) {
  return new AgentRosterManager(db, {
    domain: 'site.test', fetchImpl, queries: ['q'],
    keywordEngine: new KeywordIntelligenceEngine(new DataForSeoKeywordAdapter({ login: '', password: '', fetchImpl: fakeFetch({}) }), db),
    competitorEngine: new CompetitorIntelligenceEngine([], db, { fetchImpl: fakeFetch({}) }),
    aeoEngine: new AeoIntelligenceEngine(new UnconfiguredAeoProvider(), db), geoEngine: new GeoCitationEngine(new UnconfiguredGeoProvider(), db)
  });
}

test('AI Content Auditor: reports what the server delivers per page, retired markup, and effective AI-crawler access', async () => {
  const f = fakeFetch({
    'https://site.test/robots.txt': { status: 200, body: 'User-agent: GPTBot\nDisallow: /\n' },
    'https://site.test/sitemap.xml': { status: 200, body: urlset(['https://site.test/', 'https://site.test/guide', 'https://other.test/x']) },
    'https://site.test/': { status: 200, body: HTML_EMPTY_SHELL },
    'https://site.test/guide': { status: 200, body: HTML_RICH }
  });
  const run = await rosterWith(new SeoDatabase(':memory:'), f).executeAgent('agent-ai-content-auditor', 't1');
  assert.equal(run.status, 'COMPLETED');
  assert.equal(run.provenance, '[OBSERVED: LIVE PAGE FETCH]');
  const d: any = run.details;
  assert.equal(d.pages.length, 2, 'off-domain sitemap URLs are never fetched');
  assert.equal(d.pages.find((p: any) => p.url.endsWith('/guide')).staticWords, 151, 'element boundaries are word boundaries: h1 + 150 words');
  assert.equal(d.pages[0].staticWords, 0, 'JS-only shell has no readable words in the delivered HTML');
  assert.deepEqual(d.pages.find((p: any) => p.url.endsWith('/guide')).retiredSchemaTypes, ['HowTo']);
  assert.match(run.outputSummary, /1 with under 100 readable words/);
  assert.match(run.outputSummary, /1 without an h1/);
  assert.match(run.outputSummary, /3 of 3 AI search crawlers are not blocked/, 'GPTBot is a training crawler, not a search one');
  assert.ok(d.aiCrawlers.some((c: any) => c.crawler === 'gptbot' && c.access === 'blocked' && c.via === 'own rule'));
  assert.doesNotMatch(JSON.stringify(run), /score|citab/i, 'no invented score');
  assert.ok(!/[A-Z][A-Z0-9]*(?:_[A-Z0-9]+){2,}/.test(JSON.stringify(d)), 'no UPPER_SNAKE identifiers that the API bridge would redact');
});

test('AI Content Auditor: nothing fetched means NOT AVAILABLE, never a clean result', async () => {
  const run = await rosterWith(new SeoDatabase(':memory:'), fakeFetch({})).executeAgent('agent-ai-content-auditor', 't1');
  assert.equal(run.status, 'ALERT');
  assert.equal(run.provenance, '[NOT AVAILABLE]');
  assert.match(run.outputSummary, /nothing is reported/);
});

// ── tier-1: confirm before P0 ────────────────────────────────────────────────

function monitor(root: Array<{ status: number } | { throw: Error }>) {
  let i = 0;
  const probeFetch = (async (url: any) => {
    const u = String(url);
    if (u.endsWith('/robots.txt') || u.endsWith('/sitemap.xml')) return new Response('User-agent: *\nAllow: /\n', { status: 200 });
    const r = root[Math.min(i++, root.length - 1)];
    if ('throw' in r) throw r.throw;
    return new Response(r.status === 200 ? '<html><head><title>t</title></head><body><h1>x</h1></body></html>' : 'err', { status: r.status });
  }) as typeof fetch;
  return new SeoMonitoringWorker({ tenantId: 'sanocea', domain: 'www.sanocea.com', dbPath: ':memory:', enableTier1: false, enableTier2: false, enableTier3: false, probeFetch, confirmDelayMs: 0 });
}

test('tier-1: a failure that repeats on the re-check is a confirmed P0', async () => {
  const w = monitor([{ status: 503 }, { status: 503 }]);
  const r = await w.runTier1();
  const c = r.changes.find(x => x.changeType === 'CRITICAL_URL_HTTP_STATUS')!;
  assert.equal(c.severity, 'P0');
  assert.match(c.observedValue!, /confirmed/);
  assert.equal(r.status, 'alert');
  w.stop();
});

test('tier-1: one failed request that recovers is recorded as P2 (visible), and does not raise an alert', async () => {
  const w = monitor([{ status: 503 }, { status: 200 }]);
  const r = await w.runTier1();
  assert.equal(r.changes.some(x => x.severity === 'P0'), false);
  const c = r.changes.find(x => x.changeType === 'CRITICAL_URL_TRANSIENT_FAILURE')!;
  assert.equal(c.severity, 'P2');
  assert.match(c.observedValue!, /HTTP 503 on the first check, HTTP 200 on the re-check/);
  assert.notEqual(r.status, 'alert');
  w.stop();
});

test('tier-1: a re-check that cannot complete is unconfirmed (P2), not a P0', async () => {
  const w = monitor([{ status: 503 }, { throw: new Error('network down') }]);
  const r = await w.runTier1();
  const c = r.changes.find(x => x.changeType === 'CRITICAL_URL_UNCONFIRMED')!;
  assert.equal(c.severity, 'P2');
  assert.equal(r.changes.some(x => x.severity === 'P0'), false);
  w.stop();
});
