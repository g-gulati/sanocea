/**
 * Diagnosis and action selection for ONE finding family: a sitemap URL that redirects (sitemap / redirect / canonical).
 *
 *   facts (observed, persisted with the opportunity) -> diagnose -> selectAction -> [existing autonomy policy] -> execute -> verify -> learn
 *
 * Detectors only supply facts. Nothing here maps a finding type to an action: the action is DERIVED from which declared
 * signals (sitemap, redirect, canonical) disagree with an address the evidence establishes as intended. If the evidence does
 * not establish it, the answer is INVESTIGATE with the missing evidence named. Confidence is categorical and every claim cites
 * fact ids; there is no numeric score. The policy (autonomyPolicy.ts) decides whether the selected action may run; it never chooses.
 */
import { createHash } from 'node:crypto';

export interface Fact { id: string; kind: string; subject: string; value: string | null; source: string }
export type HypothesisStatus = 'ESTABLISHED' | 'LIKELY' | 'POSSIBLE' | 'RULED_OUT';
export interface Hypothesis { statement: string; supported_by: string[]; contradicted_by: string[]; status: HypothesisStatus }
export interface Diagnosis { finding: string; hypotheses: Hypothesis[]; conclusion: string; sufficient: boolean; missing_evidence: string[]; intended?: string }
export interface Expectation { kind: string; subject: string; equals?: string; absent?: boolean }
export interface Candidate { action: string; addresses: string; preconditions: string[]; expected_outcome: Expectation[]; verification: string; fallback: 'ROLLBACK' | 'INVESTIGATE' }
export interface ActionPlan { candidates: Candidate[]; selected: string; why: string; rejected: Array<{ action: string; reason: string }>; investigate_next: string[] }

export interface PageObs { url: string; status: number; finalUrl?: string; redirected?: boolean; canonical?: string | null; internalLinks?: string[] }
export interface InspectionObs { url: string; googleCanonical: string | null }
/** GA4 first-party behaviour for one landing path over a window. Behaviour evidence only: it never establishes an intended address. */
export interface Ga4LandingObs { landingPage: string; sessions: number; engagedSessions: number; organicSessions: number; windowStart: string; windowEnd: string }
export const GA4_SOURCE = '[OBSERVED: GOOGLE ANALYTICS 4 DATA API]';

