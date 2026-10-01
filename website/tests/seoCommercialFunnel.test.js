import test from 'node:test'
import assert from 'node:assert/strict'
import {
  PROSPECT_SEO_AUDIT_DATA,
  SANOCEA_CASE_STUDY_DATA,
  HOSTILE_AUDIT_VERIFICATION_QUESTIONS,
  getSeoAuditData
} from '../src/whatsapp-demo/data/seoAuditData.js'

test('Commercial Funnel Integrity: Dynamic Counts & 5-Step Pipeline', () => {
  const waaree = getSeoAuditData('waaree')
  assert.equal(waaree.totalFindingsCount, 214)
  assert.equal(waaree.displayCountLabel, '200+ findings detected')

  // Verify 5-step funnel counts
  const funnel = waaree.funnel
  assert.equal(funnel.totalDiscovered, 214)
  assert.equal(funnel.validatedIssues, 186)
  assert.equal(funnel.commerciallyConsequential, 42)
  assert.equal(funnel.topPriorityCount, 10)
  assert.equal(funnel.actionableCount, 5)
  assert.equal(funnel.steps.length, 5)

  // Verify steps reflect exact numbers
  assert.equal(funnel.steps[0].metric, '214 Detected')
  assert.equal(funnel.steps[1].metric, '186 Validated')
  assert.equal(funnel.steps[2].metric, '42 Consequential')
  assert.equal(funnel.steps[3].metric, 'Top 10 Priority')
  assert.equal(funnel.steps[4].metric, 'Top 5 to Fix First')

  // Verify Carzex has its own independent dynamic numbers (no hardcoding 200)
  const carzex = getSeoAuditData('carzex')
  assert.equal(carzex.totalFindingsCount, 142)
  assert.equal(carzex.displayCountLabel, '100+ findings detected')
  assert.equal(carzex.funnel.totalDiscovered, 142)
  assert.equal(carzex.funnel.validatedIssues, 128)
  assert.equal(carzex.funnel.commerciallyConsequential, 28)
  assert.equal(carzex.funnel.actionableCount, 3)
})

test('Every Prioritized Finding Must Remain Inspectable with Full Provenance, CII & Automation Feasibility', () => {
  const waaree = getSeoAuditData('waaree')
  assert.ok(waaree.priorityQueue && waaree.priorityQueue.length >= 5)

  for (const item of waaree.priorityQueue) {
    // 1. Core identifiers & URLs
    assert.ok(item.id, 'Every finding must have an ID')
    assert.ok(item.url, 'Every finding must have a target URL')
    assert.ok(item.liveEvidenceUrl || item.exactEvidence?.sourceUrl, 'Every finding must have a direct live evidence URL')
    assert.ok(item.findingTitle, 'Every finding must have a title')

    // 2. What was observed vs expected
    assert.ok(item.observed, `Finding ${item.id} must declare what was observed`)
    assert.ok(item.expected, `Finding ${item.id} must declare expected state`)

    // 3. Exact code / DOM evidence
    assert.ok(item.exactEvidence, `Finding ${item.id} must have exact evidence`)
    assert.ok(item.exactEvidence.sourceUrl, `Finding ${item.id} exact evidence must include source URL`)

    // 4. Commercial consequence & provenance tier
    assert.ok(item.businessImpact, `Finding ${item.id} must declare business impact`)
    assert.ok(
      ['[OBSERVED]', '[CALCULATED]', '[ESTIMATED]', '[REQUIRES_ACCESS]'].includes(item.provenanceTier),
      `Finding ${item.id} provenance tier must be valid: got ${item.provenanceTier}`
    )

    // 5. Explainable Commercial Impact Index (CII) breakdown
    assert.ok(item.ciiBreakdown, `Finding ${item.id} must have ciiBreakdown`)
    assert.ok(item.ciiBreakdown.wChannel, `Finding ${item.id} must declare wChannel`)
    assert.ok(item.ciiBreakdown.wRisk, `Finding ${item.id} must declare wRisk`)
    assert.ok(item.ciiBreakdown.wIntent, `Finding ${item.id} must declare wIntent`)
    assert.ok(item.ciiBreakdown.wConfidence, `Finding ${item.id} must declare wConfidence`)
    assert.ok(item.ciiBreakdown.fAccess, `Finding ${item.id} must declare fAccess`)
    assert.ok(item.ciiBreakdown.challengeDefense, `Finding ${item.id} must provide challengeDefense for CTO`)

    // 6. Automation suitability & access tier discipline
    assert.ok(item.automationSuitability, `Finding ${item.id} must declare automationSuitability`)
    assert.equal(typeof item.automationSuitability.canExecute, 'boolean')
    assert.ok(
      ['NO_ACCESS_REQUIRED', 'FEED_ONLY', 'TAG_MANAGER_ONLY', 'ADMIN_OAUTH', 'CODE_REPO'].includes(item.automationSuitability.accessTier),
      `Invalid access tier: ${item.automationSuitability.accessTier}`
    )
    assert.ok(item.automationSuitability.executionMechanism)
    assert.ok(item.automationSuitability.verificationMethod)

    // 7. Execution route & 8-step lifecycle
    assert.ok(item.executionClass, `Finding ${item.id} must declare executionClass`)
    assert.ok(item.executionPath, `Finding ${item.id} must have executionPath`)
    assert.ok(item.executionPath.detect, `Finding ${item.id} executionPath must include detect step`)
    assert.ok(item.executionPath.explain, `Finding ${item.id} executionPath must include explain step`)
    assert.ok(item.executionPath.prepare, `Finding ${item.id} executionPath must include prepare step`)
    assert.ok(item.executionPath.approve, `Finding ${item.id} executionPath must include approve step`)
    assert.ok(item.executionPath.execute, `Finding ${item.id} executionPath must include execute step`)
    assert.ok(item.executionPath.verify, `Finding ${item.id} executionPath must include verify step`)
  }
})

