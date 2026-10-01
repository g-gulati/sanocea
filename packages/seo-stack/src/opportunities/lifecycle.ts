/**
 * Customer-facing lifecycle of one opportunity: Found -> Concluded -> Selected -> Policy decision -> Executed -> Verified.
 *
 * Pure and deterministic: every sentence is derived from what the worker persisted (the opportunity, its diagnosis and action plan,
 * its approval record and its audit events). Nothing is estimated or invented; a stage with no evidence is `waiting` or
 * `not_applicable` and says so. Business wording only: no database ids, worker/actor identifiers, policy versions or file paths.
 */
import type { Opportunity } from './opportunityEngine.js';
import { classifyAction, modeAllows, AutonomyMode } from './autonomyPolicy.js';

export type StageState = 'done' | 'current' | 'waiting' | 'blocked' | 'not_applicable';
export interface LifecycleStage { key: 'found' | 'concluded' | 'selected' | 'policy' | 'executed' | 'verified'; label: string; state: StageState; headline: string; detail?: string; at?: string | null }
export interface Lifecycle { stages: LifecycleStage[]; decisionNeeded: { question: string; why: string; options: Array<{ address: string; signals: string[]; consequence: string }> } | null; summary: string }
interface Ev { at: string; actor: string; from: string | null; to: string; note: string }

export const ACTION_WORDS: Record<string, string> = {
  FIX_SITEMAP_ENTRY: 'Correct the address listed in the sitemap', CHANGE_CANONICAL: "Correct the page's preferred (canonical) address", CHANGE_REDIRECT: 'Change the web-server redirect',
  CHANGE_SERVER_RENDERING: 'Change how the page is delivered so its text is in the HTML', UPDATE_TITLE_META: 'Update the page title or description', ADD_INTERNAL_LINK: 'Add an internal link', UPDATE_SCHEMA: 'Update the structured data',
  CREATE_SEO_PAGE: 'Create a new page', CREATE_SUPPORTING_CONTENT: 'Create supporting content', UPDATE_EXISTING_PAGE: 'Update the existing page', CHANGE_INDEXABILITY: 'Change whether the page may be indexed',
  INVESTIGATE: 'Keep investigating', NO_ACTION: 'Take no action'
};
const MODE_WORDS: Record<string, string> = {
  AUTONOMY_DISABLED: 'Autonomy is switched off', RECOMMEND_ONLY: 'Recommend-only mode', AUTONOMOUS_SEO: 'Autonomous SEO mode (technical fixes)',
  AUTONOMOUS_CONTENT: 'Autonomous content mode', AUTONOMOUS_DISTRIBUTION: 'Autonomous distribution mode'
};
const CLASS_WORDS: Record<string, string> = { A: 'low-risk technical fix', B: 'change to page content or search behaviour', C: 'change that always needs a person', D: 'publication outside the website' };
const word = (a: string) => ACTION_WORDS[a] ?? 'Take the recommended action';
const strip = (s: string) => s.replace(/^[A-Z_]+(?: \([^)]*\))?:\s*/, '');

