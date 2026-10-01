import test from 'node:test'
import assert from 'node:assert/strict'
import {
  TENANT_SEO_CONFIGS,
  getTenantSeoConfig,
  getSeoAuditData,
  getHostileQuestionsForTenant,
  SANOCEA_CASE_STUDY_DATA,
} from '../src/whatsapp-demo/data/seoAuditData.js'
import {ALL_DEMO_COMPANIES, getFreshInitialState} from '../src/whatsapp-demo/operationalStore.js'
import {getCompanyOperationalData} from '../src/whatsapp-demo/data/companyData.js'

test('Tenant SEO Registry — All 5 demo companies have registered authoritative configs', () => {
  const companyIds = ['waaree', 'premium-basket', 'carzex', 'ajanta-soya', 'golden-bird-jewels']

  for (const cid of companyIds) {
    const config = getTenantSeoConfig(cid)
    assert.ok(config, `Tenant config for ${cid} must exist`)
    assert.equal(config.tenantId, cid)
    assert.ok(config.domain, `Tenant ${cid} must have a domain`)
    assert.ok(config.displayName, `Tenant ${cid} must have a displayName`)
    assert.ok(config.findingCount > 0, `Tenant ${cid} must have positive findingCount`)
    assert.ok(config.validatedCount > 0, `Tenant ${cid} must have positive validatedCount`)
    assert.ok(config.consequentialCount > 0, `Tenant ${cid} must have positive consequentialCount`)
    assert.ok(config.priorityActions > 0, `Tenant ${cid} must have priorityActions`)
    assert.ok(config.auditDataset, `Tenant ${cid} must have an auditDataset`)
    assert.ok(config.evidencePack?.urls?.length > 0, `Tenant ${cid} must have evidence URLs`)
    assert.ok(config.searchIntelligence?.targetDomain, `Tenant ${cid} must have search intelligence target domain`)
  }
})

test('Tenant SEO Registry — SANOCEA.com is registered as an explicit autonomous monitored tenant', () => {
  const config = getTenantSeoConfig('sanocea')
  assert.ok(config, 'SANOCEA tenant config must exist')
  assert.equal(config.tenantId, 'sanocea')
  assert.equal(config.domain, 'www.sanocea.com')
  assert.equal(config.mode, 'AUTONOMOUS_24_7_MONITORED')
  assert.equal(config.status, 'AUTONOMOUS_SERVICE_ACTIVE')
  // The two conflicting "SEO health" scorecards were retired (2026-10-01): no authoritative live source. Their figures
  // live in docs/case-studies/SANOCEA_SEO_INTERVENTION_2026-09_HISTORICAL.md.
  assert.equal(config.scorecard, undefined, 'SANOCEA must not carry a static SEO scorecard')

  const audit = getSeoAuditData('sanocea')
  assert.ok(audit)
  assert.equal(audit.mode, 'AUTONOMOUS_24_7_MONITORED')
  assert.equal(audit.allFindings.length, 7)
  assert.ok(audit.funnel, 'SANOCEA audit must have a funnel object')
  assert.equal(audit.funnel.steps.length, 5)
  assert.equal(audit.funnel.whatsappSummary.immediateAttention, 2)
  assert.ok(audit.priorityQueue, 'SANOCEA audit must have a priorityQueue')
  assert.equal(audit.priorityQueue.length, 2)
  assert.ok(audit.priorityQueue[0].findingTitle)
  assert.ok(audit.priorityQueue[0].priorityTier)
  assert.ok(audit.priorityQueue[0].priorityScore > 0)
  assert.ok(audit.severityBreakdown)
  assert.equal(audit.severityBreakdown.CRITICAL, 2)
  assert.ok(audit.categoryBreakdown)
  assert.equal(audit.categoryBreakdown['Technical SEO'], 2)
  assert.ok(audit.threeTruths)
  assert.ok(audit.searchAppearanceProgression?.length > 0)

  // Verify operational data and fresh initial state for SANOCEA
  const opData = getCompanyOperationalData('sanocea')
  assert.ok(opData, 'Operational data for sanocea must exist')
  assert.equal(opData.companyId, 'sanocea')
  assert.equal(opData.channels.length, 3, 'SANOCEA must have exactly 3 channels: Production Web, Google SERP, AI Crawlers')
  for (const key of ['seoHealthBaseline', 'seoHealthCurrent', 'seoHealthDelta', 'seoRelativeGain', 'issuesDetected', 'issuesRemediated', 'issuesObserving', 'latestReceipt', 'receiptVerification']) {
    assert.equal(opData.kpis[key], undefined, `SANOCEA kpis must not carry the retired static scorecard figure: ${key}`)
  }
  assert.equal(opData.urgentActions.length, 0, 'SANOCEA Dashboard operational store must contain 0 SEO urgent actions')
  assert.ok(opData.inventoryItems.length >= 1)
  assert.equal(opData.inventoryItems[0].riskLevel, 'healthy')
  assert.ok(!opData.kpis.revenueMtd, 'SANOCEA must not display conventional merchant revenueMtd')

  const freshState = getFreshInitialState('sanocea')
  assert.ok(freshState, 'getFreshInitialState for sanocea must not throw')
  assert.equal(freshState.urgentActions.length, 0, 'Fresh initial state must have 0 urgent actions for sanocea')
  assert.equal(freshState.channels.length, 3, 'Fresh initial state must have 3 channels for sanocea')
  assert.ok(freshState.kpis)

  // Verify in ALL_DEMO_COMPANIES
  const foundCompany = ALL_DEMO_COMPANIES.find(c => c.id === 'sanocea')
  assert.ok(foundCompany, 'SANOCEA must be present in ALL_DEMO_COMPANIES')
})

