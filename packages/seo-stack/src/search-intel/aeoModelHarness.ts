/**
 * SANOCEA SEO Stack — Model-specific AI visibility harness (AEO/GEO, zero-cost)
 *
 * Asks an OpenAI-compatible chat endpoint (default: a local Ollama at 127.0.0.1:11434) the buyer-style questions we
 * track, N samples each, and records whether the answer mentions our brand or domain.
 *
 * What an observation honestly means:
 *   "Model M, served at host H, answered prompt P with text T at time X, sampled at temperature τ."
 * It is OBSERVED for that model only. It is NOT ChatGPT, Perplexity, Gemini, Claude.ai or Google AI Overview visibility:
 * no consumer product is queried. A model without web access reflects its training data, so "not mentioned" from a small
 * local model is expected for a young brand and says nothing about search engines. Every summary carries this scope.
 *
 * Truth rules:
 * - Endpoint unreachable, HTTP error, empty/invalid response => ProviderUnavailable for that sample; nothing stored.
 * - The full response text is stored, so any mention/non-mention can be audited.
 * - Provenance says LOCAL only when the endpoint host is loopback/private; otherwise it says MODEL API.
 * - STATUS: implemented and tested with HTTP fakes. No model runtime exists on this host, so it has not run live.
 */

import { createHash, randomUUID } from 'node:crypto';
import { SeoDatabase } from '../persistence/seoDb.js';
import { ProviderUnavailable } from './rankCommandTypes.js';

export const MODEL_SCOPE_NOTICE =
  'Observed for the named model only. This is not ChatGPT, Perplexity, Gemini or Google AI Overview visibility; no consumer product was queried.';

export interface ModelVisibilityObservation {
  observationId: string; tenantId: string; prompt: string; sampleIndex: number; model: string; endpointHost: string; temperature: number;
  responseText: string; brandMentioned: boolean; matchedTerms: string[]; urlsInResponse: string[]; observedAt: string;
  provenance: '[OBSERVED: LOCAL MODEL RESPONSE]' | '[OBSERVED: MODEL API RESPONSE]';
  scope: 'MODEL_SPECIFIC';
}

export interface ModelVisibilityRun {
  model: string; endpointHost: string;
  observations: ModelVisibilityObservation[];
  unavailable: ProviderUnavailable[];
  mentionRatePercent: number | null; // null when nothing was observed
  scopeNotice: string;
}

export function isPrivateHost(host: string): boolean {
  return /^(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|\[?::1\]?$)/i.test(host);
}

/** Buyer-style, brand-neutral prompt: it must not name the brand or it would measure nothing. */
export function buildPrompt(query: string): string {
  return `I am researching options for: "${query}". Which specific companies, products or tools would you recommend, and why? Name concrete options.`;
}

