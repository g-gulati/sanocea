/**
 * Authorisation for the worker's few MUTATING control endpoints (opportunity transitions / result links).
 *
 * The worker listens on loopback with no user authentication, so a mutation must prove it comes from the process that
 * holds the control token (SEO_WORKER_CONTROL_TOKEN). With no token configured every mutation is refused (fail closed).
 * This gates WHICH PROCESS may write; "who is the human" is still an actor label set by the caller. A real
 * operator-authenticated approval endpoint is a prerequisite before approvals are exposed in any UI.
 */
import { timingSafeEqual } from 'node:crypto';

export function controlAuthorized(presented: string | undefined, configured: string | undefined): boolean {
  if (!configured || configured.length < 16) return false;
  if (!presented) return false;
  const a = Buffer.from(presented); const b = Buffer.from(configured);
  return a.length === b.length && timingSafeEqual(a, b);
}