test('Tenant Isolation — Premium Basket has zero Waaree data leakage', () => {
  const pbConfig = getTenantSeoConfig('premium-basket')
  const pbAudit = getSeoAuditData('premium-basket')

  assert.equal(pbConfig.domain, 'thepremiumbasket.in')
  assert.equal(pbConfig.findingCount, 118)
  assert.equal(pbConfig.validatedCount, 96)
  assert.equal(pbConfig.consequentialCount, 26)
  assert.equal(pbConfig.priorityActions, 4)

  assert.equal(pbAudit.domain, 'thepremiumbasket.in')
  assert.equal(pbAudit.totalFindingsCount, 118)
  assert.equal(pbAudit.funnel.totalDiscovered, 118)
  assert.equal(pbAudit.funnel.validatedIssues, 96)
  assert.equal(pbAudit.funnel.commerciallyConsequential, 26)
  assert.equal(pbAudit.funnel.actionableCount, 4)

  // Verify all URLs in priority queue belong to thepremiumbasket
  for (const item of pbAudit.priorityQueue) {
    assert.ok(
      item.url.includes('thepremiumbasket'),
      `Priority item URL ${item.url} must belong to thepremiumbasket`
    )
    assert.ok(
      !item.url.includes('waaree.com'),
      `Priority item URL ${item.url} must not contain waaree.com`
    )
  }

  // Verify search intelligence domain
  assert.equal(pbAudit.searchIntelligence.targetDomain, 'thepremiumbasket.in')
  assert.equal(pbConfig.searchIntelligence.targetDomain, 'thepremiumbasket.in')

  // Verify evidence URLs
  for (const url of pbConfig.evidencePack.urls) {
    assert.ok(
      url.includes('thepremiumbasket'),
      `Evidence URL ${url} must belong to thepremiumbasket`
    )
    assert.ok(!url.includes('waaree.com'), `Evidence URL ${url} must not leak waaree.com`)
  }

  // Verify hostile questions
  const hostileQ = getHostileQuestionsForTenant('premium-basket')
  assert.ok(hostileQ.length >= 10, 'Hostile questions must contain at least 10 questions')
  for (const q of hostileQ) {
    if (q.evidenceUrl) {
      assert.ok(
        q.evidenceUrl.includes('thepremiumbasket'),
        `Hostile evidence URL ${q.evidenceUrl} must belong to thepremiumbasket`
      )
      assert.ok(!q.evidenceUrl.includes('waaree.com'), `Hostile evidence URL must not leak waaree.com`)
    }
  }
})

test('Tenant Isolation — Carzex has zero Waaree or Premium Basket data leakage', () => {
  const carzexConfig = getTenantSeoConfig('carzex')
  const carzexAudit = getSeoAuditData('carzex')

  assert.equal(carzexConfig.domain, 'carzex.com')
  assert.equal(carzexConfig.findingCount, 142)
  assert.equal(carzexConfig.validatedCount, 128)
  assert.equal(carzexConfig.consequentialCount, 28)
  assert.equal(carzexConfig.priorityActions, 3)

  assert.equal(carzexAudit.domain, 'carzex.com')
  assert.equal(carzexAudit.totalFindingsCount, 142)

  for (const item of carzexAudit.priorityQueue) {
    assert.ok(
      item.url.includes('carzex.com'),
      `Carzex priority item URL ${item.url} must belong to carzex.com`
    )
    assert.ok(!item.url.includes('waaree.com'))
    assert.ok(!item.url.includes('thepremiumbasket.in'))
  }
})

