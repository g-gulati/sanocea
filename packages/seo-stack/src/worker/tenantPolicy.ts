/**
 * SANOCEA SEO Stack — Tenant Monitoring & Remediation Policy Guard
 * 
 * STRICT ARCHITECTURAL INVARIANT:
 * Autonomous 24/7 background monitoring, automated GSC polling, and closed-loop
 * automated remediation are strictly enabled ONLY for SANOCEA.com.
 * 
 * All prospect tenants (Waaree, Carzex, Premium Basket, Ajanta Soya, Golden Bird Jewels)
 * are strictly restricted to ON-DEMAND AUDIT ONLY.
 * 
 * Attempting to run autonomous monitoring or remediation against prospect tenants
 * throws a TenantPolicyViolationError and aborts immediately.
 */

export type TenantExecutionMode = 'AUTONOMOUS_24_7_MONITORED' | 'ON_DEMAND_AUDIT_ONLY';

export interface TenantPolicy {
  tenantId: string;
  primaryDomain: string;
  mode: TenantExecutionMode;
  monitoringEnabled: boolean;
  autoRemediationEnabled: boolean;
  backgroundGscPolling: boolean;
  tier1IntervalMinutes: number; // Tier 1: Hourly lightweight probe
  tier2IntervalHours: number;   // Tier 2: Daily GSC & Feed sync
  tier3IntervalDays: number;    // Tier 3: Bi-weekly full audit
}

export class TenantPolicyViolationError extends Error {
  constructor(message: string) {
    super(`[TENANT_POLICY_VIOLATION] ${message}`);
    this.name = 'TenantPolicyViolationError';
  }
}

/**
 * Authoritative Policy Registry
 */
const AUTHORITATIVE_POLICIES: Record<string, TenantPolicy> = {
  sanocea: {
    tenantId: 'sanocea',
    primaryDomain: 'www.sanocea.com',
    mode: 'AUTONOMOUS_24_7_MONITORED',
    monitoringEnabled: true,
    autoRemediationEnabled: true,
    backgroundGscPolling: true,
    tier1IntervalMinutes: 60,
    tier2IntervalHours: 24,
    tier3IntervalDays: 14
  },
  waaree: {
    tenantId: 'waaree',
    primaryDomain: 'shop.waaree.com',
    mode: 'ON_DEMAND_AUDIT_ONLY',
    monitoringEnabled: false,
    autoRemediationEnabled: false,
    backgroundGscPolling: false,
    tier1IntervalMinutes: 0,
    tier2IntervalHours: 0,
    tier3IntervalDays: 0
  },
  carzex: {
    tenantId: 'carzex',
    primaryDomain: 'carzex.com',
    mode: 'ON_DEMAND_AUDIT_ONLY',
    monitoringEnabled: false,
    autoRemediationEnabled: false,
    backgroundGscPolling: false,
    tier1IntervalMinutes: 0,
    tier2IntervalHours: 0,
    tier3IntervalDays: 0
  },
  'premium-basket': {
    tenantId: 'premium-basket',
    primaryDomain: 'thepremiumbasket.in',
    mode: 'ON_DEMAND_AUDIT_ONLY',
    monitoringEnabled: false,
    autoRemediationEnabled: false,
    backgroundGscPolling: false,
    tier1IntervalMinutes: 0,
    tier2IntervalHours: 0,
    tier3IntervalDays: 0
  },
  'ajanta-soya': {
    tenantId: 'ajanta-soya',
    primaryDomain: 'ajantasoya.com',
    mode: 'ON_DEMAND_AUDIT_ONLY',
    monitoringEnabled: false,
    autoRemediationEnabled: false,
    backgroundGscPolling: false,
    tier1IntervalMinutes: 0,
    tier2IntervalHours: 0,
    tier3IntervalDays: 0
  },
  'golden-bird-jewels': {
    tenantId: 'golden-bird-jewels',
    primaryDomain: 'goldenbirdjewels.com',
    mode: 'ON_DEMAND_AUDIT_ONLY',
    monitoringEnabled: false,
    autoRemediationEnabled: false,
    backgroundGscPolling: false,
    tier1IntervalMinutes: 0,
    tier2IntervalHours: 0,
    tier3IntervalDays: 0
  }
};

export class TenantMonitoringPolicyManager {
  /**
   * Normalizes tenant ID
   */
  public static normalizeTenantId(id: string): string {
    const clean = (id || '').toLowerCase().trim();
    if (clean === 'sanocea' || clean.includes('sanocea.com')) return 'sanocea';
    if (clean.includes('waaree')) return 'waaree';
    if (clean.includes('carzex')) return 'carzex';
    if (clean.includes('basket') || clean.includes('premium')) return 'premium-basket';
    if (clean.includes('ajanta') || clean.includes('soya')) return 'ajanta-soya';
    if (clean.includes('golden') || clean.includes('jewel')) return 'golden-bird-jewels';
    return clean;
  }

  /**
   * Retrieves policy for tenant.
   * Any unregistered tenant defaults to strict ON_DEMAND_AUDIT_ONLY.
   */
  public static getPolicy(tenantId: string): TenantPolicy {
    const normalized = this.normalizeTenantId(tenantId);
    if (AUTHORITATIVE_POLICIES[normalized]) {
      return { ...AUTHORITATIVE_POLICIES[normalized] };
    }

    // Default safe fallback: strictly ON_DEMAND
    return {
      tenantId: normalized,
      primaryDomain: '',
      mode: 'ON_DEMAND_AUDIT_ONLY',
      monitoringEnabled: false,
      autoRemediationEnabled: false,
      backgroundGscPolling: false,
      tier1IntervalMinutes: 0,
      tier2IntervalHours: 0,
      tier3IntervalDays: 0
    };
  }

  /**
   * Checks if autonomous background monitoring is permitted
   */
  public static isMonitoringAllowed(tenantId: string): boolean {
    const policy = this.getPolicy(tenantId);
    return policy.monitoringEnabled === true && policy.tenantId === 'sanocea';
  }

  /**
   * Checks if automated remediation execution is permitted
   */
  public static isAutoRemediationAllowed(tenantId: string): boolean {
    const policy = this.getPolicy(tenantId);
    return policy.autoRemediationEnabled === true && policy.tenantId === 'sanocea';
  }

  /**
   * Enforces monitoring permission or throws
   */
  public static assertMonitoringAllowed(tenantId: string): void {
    if (!this.isMonitoringAllowed(tenantId)) {
      throw new TenantPolicyViolationError(
        `Autonomous background monitoring is strictly prohibited for tenant "${tenantId}". Only "sanocea" is authorized.`
      );
    }
  }

  /**
   * Enforces auto-remediation permission or throws
   */
  public static assertAutoRemediationAllowed(tenantId: string): void {
    if (!this.isAutoRemediationAllowed(tenantId)) {
      throw new TenantPolicyViolationError(
        `Automated remediation execution is strictly prohibited for tenant "${tenantId}". Only "sanocea" is authorized.`
      );
    }
  }

  /**
   * Returns list of all known prospect tenants
   */
  public static getProspectTenantIds(): string[] {
    return ['waaree', 'carzex', 'premium-basket', 'ajanta-soya', 'golden-bird-jewels'];
  }
}
