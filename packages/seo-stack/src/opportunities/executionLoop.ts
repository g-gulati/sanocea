/**
 * Execution loop: APPROVED -> execute (Python publisher) -> COMPLETED -> re-observe -> verify -> LEARN | ROLLBACK | INVESTIGATE.
 *
 * It never decides whether work is permitted (the autonomy policy already authorised it; the publisher re-checks eligibility) and
 * never marks anything done on the publisher's say-so: a change counts as verified only when freshly re-observed facts meet the
 * plan's expected outcome (verifyOutcome). Everything is audited as opportunity events by `agent:executor` / `agent:verification`.
 *
 * Crash-safe: IN_PROGRESS without a linked result is resumed through the publisher's idempotency (it returns the existing
 * publication, never a second one). Unobservable live state defers the verdict; it is never read as success or failure.
 */
import { OpportunityEngine, Opportunity } from './opportunityEngine.js';
import { ExecutorBridge } from './executorBridge.js';
import { classifyAction, modeAllows } from './autonomyPolicy.js';

export const EXECUTABLE_ACTIONS: ReadonlySet<string> = new Set(['FIX_SITEMAP_ENTRY']);
export const EXECUTOR_ACTOR = 'agent:executor';
const VERIFIER = 'agent:verification';

export interface ExecutionSummary { executed: number; blocked: number; verified: number; rolledBack: number; deferred: number; errors: number }

export class ExecutionLoop {
  constructor(private engine: OpportunityEngine, private bridge: ExecutorBridge | null,
    private opts: { settleAfterMs?: number; maxDeferrals?: number } = {}) {}

  public get configured(): boolean { return this.bridge !== null; }

  public async run(tenantId: string, now = new Date()): Promise<ExecutionSummary> {
    const sum: ExecutionSummary = { executed: 0, blocked: 0, verified: 0, rolledBack: 0, deferred: 0, errors: 0 };
    if (!this.bridge) return sum;
    for (const o of this.engine.list(tenantId).opportunities) {
      try {
        const action = o.decision?.action ?? o.recommendedAction;
        if (o.status === 'APPROVED' || o.status === 'IN_PROGRESS') { if (!this.policyPermits(tenantId, o, action)) continue; }
        if ((o.status === 'APPROVED' || (o.status === 'IN_PROGRESS' && !o.resultingAction)) && o.approval && EXECUTABLE_ACTIONS.has(action)) await this.executeOne(tenantId, o, sum, now);
        else if ((o.status === 'COMPLETED' || o.status === 'MEASURING') && o.resultingAction?.startsWith('change:')) await this.verifyOne(tenantId, o, sum, now);
      } catch (e: any) {
        sum.errors++;
        this.note(tenantId, o, EXECUTOR_ACTOR, `EXECUTION_ERROR: ${String(e?.message ?? e).slice(0, 200)}`, now);
      }
    }
    return sum;
  }

  /**
   * Last line of defence before anything is handed to the publisher: the action must be one this loop supports, must not be
   * Class C, the standing approval must be for exactly this action, and (for an autonomous approval) the tenant's CURRENT mode
   * must still permit its class. A mode lowered after approval therefore stops execution.
   */
  public policyPermits(tenantId: string, o: Opportunity, action: string): boolean {
    if (!EXECUTABLE_ACTIONS.has(action)) return false; // everything else stays with the policy/human path; this loop does not touch it
    const cls = classifyAction(action);
    let reason: string | null = null;
    if (cls === 'C' || cls === 'D') reason = `class ${cls} actions are never executed by this loop`;
    else if (!o.approval) reason = 'no standing approval';
    else if (o.approval.approvedAction !== action) reason = `approval is for ${o.approval.approvedAction}, not ${action}`;
    else if (o.approval.actorType === 'AUTONOMOUS_AGENT') { const m = modeAllows(this.engine.getAutonomyMode(tenantId), cls, action); if (!m.allowed) reason = `the tenant mode no longer permits it: ${m.reason}`; }
    if (reason) this.note(tenantId, o, EXECUTOR_ACTOR, `EXECUTION_NOT_PERMITTED: ${reason}`, new Date());
    return reason === null;
  }

  /** One audit event per distinct note: a condition that persists across passes is recorded once, not every 15 minutes. */
  private note(tenantId: string, o: Opportunity, actor: string, text: string, now: Date): void {
    if (this.engine.history(tenantId, o.opportunityId).some(e => e.note === text)) return;
    this.engine.annotate(tenantId, o.opportunityId, actor, text, now.toISOString());
  }