test('Tenant Isolation — Ajanta Soya and Golden Bird Jewels resolve isolated datasets', () => {
  const ajanta = getSeoAuditData('ajanta-soya')
  assert.equal(ajanta.domain, 'ajantasoya.com')
  assert.equal(ajanta.totalFindingsCount, 86)
  assert.equal(ajanta.funnel.commerciallyConsequential, 18)

  const golden = getSeoAuditData('golden-bird-jewels')
  assert.equal(golden.domain, 'goldenbirdjewels.com')
  assert.equal(golden.totalFindingsCount, 96)
  assert.equal(golden.funnel.commerciallyConsequential, 22)
})

test('Tenant Switching Cycle — Waaree -> Premium Basket -> Carzex -> Ajanta Soya -> Waaree', () => {
  const sequence = [
    { id: 'waaree', domain: 'shop.waaree.com', count: 214, consequential: 42, topActions: 5 },
    { id: 'premium-basket', domain: 'thepremiumbasket.in', count: 118, consequential: 26, topActions: 4 },
    { id: 'carzex', domain: 'carzex.com', count: 142, consequential: 28, topActions: 3 },
    { id: 'ajanta-soya', domain: 'ajantasoya.com', count: 86, consequential: 18, topActions: 3 },
    { id: 'golden-bird-jewels', domain: 'goldenbirdjewels.com', count: 96, consequential: 22, topActions: 4 },
    { id: 'waaree', domain: 'shop.waaree.com', count: 214, consequential: 42, topActions: 5 },
  ]

  for (const step of sequence) {
    const audit = getSeoAuditData(step.id)
    const config = getTenantSeoConfig(step.id)

    assert.equal(audit.domain, step.domain, `Step ${step.id} domain mismatch`)
    assert.equal(audit.totalFindingsCount, step.count, `Step ${step.id} count mismatch`)
    assert.equal(audit.funnel.commerciallyConsequential, step.consequential, `Step ${step.id} consequential mismatch`)
    assert.equal(audit.funnel.actionableCount, step.topActions, `Step ${step.id} topActions mismatch`)
    assert.equal(config.domain, step.domain)
    assert.equal(config.findingCount, step.count)
    assert.equal(config.consequentialCount, step.consequential)

    // Verify first priority queue item domain
    assert.ok(
      audit.priorityQueue[0].url.includes(step.domain),
      `First priority item for ${step.id} must be on domain ${step.domain}`
    )
  }
})

test('SANOCEA Case Study Invariance — Global case study remains strictly sanocea.com across tenant switches', () => {
  assert.ok(SANOCEA_CASE_STUDY_DATA.domain.includes('sanocea.com'))
  assert.ok(SANOCEA_CASE_STUDY_DATA.title.includes('SANOCEA.com'))
  assert.equal(SANOCEA_CASE_STUDY_DATA.experimentId, 'EXP-SANOCEA-CONTROLLED-001')

  // Verify that calling getSeoAuditData for each tenant does NOT mutate or alter the case study
  for (const comp of ALL_DEMO_COMPANIES) {
    const audit = getSeoAuditData(comp.id)
    assert.notEqual(audit.domain, 'sanocea.com', `Tenant ${comp.id} must not overwrite or be sanocea.com`)
    assert.ok(SANOCEA_CASE_STUDY_DATA.domain.includes('sanocea.com'))
  }
})

test('Regression 1: Dashboard contains no SANOCEA SEO case-study or audit component', async () => {
  const fs = await import('node:fs')
  const path = await import('node:path')
  const dashboardPath = path.resolve('src/whatsapp-demo/components/DashboardView.jsx')
  const dashboardContent = fs.readFileSync(dashboardPath, 'utf8')

  // Dashboard must NOT import or render SeoAuditSection or SanoceaCaseStudyView
  assert.ok(!dashboardContent.includes('SeoAuditSection'), 'DashboardView must not import or embed SeoAuditSection')
  assert.ok(!dashboardContent.includes('SanoceaCaseStudyView'), 'DashboardView must not import or embed SanoceaCaseStudyView')
  assert.ok(!dashboardContent.includes('id="seo-audit"'), 'DashboardView must not contain the seo-audit container')
})

