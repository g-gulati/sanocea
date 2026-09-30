/**
 * SANOCEA SEO Stack — Autonomous SEO Agent Roster
 *
 * Ten agent routines. Each one either consumes real persisted data / a real provider call and reports
 * exactly what it found, or reports AWAITING_PROVIDER with provenance [NOT AVAILABLE]. No agent returns
 * a pre-written result; an agent that does not perform a check does not claim its outcome.
 *
 * Scheduling: this module provides on-demand execution + persisted execution records only. There is no
 * executor for `nextScheduledAt` yet, so it is left empty rather than claiming a schedule.
 */

import { randomUUID } from 'node:crypto';
import { AgentRole, AgentStatus, AgentTaskExecution, AgentRosterSummary } from '../search-intel/rankCommandTypes.js';
import { SeoDatabase } from '../persistence/seoDb.js';
import { KeywordIntelligenceEngine } from '../search-intel/keywordIntelligence.js';
import { AeoIntelligenceEngine } from '../search-intel/aeoIntelligence.js';
import { GeoCitationEngine } from '../search-intel/geoCitationEngine.js';
import { CompetitorIntelligenceEngine } from '../search-intel/competitorWorker.js';

export interface AgentContext {
  tenantId: string;
  domain: string;
  /** GSC property URL, used to scope GSC position observations. */
  siteUrl?: string;
  queries: string[];
  db?: SeoDatabase;
  keywordEngine: KeywordIntelligenceEngine;
  aeoEngine: AeoIntelligenceEngine;
  geoEngine: GeoCitationEngine;
  competitorEngine: CompetitorIntelligenceEngine;
}

export type AgentResult = Pick<AgentTaskExecution, 'status' | 'currentTask' | 'outputSummary' | 'provenance' | 'details'>;

export interface AutonomousAgent {
  id: string;
  name: string;
  role: AgentRole;
  run(ctx: AgentContext): Promise<AgentResult>;
}

const awaiting = (currentTask: string, reason: string, details?: Record<string, any>): AgentResult => ({
  status: 'AWAITING_PROVIDER', currentTask, outputSummary: reason, provenance: '[NOT AVAILABLE]', details
});

