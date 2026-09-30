#!/usr/bin/env node
/**
 * SANOCEA SEO Stack — CLI Runner
 * Phase 3: Commercial Client-Audit & Dual-Track Intelligence Engine
 */

import * as fs from 'fs';
import { SeoAuditPipeline } from './pipeline/auditPipeline.js';
import { ClientReportGenerator } from './reporting/clientReportGenerator.js';
import { SANOCEA_BASELINE_HTML, SANOCEA_ROBOTS_TXT } from './fixtures/sanoceaFixtures.js';

async function main() {
  const args = process.argv.slice(2);
  const command = args[0] || 'fixture';

  if (command === 'fixture') {
    console.log('── Running SANOCEA SEO Stack on Sanocea.com Baseline Fixture ──\n');

    const pipeline = new SeoAuditPipeline({
      seedUrl: 'https://www.sanocea.com/',
      maxPages: 5,
      maxDepth: 2,
      allowSubdomains: false,
      enableJsRendering: true,
      customRobotsTxt: SANOCEA_ROBOTS_TXT
    }, async () => SANOCEA_BASELINE_HTML);

    const report = await pipeline.runAudit();

    console.log(`Audit Target: ${report.targetDomain}`);
    console.log(`Generated At: ${report.generatedAt}`);
    console.log(`Pages Crawled: ${report.crawledPagesCount}`);
    console.log(`Total Monthly Commercial Risk: ₹${report.totalCommercialRiskInr.toLocaleString('en-IN')}`);
    console.log(`Track A (Core SEO): ${report.trackASummary.findingsCount} findings`);
    console.log(`Track B (Commerce Intel): ${report.trackBSummary.findingsCount} findings`);
    console.log(`Total Findings: ${report.findingsCount}`);
    
    console.log('\n── Severity Breakdown ──');
    console.table(report.severitySummary);

    console.log('\n── Commercial Risk Breakdown ──');
    console.table(report.commercialRiskBreakdown);

    console.log('\n── WhatsApp Dispatch Alert Preview ──');
    console.log(ClientReportGenerator.generateWhatsAppDispatch(report));
  } else if (command === 'audit') {
    const targetUrl = args[1] || 'https://www.sanocea.com/';
    const htmlFlag = args.find(a => a.startsWith('--html='));
    const jsonFlag = args.find(a => a.startsWith('--json='));
    const waFlag = args.find(a => a.startsWith('--wa='));

    console.log(`Running live dual-track audit against ${targetUrl}...`);
    const pipeline = new SeoAuditPipeline({
      seedUrl: targetUrl,
      maxPages: 15,
      maxDepth: 2,
      allowSubdomains: false,
      enableJsRendering: false
    });
    const report = await pipeline.runAudit();

    console.log(`\nAudit Target: ${report.targetDomain}`);
    console.log(`Total Commercial Risk: ₹${report.totalCommercialRiskInr.toLocaleString('en-IN')}/mo`);
    console.log(`Findings: ${report.findingsCount} (Track A: ${report.trackASummary.findingsCount}, Track B: ${report.trackBSummary.findingsCount})`);

    if (htmlFlag) {
      const htmlPath = htmlFlag.split('=')[1];
      const htmlContent = ClientReportGenerator.generateHtmlReport(report);
      fs.writeFileSync(htmlPath, htmlContent, 'utf-8');
      console.log(`HTML report written to: ${htmlPath}`);
    }

    if (jsonFlag) {
      const jsonPath = jsonFlag.split('=')[1];
      fs.writeFileSync(jsonPath, JSON.stringify(report, null, 2), 'utf-8');
      console.log(`JSON report written to: ${jsonPath}`);
    }

    if (waFlag) {
      const waPath = waFlag.split('=')[1];
      const waText = ClientReportGenerator.generateWhatsAppDispatch(report);
      fs.writeFileSync(waPath, waText, 'utf-8');
      console.log(`WhatsApp dispatch written to: ${waPath}`);
    }

    if (!htmlFlag && !jsonFlag && !waFlag) {
      console.log('\n── WhatsApp Dispatch Alert ──');
      console.log(ClientReportGenerator.generateWhatsAppDispatch(report));
    }
  } else {
    console.log('Usage: node dist/src/cli.js [fixture|audit] [url] [--html=out.html] [--json=out.json] [--wa=out.txt]');
  }
}

main().catch(err => {
  console.error('Fatal CLI Error:', err);
  process.exit(1);
});