test('3-State Google Search Appearance Progression (Declared -> Eligible -> Surfaced)', () => {
  const waaree = getSeoAuditData('waaree')
  const progression = waaree.searchAppearanceProgression
  assert.ok(Array.isArray(progression) && progression.length >= 3)

  // 1. Verify 3 distinct states exist and are never conflated
  const states = progression.map(p => p.state)
  assert.ok(states.includes('SURFACED_IN_SERP'), 'Must represent actively surfaced state')
  assert.ok(states.includes('DECLARED_ONLY'), 'Must represent declared but disqualified state')
  assert.ok(states.includes('ELIGIBLE_UNSURFACED'), 'Must represent eligible but unsurfaced state')

  // 2. Disqualified example: Declared = true, Eligible = false, Surfaced = false
  const disqualified = progression.find(p => p.state === 'DECLARED_ONLY')
  assert.ok(disqualified)
  assert.equal(disqualified.schemaDeclared.status, true)
  assert.equal(disqualified.googleEligible.status, false)
  assert.equal(disqualified.actuallySurfaced.status, false)

  // 3. Eligible Unsurfaced example: Declared = true, Eligible = true, Surfaced = false
  const unsurfaced = progression.find(p => p.state === 'ELIGIBLE_UNSURFACED')
  assert.ok(unsurfaced)
  assert.equal(unsurfaced.schemaDeclared.status, true)
  assert.equal(unsurfaced.googleEligible.status, true)
  assert.equal(unsurfaced.actuallySurfaced.status, false)

  // 4. Surfaced example: Declared = true, Eligible = true, Surfaced = true
  const surfaced = progression.find(p => p.state === 'SURFACED_IN_SERP')
  assert.ok(surfaced)
  assert.equal(surfaced.schemaDeclared.status, true)
  assert.equal(surfaced.googleEligible.status, true)
  assert.equal(surfaced.actuallySurfaced.status, true)
})