test('Regression 2: SEO view renders the SANOCEA case study when companyId=sanocea', () => {
  const sanoceaAudit = getSeoAuditData('sanocea')
  const sanoceaConfig = getTenantSeoConfig('sanocea')

  assert.equal(sanoceaAudit.companyId, 'sanocea')
  assert.equal(sanoceaAudit.mode, 'AUTONOMOUS_24_7_MONITORED')
  assert.ok(sanoceaAudit.caseStudy, 'sanoceaAudit must have caseStudy object')
  assert.equal(sanoceaConfig.scorecard, undefined, 'sanoceaConfig must not contain a static scorecard')
  assert.equal(sanoceaConfig.status, 'AUTONOMOUS_SERVICE_ACTIVE')
})

test('Regression 3: SANOCEA SEO monitoring data never appears for prospect tenants', () => {
  const prospectTenants = ['waaree', 'premium-basket', 'carzex', 'ajanta-soya', 'golden-bird-jewels']

  for (const tid of prospectTenants) {
    const audit = getSeoAuditData(tid)
    const config = getTenantSeoConfig(tid)

    // Mode must NOT be autonomous monitored
    assert.notEqual(audit.mode, 'AUTONOMOUS_24_7_MONITORED', `Tenant ${tid} must not have autonomous monitored mode`)
    assert.notEqual(config.mode, 'AUTONOMOUS_24_7_MONITORED', `Config ${tid} must not have autonomous monitored mode`)
    assert.notEqual(config.status, 'AUTONOMOUS_SERVICE_ACTIVE', `Config ${tid} must not claim autonomous service active`)

    // Must not contain SANOCEA verification receipts
    for (const f of audit.allFindings || []) {
      if (f.remediationReceipt) {
        assert.ok(!f.remediationReceipt.startsWith('VRCP-ACT-SANOCEA'), `Tenant ${tid} finding must not have SANOCEA receipt`)
      }
    }

    // Priority queue must not reference sanocea domain
    for (const p of audit.priorityQueue || []) {
      assert.ok(!p.url.includes('sanocea.com'), `Tenant ${tid} priority queue URL must not reference sanocea.com`)
    }
  }
})

test('Regression 4: Switching Dashboard <-> SEO does not retain stale SEO state', () => {
  const p1 = getSeoAuditData('premium-basket')
  const p2 = getSeoAuditData('sanocea')
  const p3 = getSeoAuditData('waaree')

  assert.equal(p1.companyId || p1.tenantId, 'premium-basket')
  assert.equal(p2.companyId || p2.tenantId, 'sanocea')
  assert.equal(p3.companyId || p3.tenantId, 'waaree')

  // Verify that fresh calls do not mutate other tenant datasets
  assert.equal(p1.totalFindingsCount, 118)
  assert.equal(p2.totalFindingsCount, 7)
  assert.equal(p3.totalFindingsCount, 214)

  const c1 = getTenantSeoConfig('premium-basket')
  const c2 = getTenantSeoConfig('sanocea')
  const c3 = getTenantSeoConfig('waaree')
  assert.equal(c1.tenantId, 'premium-basket')
  assert.equal(c2.tenantId, 'sanocea')
  assert.equal(c3.tenantId, 'waaree')
})

test('Regression 5: Switching tenants cannot leak SEO findings between tenants', () => {
  const tenants = ['waaree', 'premium-basket', 'carzex', 'ajanta-soya', 'golden-bird-jewels', 'sanocea']
  const findingIdSets = new Map()

  for (const tid of tenants) {
    const audit = getSeoAuditData(tid)
    const ids = new Set((audit.allFindings || []).map(f => f.id || f.findingId))
    findingIdSets.set(tid, ids)
  }

  // Check every pair has zero intersection
  for (let i = 0; i < tenants.length; i++) {
    for (let j = i + 1; j < tenants.length; j++) {
      const setA = findingIdSets.get(tenants[i])
      const setB = findingIdSets.get(tenants[j])
      for (const id of setA) {
        assert.ok(!setB.has(id), `Finding ${id} leaked between ${tenants[i]} and ${tenants[j]}`)
      }
    }
  }
})