export const DEFAULT_AGENTS: AutonomousAgent[] = [
  {
    id: 'agent-seo-strategist', name: 'SEO Strategist', role: 'SEO_STRATEGIST',
    async run(ctx) {
      const task = 'Summarising which persisted evidence layers currently exist for this tenant';
      const gsc = ctx.db?.getGscSnapshotsForTenant(ctx.tenantId) ?? [];
      const inputs = {
        gscSnapshots: gsc.length,
        serpProviderTrajectories: ctx.db?.getAllSerpTrajectories(ctx.tenantId).length ?? 0,
        gscPositionObservations: ctx.db?.getGscPositionObservations(ctx.tenantId, ctx.siteUrl ?? '').length ?? 0,
        keywordObservations: ctx.db?.getLatestKeywordObservations(ctx.tenantId).length ?? 0,
        aeoObservations: ctx.db?.getLatestAeoObservations(ctx.tenantId).length ?? 0,
        geoObservations: ctx.db?.getGeoCitationsForTenant(ctx.tenantId).length ?? 0,
        competitorSitemapPolls: ctx.db?.getLatestCompetitorSitemapObservations(ctx.tenantId).filter(s => s.status === 'POLL_OK').length ?? 0
      };
      const present = Object.entries(inputs).filter(([, n]) => n > 0).map(([k, n]) => `${k}=${n}`);
      const missing = Object.entries(inputs).filter(([, n]) => n === 0).map(([k]) => k);
      if (present.length === 0) return awaiting(task, 'No persisted SEO evidence exists for this tenant yet', { inputs });
      return { status: 'COMPLETED', currentTask: task, provenance: '[CALCULATED]', details: { inputs },
        outputSummary: `Evidence available: ${present.join(', ')}. No evidence yet: ${missing.length ? missing.join(', ') : 'none'}.` };
    }
  },
  {
    id: 'agent-keyword-researcher', name: 'Keyword Researcher', role: 'KEYWORD_RESEARCHER',
    async run(ctx) {
      const task = 'Fetching keyword volume / CPC / competition from the keyword provider';
      const report = await ctx.keywordEngine.evaluateKeywords(ctx.tenantId, ctx.queries);
      if (report.observedKeywordsCount === 0) {
        const reason = report.observations[0]?.rawJson ? (JSON.parse(report.observations[0].rawJson).error ?? 'provider returned no data') : 'provider returned no data';
        return awaiting(task, `No keyword metrics observed: ${reason}`, { provider: report.provider, tracked: report.totalKeywordsTracked });
      }
      return { status: 'COMPLETED', currentTask: task, provenance: '[OBSERVED: KEYWORD PROVIDER]',
        outputSummary: `Observed ${report.observedKeywordsCount}/${report.totalKeywordsTracked} queries, ${report.totalObservedVolume} total monthly volume (provider ${report.provider})`,
        details: { provider: report.provider, observed: report.observedKeywordsCount, tracked: report.totalKeywordsTracked, clusters: report.clusters.length } };
    }
  },
  {
    id: 'agent-content-optimizer', name: 'Content Optimizer', role: 'CONTENT_OPTIMIZER',
    async run() {
      return awaiting('Title / meta / heading optimisation checks',
        'NOT IMPLEMENTED: no page-content audit is performed by this routine; it needs a page-content input source (crawler output) before it can report anything');
    }
  },
  {
    id: 'agent-technical-seo', name: 'Technical SEO', role: 'TECHNICAL_SEO',
    async run(ctx) {
      const task = 'Reading the latest persisted tier-1 technical monitoring heartbeat';
      const beats = (ctx.db?.getRecentHeartbeats(ctx.tenantId, 50) ?? []).filter(h => h.tier === 'tier1');
      if (beats.length === 0) return awaiting(task, 'No tier-1 monitoring heartbeat has been persisted for this tenant');
      const h = beats[0];
      return { status: h.status === 'ok' ? 'COMPLETED' : 'ALERT', currentTask: task, provenance: '[OBSERVED: TIER-1 MONITOR HEARTBEAT]',
        outputSummary: `Last tier-1 run ${h.timestamp}: status=${h.status}, ${h.changeCount} change(s) detected, ${h.durationMs}ms`,
        details: { heartbeatId: h.id, timestamp: h.timestamp, status: h.status, changeCount: h.changeCount } };
    }
  },
  {
    id: 'agent-aeo-specialist', name: 'AEO Specialist', role: 'AEO_SPECIALIST',
    async run(ctx) {
      const task = 'Observing Featured Snippets, PAA and AI Overview via the SERP provider';
      const s = await ctx.aeoEngine.trackQueries(ctx.tenantId, ctx.queries, ctx.domain);
      if (s.observations.length === 0) {
        return awaiting(task, `No SERP feature data observed: ${s.unavailable[0]?.reason ?? 'no result'}`, { unavailable: s.unavailable.length });
      }
      return { status: 'COMPLETED', currentTask: task, provenance: '[OBSERVED: SERP PROVIDER]',
        outputSummary: `Observed ${s.observations.length}/${s.totalQueriesTracked} queries; snippets owned ${s.featuredSnippetCaptureCount}; AI Overviews present ${s.aiOverviewCoverageCount}`,
        details: { observed: s.observations.length, unavailable: s.unavailable.length } };
    }
  },
  {
    id: 'agent-geo-specialist', name: 'GEO Specialist', role: 'GEO_SPECIALIST',
    async run(ctx) {
      const task = 'Observing AI-assistant citations via the citation provider';
      const s = await ctx.geoEngine.pollCitations(ctx.tenantId, ctx.queries, ctx.domain);
      if (s.observations.length === 0) {
        return awaiting(task, `No AI citation data observed: ${s.unavailable[0]?.reason ?? 'no result'}`, { unavailable: s.unavailable.length });
      }
      return { status: 'COMPLETED', currentTask: task, provenance: '[OBSERVED: AI CITATION ENGINE]',
        outputSummary: `Observed ${s.observations.length} query/engine checks; cited in ${s.totalCitationsObserved}`,
        details: { observed: s.observations.length, cited: s.totalCitationsObserved, unavailable: s.unavailable.length } };
    }
  },
  {
    id: 'agent-link-building', name: 'Link Building Manager', role: 'LINK_BUILDING_MANAGER',
    async run(ctx) {
      return awaiting('External referring-domain tracking + internal link equity mapping',
        'NOT AVAILABLE: no backlink provider is connected and no internal-link check is implemented in this routine',
        { backlinks: ctx.competitorEngine.getBacklinkStatus() });
    }
  },
  {
    id: 'agent-analytics-manager', name: 'Analytics Manager', role: 'ANALYTICS_MANAGER',
    async run(ctx) {
      const task = 'Reading the latest persisted Google Search Console snapshot';
      const snaps = ctx.db?.getGscSnapshotsForTenant(ctx.tenantId) ?? [];
      if (snaps.length === 0) return awaiting(task, 'No GSC snapshot has been persisted for this tenant');
      const s = [...snaps].sort((a, b) => a.capturedAt.localeCompare(b.capturedAt))[snaps.length - 1];
      return { status: 'COMPLETED', currentTask: task, provenance: '[OBSERVED: PERSISTED GSC SNAPSHOT]',
        outputSummary: `${s.totalClicks} clicks / ${s.totalImpressions} impressions, CTR ${(s.averageCtr * 100).toFixed(2)}%, avg position ${s.averagePosition.toFixed(2)} (${s.dateRange.startDate}..${s.dateRange.endDate}, captured ${s.capturedAt})`,
        details: { snapshotId: s.snapshotId, siteUrl: s.siteUrl, capturedAt: s.capturedAt } };
    }
  },
  {
    id: 'agent-competitive-intel', name: 'Competitive Intelligence', role: 'COMPETITIVE_INTELLIGENCE',
    async run(ctx) {
      const task = 'Polling competitor sitemaps and comparing keyword coverage';
      const r = await ctx.competitorEngine.generateReport(ctx.tenantId, ctx.queries);
      const ok = r.sitemapObservations.filter(o => o.status === 'POLL_OK');
      const failed = r.sitemapObservations.filter(o => o.status === 'POLL_FAILED');
      const newUrls = ok.reduce((n, o) => n + o.newlyDiscoveredUrls.length, 0);
      const removed = ok.reduce((n, o) => n + o.removedUrls.length, 0);
      const gapNote = r.keywordGapsStatus === 'OBSERVED' ? `${r.keywordGaps.length} keyword gap(s) observed` : `keyword gaps NOT AVAILABLE (${r.keywordGapsUnavailableReason})`;
      const details = { polled: r.sitemapObservations.length, ok: ok.length, failed: failed.length, newUrls, removedUrls: removed,
        failures: failed.map(f => ({ competitor: f.competitorId, error: f.error })) };
      if (ok.length === 0) {
        return { status: 'ALERT', currentTask: task, provenance: '[NOT AVAILABLE]', details,
          outputSummary: `All ${r.sitemapObservations.length} competitor sitemap polls failed or were degraded; ${gapNote}` };
      }
      return { status: 'COMPLETED', currentTask: task, provenance: '[OBSERVED: SITEMAP FETCH]', details,
        outputSummary: `Sitemap polls ok ${ok.length}/${r.sitemapObservations.length} (failed ${failed.length}); +${newUrls}/-${removed} URLs vs previous baseline; ${gapNote}` };
    }
  },
  {
    id: 'agent-ai-content-auditor', name: 'AI Content Auditor', role: 'AI_CONTENT_AUDITOR',
    async run() {
      return awaiting('Draft factual-claim / thin-content / schema audit',
        'NOT IMPLEMENTED: no content-draft audit is performed by this routine; it needs a content-engine draft input before it can report anything');
    }
  }
];

