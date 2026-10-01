/**
 * SANOCEA autonomy policy: who/what may authorise SEO/content work, and under which tenant mode.
 *
 * This replaces "only a human can approve" with a policy-governed authorisation event that is recorded as what it is:
 * an AUTONOMOUS_AGENT decision under a named policy version, never relabelled as a human one. Human approval and human
 * override remain available and are recorded as HUMAN.
 *
 * Fail closed: an unknown action is Class C. Class C is never authorised autonomously in ANY mode. A tenant with no
 * configuration is RECOMMEND_ONLY. Changing a tenant's mode is itself a human-only act.
 *
 * Two decision points: (1) authorisation to start work (this file: evidence, decision, overlap, tenant mode, class);
 * (2) publish eligibility, evaluated after QA by the content workflow (grounding, ClaimsGate, SEO QA, duplicates, publish
 * target, audit event, rollback information). Authorisation alone never publishes anything.
 */
export const POLICY_ID = 'sanocea-autonomy-policy';
export const POLICY_VERSION = '1.0.0';
export const POLICY_REF = `${POLICY_ID}@${POLICY_VERSION}`;
export const AUTONOMOUS_ACTOR = `autonomous:${POLICY_REF}`;

export const AUTONOMY_MODES = ['AUTONOMY_DISABLED', 'RECOMMEND_ONLY', 'AUTONOMOUS_SEO', 'AUTONOMOUS_CONTENT', 'AUTONOMOUS_DISTRIBUTION'] as const;
export type AutonomyMode = typeof AUTONOMY_MODES[number];
export const DEFAULT_MODE: AutonomyMode = 'RECOMMEND_ONLY';
export type ActionClass = 'A' | 'B' | 'C' | 'D';

/** Class A: low-risk SEO maintenance. Never distribution, never delivery/infrastructure changes. */
export const CLASS_A: ReadonlySet<string> = new Set(['UPDATE_TITLE_META', 'ADD_INTERNAL_LINK', 'UPDATE_SCHEMA', 'FIX_SITEMAP_ENTRY']);
/** Class B: substantive website content or search behaviour; autonomous only if every publish gate passes. */
export const CLASS_B: ReadonlySet<string> = new Set(['CREATE_SEO_PAGE', 'CREATE_SUPPORTING_CONTENT', 'UPDATE_EXISTING_PAGE', 'CHANGE_CANONICAL', 'CHANGE_INDEXABILITY']);
/** Class D: external distribution (publication outside the website). */
export const CLASS_D: ReadonlySet<string> = new Set(['DISTRIBUTE_EXISTING_CONTENT', 'PUBLISH_SOCIAL_DERIVATIVE', 'OTHER_EXTERNAL_CHANNEL_PUBLICATION']);
/** Class C: prohibited autonomously. Listed for documentation; anything unlisted (including the retired FIX_TECHNICAL_SEO) is also C. */
export const CLASS_C_PROHIBITED: ReadonlySet<string> = new Set([
  'CHANGE_REDIRECT', 'CHANGE_SERVER_RENDERING', 'CHANGE_DNS', 'CHANGE_DOMAIN_OWNERSHIP', 'CHANGE_CREDENTIALS', 'CHANGE_ACCESS', 'CHANGE_SECURITY',
  'CHANGE_PAYMENT', 'DESTRUCTIVE_DATABASE', 'CHANGE_INFRASTRUCTURE', 'DELETE_PAGE', 'DELETE_DATA', 'OUT_OF_SCOPE', 'INVESTIGATE'
]);

export function classifyAction(action: string): ActionClass {
  if (CLASS_C_PROHIBITED.has(action)) return 'C';
  if (CLASS_A.has(action)) return 'A';
  if (CLASS_B.has(action)) return 'B';
  if (CLASS_D.has(action)) return 'D';
  return 'C'; // unknown => fail closed
}

export function isAutonomyMode(m: string): m is AutonomyMode { return (AUTONOMY_MODES as readonly string[]).includes(m); }

