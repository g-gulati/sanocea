/**
 * SANOCEA SEO Stack — Common Crawl Domain Reference Graph (authority signal)
 *
 * NOT a backlink count. Common Crawl publishes a domain-level hyperlink graph per crawl release with two
 * centrality scores per domain: harmonic centrality (how close the domain is to all others via links) and
 * PageRank. We stream the release's `domain-ranks` file, keep only the rows for the domains we track, and store them
 * with the release id, file URL and last-modified date.
 *
 * Truth rules:
 * - Rows are data from a specific crawl release (a historical snapshot, never "current"); the release id travels
 *   with every value.
 * - A domain that is absent from the graph is `inGraph=false` (not in this release's graph). It is never stored as
 *   zero authority or a bottom rank.
 * - Fetch/parse failure, unexpected file format or timeout => ProviderUnavailable, nothing persisted.
 * - Data licence: Common Crawl Terms of Use. Free, no key.
 * - Works for ANY domain, so it is the only zero-cost authority signal that covers competitors too.
 */

import { createGunzip } from 'node:zlib';
import { Readable } from 'node:stream';
import { createInterface } from 'node:readline';
import { SeoDatabase } from '../persistence/seoDb.js';
import { ProviderUnavailable } from './rankCommandTypes.js';

export const CC_GRAPH_SOURCE = 'COMMON_CRAWL_DOMAIN_REFERENCE_GRAPH' as const;
export const CC_GRAPH_PROVENANCE = '[OBSERVED: COMMON CRAWL DOMAIN REFERENCE GRAPH]' as const;
export const CC_GRAPH_METHODOLOGY =
  'Harmonic centrality and PageRank computed by Common Crawl over its domain-level hyperlink graph for one crawl release. ' +
  'A historical snapshot of the public web graph, not a backlink count and not current. Lower position = more central. ' +
  'Domains not found in the release are reported as not-in-graph, not as zero.';
/** Latest release verified to exist on 2026-09-30. Override with CC_GRAPH_RELEASE. */
export const DEFAULT_CC_GRAPH_RELEASE = 'cc-main-2026-jul-aug-sep';
const EXPECTED_HEADER = ['#harmonicc_pos', '#harmonicc_val', '#pr_pos', '#pr_val', '#host_rev', '#n_hosts'];