test('Regression 6: Semantic Channel Icon Mapping — Production Web !== Shopify and AI Crawlers !== Amazon', async () => {
  const {CHANNEL_LOGOS, getChannelLogo, getCompanyOperationalData} = await import('../src/whatsapp-demo/data/companyData.js')

  const sanoceaData = getCompanyOperationalData('sanocea')
  assert.ok(sanoceaData, 'SANOCEA operational data must exist')

  const prodWebChannel = sanoceaData.channels.find(c => c.id === 'production-web' || c.shortName === 'Production Web')
  assert.ok(prodWebChannel, 'Production Web channel must exist')
  assert.equal(prodWebChannel.id, 'production-web')

  const aiCrawlersChannel = sanoceaData.channels.find(c => c.id === 'ai-crawlers' || c.shortName === 'AI Crawlers')
  assert.ok(aiCrawlersChannel, 'AI Crawlers channel must exist')
  assert.equal(aiCrawlersChannel.id, 'ai-crawlers')

  const googleSerpChannel = sanoceaData.channels.find(c => c.id === 'google' || c.shortName === 'Google SERP')
  assert.ok(googleSerpChannel, 'Google SERP channel must exist')

  // Strict semantic assertions
  const prodWebLogo = getChannelLogo(prodWebChannel.id, prodWebChannel.name)
  const aiCrawlersLogo = getChannelLogo(aiCrawlersChannel.id, aiCrawlersChannel.name)
  const googleLogo = getChannelLogo(googleSerpChannel.id, googleSerpChannel.name)

  assert.notEqual(prodWebLogo, CHANNEL_LOGOS.shopify, 'Production Web must NOT have the Shopify logo')
  assert.notEqual(aiCrawlersLogo, CHANNEL_LOGOS.amazon, 'AI Crawlers must NOT have the Amazon logo')

  assert.equal(prodWebLogo, CHANNEL_LOGOS['production-web'], 'Production Web must have neutral globe logo')
  assert.equal(aiCrawlersLogo, CHANNEL_LOGOS['ai-crawlers'], 'AI Crawlers must have neutral bot logo')
  assert.equal(googleLogo, CHANNEL_LOGOS.google, 'Google SERP must have Google logo')
})

test('Regression 7: Rendered SANOCEA Dashboard has 0 SEO remediation cards', async () => {
  const fs = await import('node:fs')
  const path = await import('node:path')
  const dashboardPath = path.resolve('src/whatsapp-demo/components/DashboardView.jsx')
  const dashboardContent = fs.readFileSync(dashboardPath, 'utf8')

  // Dashboard must filter out SEO category and SEO action kinds for sanocea
  assert.ok(
    dashboardContent.includes("isSanocea && (action.category === 'SEO' || action.actionKind === 'approve-seo-fix'"),
    'DashboardView must explicitly filter out SEO actions for sanocea'
  )

  const {getCompanyOperationalData} = await import('../src/whatsapp-demo/data/companyData.js')
  const sanoceaData = getCompanyOperationalData('sanocea')
  assert.equal(sanoceaData.urgentActions.length, 0, 'SANOCEA must have 0 urgent actions in companyData')
})

test('Regression 8: Channel count consistency — SANOCEA displays 3/3 channels, not 4/4', async () => {
  const fs = await import('node:fs')
  const path = await import('node:path')
  const dashboardPath = path.resolve('src/whatsapp-demo/components/DashboardView.jsx')
  const dashboardContent = fs.readFileSync(dashboardPath, 'utf8')

  // Dashboard must NOT have hardcoded '4/4 CONNECTED'
  assert.ok(!dashboardContent.includes('>4/4 CONNECTED<'), 'DashboardView must not contain hardcoded 4/4 CONNECTED')
  assert.ok(
    dashboardContent.includes('{channels.filter(c => c.status === \'healthy\').length}/{channels.length} CONNECTED'),
    'DashboardView must use dynamic channel connected count'
  )

  const {getCompanyOperationalData} = await import('../src/whatsapp-demo/data/companyData.js')
  const sanoceaData = getCompanyOperationalData('sanocea')
  assert.equal(sanoceaData.channels.length, 3, 'SANOCEA must have exactly 3 channels (Production Web, Google Search, AI Crawlers)')
})

test('Regression 9: GSC clicks are never mislabeled as orders on SANOCEA', async () => {
  const fs = await import('node:fs')
  const path = await import('node:path')
  const dashboardPath = path.resolve('src/whatsapp-demo/components/DashboardView.jsx')
  const dashboardContent = fs.readFileSync(dashboardPath, 'utf8')

  // Dashboard must distinguish between sanocea and regular commerce order tags
  assert.ok(
    dashboardContent.includes('GSC Clicks'),
    'DashboardView must render GSC Clicks for sanocea search telemetry'
  )

  const {getCompanyOperationalData} = await import('../src/whatsapp-demo/data/companyData.js')
  const sanoceaData = getCompanyOperationalData('sanocea')
  assert.ok(!sanoceaData.kpis.ordersMtd, 'SANOCEA kpis must not define ordersMtd')
  // Live GSC and worker telemetry has ONE source (the persisted SEO worker via /demo/seo/overview). No static copy may
  // exist in the demo data, or it would silently go stale and could be shown as if it were current.
  for (const key of ['gscClicks', 'gscImpressions', 'gscCtr', 'gscAvgPosition', 'workerStatus', 'workerTiers', 'lastProbe', 'persistenceEngine']) {
    assert.equal(sanoceaData.kpis[key], undefined, `SANOCEA kpis must not carry a static copy of live telemetry: ${key}`)
  }
})