/** Matrix: DISABLED/RECOMMEND_ONLY nothing; SEO = A; CONTENT = A+B; DISTRIBUTION = A+B+D. No mode authorises C. */
export function modeAllows(mode: AutonomyMode, cls: ActionClass, action: string): { allowed: boolean; reason: string } {
  if (cls === 'C') return { allowed: false, reason: `Class C action (${action}) requires explicit human authorisation in every mode.` };
  if (mode === 'AUTONOMY_DISABLED') return { allowed: false, reason: 'Autonomy is disabled for this tenant.' };
  if (mode === 'RECOMMEND_ONLY') return { allowed: false, reason: 'This tenant is recommend-only: SANOCEA proposes, it does not authorise.' };
  if (cls === 'A') return { allowed: true, reason: `Class A action permitted in ${mode}.` };
  if (cls === 'B') return mode === 'AUTONOMOUS_SEO'
    ? { allowed: false, reason: 'Class B (substantive content or search behaviour) needs mode AUTONOMOUS_CONTENT or higher.' }
    : { allowed: true, reason: `Class B action permitted in ${mode}; publication still requires every publish gate.` };
  return mode === 'AUTONOMOUS_DISTRIBUTION'
    ? { allowed: true, reason: `Class D (external distribution) permitted in ${mode}.` }
    : { allowed: false, reason: `Class D (external distribution) needs mode AUTONOMOUS_DISTRIBUTION (tenant mode is ${mode}).` };
}

export interface Gate { gate: string; passed: boolean; detail: string }
export interface AuthorizationDecision {
  allowed: boolean; actionClass: ActionClass; action: string; mode: AutonomyMode; policy: string; gates: Gate[]; reason: string;
}
export interface PolicyOpportunity {
  status: string; type: string; source: string; target: string; recommendedAction: string;
  evidence: Record<string, unknown>; decision: { action?: string; rationale?: string; checks?: string[]; requiresApproval?: boolean };
}

/** Pure, deterministic. Evaluated only for an opportunity awaiting authorisation. */
export function evaluateAuthorization(mode: AutonomyMode, o: PolicyOpportunity): AuthorizationDecision {
  const action = o.decision?.action ?? o.recommendedAction;
  const cls = classifyAction(action);
  const gates: Gate[] = [];
  gates.push({ gate: 'awaiting_authorization', passed: o.status === 'AWAITING_APPROVAL', detail: `status is ${o.status}` });
  gates.push({ gate: 'evidence_backed_opportunity', passed: Object.keys(o.evidence ?? {}).length > 0 && !!o.source, detail: o.source ? `source ${o.source}` : 'no evidence source' });
  const decisionOk = !!o.decision?.rationale && action === o.recommendedAction && Array.isArray(o.decision.checks) && o.decision.checks.length > 0;
  gates.push({ gate: 'valid_decision', passed: decisionOk, detail: decisionOk ? `action ${action} with recorded rationale and checks` : 'decision missing rationale/checks or disagrees with the recommended action' });
  const overlap = o.type === 'QUERY_PAGE_MATCH_GAP' && action === 'CREATE_SEO_PAGE' ? Number(o.evidence?.bestMatchOverlap ?? 1) : null;
  gates.push({ gate: 'no_page_overlap', passed: overlap === null || overlap < 0.5, detail: overlap === null ? 'not a new-page opportunity' : `best existing page overlaps ${(overlap * 100).toFixed(0)}% of the query (limit 50%)` });
  const m = modeAllows(mode, cls, action);
  gates.push({ gate: 'tenant_authorization', passed: m.allowed, detail: m.reason });
  const allowed = gates.every(g => g.passed);
  const failed = gates.filter(g => !g.passed).map(g => g.gate);
  return { allowed, actionClass: cls, action, mode, policy: POLICY_REF, gates, reason: allowed ? `All authorisation gates passed under ${POLICY_REF}: ${m.reason}` : `Not authorised (${failed.join(', ')}): ${gates.find(g => !g.passed)!.detail}` };
}