export function buildLifecycle(o: Opportunity, history: Ev[], mode: AutonomyMode): Lifecycle {
  const action = o.decision?.action ?? o.recommendedAction;
  const cls = classifyAction(action);
  const last = (re: RegExp) => [...history].reverse().find(e => re.test(e.note));
  const stages: LifecycleStage[] = [];

  stages.push({ key: 'found', label: 'Found', state: 'done', headline: o.diagnosis?.finding ?? (o.plainEnglish || o.reason), detail: !o.diagnosis && o.reason !== o.plainEnglish ? o.reason : undefined, at: o.detectedAt });

  const dn = o.diagnosis?.decision_needed ?? null;
  if (o.diagnosis) {
    const d = o.diagnosis;
    const ruledOut = d.hypotheses.filter(h => h.status === 'RULED_OUT').length;
    stages.push({ key: 'concluded', label: 'Concluded', state: dn ? 'blocked' : d.sufficient ? 'done' : 'current',
      headline: dn ? 'The evidence is split; the owner needs to choose' : d.sufficient ? d.conclusion : 'More evidence is needed before SANOCEA can conclude',
      detail: dn ? d.conclusion : d.sufficient ? (ruledOut ? 'The competing explanation was ruled out by the evidence.' : undefined) : (d.missing_evidence.length ? `Still gathering: ${d.missing_evidence.join('; ')}.` : d.conclusion), at: o.updatedAt });
  } else {
    stages.push({ key: 'concluded', label: 'Concluded', state: 'done', headline: /GOOGLE/i.test(o.source) ? "Taken from Google's own report, quoted as Google gave it." : 'Observed directly: SANOCEA recorded what the page actually returns.', detail: 'No competing explanations were needed for this observation.', at: o.detectedAt });
  }

  const plan = o.actionPlan;
  const selectedAction = plan?.selected ?? action;
  stages.push({ key: 'selected', label: 'Selected', state: dn || selectedAction === 'INVESTIGATE' && !plan?.investigate_next?.length ? 'waiting' : 'done',
    headline: dn ? 'No action chosen yet: waiting for the owner’s answer' : word(selectedAction),
    detail: dn ? undefined : (plan?.why ?? o.decision?.rationale) || undefined, at: o.updatedAt });

  const denied = last(/^POLICY_DENIED:/), appr = o.approval;
  const investigating = selectedAction === 'INVESTIGATE' || selectedAction === 'NO_ACTION' || !!dn;
  if (investigating && !appr) {
    stages.push({ key: 'policy', label: 'Policy decision', state: 'not_applicable', headline: 'Nothing to authorise yet', detail: 'SANOCEA does not need permission to investigate; it asks only once there is a change to make.' });
  } else if (appr) {
    stages.push({ key: 'policy', label: 'Policy decision', state: 'done', at: appr.at,
      headline: appr.actorType === 'AUTONOMOUS_AGENT' ? 'Permitted automatically' : 'Approved by a person',
      detail: appr.actorType === 'AUTONOMOUS_AGENT' ? `This is a ${CLASS_WORDS[appr.actionClass] ?? 'change'}. ${MODE_WORDS[mode] ?? 'The tenant mode'} allows it, the evidence and decision were on record, and nothing about it needed a person.` : 'A person approved this action.' });
  } else if (denied) {
    stages.push({ key: 'policy', label: 'Policy decision', state: 'blocked', at: denied.at, headline: cls === 'C' ? 'Not permitted automatically: this always needs a person' : 'Not permitted automatically in the current mode', detail: strip(denied.note).replace(/\bClass [A-D]\b/g, 'This kind of change') });
  } else {
    const m = modeAllows(mode, classifyAction(selectedAction), selectedAction);
    stages.push({ key: 'policy', label: 'Policy decision', state: m.allowed ? 'current' : 'blocked', headline: m.allowed ? 'About to be authorised' : 'Not permitted automatically in the current mode',
      detail: m.allowed ? undefined : `This is a ${CLASS_WORDS[classifyAction(selectedAction)] ?? 'change'}. ${MODE_WORDS[mode] ?? ''} does not allow SANOCEA to make it on its own.` });
  }

  const exec = last(/^EXECUTED /), blocked = last(/^EXECUTION_(BLOCKED|NOT_PERMITTED|ERROR)/);
  stages.push(exec ? { key: 'executed', label: 'Executed', state: 'done', at: exec.at, headline: 'The change was made on the live website', detail: exec.note.replace(/^EXECUTED [A-Z_]+: /, '').replace(/release \S+ -> \S+; /, '').replace(/; source .*$/, '') ? 'Done as a new release; the previous version is kept so it can be restored.' : undefined }
    : blocked ? { key: 'executed', label: 'Executed', state: 'blocked', at: blocked.at, headline: 'Authorised, but SANOCEA held back from making the change', detail: strip(blocked.note) }
    : appr ? { key: 'executed', label: 'Executed', state: 'current', headline: 'Waiting for the next execution cycle' }
    : { key: 'executed', label: 'Executed', state: 'waiting', headline: 'Nothing has been changed' });

  const met = history.filter(e => e.note.startsWith('VERIFICATION MET')), rolled = last(/^ROLLED_BACK/), vbad = last(/^VERIFICATION (NOT_MET|INCONCLUSIVE)|^VERIFICATION_INVESTIGATE|^ROLLBACK_UNAVAILABLE|^VERIFICATION_ABANDONED/), deferred = last(/^VERIFICATION_DEFERRED/);
  stages.push(rolled ? { key: 'verified', label: 'Verified', state: 'blocked', at: rolled.at, headline: 'Re-checking showed the change did not work, so it was undone', detail: 'The previous version of the website was restored automatically.' }
    : met.length >= 2 ? { key: 'verified', label: 'Verified', state: 'done', at: met[1].at, headline: 'Confirmed twice on the live site: right after the change and again a day later' }
    : met.length === 1 ? { key: 'verified', label: 'Verified', state: 'current', at: met[0].at, headline: 'Confirmed on the live site; one more check is scheduled for a day later' }
    : vbad ? { key: 'verified', label: 'Verified', state: 'blocked', at: vbad.at, headline: 'The result could not be confirmed and needs a look', detail: strip(vbad.note) }
    : exec ? { key: 'verified', label: 'Verified', state: 'current', at: deferred?.at ?? null, headline: deferred ? 'The live site could not be read yet; SANOCEA will retry' : 'Being re-checked on the live site' }
    : { key: 'verified', label: 'Verified', state: 'waiting', headline: 'Nothing to verify yet' });

  const cur = stages.find(s => s.state === 'blocked' || s.state === 'current') ?? stages[stages.length - 1];
  const summary = dn ? 'Waiting for one decision from the owner.' : cur.state === 'blocked' ? `${cur.label}: ${cur.headline}` : stages.every(s => s.state === 'done' || s.state === 'not_applicable') ? 'Complete.' : `${cur.label}: ${cur.headline}`;
  return { stages, decisionNeeded: dn, summary };
}