test('Regression 10: The conflicting SEO-health scorecards are gone from the Dashboard and the SEO tab', async () => {
  const fs = await import('node:fs')
  const path = await import('node:path')
  const read = (rel) => fs.readFileSync(path.resolve(rel), 'utf8')
  const dash = read('src/whatsapp-demo/components/DashboardView.jsx')
  const view = read('src/whatsapp-demo/components/SanoceaCaseStudyView.jsx')
  for (const bad of ['sanocea-scorecard-hero', 'SEO Health Scorecard', 'Baseline SEO Health', 'Current SEO Health', 'Technical Findings Lifecycle', 'Latest Verification Receipt', 'kpis.seoHealth', 'kpis.issues', 'kpis.latestReceipt']) {
    assert.ok(!dash.includes(bad), `Dashboard must not contain: ${bad}`)
  }
  for (const bad of ['cs-health-scorecard-section', 'MEASURED IMPACT', '15% ➔ 100%', 'Technical Compliance', 'scorecard.']) {
    assert.ok(!view.includes(bad), `SEO tab must not contain: ${bad}`)
  }
  const css = read('src/whatsapp-demo/commerceOps.css')
  for (const dead of ['.cs-health-scorecard-section', '.cs-scorecard-grid', '.cs-compliance-pill', '.sanocea-scorecard-hero']) assert.ok(!css.includes(dead), `dead style left behind: ${dead}`)
  const doc = read('../docs/case-studies/SANOCEA_SEO_INTERVENTION_2026-09_HISTORICAL.md')
  assert.ok(doc.includes('HISTORICAL · STATIC') && doc.includes('15.0%') && doc.includes('15% → 100%'), 'the historical evidence must be preserved in documentation, labelled historical')
  const live = view.includes('<HistoricalNotice />') ? (view.match(/<HistoricalNotice \/>/g) || []).length : 0
  assert.equal(live, 3, 'the static case-study tabs 2, 4 and 5 must each carry the historical notice')
})

test('Regression 11: Prospect tenants retain commerce operations without autonomous monitoring', async () => {
  const {getCompanyOperationalData} = await import('../src/whatsapp-demo/data/companyData.js')
  const prospectIds = ['waaree', 'premium-basket', 'carzex', 'ajanta-soya', 'golden-bird-jewels']

  for (const pid of prospectIds) {
    const data = getCompanyOperationalData(pid)
    assert.ok(data.kpis.revenueMtd, `Prospect ${pid} must retain commerce revenueMtd`)
    assert.ok(data.kpis.ordersMtd, `Prospect ${pid} must retain commerce ordersMtd`)
    assert.ok(!data.kpis.workerStatus, `Prospect ${pid} must not have autonomous workerStatus`)
  }
})

const readSrc = async (rel) => {
  const fs = await import('node:fs')
  const path = await import('node:path')
  return fs.readFileSync(path.resolve(rel), 'utf8')
}
const VIEW = 'src/whatsapp-demo/components/SanoceaCaseStudyView.jsx'
const DASH = 'src/whatsapp-demo/components/DashboardView.jsx'
const SHARED = 'src/whatsapp-demo/components/SeoShared.jsx'