const fid = (kind: string, subject: string, value: string | null) => `fact:${kind}:${createHash('sha1').update(`${subject}|${value}`).digest('hex').slice(0, 8)}`;
const mk = (kind: string, subject: string, value: string | null, source: string): Fact => ({ id: fid(kind, subject, value), kind, subject, value, source });
const norm = (u: string) => u.replace(/#.*$/, '');
const form = (u: string) => (new URL(u).pathname.endsWith('/') ? 'slash' : 'no-slash');
const stripSlash = (u: string) => norm(u).replace(/\/+$/, '');

/** Facts for one redirecting sitemap URL, from what the audit and Google inspection already observed. Observation only. */
export function collectRedirectFamilyFacts(page: PageObs, allPages: PageObs[], inspections: InspectionObs[], crawlSource = '[OBSERVED: LIVE PAGE FETCH]', ga4: Ga4LandingObs[] = []): Fact[] {
  const L = page.url, D = page.finalUrl!;
  const facts: Fact[] = [mk('sitemap_lists', L, L, crawlSource), mk('redirects_to', L, D, crawlSource), mk('destination_status', D, String(page.status), crawlSource), mk('destination_canonical', D, page.canonical ?? null, crawlSource)];
  for (const p of allPages) for (const href of p.internalLinks ?? []) if (stripSlash(href) === stripSlash(L) || stripSlash(href) === stripSlash(D)) facts.push(mk('internal_link', `${p.url}->`, norm(href), crawlSource));
  const insp = inspections.find(i => i.url === D);
  if (insp) facts.push(mk('google_canonical', D, insp.googleCanonical, '[OBSERVED: GOOGLE SEARCH CONSOLE API]'));
  // Where real visitors actually land (GA4 reports a path). Recorded for both addresses, including zero when GA4 saw no landings.
  if (ga4.length) {
    for (const addr of [L, D]) {
      const path = new URL(addr).pathname;
      const row = ga4.find(g => g.landingPage === path);
      facts.push(mk('ga4_landing_sessions', addr, row ? `${row.sessions} sessions (${row.organicSessions} organic search), ${row.engagedSessions} engaged, ${row.windowStart} to ${row.windowEnd}` : `0 sessions, ${ga4[0].windowStart} to ${ga4[0].windowEnd}`, GA4_SOURCE));
    }
  }
  for (const p of allPages) {
    if (p.url === L) continue;
    const u = new URL(p.finalUrl ?? p.url);
    if (u.pathname === '/' || p.status !== 200) continue; // the root is always slash-form: it says nothing about convention
    facts.push(mk('sibling_form', p.finalUrl ?? p.url, form(p.finalUrl ?? p.url), crawlSource));
  }
  return dedupe(facts);
}
const dedupe = (fs: Fact[]) => [...new Map(fs.map(f => [f.id, f])).values()];

export function diagnoseRedirectFamily(facts: Fact[]): Diagnosis {
  const by = (k: string) => facts.filter(f => f.kind === k);
  const L = by('sitemap_lists')[0].value!, D = by('redirects_to')[0].value!;
  const canon = by('destination_canonical')[0];
  const votes = (addr: string) => ({
    for: [by('sitemap_lists')[0], by('redirects_to')[0], canon].filter(f => (f.kind === 'sitemap_lists' ? L : f.kind === 'redirects_to' ? D : f.value) === addr && (f.kind !== 'destination_canonical' || !!f.value)).map(f => f.id),
  });
  const g = by('google_canonical')[0];
  const links = by('internal_link'), sibs = by('sibling_form');
  const landings = by('ga4_landing_sessions');
  const visited = (addr: string) => landings.filter(f => f.subject === addr && !f.value!.startsWith('0 sessions')).map(f => f.id); // behaviour: supports, never establishes
  const sameForm = L !== D && stripSlash(L) === stripSlash(D); // L and D differ only by a trailing slash
  const practiceFor = (addr: string): { present: string[]; agree: string[]; against: string[] } => {
    const present: string[] = [], agree: string[] = [], against: string[] = [];
    if (g) { present.push(g.id); (g.value === addr ? agree : g.value === (addr === L ? D : L) ? against : []).push(g.id); }
    if (links.length) { present.push(links[0].id); const all = links.every(l => l.value === addr); (all ? agree : against).push(...links.map(l => l.id)); }
    if (sibs.length && sameForm) { present.push(sibs[0].id); const ok = sibs.every(s => s.value === form(addr)); (ok ? agree : against).push(...sibs.map(s => s.id)); }
    return { present, agree, against };
  };
  const missing: string[] = [];
  if (!g) missing.push('Google-selected canonical for the redirect destination (URL Inspection of the destination)');
  if (!links.length) missing.push('internal links to this page');
  if (!sibs.length || !sameForm) missing.push('established URL convention from sibling pages (no non-root sibling pages observed)');
  const independent = (addr: string) => { const p = practiceFor(addr); return p.present.length === 3 && p.agree.length >= 3 && p.against.length === 0; };
  // RULED_OUT only when the other address is ESTABLISHED by independent evidence; a single contradicting signal never rules anything out.
  const status = (addr: string, other: string): HypothesisStatus => (independent(addr) ? 'ESTABLISHED' : independent(other) ? 'RULED_OUT' : practiceFor(addr).agree.length >= 2 && practiceFor(addr).against.length === 0 ? 'LIKELY' : 'POSSIBLE');
  const hD: Hypothesis = { statement: `The intended address of this page is ${D} (the redirect destination).`, supported_by: [...votes(D).for, ...practiceFor(D).agree, ...visited(D)], contradicted_by: [...votes(L).for.filter(i => !votes(D).for.includes(i)), ...practiceFor(D).against], status: status(D, L) };
  const hL: Hypothesis = { statement: `The intended address of this page is ${L} (the address listed in the sitemap).`, supported_by: [...votes(L).for, ...practiceFor(L).agree, ...visited(L)], contradicted_by: [...votes(D).for.filter(i => !votes(L).for.includes(i)), ...practiceFor(L).against], status: status(L, D) };
  const finding = `The sitemap lists ${L}, which redirects to ${D}; the destination's canonical is ${canon.value ?? 'absent'}.`;
  const est = hD.status === 'ESTABLISHED' ? D : hL.status === 'ESTABLISHED' ? L : null;
  if (!est) return { finding, hypotheses: [hD, hL], conclusion: 'The sitemap, the redirect and the canonical disagree, and the available evidence does not establish which address is intended.', sufficient: false, missing_evidence: missing };
  return { finding, hypotheses: [hD, hL], conclusion: `The intended address is ${est}, established by Google's canonical, internal links and sibling convention agreeing. Signals that disagree with it need correcting.`, sufficient: true, missing_evidence: [], intended: est };
}

/** Action selection: derived from which declared signals disagree with the established address. Policy is NOT consulted here. */
export function selectAction(d: Diagnosis, facts: Fact[]): ActionPlan {
  const L = facts.find(f => f.kind === 'sitemap_lists')!.value!, D = facts.find(f => f.kind === 'redirects_to')!.value!;
  const canon = facts.find(f => f.kind === 'destination_canonical')!.value;
  if (!d.sufficient || !d.intended) {
    const reasonFor = (a: string) => ({ FIX_SITEMAP_ENTRY: `would put ${D} in the sitemap; the destination's canonical (${canon ?? 'absent'}) does not establish that this is the intended address`, CHANGE_CANONICAL: 'the evidence does not establish which address is intended, so changing the canonical could point it the wrong way', CHANGE_REDIRECT: 'the evidence does not establish which address is intended, so changing the redirect could break working links' } as Record<string, string>)[a];
    return { candidates: [{ action: 'INVESTIGATE', addresses: 'missing evidence', preconditions: [], expected_outcome: [], verification: 'Re-run the diagnosis after the missing evidence is gathered.', fallback: 'INVESTIGATE' }], selected: 'INVESTIGATE', why: d.conclusion,
      rejected: ['FIX_SITEMAP_ENTRY', 'CHANGE_CANONICAL', 'CHANGE_REDIRECT'].map(a => ({ action: a, reason: reasonFor(a) })), investigate_next: d.missing_evidence.map(m => `Gather: ${m}`) };
  }
  const X = d.intended, cands: Candidate[] = [];
  if ((canon ?? null) !== X) cands.push({ action: 'CHANGE_CANONICAL', addresses: `destination canonical (${canon ?? 'absent'}) disagrees with ${X}`, preconditions: ['the intended address is established by independent evidence'], expected_outcome: [{ kind: 'destination_canonical', subject: D, equals: X }], verification: `Re-fetch ${D} and confirm its canonical is ${X}.`, fallback: 'ROLLBACK' });
  if (L !== X) cands.push({ action: 'FIX_SITEMAP_ENTRY', addresses: `sitemap entry ${L} disagrees with ${X}`, preconditions: [`the destination's canonical equals ${X}`, 'destination returns 200 on the same host'], expected_outcome: [{ kind: 'sitemap_lists', subject: X, equals: X }, { kind: 'sitemap_lists', subject: L, absent: true }, { kind: 'redirects_to', subject: X, absent: true }], verification: `Re-read the sitemap and confirm it lists ${X} and that entry no longer redirects.`, fallback: 'ROLLBACK' });
  if (D !== X) cands.push({ action: 'CHANGE_REDIRECT', addresses: `redirect to ${D} disagrees with ${X}`, preconditions: ['the intended address is established by independent evidence'], expected_outcome: [{ kind: 'redirects_to', subject: L, absent: true }], verification: `Request ${L} and confirm it returns 200 without a redirect.`, fallback: 'ROLLBACK' });
  const order = ['CHANGE_CANONICAL', 'FIX_SITEMAP_ENTRY', 'CHANGE_REDIRECT']; // dependency order: the sitemap fix requires a self-consistent canonical
  cands.sort((a, b) => order.indexOf(a.action) - order.indexOf(b.action));
  const sel = cands[0];
  return { candidates: cands, selected: sel.action, why: `${d.conclusion} Selected ${sel.action} first: ${sel.addresses}.`,
    rejected: cands.slice(1).map(c => ({ action: c.action, reason: `deferred: ${c.action === 'FIX_SITEMAP_ENTRY' ? 'its precondition (destination canonical equals the intended address) is only met after the earlier change' : 'it follows the earlier change in dependency order'}` })), investigate_next: [] };
}

export interface Verification { status: 'MET' | 'NOT_MET' | 'INCONCLUSIVE'; checks: Array<{ expectation: Expectation; ok: boolean | null; observed: string | null }>; next: 'LEARN' | 'ROLLBACK' | 'INVESTIGATE'; reason: string }

/** Compare re-observed facts with the plan's expected outcome. Missing evidence is never read as success. */
export function verifyOutcome(plan: ActionPlan, observed: Fact[], rollbackAvailable: boolean): Verification {
  const sel = plan.candidates.find(c => c.action === plan.selected);
  if (!sel || sel.expected_outcome.length === 0) return { status: 'INCONCLUSIVE', checks: [], next: 'INVESTIGATE', reason: 'The selected action has no expected outcome to verify.' };
  const checks = sel.expected_outcome.map(e => {
    const f = observed.filter(o => o.kind === e.kind && o.subject === e.subject);
    if (e.absent) return { expectation: e, ok: f.length === 0 ? true : false, observed: f[0]?.value ?? null };
    if (!f.length) return { expectation: e, ok: null, observed: null };
    return { expectation: e, ok: f.some(x => x.value === e.equals), observed: f[0].value };
  });
  if (checks.some(c => c.ok === false)) return { status: 'NOT_MET', checks, next: rollbackAvailable && sel.fallback === 'ROLLBACK' ? 'ROLLBACK' : 'INVESTIGATE', reason: 'Re-observed facts contradict the expected outcome.' };
  if (checks.some(c => c.ok === null)) return { status: 'INCONCLUSIVE', checks, next: 'INVESTIGATE', reason: 'Some expected facts were not re-observed.' };
  return { status: 'MET', checks, next: 'LEARN', reason: 'Every expected outcome was observed.' };
}
