/**
 * SANOCEA SEO Stack — AI crawler access policy (robots.txt, RFC 9309 semantics)
 *
 * Two corrections over the previous line-by-line parser:
 *
 * 1. GROUPS. In RFC 9309 several consecutive `User-agent:` lines share the rules that follow them. The old parser
 *    kept only the LAST user-agent, so `User-agent: GPTBot` + `User-agent: ClaudeBot` + `Disallow: /` reported
 *    GPTBot as unrestricted. Rules are now attached to every user-agent of their group.
 * 2. EFFECTIVE ACCESS. A crawler with no group of its own obeys the `*` group. A site that blocks `*` blocks every
 *    AI crawler, and a site that allows `*` has said nothing special about them; neither was visible before.
 *
 * It also records WHAT each crawler is for. Allowing or blocking a training crawler says nothing about whether the
 * same vendor's search/citation crawler can reach the site (OpenAI: "Each setting is independent of the others").
 *
 * Provenance: independent implementation from RFC 9309. The crawler catalogue was prompted by claude-seo's and
 * geo-seo-claude's AI-crawler tables (both MIT; no code copied). OpenAI and Anthropic purposes were re-read from
 * their own documentation on 2026-10-01 (`VENDOR_DOCUMENTED`); every other token is `REPORTED` and is worded
 * cautiously in findings until it is checked against the vendor's own page.
 */

export type AiCrawlerPurpose = 'SEARCH_CITATION' | 'TRAINING' | 'USER_TRIGGERED';
export type AiCrawlerBasis = 'VENDOR_DOCUMENTED' | 'REPORTED';

export interface AiCrawlerInfo {
  token: string; // lower-case robots.txt product token
  operator: string;
  purpose: AiCrawlerPurpose;
  basis: AiCrawlerBasis;
  docs?: string;
}

const OPENAI_DOCS = 'https://developers.openai.com/api/docs/bots';
const ANTHROPIC_DOCS = 'https://support.claude.com/en/articles/8896518';

export const AI_CRAWLERS: AiCrawlerInfo[] = [
  { token: 'oai-searchbot', operator: 'OpenAI', purpose: 'SEARCH_CITATION', basis: 'VENDOR_DOCUMENTED', docs: OPENAI_DOCS },
  { token: 'gptbot', operator: 'OpenAI', purpose: 'TRAINING', basis: 'VENDOR_DOCUMENTED', docs: OPENAI_DOCS },
  { token: 'chatgpt-user', operator: 'OpenAI', purpose: 'USER_TRIGGERED', basis: 'VENDOR_DOCUMENTED', docs: OPENAI_DOCS },
  { token: 'claude-searchbot', operator: 'Anthropic', purpose: 'SEARCH_CITATION', basis: 'VENDOR_DOCUMENTED', docs: ANTHROPIC_DOCS },
  { token: 'claudebot', operator: 'Anthropic', purpose: 'TRAINING', basis: 'VENDOR_DOCUMENTED', docs: ANTHROPIC_DOCS },
  { token: 'claude-user', operator: 'Anthropic', purpose: 'USER_TRIGGERED', basis: 'VENDOR_DOCUMENTED', docs: ANTHROPIC_DOCS },
  { token: 'perplexitybot', operator: 'Perplexity', purpose: 'SEARCH_CITATION', basis: 'REPORTED' },
  { token: 'perplexity-user', operator: 'Perplexity', purpose: 'USER_TRIGGERED', basis: 'REPORTED' },
  { token: 'google-extended', operator: 'Google', purpose: 'TRAINING', basis: 'REPORTED' },
  { token: 'applebot-extended', operator: 'Apple', purpose: 'TRAINING', basis: 'REPORTED' },
  { token: 'meta-externalagent', operator: 'Meta', purpose: 'TRAINING', basis: 'REPORTED' },
  { token: 'ccbot', operator: 'Common Crawl', purpose: 'TRAINING', basis: 'REPORTED' },
  { token: 'bytespider', operator: 'ByteDance', purpose: 'TRAINING', basis: 'REPORTED' }
];

/** Tokens SANOCEA has always watched whose purpose is not documented; kept so existing evidence does not vanish. */
const LEGACY_TOKENS = ['claude-web'];

export const WATCHED_AI_TOKENS: ReadonlySet<string> = new Set([...AI_CRAWLERS.map(c => c.token), ...LEGACY_TOKENS]);

export interface RobotsRule { type: 'allow' | 'disallow'; path: string }
export interface RobotsGroup { agents: string[]; rules: RobotsRule[] }

/** RFC 9309 grouping: consecutive User-agent lines open one group; rules attach to every agent in it. */
export function parseRobotsGroups(robotsContent: string): RobotsGroup[] {
  const groups: RobotsGroup[] = [];
  let current: RobotsGroup | null = null;
  let lastWasAgent = false;
  for (let raw of robotsContent.split(/\r?\n/)) {
    const line = raw.split('#')[0].trim();
    if (!line) continue;
    const colon = line.indexOf(':');
    if (colon === -1) continue;
    const directive = line.slice(0, colon).trim().toLowerCase();
    const value = line.slice(colon + 1).trim();
    if (directive === 'user-agent') {
      if (!current || !lastWasAgent) {
        current = { agents: [], rules: [] };
        groups.push(current);
      }
      current.agents.push(value.toLowerCase());
      lastWasAgent = true;
    } else if (directive === 'allow' || directive === 'disallow') {
      if (current) current.rules.push({ type: directive, path: value });
      lastWasAgent = false;
    } else {
      // Sitemap and other non-group directives neither start nor end a group.
      if (directive !== 'sitemap') lastWasAgent = false;
    }
  }
  return groups;
}