test('SANOCEA.com Flagship Controlled Case Study: 5-Phase Progression, Pending Window, and Anti-Causality Rule', () => {
  const cs = SANOCEA_CASE_STUDY_DATA
  assert.equal(cs.domain, 'www.sanocea.com')
  assert.equal(cs.experimentId, 'EXP-SANOCEA-CONTROLLED-001')

  // Phase 1: BEFORE Technical Baseline (Hostile Audit Criteria)
  assert.ok(cs.before)
  assert.match(cs.before.technicalState.titlePixelWidth.observed, /78-character.*624px/)
  assert.equal(cs.before.technicalState.titlePixelWidth.status, 'FAILED')
  assert.match(cs.before.technicalState.metaDescriptionLength.observed, /219-character/)
  assert.match(cs.before.technicalState.ssrH1Heading.observed, /0 SSR H1/)
  assert.match(cs.before.technicalState.internalLinkGraph.observed, /0 static internal outlinks/)
  assert.match(cs.before.technicalState.securityHeaders.observed, /Missing security headers/)
  assert.match(cs.before.technicalState.llmsTxtStatus.observed, /Missing \/llms\.txt/)
  assert.match(cs.before.technicalState.crawlDiscoverability.observed, /Crawler stalled at 1 URL/)
  assert.equal(cs.before.gscBaseline.clicks, 1240)
  assert.equal(cs.before.gscBaseline.impressions, 45200)

  // Phase 2: INTERVENTION Receipt
  assert.ok(cs.intervention)
  assert.equal(cs.intervention.receiptId, 'ACT-SANOCEA-SEO-001')
  assert.equal(cs.intervention.verifiedBy, '@sanocea/seo-stack/ClosedLoopRemediator')
  assert.ok(cs.intervention.changesApplied.length >= 5)

  // Phase 3: TECHNICAL VERIFICATION Receipt
  assert.ok(cs.technicalVerification)
  assert.equal(cs.technicalVerification.status, 'CLEAN_VERIFIED')
  assert.equal(cs.technicalVerification.openFlawsCount, 0)
  assert.ok(cs.technicalVerification.assertions.length >= 5)

  // Phase 4: OBSERVATION WINDOW
  assert.ok(cs.observationWindow)
  assert.equal(cs.observationWindow.status, 'OBSERVATION_WINDOW_IN_PROGRESS')
  assert.ok(cs.observationWindow.minimumDaysRequired >= 14)

  // Phase 5: AFTER Observation Window Integrity (NO manufactured improvement)
  assert.ok(cs.after)
  assert.equal(cs.after.status, 'OBSERVATION_WINDOW_IN_PROGRESS')
  assert.equal(cs.after.gscPostDeployment.status, '[REQUIRES_ACCESS]')
  assert.equal(cs.after.gscPostDeployment.clicks, null, 'Must NOT manufacture post-deployment clicks when observation window is open')
  assert.equal(cs.after.gscPostDeployment.impressions, null, 'Must NOT manufacture post-deployment impressions when observation window is open')
  assert.equal(cs.after.gscPostDeployment.rankingImprovement, 'UNCLAIMED (Observation window in progress)')

  // Epistemological & Anti-Causality Rules
  assert.ok(cs.governance)
  assert.match(cs.governance.antiCausalityDisclaimer, /does NOT constitute single-variable causation/)
  assert.match(cs.governance.algorithmBoundaryNote, /It does not reveal Google's proprietary ranking algorithm/)
  assert.ok(cs.governance.algorithmContext.length >= 3)
})

test('The Three Different Truths: Observed, Calculated, and Requires Client Access', () => {
  const waaree = getSeoAuditData('waaree')
  const carzex = getSeoAuditData('carzex')

  for (const client of [waaree, carzex]) {
    assert.ok(client.threeTruths, 'Every prospect dataset must declare threeTruths')
    assert.ok(client.threeTruths.observed, 'Must declare observed truth')
    assert.ok(client.threeTruths.calculated, 'Must declare calculated truth')
    assert.ok(client.threeTruths.requiresAccess, 'Must declare requiresAccess truth')
    assert.equal(client.threeTruths.governanceMotto, 'Never turn an estimate into an observed business result.')

    assert.ok(client.threeTruths.observed.evidenceItems.length >= 3)
    assert.ok(client.threeTruths.calculated.evidenceItems.length >= 2)
    assert.ok(client.threeTruths.requiresAccess.evidenceItems.length >= 2)
  }
})

test('Commercial Narrative: 8-Stage Operational Decision Engine (Detect -> Verify)', () => {
  const waaree = getSeoAuditData('waaree')
  assert.ok(waaree.operationalNarrative)
  assert.match(waaree.operationalNarrative.motto, /operational decision layer/)

  const expectedStages = ['Detect', 'Validate', 'Quantify', 'Prioritise', 'Prepare', 'Approve', 'Execute', 'Verify']
  assert.equal(waaree.operationalNarrative.stages.length, 8)
  for (let i = 0; i < 8; i++) {
    assert.equal(waaree.operationalNarrative.stages[i].name, expectedStages[i])
  }

  // Verify priority items carry 8-step lifecycle
  for (const item of waaree.priorityQueue) {
    assert.ok(item.executionPath.detect)
    assert.ok(item.executionPath.validate)
    assert.ok(item.executionPath.quantify)
    assert.ok(item.executionPath.prioritise)
    assert.ok(item.executionPath.prepare)
    assert.ok(item.executionPath.approve)
    assert.ok(item.executionPath.execute)
    assert.ok(item.executionPath.verify)
  }
})

test('Waaree Live Evidence Pack: Status Discipline & Quarantine of Unverified Claims', () => {
  const waaree = getSeoAuditData('waaree')
  
  // 1. Every priority queue finding must be verified (REPRODUCED or PARTIAL or SNAPSHOT)
  for (const item of waaree.priorityQueue) {
    assert.ok(
      ['REPRODUCED', 'PARTIAL', 'SNAPSHOT'].includes(item.evidenceStatus),
      `Priority item ${item.id} must have confirmed evidence status: got ${item.evidenceStatus}`
    )
    assert.ok(item.evidenceStatusNote, `Priority item ${item.id} must cite live evidence note`)
    assert.notEqual(item.evidenceStatus, 'NOT_VERIFIABLE', 'NOT_VERIFIABLE findings must NEVER be in priorityQueue')
  }

  // 2. In allFindings, unverified claims MUST be quarantined with reason
  const quarantined = waaree.allFindings.filter(f => f.evidenceStatus === 'NOT_VERIFIABLE' || f.isQuarantined)
  assert.ok(quarantined.length >= 2, 'Must include quarantined unverified audit claims')

  for (const item of quarantined) {
    assert.equal(item.isQuarantined, true)
    assert.ok(item.quarantineReason, `Quarantined finding ${item.id} must declare quarantineReason`)
    assert.match(item.quarantineReason, /Honesty Protocol:/)
    assert.notEqual(item.tier, 'P0', 'Quarantined finding cannot be P0')
    assert.notEqual(item.tier, 'P1', 'Quarantined finding cannot be P1')
  }
})

test('Hostile Audit Verification: 10 Critical CTO Questions Answered Without Hand-Waving', () => {
  assert.equal(HOSTILE_AUDIT_VERIFICATION_QUESTIONS.length, 10)

  for (const qa of HOSTILE_AUDIT_VERIFICATION_QUESTIONS) {
    assert.ok(qa.qNumber >= 1 && qa.qNumber <= 10)
    assert.ok(qa.question, `Q${qa.qNumber} must declare question`)
    assert.ok(qa.answer, `Q${qa.qNumber} must declare rigorous answer`)
    assert.ok(qa.evidencePointers && qa.evidencePointers.length >= 2, `Q${qa.qNumber} must provide evidence pointers`)
  }

  // Q10 strictly asserts ranking improvement is not yet established
  const q10 = HOSTILE_AUDIT_VERIFICATION_QUESTIONS.find(q => q.qNumber === 10)
  assert.match(q10.answer, /Not yet established/)
  assert.match(q10.answer, /UNCLAIMED/)
})