test('Regression 12: Autonomous Activity Feed is built from the worker ledger, never a static fixture', async () => {
  const data = await import('../src/whatsapp-demo/data/seoAuditData.js')
  assert.equal(data.SANOCEA_AUTONOMOUS_OPERATIONS_FEED, undefined, 'no static Sanocea activity feed may exist')
  const view = await readSrc(VIEW)
  assert.ok(view.includes("view(seo.overview, 'heartbeats')") && view.includes("view(seo.overview, 'deltas')"), 'feed must come from the persisted heartbeats and detected-change ledger')
  assert.ok(view.includes('relativeAge(op.timestamp)'), 'relative times must be computed from the worker timestamp')
  assert.ok(!/relativeTime:\s*'/.test(view), 'no hard-coded relative times')
})

test('Regression 13: Activity Feed Isolation — Prospect tenants NEVER expose autonomous operations feed', () => {
  const prospectIds = ['waaree', 'premium-basket', 'carzex', 'ajanta-soya', 'golden-bird-jewels']

  for (const pid of prospectIds) {
    const config = getTenantSeoConfig(pid)
    assert.equal(
      config.liveOperationsFeed,
      undefined,
      `Prospect tenant ${pid} must NOT have liveOperationsFeed in config`
    )

    const audit = getSeoAuditData(pid)
    assert.equal(
      audit.liveOperationsFeed,
      undefined,
      `Prospect tenant ${pid} must NOT have liveOperationsFeed in auditData`
    )
  }

  // SANOCEA has no static feed either: its activity is read from the SEO worker's persisted ledger at render time
  assert.equal(getTenantSeoConfig('sanocea').liveOperationsFeed, undefined, 'SANOCEA must not carry a static liveOperationsFeed')
})

test('Regression 14: Hierarchy is preserved and the hero is driven by real worker state', async () => {
  const view = await readSrc(VIEW)
  assert.ok(view.includes('SANOCEA Autonomous SEO'), 'primary banner stays')
  assert.ok(view.includes('LIVE · Sentinel Active'), 'live badge text stays, but only when the scheduler is actually live')
  assert.ok(view.includes("sentinelStatus(seo.overview).state === 'live'"), 'badge must be derived from the scheduler view')
  assert.ok(!view.includes('Last verification 42s ago'), 'no hard-coded verification age')
  assert.ok(view.includes('SENTINEL STATUS NOT AVAILABLE'), 'badge must say so when the scheduler is not available')
  assert.ok(view.includes('showRuntimeDetails') && view.includes('System Evidence & Runtime Details'), 'runtime drawer toggle stays')
  for (const leak of ['PID 471235', '127.0.0.1', 'seo_monitoring.sqlite', '8089']) assert.ok(!view.includes(leak), `runtime drawer must not expose worker internals: ${leak}`)
  assert.ok(!view.includes('cs-health-scorecard-section'), 'the retired scorecard must not come back')
  assert.ok(view.includes('cs-live-activity-stream') && view.includes('LIVE AUTONOMOUS ACTIVITY') && view.includes('Inspect Evidence'), 'activity stream stays')
  const css = await readSrc('src/whatsapp-demo/commerceOps.css')
  assert.ok(/\.cs-operation-card \.op-title\s*\{[^}]*color:\s*#0F172A/.test(css), 'activity titles must be dark on the light card')
  assert.ok(!/^\.op-title\s*\{/m.test(css), 'no unscoped .op-title rule may exist: it leaks white text onto light cards')
})

test('Regression 15: Dashboard SEO telemetry comes from the shared loader with no fallbacks', async () => {
  const dash = await readSrc(DASH)
  assert.ok(dash.includes('LAYER 1 · OBSERVED') && dash.includes('LAYER 2 · MODELED'), 'layered structure stays')
  assert.ok(dash.includes('SEO Opportunity Model — Not GSC Observed') && dash.includes('<OpportunityModelUnavailable />'), 'Opportunity Model must render NOT AVAILABLE')
  assert.ok(!dash.includes('Target Search Query [MODELED]'), 'no modeled demand table')
  assert.ok(dash.includes('useSeoOverview(isSanocea)') && dash.includes('gscNumbers(seo.overview)'), 'must use the shared SEO data contract')
  for (const bad of ["|| '39.29%'", "|| '2.43'", "|| '28'", "|| '11'", 'kpis.gscClicks', 'kpis.gscImpressions', 'kpis.gscCtr', 'kpis.gscAvgPosition', 'PID 471235', 'Port 8089', 'Root URL (100%)', '0 open critical flaws']) {
    assert.ok(!dash.includes(bad), `Dashboard must not contain: ${bad}`)
  }
  for (const label of ['Clicks [OBSERVED]', 'Impressions [OBSERVED]', 'CTR [CALCULATED]', 'Avg Position [OBSERVED]', 'GSC Query Anonymization Active — Query-Level Attribution Unavailable [OBSERVED FACT]']) {
    assert.ok(dash.includes(label), `Dashboard must keep the label: ${label}`)
  }
  assert.ok(dash.includes('gsc.queryRows'), 'the query-row count must come from the snapshot, not literal text')
  assert.ok(!dash.includes('[HISTORICAL · STATIC]'), 'the Dashboard no longer carries any static intervention figures to label')
})

test('Regression 16: No static copy of GSC telemetry or a modeled opportunity table exists', async () => {
  const {getTenantSeoConfig} = await import('../src/whatsapp-demo/data/seoAuditData.js')
  const si = getTenantSeoConfig('sanocea').searchIntelligence
  assert.deepEqual(Object.keys(si).sort(), ['propertyUrl', 'targetDomain'], 'Sanocea searchIntelligence may hold only identifiers')
  const panel = await readSrc('src/whatsapp-demo/components/SeoSearchIntelPanel.jsx')
  assert.ok(panel.includes('GSC Query-Level Data: Withheld Under Privacy Anonymization') && panel.includes('SEO Opportunity Model — Not GSC Observed'), 'both labeled sections stay')
  assert.ok(panel.includes('<Chip label="[MODELED]" />') && panel.includes('<OpportunityModelUnavailable />'), 'modeled section must be NOT AVAILABLE')
  assert.ok(!/est\.|Est\. Monthly Demand|ecommerce operations automation/.test(panel), 'no invented demand figures')
  const shared = await readSrc(SHARED)
  assert.ok(shared.includes('no persisted opportunity-model source'), 'NOT AVAILABLE must state the reason')
})

test('Regression 17: Exact keyword SERP positions are NOT AVAILABLE unless a verified provider reports rows', async () => {
  const {getTenantSeoConfig} = await import('../src/whatsapp-demo/data/seoAuditData.js')
  assert.equal(getTenantSeoConfig('sanocea').searchIntelligence.serpTrajectories, undefined, 'no fabricated rank trajectories')
  const shared = await readSrc(SHARED)
  assert.ok(shared.includes("serpV.data.status !== 'NOT_AVAILABLE'") && shared.includes('No verified SERP provider is connected'), 'ledger must default to NOT AVAILABLE')
  assert.ok(shared.includes('rank_movement_gsc') && shared.includes('LOW SAMPLE'), 'GSC position movement with the low-sample flag must be present')
  const dash = await readSrc(DASH)
  for (const bad of ['LAYER 3 · OBSERVED [SERP PROVIDER]', 'PROVENANCE: [OBSERVED: SERP Provider]', 'DATA_FOR_SEO']) assert.ok(!dash.includes(bad), `Dashboard must not claim: ${bad}`)
  assert.ok(dash.includes('<RankMovementAndSerp'), 'Dashboard must render the shared rank-movement component')
})

test('Regression 18: Growth Constraints are explicitly editorial and carry no live-looking figures', async () => {
  const {getTenantSeoConfig} = await import('../src/whatsapp-demo/data/seoAuditData.js')
  const constraints = getTenantSeoConfig('sanocea').growthConstraints
  assert.equal(constraints.length, 4)
  assert.deepEqual(constraints.map((c) => c.classification), ['OBSERVED / STRUCTURAL GAP', 'CAPABILITY GAP', 'DATA GAP / REQUIRES DATA', 'PARTIALLY OBSERVED'])
  for (const c of constraints) {
    assert.ok(!/\b\d+\s*\/\s*\d+\b|100%|HTTP 200/.test(c.evidence), `${c.id} evidence must not embed figures that can drift from telemetry`)
  }
  assert.ok(constraints[2].evidence.includes('cannot be asserted without an authoritative backlink dataset'))
  assert.ok(constraints[3].evidence.includes('XML sitemap ping was deprecated by Google in 2023'))
  const shared = await readSrc(SHARED)
  assert.ok(shared.includes('[EDITORIAL · STATIC]'), 'editorial label required')
  const dash = await readSrc(DASH)
  assert.ok(dash.includes('<GrowthConstraintsEditorial'), 'Dashboard must render the shared constraints component')
  const view = await readSrc('src/whatsapp-demo/components/SeoSearchIntelPanel.jsx')
  assert.ok(view.includes('<GrowthConstraintsEditorial'), 'SEO tab must render the shared constraints component')
})

test('Regression 19: ONE shared SEO data contract: only the store fetches, nothing else calls the bridge', async () => {
  const fs = await import('node:fs')
  const path = await import('node:path')
  const walk = (d) => fs.readdirSync(d, {withFileTypes: true}).flatMap((e) => (e.isDirectory() ? walk(path.join(d, e.name)) : [path.join(d, e.name)]))
  const files = walk(path.resolve('src')).filter((f) => /\.(js|jsx)$/.test(f))
  const callers = files.filter((f) => fs.readFileSync(f, 'utf8').includes('/demo/seo/overview')).map((f) => path.basename(f))
  assert.deepEqual(callers, ['seoOverview.js'], 'only seoOverview.js may reference the bridge route')
  const importers = files.filter((f) => /import\s*\{[^}]*fetchSeoOverview[^}]*\}/.test(fs.readFileSync(f, 'utf8'))).map((f) => path.basename(f)).sort()
  assert.deepEqual(importers, ['useSeoOverview.js'], 'only the shared store may call fetchSeoOverview')
})