/** Converts a robots path pattern (`*` wildcard, `$` end anchor) to a prefix-matching RegExp. */
function patternToRegExp(pattern: string): RegExp {
  const escaped = pattern.replace(/[.+?^{}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*');
  return new RegExp('^' + (escaped.endsWith('$') ? escaped.slice(0, -1) + '$' : escaped));
}

/** RFC 9309 longest-match-wins; on equal length Allow beats Disallow; no matching rule means allowed. */
export function isPathAllowed(rules: RobotsRule[], path: string): boolean {
  let best: { len: number; allow: boolean } | null = null;
  for (const r of rules) {
    if (r.path === '') continue; // an empty Disallow means "nothing disallowed"; an empty Allow adds nothing
    if (!patternToRegExp(r.path).test(path)) continue;
    const len = r.path.length;
    const allow = r.type === 'allow';
    if (!best || len > best.len || (len === best.len && allow && !best.allow)) best = { len, allow };
  }
  return best ? best.allow : true;
}

export type AiAccess = 'ALLOWED' | 'PARTIAL' | 'BLOCKED';
export type AiAccessBasis = 'EXPLICIT_GROUP' | 'INHERITED_WILDCARD' | 'NO_APPLICABLE_RULES';

export interface AiCrawlerAccess extends AiCrawlerInfo {
  access: AiAccess;
  basis_of_access: AiAccessBasis;
  rules: string[];
}

function effectiveRules(groups: RobotsGroup[], token: string): { rules: RobotsRule[]; basis: AiAccessBasis } {
  // A crawler matches the group(s) naming its product token; several matching groups are merged (RFC 9309 §2.2.1).
  const named = groups.filter(g => g.agents.includes(token));
  if (named.length) return { rules: named.flatMap(g => g.rules), basis: 'EXPLICIT_GROUP' };
  const star = groups.filter(g => g.agents.includes('*'));
  if (star.length) return { rules: star.flatMap(g => g.rules), basis: 'INHERITED_WILDCARD' };
  return { rules: [], basis: 'NO_APPLICABLE_RULES' };
}

export function classifyAccess(rules: RobotsRule[]): AiAccess {
  const blocksRoot = !isPathAllowed(rules, '/');
  const hasRealDisallow = rules.some(r => r.type === 'disallow' && r.path !== '');
  const hasAllow = rules.some(r => r.type === 'allow' && r.path !== '');
  if (blocksRoot) return hasAllow ? 'PARTIAL' : 'BLOCKED';
  return hasRealDisallow ? 'PARTIAL' : 'ALLOWED';
}

/** Effective robots.txt access for every catalogued AI crawler. */
export function resolveAiCrawlerAccess(robotsContent: string): AiCrawlerAccess[] {
  const groups = parseRobotsGroups(robotsContent);
  return AI_CRAWLERS.map(info => {
    const { rules, basis } = effectiveRules(groups, info.token);
    return {
      ...info,
      access: classifyAccess(rules),
      basis_of_access: basis,
      rules: rules.map(r => `${r.type === 'allow' ? 'Allow' : 'Disallow'}: ${r.path}`)
    };
  });
}

export interface AiBotDirective {
  allowed: boolean;
  rules: string[];
  purpose?: AiCrawlerPurpose;
  operator?: string;
  basis?: AiCrawlerBasis;
  access?: AiAccess;
  inherited?: boolean;
}

/**
 * Directive map consumed by the GEO observer. Includes every watched bot that has its own group, plus any bot that is
 * restricted only because it inherits a restrictive `*` group. A bot that merely inherits an open `*` is omitted: the
 * site said nothing about it, so there is nothing to report.
 */
export function buildAiBotDirectives(robotsContent: string): Record<string, AiBotDirective> {
  const out: Record<string, AiBotDirective> = {};
  const groups = parseRobotsGroups(robotsContent);
  const tokens = [...AI_CRAWLERS.map(c => c.token), ...LEGACY_TOKENS];
  for (const token of tokens) {
    const info = AI_CRAWLERS.find(c => c.token === token);
    const { rules, basis } = effectiveRules(groups, token);
    const access = classifyAccess(rules);
    if (basis === 'NO_APPLICABLE_RULES') continue;
    if (basis === 'INHERITED_WILDCARD' && access === 'ALLOWED') continue;
    out[token] = {
      allowed: access !== 'BLOCKED',
      rules: rules.map(r => `${r.type === 'allow' ? 'Allow' : 'Disallow'}: ${r.path}`),
      access,
      inherited: basis === 'INHERITED_WILDCARD',
      ...(info ? { purpose: info.purpose, operator: info.operator, basis: info.basis } : {})
    };
  }
  return out;
}
