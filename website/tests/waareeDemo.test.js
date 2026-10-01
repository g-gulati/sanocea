import test from 'node:test'
import assert from 'node:assert/strict'
import {
  getFreshInitialState,
  resolveOperationalAction,
  resetCompanyOperationalState,
  ALL_DEMO_COMPANIES,
} from '../src/whatsapp-demo/operationalStore.js'
import {
  processWhatsAppCommand,
} from '../src/whatsapp-demo/whatsappCommandHandler.js'

test('Waaree Energies — Registration in ALL_DEMO_COMPANIES', () => {
  const waaree = ALL_DEMO_COMPANIES.find((c) => c.id === 'waaree')
  assert.ok(waaree, 'waaree must be in ALL_DEMO_COMPANIES')
  assert.equal(waaree.name, 'Waaree Energies (Solar Ecommerce)')
})

test('Waaree Energies — Fresh initial state has 5 channels, 4 urgent actions, and deep operational datasets', () => {
  const state = getFreshInitialState('waaree')
  assert.equal(state.companyId, 'waaree')
  assert.equal(state.companyName, 'Waaree Energies')

  // Verify 5 channels
  assert.equal(state.channels.length, 5)
  const channelIds = state.channels.map((c) => c.id)
  assert.ok(channelIds.includes('amazon'))
  assert.ok(channelIds.includes('flipkart'))
  assert.ok(channelIds.includes('bigcommerce'))
  assert.ok(channelIds.includes('lnt-sufin'))
  assert.ok(channelIds.includes('moglix'))

  // Verify 4 urgent actions, all pending
  assert.equal(state.urgentActions.length, 4)
  assert.equal(state.urgentActions.filter((a) => !a.resolved).length, 4)

  // Verify KPIs
  assert.equal(state.kpis.pendingApprovalsCount, 4)
  assert.equal(state.kpis.crossChannelDiscrepancies, 28)

  // Verify deep audit perspectives are present
  assert.ok(Array.isArray(state.auditedDiscrepancies))
  assert.ok(state.auditedDiscrepancies.length >= 24, 'Must have at least 24 audited discrepancies')

  assert.ok(Array.isArray(state.automationOpportunityMap))
  assert.equal(state.automationOpportunityMap.length, 10, 'Must have 10 automation opportunity areas')

  assert.ok(Array.isArray(state.automationCoverageMatrix))
  assert.equal(state.automationCoverageMatrix.length, 10, 'Must have 10 coverage matrix items')

  assert.ok(Array.isArray(state.validationRequirements))
  assert.ok(state.validationRequirements.length >= 7, 'Must have at least 7 validation items')

  // Verify strict evidentiary classes [O], [I], [V]
  const observedDiscrepancies = state.auditedDiscrepancies.filter((d) => d.class && d.class.includes('[O]'))
  const inferredDiscrepancies = state.auditedDiscrepancies.filter((d) => d.class && d.class.includes('[I]'))
  assert.ok(observedDiscrepancies.length >= 18, 'At least 18 findings must be [O] Observed')
  assert.ok(inferredDiscrepancies.length >= 2, 'Must include [I] Inferred findings')

  // All 4 urgent actions must be grounded in [O] Observed discrepancies
  state.urgentActions.forEach((action) => {
    assert.equal(action.evidenceClass, '[O] Observed', `Urgent action ${action.id} must be [O] Observed`)
  })

  // EVIDENCE PACK: must be present and have corrected counts
  assert.ok(state.evidencePack, 'evidencePack must be present in Waaree state')
  assert.equal(state.evidencePack.baseStorefront, 'https://shop.waaree.com')
  assert.ok(state.evidencePack.keyIntegrityCorrections.length >= 4, 'Must have integrity corrections from evidence pack re-test')

  // C1: must now say "3 confirmed cases" not 12+
  const c1 = state.auditedDiscrepancies.find((d) => d.id === 'C1')
  assert.ok(c1, 'C1 must exist')
  assert.ok(c1.title.includes('3 confirmed'), 'C1 title must reflect corrected 3-case count, not 12+')
  assert.equal(c1.evidenceStatus, 'REPRODUCED_PARTIAL')
  assert.ok(c1.evidenceUrl, 'C1 must have an evidenceUrl')

  // P9 and I9: must be NOT_VERIFIABLE
  const p9 = state.auditedDiscrepancies.find((d) => d.id === 'P9')
  const i9 = state.auditedDiscrepancies.find((d) => d.id === 'I9')
  assert.ok(p9, 'P9 (Flipkart price) must be present')
  assert.equal(p9.evidenceStatus, 'NOT_VERIFIABLE', 'P9 must be NOT_VERIFIABLE (item-id URL 404)')
  assert.ok(i9, 'I9 (Flipkart OOS) must be present')
  assert.equal(i9.evidenceStatus, 'NOT_VERIFIABLE', 'I9 must be NOT_VERIFIABLE (item-id URL 404)')

  // All REPRODUCED findings must have at least one evidenceUrl
  const reproducedFindings = state.auditedDiscrepancies.filter((d) =>
    d.evidenceStatus && (d.evidenceStatus === 'REPRODUCED' || d.evidenceStatus === 'REPRODUCED_LARGER')
  )
  reproducedFindings.forEach((d) => {
    assert.ok(d.evidenceUrl, `Finding ${d.id} (${d.evidenceStatus}) must have an evidenceUrl`)
  })
})