export class AgentRosterManager {
  private agents = new Map<string, AutonomousAgent>();

  constructor(private db: SeoDatabase | undefined, private deps: Omit<AgentContext, 'tenantId' | 'db'>, agents: AutonomousAgent[] = DEFAULT_AGENTS) {
    for (const a of agents) this.registerAgent(a);
  }

  private nextRunResolver?: () => string;

  /** Supplies the real persisted next-run time (from the job scheduler). Without it, no schedule is claimed. */
  public setNextRunResolver(fn: () => string): void { this.nextRunResolver = fn; }

  public registerAgent(agent: AutonomousAgent): void { this.agents.set(agent.id, agent); }
  public getAgent(id: string): AutonomousAgent | undefined { return this.agents.get(id); }
  public getAllAgents(): AutonomousAgent[] { return [...this.agents.values()]; }

  private async runAgent(agent: AutonomousAgent, tenantId: string): Promise<AgentTaskExecution> {
    const executedAt = new Date().toISOString();
    let result: AgentResult;
    try {
      result = await agent.run({ ...this.deps, tenantId, db: this.db });
    } catch (err: any) {
      result = { status: 'ALERT' as AgentStatus, currentTask: 'Agent execution', provenance: '[NOT AVAILABLE]', outputSummary: `Agent threw: ${err?.message ?? err}`, details: { error: String(err?.stack ?? err) } };
    }
    const task: AgentTaskExecution = { taskId: `task-${agent.role.toLowerCase()}-${randomUUID()}`, tenantId, agentId: agent.id, agentName: agent.name,
      role: agent.role, executedAt, nextScheduledAt: '', ...result };
    this.db?.recordAgentTaskExecution(task);
    return task;
  }

  public async executeAgent(agentId: string, tenantId: string): Promise<AgentTaskExecution> {
    const agent = this.agents.get(agentId);
    if (!agent) throw new Error(`Agent ${agentId} not found in roster`);
    return this.runAgent(agent, tenantId);
  }

  public async executeAll(tenantId: string): Promise<AgentTaskExecution[]> {
    const out: AgentTaskExecution[] = [];
    for (const agent of this.agents.values()) out.push(await this.runAgent(agent, tenantId));
    return out;
  }

  /** Persisted state only: never triggers agent execution or provider calls. */
  public getRosterSummary(tenantId: string): AgentRosterSummary {
    const next = this.nextRunResolver?.() ?? '';
    const roster = (this.db ? this.db.getLatestAgentRoster(tenantId) : []).map(r => ({ ...r, nextScheduledAt: next }));
    return {
      tenantId,
      activeAgentsCount: roster.filter(e => e.status === 'COMPLETED' || e.status === 'EXECUTING').length,
      totalAgentsCount: this.agents.size,
      roster,
      lastSynchronizedAt: roster.map(r => r.executedAt).sort().pop() ?? '',
      provenance: roster.length ? '[OBSERVED: AGENT EXECUTION LEDGER]' : '[NOT AVAILABLE]'
    };
  }
}
