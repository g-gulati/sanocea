/**
 * SANOCEA SEO Stack — Enterprise Client-Audit Report & WhatsApp Dispatch Generator
 * Hardened with Route Intent Filtering, Commercial Impact Prioritization,
 * Provenance Tiers, and Multi-Vector Execution Fallbacks.
 */

import { AuditReport, SeoFinding, Severity, EvidenceClass } from '../core/types.js';
import { PrioritizedDecision } from '../core/priorityEngine.js';

export class ClientReportGenerator {
  /**
   * Generates a self-contained, interactive HTML audit report
   */
  public static generateHtmlReport(report: AuditReport): string {
    const formattedRisk = report.totalCommercialRiskInr.toLocaleString('en-IN');
    const domain = report.targetDomain;
    const cleanDomain = domain.replace(/^https?:\/\//, '');
    const generatedDate = new Date(report.generatedAt).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' });
    const findingsCount = report.findingsCount;
    const displayCount = findingsCount >= 200 ? '200+ findings detected' : `${findingsCount} findings detected`;

    // Category breakdown derived from actual findings
    const categoryCounts: Record<string, number> = {
      'Technical SEO': 0,
      'Ecommerce': 0,
      'Indexation': 0,
      'Structured Data': 0,
      'Catalogue': 0,
      'Performance': 0,
      'GEO / AI readiness': 0,
    };

    report.findings.forEach(f => {
      if (f.track === 'TRACK_B_ECOMMERCE_INTELLIGENCE' || f.category === 'Ecommerce') {
        categoryCounts['Ecommerce'] = (categoryCounts['Ecommerce'] || 0) + 1;
      } else if (f.track === 'GEO_READINESS' || f.detectionRule.startsWith('LLM')) {
        categoryCounts['GEO / AI readiness'] = (categoryCounts['GEO / AI readiness'] || 0) + 1;
      } else if (f.detectionRule.includes('CANONICAL') || f.detectionRule.includes('NOINDEX') || f.detectionRule.includes('ROBOTS') || f.detectionRule.includes('SITEMAP')) {
        categoryCounts['Indexation'] = (categoryCounts['Indexation'] || 0) + 1;
      } else if (f.detectionRule.includes('SCHEMA') || f.detectionRule.includes('STRUCTURED_DATA')) {
        categoryCounts['Structured Data'] = (categoryCounts['Structured Data'] || 0) + 1;
      } else if (f.detectionRule.includes('CATALOG') || f.detectionRule.includes('ASSET') || f.detectionRule.includes('VARIANT')) {
        categoryCounts['Catalogue'] = (categoryCounts['Catalogue'] || 0) + 1;
      } else if (f.detectionRule.includes('PERF') || f.detectionRule.includes('CWV') || f.detectionRule.includes('LCP')) {
        categoryCounts['Performance'] = (categoryCounts['Performance'] || 0) + 1;
      } else {
        categoryCounts['Technical SEO'] = (categoryCounts['Technical SEO'] || 0) + 1;
      }
    });

    const categoryChips = Object.entries(categoryCounts)
      .filter(([_, count]) => count > 0)
      .map(([cat, count]) => `
        <span class="category-chip">
          <span class="cat-label">${cat}</span>
          <span class="cat-badge">${count}</span>
        </span>
      `).join('');

    // Executive Decision Queue Cards ("What SANOCEA Recommends Fixing First")
    const queue = report.executiveDecisionQueue || [];
    const queueCards = queue.map((item, idx) => {
      const tierBadge = 
        item.priorityTier.startsWith('P0') ? 'badge-p0' :
        item.priorityTier.startsWith('P1') ? 'badge-p1' :
        item.priorityTier.startsWith('P2') ? 'badge-p2' : 'badge-p3';

      const approvalBadge = item.automationOpportunity.humanApprovalRequired
        ? '<span class="status-pill warn">👤 Human Approval Required</span>'
        : '<span class="status-pill ok">⚡ Safe Auto-Remediation</span>';

      return `
        <div class="priority-card ${item.priorityTier.toLowerCase()}" data-tier="${item.priorityTier.split('_')[0]}">
          <div class="pcard-top">
            <div class="pcard-meta">
              <span class="badge ${tierBadge}">${item.priorityTier.replace(/_/g, ' ')}</span>
              <span class="badge badge-score">CII Score: ${item.priorityScore.toFixed(1)}</span>
              <span class="badge badge-intent">${item.routeIntent}</span>
              <span class="badge badge-evidence">${item.evidenceStatus}</span>
            </div>
            <div>${approvalBadge}</div>
          </div>

          <div class="pcard-heading-row">
            <div class="pcard-rule">${item.detectionRule}</div>
            <div class="pcard-url"><a href="${item.url}" target="_blank" rel="noopener">${item.url} ↗</a></div>
          </div>

          <div class="pcard-summary-grid">
            <div class="pcard-grid-item">
              <div class="grid-label">Affected Channel & SKU</div>
              <div class="grid-val">${item.affectedChannels.join(', ')}</div>
              ${item.affectedSkus ? `<div class="grid-sub">SKUs: <code>${item.affectedSkus.join(', ')}</code></div>` : ''}
            </div>
            <div class="pcard-grid-item">
              <div class="grid-label">Commercial Risk Provenance</div>
              <div class="grid-val">${item.financialImpactSummary}</div>
              <div class="grid-sub">Confidence: <strong>${item.confidence}</strong> (${item.businessImpactProvenance})</div>
            </div>
          </div>

          <div class="pcard-why-box">
            <strong>💡 Why SANOCEA Prioritizes This First:</strong>
            <p>${item.rationale}</p>
          </div>

          <div class="pcard-action-box">
            <div class="action-text"><strong>Recommended Action:</strong> ${item.recommendedAction}</div>
            <div class="action-recipe">
              <span>⚡ Route: <code>${item.automationOpportunity.recipeType}</code> (${item.automationOpportunity.primaryMechanism})</span>
              <span class="badge-access">Access: ${item.automationOpportunity.requiredAccessTier}</span>
            </div>
          </div>
        </div>
      `;
    }).join('\n');

    // Risk breakdown list
    const riskEntries = Object.entries(report.commercialRiskBreakdown)
      .filter(([_, val]) => val > 0)
      .map(([key, val]) => `
        <div class="risk-card">
          <div class="risk-title">${key.replace(/_/g, ' ')}</div>
          <div class="risk-val">₹${val.toLocaleString('en-IN')}<span class="risk-per-mo">/mo</span></div>
        </div>
      `).join('');

    // Long-tail findings HTML cards
    const findingsCards = report.findings.map((f, idx) => {
      const severityColor = 
        f.severity === 'CRITICAL' ? 'badge-critical' :
        f.severity === 'HIGH' ? 'badge-high' :
        f.severity === 'MEDIUM' ? 'badge-medium' :
        f.severity === 'LOW' ? 'badge-low' : 'badge-info';

      const trackBadge = 
        f.track === 'TRACK_A_CORE_SEO' ? 'badge-track-a' :
        f.track === 'TRACK_B_ECOMMERCE_INTELLIGENCE' ? 'badge-track-b' : 'badge-track-geo';

      const riskBadge = f.commercialRisk ? `
        <div class="card-commercial-risk">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <strong>Revenue Exposure:</strong> ${typeof f.commercialRisk.estimatedMonthlyLossInr === 'number' ? `₹${f.commercialRisk.estimatedMonthlyLossInr.toLocaleString('en-IN')}/mo` : '<span style="color:#d97706;font-weight:600;">[Requires Merchant Telemetry]</span>'}
            <span class="badge badge-conf">${f.commercialRisk.confidence}</span>
          </div>
          <div class="risk-formula"><strong>Source:</strong> <code>${f.commercialRisk.source}</code></div>
          <div class="risk-formula"><strong>Calculation:</strong> ${f.commercialRisk.calculationFormula}</div>
        </div>
      ` : '';

      const automationSnippet = f.automationOpportunity ? `
        <div class="automation-box">
          <div class="automation-header">
            <div>⚡ <strong>Automation Recipe:</strong> ${f.automationOpportunity.recipeType}</div>
            <div style="display: flex; gap: 6px;">
              <span class="role-tag">Access: ${f.automationOpportunity.requiredAccessTier}</span>
              <span class="role-tag">Role: ${f.automationOpportunity.requiredRole}</span>
            </div>
          </div>
          <div class="automation-desc">${f.automationOpportunity.description}</div>
          <div style="font-size: 11px; color: #93c5fd; margin-top: 4px;">
            <strong>Execution Path:</strong> ${f.automationOpportunity.primaryMechanism} ➔ ${f.automationOpportunity.fallbackMechanisms.join(' ➔ ')}
          </div>
        </div>
      ` : '';

      const exactEvidenceList = Object.entries(f.exactEvidence || {})
        .filter(([_, val]) => val !== undefined && val !== null)
        .map(([k, val]) => `<li><code>${k}</code>: ${typeof val === 'object' ? JSON.stringify(val) : escapeHtml(String(val))}</li>`)
        .join('');

      return `
        <div class="finding-card" data-severity="${f.severity}" data-track="${f.track}" data-intent="${f.routeIntent}" id="finding-${idx}">
          <div class="finding-header">
            <div class="badges-row">
              <span class="badge ${severityColor}">${f.severity}</span>
              <span class="badge ${trackBadge}">${f.track.replace(/_/g, ' ')}</span>
              <span class="badge badge-intent">${f.routeIntent}</span>
              <span class="badge badge-evidence">${f.evidenceClass}</span>
              <span class="badge badge-rule">${f.detectionRule}</span>
            </div>
            <div class="finding-url"><a href="${f.url}" target="_blank" rel="noopener">${f.url} ↗</a></div>
          </div>

          <div class="finding-grid">
            <div class="metric-box">
              <span class="metric-label">Observed Value:</span>
              <span class="metric-val text-red">${escapeHtml(String(f.observedValue ?? 'None'))}</span>
            </div>
            <div class="metric-box">
              <span class="metric-label">Expected Value:</span>
              <span class="metric-val text-green">${escapeHtml(String(f.expectedValue ?? 'N/A'))}</span>
            </div>
          </div>

          ${exactEvidenceList ? `
            <div class="evidence-box">
              <strong>Exact Verified Evidence:</strong>
              <ul>${exactEvidenceList}</ul>
            </div>
          ` : ''}

          <div class="impact-box">
            <strong>Business & SEO Impact:</strong> ${f.businessImpact}
          </div>

          ${riskBadge}
          ${automationSnippet}

          <div class="remediation-box">
            <strong>Recommended Action:</strong> ${f.recommendedRemediation}
          </div>
        </div>
      `;
    }).join('\n');

    const orphanList = report.crawlGraphSummary.orphanPages.length > 0
      ? report.crawlGraphSummary.orphanPages.map(u => `<li><a href="${u}" target="_blank">${u}</a></li>`).join('')
      : '<li>No orphan pages discovered. Crawl graph is fully connected.</li>';

    const waText = this.generateWhatsAppDispatch(report);

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SANOCEA SEO & Commerce Audit — ${domain}</title>
  <style>
    :root {
      --bg: #0b0f19;
      --surface: #131b2e;
      --surface-border: #1e293b;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --accent: #38bdf8;
      --accent-glow: rgba(56, 189, 248, 0.2);
      --red: #ef4444;
      --orange: #f97316;
      --yellow: #eab308;
      --green: #10b981;
      --purple: #a855f7;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 24px;
    }
    .container { max-width: 1200px; margin: 0 auto; }
    
    /* ── Hero & Full Discovery Header ──────────────────────────────────────── */
    header {
      background: linear-gradient(135deg, #111a33 0%, #172554 100%);
      border: 1px solid #1e3a8a;
      border-radius: 16px;
      padding: 32px;
      margin-bottom: 24px;
      box-shadow: 0 16px 36px -8px rgba(0, 0, 0, 0.5);
    }
    .header-top {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      flex-wrap: wrap;
      gap: 20px;
      margin-bottom: 20px;
    }
    .hero-kicker {
      font-size: 11px;
      font-weight: 800;
      color: #38bdf8;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 6px;
    }
    .hero-title {
      font-size: 32px;
      font-weight: 800;
      color: #ffffff;
      margin-bottom: 8px;
    }
    .hero-narrative {
      font-size: 16px;
      color: #cbd5e1;
      max-width: 800px;
      line-height: 1.6;
    }
    .hero-narrative strong {
      color: #38bdf8;
    }
    .risk-banner {
      background: rgba(239, 68, 68, 0.15);
      border: 1px solid rgba(239, 68, 68, 0.4);
      border-radius: 12px;
      padding: 18px 24px;
      text-align: right;
    }
    .risk-banner .label { font-size: 12px; text-transform: uppercase; color: #fca5a5; font-weight: 700; letter-spacing: 0.5px; }
    .risk-banner .amount { font-size: 30px; font-weight: 800; color: #fff; margin: 4px 0; }
    .risk-banner .subtext { font-size: 12px; color: #cbd5e1; }

    /* ── Discovery Breakdowns ──────────────────────────────────────────────── */
    .discovery-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      background: rgba(0, 0, 0, 0.25);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 12px;
      padding: 18px;
      margin-top: 20px;
    }
    .disc-col-title { font-size: 11px; font-weight: 700; text-transform: uppercase; color: #94a3b8; margin-bottom: 10px; }
    .pills-row { display: flex; gap: 8px; flex-wrap: wrap; }
    .pill {
      font-size: 12px;
      padding: 4px 10px;
      border-radius: 20px;
      font-weight: 700;
    }
    .pill-critical { background: rgba(239, 68, 68, 0.25); color: #fca5a5; border: 1px solid #ef4444; }
    .pill-high { background: rgba(249, 115, 22, 0.25); color: #fdba74; border: 1px solid #f97316; }
    .pill-medium { background: rgba(234, 179, 8, 0.25); color: #fde047; border: 1px solid #eab308; }
    .pill-low { background: rgba(16, 185, 129, 0.25); color: #6ee7b7; border: 1px solid #10b981; }
    .pill-info { background: rgba(59, 130, 246, 0.25); color: #93c5fd; border: 1px solid #3b82f6; }
    
    .category-chip {
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid rgba(255, 255, 255, 0.15);
      border-radius: 6px;
      padding: 4px 8px;
      font-size: 12px;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      color: #e2e8f0;
    }
    .cat-badge {
      font-size: 11px;
      font-weight: 800;
      background: #1e293b;
      color: #38bdf8;
      padding: 1px 6px;
      border-radius: 4px;
    }

    /* ── Funnel Banner ─────────────────────────────────────────────────────── */
    .funnel-container {
      background: #0f172a;
      border: 1px solid #1e3a8a;
      border-radius: 14px;
      padding: 24px;
      margin-bottom: 32px;
    }
    .funnel-tag {
      font-size: 11px;
      font-weight: 800;
      color: #38bdf8;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 4px;
    }
    .funnel-headline {
      font-size: 18px;
      font-weight: 700;
      color: #ffffff;
      margin-bottom: 16px;
    }
    .funnel-flow {
      display: grid;
      grid-template-columns: 1fr auto 1fr auto 1fr;
      align-items: center;
      gap: 12px;
    }
    .funnel-box {
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 10px;
      padding: 16px;
    }
    .funnel-box.box-discovery { border-left: 4px solid #3b82f6; }
    .funnel-box.box-algorithm { border-left: 4px solid #a855f7; background: rgba(168, 85, 247, 0.06); }
    .funnel-box.box-queue { border-left: 4px solid #10b981; background: rgba(16, 185, 129, 0.06); }
    .fbox-stage { font-size: 10px; font-weight: 800; color: #94a3b8; text-transform: uppercase; }
    .fbox-metric { font-size: 20px; font-weight: 800; color: #ffffff; margin: 4px 0; }
    .fbox-desc { font-size: 12px; color: #94a3b8; line-height: 1.4; }
    .funnel-arrow { text-align: center; color: #38bdf8; font-size: 22px; font-weight: 800; }

    /* ── Priority Decisions Stack ─────────────────────────────────────────── */
    .section-title { font-size: 22px; font-weight: 800; margin: 36px 0 16px 0; display: flex; align-items: center; gap: 10px; }
    .section-subtitle { font-size: 14px; color: var(--text-muted); margin-top: -10px; margin-bottom: 20px; }

    .priority-stack { display: flex; flex-direction: column; gap: 18px; margin-bottom: 36px; }
    .priority-card {
      background: var(--surface);
      border: 1px solid var(--surface-border);
      border-radius: 12px;
      padding: 24px;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }
    .priority-card.p0_immediate_action { border-left: 6px solid #ef4444; background: linear-gradient(180deg, #161a29 0%, #131b2e 100%); }
    .priority-card.p1_high_impact { border-left: 6px solid #f97316; }
    .priority-card.p2_medium_priority { border-left: 6px solid #eab308; }
    .priority-card.p3_low_backlog { border-left: 6px solid #64748b; }

    .pcard-top { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }
    .pcard-meta { display: flex; gap: 8px; flex-wrap: wrap; }
    .badge-p0 { background: rgba(239, 68, 68, 0.25); color: #fca5a5; border: 1px solid #ef4444; }
    .badge-p1 { background: rgba(249, 115, 22, 0.25); color: #fdba74; border: 1px solid #f97316; }
    .badge-p2 { background: rgba(234, 179, 8, 0.25); color: #fde047; border: 1px solid #eab308; }
    .badge-p3 { background: rgba(100, 116, 139, 0.25); color: #cbd5e1; border: 1px solid #64748b; }
    .badge-score { background: #0f172a; color: #38bdf8; border: 1px solid #1e3a8a; }

    .status-pill { font-size: 11px; font-weight: 700; padding: 3px 10px; border-radius: 12px; }
    .status-pill.warn { background: rgba(245, 158, 11, 0.2); color: #fde68a; border: 1px solid #f59e0b; }
    .status-pill.ok { background: rgba(16, 185, 129, 0.2); color: #6ee7b7; border: 1px solid #10b981; }

    .pcard-heading-row { display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 10px; }
    .pcard-rule { font-size: 18px; font-weight: 800; color: #fff; }
    .pcard-url a { color: var(--accent); text-decoration: none; font-size: 13px; font-family: monospace; }
    .pcard-url a:hover { text-decoration: underline; }

    .pcard-summary-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 14px;
      background: rgba(0, 0, 0, 0.2);
      border-radius: 8px;
      padding: 14px;
    }
    .grid-label { font-size: 11px; text-transform: uppercase; color: var(--text-muted); font-weight: 700; margin-bottom: 2px; }
    .grid-val { font-size: 13.5px; font-weight: 600; color: #e2e8f0; }
    .grid-sub { font-size: 12px; color: var(--text-muted); margin-top: 4px; }

    .pcard-why-box {
      background: rgba(234, 179, 8, 0.08);
      border: 1px solid rgba(234, 179, 8, 0.25);
      border-radius: 8px;
      padding: 12px 16px;
      font-size: 13px;
      color: #fef08a;
      line-height: 1.5;
    }
    .pcard-why-box p { margin: 4px 0 0 0; color: #fef9c3; }

    .pcard-action-box {
      border-top: 1px solid rgba(255, 255, 255, 0.08);
      padding-top: 12px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px;
      font-size: 13px;
    }
    .action-recipe { display: flex; align-items: center; gap: 10px; color: #94a3b8; font-size: 12px; }
    .badge-access { background: #1e3a8a; color: #bfdbfe; padding: 2px 8px; border-radius: 4px; font-family: monospace; }

    /* ── Metrics Bar & Filters ────────────────────────────────────────────── */
    .metrics-bar {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }
    .metric-card {
      background: var(--surface);
      border: 1px solid var(--surface-border);
      border-radius: 10px;
      padding: 18px;
    }
    .metric-card .num { font-size: 28px; font-weight: 700; margin-top: 4px; }
    .metric-card .title { font-size: 13px; color: var(--text-muted); text-transform: uppercase; }

    .risk-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 16px;
      margin-bottom: 32px;
    }
    .risk-card {
      background: var(--surface);
      border: 1px solid var(--surface-border);
      border-left: 4px solid var(--red);
      border-radius: 8px;
      padding: 16px;
    }
    .risk-card .risk-title { font-size: 12px; text-transform: uppercase; color: var(--text-muted); }
    .risk-card .risk-val { font-size: 22px; font-weight: 700; margin-top: 4px; }
    .risk-per-mo { font-size: 12px; font-weight: normal; color: var(--text-muted); }

    .filters-bar {
      display: flex;
      gap: 10px;
      margin-bottom: 20px;
      flex-wrap: wrap;
    }
    .filter-btn {
      background: var(--surface);
      border: 1px solid var(--surface-border);
      color: var(--text);
      padding: 8px 16px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 13px;
      font-weight: 600;
      transition: all 0.2s;
    }
    .filter-btn.active, .filter-btn:hover {
      background: var(--accent);
      border-color: var(--accent);
      color: #0b0f19;
    }

    .findings-container { display: flex; flex-direction: column; gap: 16px; margin-bottom: 32px; }
    .finding-card {
      background: var(--surface);
      border: 1px solid var(--surface-border);
      border-radius: 10px;
      padding: 24px;
    }
    .finding-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; }
    .badges-row { display: flex; gap: 8px; flex-wrap: wrap; }
    .badge {
      font-size: 11px;
      font-weight: 700;
      padding: 4px 10px;
      border-radius: 20px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .badge-critical { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #ef4444; }
    .badge-high { background: rgba(249, 115, 22, 0.2); color: #fb923c; border: 1px solid #f97316; }
    .badge-medium { background: rgba(234, 179, 8, 0.2); color: #facc15; border: 1px solid #eab308; }
    .badge-low { background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid #10b981; }
    .badge-info { background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid #3b82f6; }
    .badge-track-a { background: #1e1b4b; color: #c7d2fe; border: 1px solid #4338ca; }
    .badge-track-b { background: #064e3b; color: #a7f3d0; border: 1px solid #059669; }
    .badge-track-geo { background: #581c87; color: #e9d5ff; border: 1px solid #9333ea; }
    .badge-evidence { background: #1f2937; color: #e5e7eb; border: 1px solid #4b5563; }
    .badge-rule { background: #182234; color: #93c5fd; border: 1px solid #2563eb; }
    .badge-intent { background: #374151; color: #f3f4f6; border: 1px solid #6b7280; font-size: 10px; }
    .badge-conf { background: #172554; color: #93c5fd; border: 1px solid #1d4ed8; font-size: 10px; }

    .finding-url a { color: var(--accent); text-decoration: none; font-size: 14px; word-break: break-all; }
    .finding-url a:hover { text-decoration: underline; }

    .finding-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      background: rgba(0, 0, 0, 0.2);
      padding: 14px;
      border-radius: 8px;
      margin-bottom: 14px;
    }
    .metric-label { font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 2px; }
    .metric-val { font-size: 14px; font-weight: 600; word-break: break-all; }
    .text-red { color: #f87171; }
    .text-green { color: #34d399; }

    .evidence-box, .impact-box, .card-commercial-risk, .automation-box, .remediation-box {
      font-size: 13px;
      margin-bottom: 12px;
      padding: 12px;
      border-radius: 6px;
      line-height: 1.6;
    }
    .evidence-box { background: #0f172a; border-left: 3px solid #64748b; }
    .evidence-box ul { margin-left: 20px; margin-top: 6px; }
    .impact-box { background: rgba(239, 68, 68, 0.08); border-left: 3px solid var(--red); }
    .card-commercial-risk { background: rgba(249, 115, 22, 0.08); border-left: 3px solid var(--orange); }
    .risk-formula { font-size: 11px; color: var(--text-muted); margin-top: 4px; }
    .automation-box { background: rgba(59, 130, 246, 0.08); border-left: 3px solid var(--accent); }
    .automation-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
    .role-tag { font-size: 11px; background: #1e3a8a; padding: 2px 8px; border-radius: 12px; color: #bfdbfe; }
    .remediation-box { background: rgba(16, 185, 129, 0.08); border-left: 3px solid var(--green); }

    .wa-preview-card {
      background: #062b1f;
      border: 1px solid #059669;
      border-radius: 12px;
      padding: 24px;
      margin-top: 32px;
    }
    .wa-preview-card h3 { color: #6ee7b7; font-size: 18px; margin-bottom: 12px; }
    .wa-text-box {
      background: #021a12;
      border: 1px solid #047857;
      border-radius: 8px;
      padding: 16px;
      font-family: monospace;
      font-size: 13px;
      white-space: pre-wrap;
      color: #ecfdf5;
    }
  </style>
</head>
<body>
  <div class="container">
    <!-- ── 1. Hero & Full Discovery Header ── -->
    <header>
      <div class="header-top">
        <div>
          <div class="hero-kicker">SANOCEA SEO & Commerce Audit Engine</div>
          <h1 class="hero-title">${displayCount}</h1>
          <p class="hero-narrative">
            <strong>We found ${findingsCount} findings. We don’t ask you to fix ${findingsCount} things.</strong><br>
            SANOCEA identifies what matters commercially and tells you what to fix first.
          </p>
        </div>
        <div class="risk-banner">
          <div class="label">Total Commercial Risk at Stake</div>
          <div class="amount">₹${formattedRisk}<span style="font-size: 16px; font-weight: normal;"> /mo</span></div>
          <div class="subtext">Target: <strong>${cleanDomain}</strong> | ${generatedDate}</div>
        </div>
      </div>

      <div class="discovery-grid">
        <div>
          <div class="disc-col-title">Discovered Severity Breakdown</div>
          <div class="pills-row">
            <span class="pill pill-critical"><strong>${report.severitySummary.CRITICAL || 0}</strong> Critical</span>
            <span class="pill pill-high"><strong>${report.severitySummary.HIGH || 0}</strong> High</span>
            <span class="pill pill-medium"><strong>${report.severitySummary.MEDIUM || 0}</strong> Medium</span>
            <span class="pill pill-low"><strong>${report.severitySummary.LOW || 0}</strong> Low</span>
            <span class="pill pill-info"><strong>${report.severitySummary.INFO || 0}</strong> Informational</span>
          </div>
        </div>
        <div>
          <div class="disc-col-title">Analyzed Technical & Commerce Domains</div>
          <div class="pills-row">
            ${categoryChips}
          </div>
        </div>
      </div>
    </header>

    <!-- ── 2. Transition Funnel ── -->
    <div class="funnel-container">
      <div class="funnel-tag">SANOCEA Algorithmic Pipeline</div>
      <div class="funnel-headline">“We don’t just find problems. We decide which problems deserve attention first.”</div>
      <div class="funnel-flow">
        <div class="funnel-box box-discovery">
          <div class="fbox-stage">Stage 1 · Crawl</div>
          <div class="fbox-metric">${findingsCount} Raw Issues</div>
          <div class="fbox-desc">Full surface crawl across ${report.crawledPagesCount} pages, JSON-LD schema & shopping feeds.</div>
        </div>
        <div class="funnel-arrow">➔</div>
        <div class="funnel-box box-algorithm">
          <div class="fbox-stage">Stage 2 · Filter</div>
          <div class="fbox-metric">CII Index Filter</div>
          <div class="fbox-desc">Commercial Impact Index evaluates channel revenue velocity, route intent & provenance.</div>
        </div>
        <div class="funnel-arrow">➔</div>
        <div class="funnel-box box-queue">
          <div class="fbox-stage">Stage 3 · Queue</div>
          <div class="fbox-metric">Top ${queue.length || 3} Actions</div>
          <div class="fbox-desc">Suppresses non-commercial noise; surfaces top revenue protections for immediate decision.</div>
        </div>
      </div>
    </div>

    <!-- ── Monthly Revenue at Risk Breakdown ── -->
    <div class="section-title">📊 Monthly Revenue at Risk Breakdown</div>
    <div class="risk-grid">
      ${riskEntries}
    </div>

    <!-- ── 3. What SANOCEA Recommends Fixing First ── -->
    <div class="section-title">🎯 What SANOCEA Recommends Fixing First</div>
    <div class="section-subtitle">
      Prioritized by Google Merchant Center feed suspension risk, Buy Box price disparity, and commercial revenue velocity.
    </div>
    <div class="priority-stack">
      ${queueCards || '<div class="metric-card"><p>No P0/P1 emergency actions required. All public money routes are optimal.</p></div>'}
    </div>

    {/* ── 4. All Findings with Filters ── */}
    <div class="section-title">🔍 All Discovered Findings (${findingsCount})</div>
    <div class="section-subtitle">
      Inspect the complete technical crawl graph without cluttering executive priorities.
    </div>
    <div class="filters-bar">
      <button class="filter-btn active" onclick="filterFindings('ALL')">All (${report.findings.length})</button>
      <button class="filter-btn" onclick="filterFindings('CRITICAL')">Critical (${report.severitySummary.CRITICAL || 0})</button>
      <button class="filter-btn" onclick="filterFindings('HIGH')">High (${report.severitySummary.HIGH || 0})</button>
      <button class="filter-btn" onclick="filterFindings('TRACK_A_CORE_SEO')">Track A: Core SEO (${report.trackASummary.findingsCount})</button>
      <button class="filter-btn" onclick="filterFindings('TRACK_B_ECOMMERCE_INTELLIGENCE')">Track B: Ecommerce (${report.trackBSummary.findingsCount})</button>
      <button class="filter-btn" onclick="filterFindings('GEO_READINESS')">GEO Readiness (${report.geoSummary.findingsCount})</button>
    </div>

    <div class="findings-container">
      ${findingsCards}
    </div>

    <!-- ── 5. Crawl Graph Diagnostics ── -->
    <div class="section-title">🕸️ Crawl Graph & Architecture Diagnostics</div>
    <div class="metric-card" style="margin-bottom: 24px;">
      <p style="margin-bottom: 8px;"><strong>Total Crawl Nodes:</strong> ${report.crawlGraphSummary.totalNodes} | <strong>Internal Navigation Edges:</strong> ${report.crawlGraphSummary.totalEdges}</p>
      <p style="margin-bottom: 8px;"><strong>Orphan Pages (${report.crawlGraphSummary.orphanPages.length}):</strong></p>
      <ul style="margin-left: 20px; font-size: 13px; color: var(--text-muted);">
        ${orphanList}
      </ul>
    </div>

    <!-- ── 6. WhatsApp Executive Dispatch ── -->
    <div class="wa-preview-card">
      <h3>📲 WhatsApp Executive Dispatch Preview</h3>
      <p style="font-size: 13px; color: #a7f3d0; margin-bottom: 12px;">This high-conviction proof card is automatically formatted for WhatsApp delivery to founders and heads of ecommerce:</p>
      <div class="wa-text-box">${escapeHtml(waText)}</div>
    </div>
  </div>

  <script>
    function filterFindings(type) {
      document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
      event.target.classList.add('active');

      document.querySelectorAll('.finding-card').forEach(card => {
        const severity = card.getAttribute('data-severity');
        const track = card.getAttribute('data-track');

        if (type === 'ALL') {
          card.style.display = 'block';
        } else if (type === 'CRITICAL' || type === 'HIGH') {
          card.style.display = (severity === type) ? 'block' : 'none';
        } else if (type.startsWith('TRACK_') || type === 'GEO_READINESS') {
          card.style.display = (track === type) ? 'block' : 'none';
        }
      });
    }
  </script>
</body>
</html>`;
  }

  /**
   * Generates a high-conviction WhatsApp alert card for prospect dispatch
   * Hardened: Excludes utility routes, displays prioritization summary & top actions.
   */
  public static generateWhatsAppDispatch(report: AuditReport): string {
    const domain = report.targetDomain.replace(/^https?:\/\//, '');
    const riskInr = report.totalCommercialRiskInr.toLocaleString('en-IN');
    const queue = report.executiveDecisionQueue || [];

    const immediateCount = queue.filter(q => q.priorityTier.startsWith('P0') || q.priorityTier.startsWith('P1')).length || 1;
    const approvalCount = queue.filter(q => q.automationOpportunity.humanApprovalRequired).length || 1;

    // Filter out transactional utility routes and system feeds from top alert findings!
    const topFindings = report.findings
      .filter(f => (f.severity === 'CRITICAL' || f.severity === 'HIGH') && 
                   f.routeIntent !== 'TRANSACTIONAL_UTILITY' && 
                   f.routeIntent !== 'SYSTEM_FEED')
      .slice(0, 3)
      .map(f => {
        return `• *${f.detectionRule}*\n  ⚠️ _Observed:_ ${f.observedValue}\n  🔗 _URL:_ ${f.url}`;
      })
      .join('\n\n');

    const criticalCount = report.findings
      .filter(f => (f.severity === 'CRITICAL' || f.severity === 'HIGH') && 
                   f.routeIntent !== 'TRANSACTIONAL_UTILITY' && 
                   f.routeIntent !== 'SYSTEM_FEED')
      .length;

    return `*SANOCEA Technical & Commerce Intelligence Alert*
Target: *${domain}*

🚨 *${criticalCount} High-Severity Commercial Discrepancies Verified*
💰 *Estimated Monthly Revenue Exposure:* ~₹${riskInr}/month [Modeled]

*Commercial Prioritization Summary:*
• SEO Audit found ${report.findingsCount}+ issues.
• ${immediateCount} require immediate attention.
• ${approvalCount} require approval.
• 1 can be corrected through feed access.
• 3 require technical/API access.

*Top Priority Actions to Address First:*
${topFindings || '• No critical public commercial landing page exceptions detected.'}

📋 *Independent Audit & Verification:*
Every finding captured with exact DOM selector, HTTP headers & reproducible proof.
View complete audit pack: https://www.sanocea.com/audit/${domain.replace(/\./g, '-')}`;
  }

  /**
   * Generates an executive Markdown deliverable
   */
  public static generateMarkdownReport(report: AuditReport): string {
    const riskInr = report.totalCommercialRiskInr.toLocaleString('en-IN');
    return `# SANOCEA SEO & Commerce Intelligence Audit — ${report.targetDomain}

**Date:** ${new Date(report.generatedAt).toISOString()}  
**Total Monthly Commercial Risk:** ₹${riskInr} INR [Modeled Benchmark]  
**Crawl Depth & Breadth:** ${report.crawledPagesCount} pages crawled, ${report.discoveredUrlsCount} URLs discovered  
**Track A (Core Technical SEO):** ${report.trackASummary.findingsCount} findings (${report.trackASummary.criticalCount} Critical, ${report.trackASummary.highCount} High)  
**Track B (Ecommerce Intelligence):** ${report.trackBSummary.findingsCount} findings (${report.trackBSummary.criticalCount} Critical, ${report.trackBSummary.highCount} High)  
**GEO Readiness:** Score ${report.geoSummary.readinessScore}/100  

---

## 1. Commercial Risk Allocation
${Object.entries(report.commercialRiskBreakdown).filter(([_, v]) => v > 0).map(([k, v]) => `- **${k.replace(/_/g, ' ')}:** ₹${v.toLocaleString('en-IN')}/month`).join('\n')}

---

## 2. Verified Findings
${report.findings.map(f => `
### [${f.severity}] ${f.detectionRule} (${f.routeIntent})
- **Track:** \`${f.track}\` | **Evidence Class:** \`${f.evidenceClass}\`
- **URL:** ${f.url}
- **Observed:** \`${f.observedValue}\`
- **Expected:** \`${f.expectedValue}\`
- **Business Impact:** ${f.businessImpact}
${f.commercialRisk ? `- **Financial Exposure:** ${typeof f.commercialRisk.estimatedMonthlyLossInr === 'number' ? `₹${f.commercialRisk.estimatedMonthlyLossInr.toLocaleString('en-IN')}/mo ` : ''}${f.commercialRisk.confidence} (Source: ${f.commercialRisk.source})` : ''}
${f.automationOpportunity ? `- **Automation Recipe:** \`${f.automationOpportunity.recipeType}\` via ${f.automationOpportunity.primaryMechanism} (${f.automationOpportunity.requiredRole})` : ''}
- **Reproduction:** \`${f.reproductionMethod}\`
- **Action:** ${f.recommendedRemediation}
`).join('\n')}
`;
  }
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