test('Waaree Energies — WhatsApp command routing: Option 1 includes evidentiary tags', () => {
  const state = getFreshInitialState('waaree')
  const res = processWhatsAppCommand('1', {
    companyData: state,
    urgentActions: state.urgentActions,
    channelStates: state.channelStates,
  })
  assert.ok(res, 'Option 1 must return a response')
  assert.equal(res.intent, 'attention')
  assert.ok(res.reply.includes('*[O] Observed*'), 'Option 1 must prefix urgent actions with evidentiary tags')
  assert.ok(res.reply.includes('3kW Hybrid Inverter') || res.reply.includes('Availability Feed Override'))
})

test('Waaree Energies — WhatsApp command routing: Automation Opportunity Map intent', () => {
  const state = getFreshInitialState('waaree')

  // Test keyword variations
  for (const cmd of ['automation', 'opportunity', 'map', 'matrix', 'show automation']) {
    const res = processWhatsAppCommand(cmd, {
      companyData: state,
      urgentActions: state.urgentActions,
      channelStates: state.channelStates,
    })
    assert.ok(res, `Command "${cmd}" should produce a response`)
    assert.equal(res.intent, 'automation')
    assert.ok(res.reply.includes('SANOCEA Automation Opportunity Map'))
    assert.ok(res.reply.includes('Catalogue & Specs'))
    assert.ok(res.reply.includes('Pricing & Parity'))
    assert.ok(res.reply.includes('Inventory & Feeds'))
  }
})

test('Waaree Energies — Dashboard approval of act-waa-01 synchronizes state and overrides availability feed', () => {
  const initial = getFreshInitialState('waaree')
  assert.equal(initial.urgentActions.filter((a) => !a.resolved).length, 4)

  const resolvedState = resolveOperationalAction(initial, 'act-waa-01', { source: 'dashboard' })

  // 1. Action is resolved with correct audit ID
  const action1 = resolvedState.urgentActions.find((a) => a.id === 'act-waa-01')
  assert.equal(action1.resolved, true)
  assert.equal(action1.resolutionAuditId, 'SAN-WAA-84021')

  // 2. Pending approvals count decrements to 3
  assert.equal(resolvedState.kpis.pendingApprovalsCount, 3)

  // 3. Inventory item stockout risk cleared and status corrected
  const invItem = resolvedState.inventoryItems.find((i) => i.sku === '3kW-HYB')
  assert.ok(invItem)
  assert.equal(invItem.status, 'OPTIMAL')
  assert.equal(invItem.riskLevel, 'healthy')
  assert.equal(invItem.revenueAtRisk, '₹0')

  // 4. Exception in exceptionsLog is resolved
  const excItem = resolvedState.exceptionsLog.find((e) => e.sku.includes('3kW-HYB') || e.sku.includes('WAA-INV-01'))
  assert.ok(excItem)
  assert.equal(excItem.status, 'RESOLVED')

  // 5. Audit event logged in streamEvents
  const auditEv = resolvedState.streamEvents.find((e) => e.detail && e.detail.includes('SAN-WAA-84021'))
  assert.ok(auditEv, 'Audit event must be logged in streamEvents')

  // 6. WhatsApp chat messages receives confirmation
  const lastMsg = resolvedState.chatMessages[resolvedState.chatMessages.length - 1]
  assert.ok(lastMsg.text.includes('SAN-WAA-84021'))
})

test('Waaree Energies — Resetting state restores pristine initial state', () => {
  const initial = getFreshInitialState('waaree')
  const modified = resolveOperationalAction(initial, 'act-waa-01', { source: 'whatsapp' })
  assert.equal(modified.urgentActions.filter((a) => !a.resolved).length, 3)

  const resetState = resetCompanyOperationalState('waaree')
  assert.equal(resetState.urgentActions.filter((a) => !a.resolved).length, 4)
  assert.equal(resetState.kpis.pendingApprovalsCount, 4)
})