export function detectMentions(text: string, brandTerms: string[]): { matched: string[]; urls: string[] } {
  const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const matched = brandTerms.filter(t => t.trim() && new RegExp(`(^|[^\\p{L}\\p{N}])${esc(t.trim())}($|[^\\p{L}\\p{N}])`, 'iu').test(text));
  const urls = [...new Set(text.match(/https?:\/\/[^\s)>\]"']+/g) ?? [])];
  return { matched, urls };
}

export interface ModelHarnessOptions {
  baseUrl?: string; model?: string; apiKey?: string; temperature?: number; samples?: number; timeoutMs?: number; fetchImpl?: typeof fetch;
}

export class ModelVisibilityHarness {
  constructor(private db: SeoDatabase, private opts: ModelHarnessOptions = {}) {}

  public get configured(): boolean { return Boolean(this.model); }

  private get baseUrl(): string { return (this.opts.baseUrl ?? process.env.SEO_LLM_BASE_URL ?? 'http://127.0.0.1:11434/v1').replace(/\/$/, ''); }
  private get model(): string | undefined { return this.opts.model ?? process.env.SEO_LLM_MODEL; }

  public async run(tenantId: string, queries: string[], brandTerms: string[]): Promise<ModelVisibilityRun> {
    const model = this.model;
    const host = new URL(this.baseUrl).host;
    const scopeNotice = MODEL_SCOPE_NOTICE;
    const observations: ModelVisibilityObservation[] = [];
    const unavailable: ProviderUnavailable[] = [];
    const na = (reason: string) => unavailable.push({ available: false, provider: `MODEL_ENDPOINT:${host}`, reason, timestamp: new Date().toISOString() });

    if (!model) {
      na('SEO_LLM_MODEL is not configured (no model selected)');
      return { model: '', endpointHost: host, observations, unavailable, mentionRatePercent: null, scopeNotice };
    }
    const temperature = this.opts.temperature ?? 0.7;
    const samples = this.opts.samples ?? 3;
    const provenance = isPrivateHost(new URL(this.baseUrl).hostname) ? '[OBSERVED: LOCAL MODEL RESPONSE]' as const : '[OBSERVED: MODEL API RESPONSE]' as const;
    const key = this.opts.apiKey ?? process.env.SEO_LLM_API_KEY;

    for (const q of queries) {
      const prompt = buildPrompt(q);
      for (let i = 0; i < samples; i++) {
        try {
          const res = await (this.opts.fetchImpl ?? fetch)(`${this.baseUrl}/chat/completions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...(key ? { Authorization: `Bearer ${key}` } : {}) },
            body: JSON.stringify({ model, messages: [{ role: 'user', content: prompt }], temperature, stream: false }),
            signal: AbortSignal.timeout(this.opts.timeoutMs ?? 120000)
          });
          if (!res.ok) { na(`HTTP ${res.status} for "${q}"`); continue; }
          const json = await res.json() as any;
          const text = json?.choices?.[0]?.message?.content;
          if (typeof text !== 'string' || text.trim() === '') { na(`empty or malformed completion for "${q}"`); continue; }
          const { matched, urls } = detectMentions(text, brandTerms);
          const obs: ModelVisibilityObservation = { observationId: `llm-${randomUUID()}`, tenantId, prompt, sampleIndex: i, model: String(json?.model ?? model), endpointHost: host,
            temperature, responseText: text, brandMentioned: matched.length > 0, matchedTerms: matched, urlsInResponse: urls, observedAt: new Date().toISOString(), provenance, scope: 'MODEL_SPECIFIC' };
          this.db.recordLlmModelObservation({ ...obs, responseSha256: createHash('sha256').update(text).digest('hex') });
          observations.push(obs);
        } catch (err: any) {
          na(err?.name === 'TimeoutError' ? `timeout for "${q}"` : `endpoint unreachable: ${err?.cause?.code ?? err?.message ?? err}`);
        }
      }
    }
    const rate = observations.length ? Math.round((observations.filter(o => o.brandMentioned).length / observations.length) * 1000) / 10 : null;
    return { model, endpointHost: host, observations, unavailable, mentionRatePercent: rate, scopeNotice };
  }

  /** Persisted-only summary, grouped per model so different models are never blended. */
  public summary(tenantId: string) {
    const rows = this.db.getLlmModelObservations(tenantId);
    const byModel = new Map<string, typeof rows>();
    for (const r of rows) { const k = `${r.model}@${r.endpointHost}`; byModel.set(k, [...(byModel.get(k) ?? []), r]); }
    return {
      scopeNotice: MODEL_SCOPE_NOTICE,
      provenance: rows.length ? (rows.every(r => isPrivateHost(r.endpointHost.split(':')[0])) ? '[OBSERVED: LOCAL MODEL RESPONSE]' : '[OBSERVED: MODEL API RESPONSE]') : '[NOT AVAILABLE]',
      models: [...byModel.entries()].map(([k, list]) => ({ modelAtHost: k, samples: list.length, mentions: list.filter(r => r.brandMentioned).length,
        mentionRatePercent: Math.round((list.filter(r => r.brandMentioned).length / list.length) * 1000) / 10, lastObservedAt: list[0].observedAt }))
    };
  }
}