export function reverseDomain(domain: string): string {
  return domain.toLowerCase().trim().replace(/^https?:\/\//, '').replace(/^www\./, '').split('/')[0].split('.').reverse().join('.');
}

export function ccDomainRanksUrl(release: string): string {
  return `https://data.commoncrawl.org/projects/hyperlinkgraph/${release}/domain/${release}-domain-ranks.txt.gz`;
}

export interface DomainAuthorityResult {
  domain: string;
  releaseId: string;
  inGraph: boolean;
  harmonicPos: number | null;
  harmonicVal: number | null;
  pagerankPos: number | null;
  pagerankVal: number | null;
  nHosts: number | null;
  provenance: typeof CC_GRAPH_PROVENANCE;
  methodology: string;
}

export interface AuthorityCollectResult {
  status: 'OBSERVED' | 'NOT_AVAILABLE';
  releaseId: string;
  fromCache: boolean;
  results: DomainAuthorityResult[];
  unavailable?: ProviderUnavailable;
}

export class CommonCrawlAuthorityCollector {
  constructor(private db: SeoDatabase, private opts: { fetchImpl?: typeof fetch; release?: string; timeoutMs?: number } = {}) {}

  private get release(): string { return this.opts.release ?? process.env.CC_GRAPH_RELEASE ?? DEFAULT_CC_GRAPH_RELEASE; }

  /** Persisted-only read of every stored release for the tenant. */
  public latest(tenantId: string): DomainAuthorityResult[] {
    return this.db.getDomainAuthority(tenantId).map(r => ({ domain: r.domain, releaseId: r.releaseId, inGraph: r.inGraph, harmonicPos: r.harmonicPos, harmonicVal: r.harmonicVal,
      pagerankPos: r.pagerankPos, pagerankVal: r.pagerankVal, nHosts: r.nHosts, provenance: CC_GRAPH_PROVENANCE, methodology: CC_GRAPH_METHODOLOGY }));
  }

  /** One streaming pass of the release file (~2.5 GB gz, nothing written to disk), skipped when already stored. */
  public async collect(tenantId: string, domains: string[]): Promise<AuthorityCollectResult> {
    const releaseId = this.release;
    const fail = (reason: string): AuthorityCollectResult => ({ status: 'NOT_AVAILABLE', releaseId, fromCache: false, results: [],
      unavailable: { available: false, provider: CC_GRAPH_SOURCE, reason, timestamp: new Date().toISOString() } });

    const wanted = new Map<string, string>(); // reversed -> display domain
    for (const d of domains) wanted.set(reverseDomain(d), d.toLowerCase().replace(/^https?:\/\//, '').replace(/^www\./, '').split('/')[0]);

    const stored = new Set(this.db.getDomainAuthority(tenantId, releaseId).map(r => r.domain));
    const missing = [...wanted.entries()].filter(([, d]) => !stored.has(d));
    if (missing.length === 0) return { status: 'OBSERVED', releaseId, fromCache: true, results: this.latest(tenantId).filter(r => r.releaseId === releaseId) };

    const url = ccDomainRanksUrl(releaseId);
    const fetchImpl = this.opts.fetchImpl ?? fetch;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.opts.timeoutMs ?? 20 * 60 * 1000);
    try {
      let res: Response;
      try { res = await fetchImpl(url, { signal: controller.signal }); }
      catch (err: any) { return fail(err?.name === 'AbortError' ? 'timeout streaming the graph file' : `network error: ${err?.cause?.code ?? err?.message ?? err}`); }
      if (!res.ok || !res.body) return fail(`HTTP ${res.status} fetching ${url}`);
      const lastModified = res.headers.get('last-modified');

      const gunzip = createGunzip();
      const input = Readable.fromWeb(res.body as any);
      input.on('error', e => gunzip.destroy(e));
      const lines = createInterface({ input: input.pipe(gunzip), crlfDelay: Infinity });

      const need = new Map(missing);
      const found = new Map<string, string[]>();
      let first = true;
      for await (const line of lines) {
        if (first) {
          first = false;
          const header = line.split('\t');
          if (EXPECTED_HEADER.some((h, i) => header[i] !== h)) return fail(`unexpected graph file header: ${line.slice(0, 120)}`);
          continue;
        }
        const tab = line.lastIndexOf('\t');
        const tab2 = line.lastIndexOf('\t', tab - 1);
        const hostRev = line.slice(tab2 + 1, tab);
        if (need.has(hostRev)) {
          found.set(hostRev, line.split('\t'));
          if (found.size === need.size) break; // every wanted domain located; stop streaming early
        }
      }
      if (first) return fail('graph file was empty');

      const fetchedAt = new Date().toISOString();
      for (const [rev, domain] of need) {
        const c = found.get(rev);
        this.db.upsertDomainAuthority({ tenantId, domain, releaseId, source: CC_GRAPH_SOURCE, inGraph: Boolean(c),
          harmonicPos: c ? Number(c[0]) : null, harmonicVal: c ? Number(c[1]) : null, pagerankPos: c ? Number(c[2]) : null, pagerankVal: c ? Number(c[3]) : null,
          nHosts: c ? Number(c[5]) : null, sourceUrl: url, sourceLastModified: lastModified, fetchedAt });
      }
      return { status: 'OBSERVED', releaseId, fromCache: false, results: this.latest(tenantId).filter(r => r.releaseId === releaseId) };
    } catch (err: any) {
      return fail(err?.name === 'AbortError' ? 'timeout streaming the graph file' : (err?.message ?? String(err)));
    } finally {
      clearTimeout(timer);
      controller.abort(); // stop any remaining download after an early exit
    }
  }
}