  private async executeOne(tenantId: string, o: Opportunity, sum: ExecutionSummary, now: Date): Promise<void> {
    const payload = { tenant_id: tenantId, opportunity_id: o.opportunityId }; // approval, status and mode are read by the executor from the worker's own state, never from this request
    // Phase 1: every gate, no side effects. Work only starts (IN_PROGRESS) when publication is actually eligible.
    const dry = await this.bridge!.run({ command: 'execute', dry_run: true, ...payload });
    if (dry.status !== 'ELIGIBLE' && dry.status !== 'ALREADY_PUBLISHED') {
      const why = dry.status === 'BLOCKED' ? `BLOCKED (${(dry.blocked_by ?? []).join(', ')}): ${dry.reason ?? ''}` : `${dry.status}: ${dry.reason ?? ''}`;
      this.note(tenantId, o, EXECUTOR_ACTOR, `EXECUTION_${why}`.slice(0, 600), now);
      dry.status === 'BLOCKED' ? sum.blocked++ : sum.errors++;
      return;
    }
    if (o.status === 'APPROVED') this.engine.transition(tenantId, o.opportunityId, 'IN_PROGRESS', EXECUTOR_ACTOR, 'Eligibility confirmed; publishing', now.toISOString());
    const res = dry.status === 'ALREADY_PUBLISHED' ? dry : await this.bridge!.run({ command: 'execute', ...payload });
    if ((res.status !== 'PUBLISHED' && res.status !== 'ALREADY_PUBLISHED') || !res.change_id) {
      this.note(tenantId, o, EXECUTOR_ACTOR, `EXECUTION_${res.status}: ${res.reason ?? (res.blocked_by ?? []).join(', ')}`.slice(0, 600), now); // stays IN_PROGRESS; resumed next pass
      sum.errors++;
      return;
    }
    const r = res.receipt ?? {};
    this.engine.transition(tenantId, o.opportunityId, 'COMPLETED', EXECUTOR_ACTOR,
      `EXECUTED ${r.action ?? 'change'}: release ${r.previous_release ?? '?'} -> ${r.new_release ?? '?'}; ${(r.changed_files ?? []).map((c: any) => c.path).join(', ')}; source ${res.source_sync?.commit ? `committed ${String(res.source_sync.commit).slice(0, 8)}` : 'synced'}`, now.toISOString());
    this.engine.linkResult(tenantId, o.opportunityId, `change:${res.change_id}`, EXECUTOR_ACTOR, now.toISOString());
    sum.executed++;
    await this.verifyOne(tenantId, this.engine.get(tenantId, o.opportunityId)!, sum, now); // re-observe immediately: the receipt is never proof
  }

  private async verifyOne(tenantId: string, o: Opportunity, sum: ExecutionSummary, now: Date): Promise<void> {
    const hist = this.engine.history(tenantId, o.opportunityId);
    if (hist.some(e => e.note.startsWith('ROLLED_BACK') || e.note.startsWith('VERIFICATION_ABANDONED') || e.note.startsWith('ROLLBACK_UNAVAILABLE') || e.note.startsWith('VERIFICATION_INVESTIGATE'))) return;
    const mets = hist.filter(e => e.note.startsWith('VERIFICATION MET'));
    const settleAfter = this.opts.settleAfterMs ?? 24 * 3600_000;
    if (mets.length >= 2) return;
    if (mets.length === 1 && now.getTime() - Date.parse(mets[0].at) < settleAfter) return; // the second, settled re-check is not yet due
    const changeId = o.resultingAction!.slice('change:'.length);
    const sel = o.actionPlan?.candidates.find(c => c.action === o.actionPlan!.selected);
    const obs = await this.bridge!.run({ command: 'observe', tenant_id: tenantId, expected_outcome: sel?.expected_outcome ?? [] });
    if (obs.status !== 'OBSERVED' || !obs.observable) {
      const deferrals = hist.filter(e => e.note.startsWith('VERIFICATION_DEFERRED')).length;
      if (deferrals + 1 >= (this.opts.maxDeferrals ?? 6)) this.engine.annotate(tenantId, o.opportunityId, VERIFIER, `VERIFICATION_ABANDONED: the live site could not be observed after ${deferrals + 1} attempts (${(obs.unobservable ?? [obs.reason ?? obs.status]).join('; ')}); needs investigation`, now.toISOString());
      else this.engine.annotate(tenantId, o.opportunityId, VERIFIER, `VERIFICATION_DEFERRED: live site not observable (${(obs.unobservable ?? [obs.reason ?? obs.status]).join('; ')}); no verdict drawn`, now.toISOString());
      sum.deferred++;
      return;
    }
    const v = this.engine.verify(tenantId, o.opportunityId, obs.facts ?? [], true, now.toISOString());
    sum.verified++;
    if (v.status === 'MET') {
      this.engine.transition(tenantId, o.opportunityId, o.status === 'COMPLETED' ? 'MEASURING' : 'LEARNED', VERIFIER, mets.length === 0 ? 'Change verified on the live site; monitoring until the settled re-check' : 'Settled re-check met; outcome learned', now.toISOString());
    } else if (v.status === 'NOT_MET' && v.next === 'ROLLBACK') {
      const rb = await this.bridge!.run({ command: 'rollback', tenant_id: tenantId, opportunity_id: o.opportunityId, change_id: changeId });
      if (rb.status === 'ROLLED_BACK') { this.engine.annotate(tenantId, o.opportunityId, VERIFIER, `ROLLED_BACK: restored release ${rb.restored_release}; repository source ${rb.source_restored ? 'restored' : 'left as is'}. Verification contradicted the expected outcome.`, now.toISOString()); sum.rolledBack++; }
      else this.engine.annotate(tenantId, o.opportunityId, VERIFIER, `ROLLBACK_UNAVAILABLE (${rb.code ?? rb.status}): ${rb.reason ?? ''} Needs investigation.`.slice(0, 600), now.toISOString());
    } else {
      this.engine.annotate(tenantId, o.opportunityId, VERIFIER, `VERIFICATION_INVESTIGATE: ${v.reason}`, now.toISOString());
    }
  }
}
