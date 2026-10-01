import test from 'node:test'
import assert from 'node:assert/strict'
import {
  getFreshInitialState,
  resolveOperationalAction,
  resetCompanyOperationalState,
  reconnectChannelInState,
  degradeChannelInState,
  ALL_DEMO_COMPANIES,
} from '../src/whatsapp-demo/operationalStore.js'
import {
  processWhatsAppCommand,
  isResetCommand,
} from '../src/whatsapp-demo/whatsappCommandHandler.js'
import {getCompanyOperationalData} from '../src/whatsapp-demo/data/companyData.js'

test('Operational Store — Fresh initial state deep cloning & isolation', () => {
  const statePb1 = getFreshInitialState('premium-basket')
  const statePb2 = getFreshInitialState('premium-basket')
  const stateAjn = getFreshInitialState('ajanta-soya')

  assert.equal(statePb1.companyId, 'premium-basket')
  assert.equal(statePb1.urgentActions.length, 3)
  assert.equal(statePb1.urgentActions.filter((a) => !a.resolved).length, 3)
  assert.equal(stateAjn.companyId, 'ajanta-soya')

  // Modifying statePb1 must not mutate statePb2 or raw data
  statePb1.urgentActions[0].resolved = true
  assert.equal(statePb2.urgentActions[0].resolved, false)

  const rawData = getCompanyOperationalData('premium-basket')
  assert.equal(rawData.urgentActions[0].resolved, false)
})

test('Operational Store — Dashboard approval synchronizes to WhatsApp, Inventory, KPIs & Exceptions', () => {
  const initial = getFreshInitialState('premium-basket')
  assert.equal(initial.urgentActions.filter((a) => !a.resolved).length, 3)

  // 1. Resolve Blinkit Restock from Dashboard
  const targetActionId = 'act-pb-01'
  const resolvedState = resolveOperationalAction(initial, targetActionId, { source: 'dashboard' })

  // (a) Urgent actions state
  const targetAction = resolvedState.urgentActions.find((a) => a.id === targetActionId)
  assert.equal(targetAction.resolved, true)
  assert.ok(targetAction.resolvedAt)
  assert.ok(targetAction.resolutionAuditId)
  assert.equal(resolvedState.urgentActions.filter((a) => !a.resolved).length, 2)

  // (b) KPI updates
  assert.equal(resolvedState.kpis.pendingApprovalsCount, 2)
  assert.equal(resolvedState.kpis.pendingApprovalsLabel, '2 pending approval')

  // (c) Inventory replenishment
  const bbqAlmonds = resolvedState.inventoryItems.find((i) => i.sku === 'GC-NT-BBQ-0250G')
  assert.ok(bbqAlmonds)
  assert.equal(bbqAlmonds.status, 'OPTIMAL')
  assert.equal(bbqAlmonds.riskLevel, 'healthy')
  assert.equal(bbqAlmonds.revenueAtRisk, '₹0')
  assert.equal(bbqAlmonds.currentStock, 120) // 0 original + 120 replenished

  // (d) Exceptions log update
  const matchingException = resolvedState.exceptionsLog.find((e) => e.sku === 'GC-NT-BBQ-0250G')
  assert.ok(matchingException)
  assert.equal(matchingException.status, 'RESOLVED')

  // (e) Live stream event
  assert.equal(resolvedState.streamEvents[0].type, 'Operator approval executed')
  assert.ok(resolvedState.streamEvents[0].headline.includes('Stock Transfer'))

  // (f) WhatsApp chat synchronization:
  // 1. Existing message buttons updated to (Executed) and disabled
  const briefingMsg = resolvedState.chatMessages.find((m) =>
    (m.quickActions || []).some((qa) => qa.actionKey === targetActionId)
  )
  assert.ok(briefingMsg)
  const updatedBtn = briefingMsg.quickActions.find((qa) => qa.actionKey === targetActionId)
  assert.equal(updatedBtn.disabled, true)
  assert.ok(updatedBtn.label.includes('(Executed)'))

  // 2. Sync confirmation appended to chat messages
  const syncMsg = resolvedState.chatMessages[resolvedState.chatMessages.length - 1]
  assert.equal(syncMsg.from, 'sanocea')
  assert.ok(syncMsg.text.includes('Operations Command Center Sync'))
  assert.ok(syncMsg.text.includes('RESOLVED & CONNECTOR ACKNOWLEDGED'))
  assert.ok(syncMsg.text.includes(targetAction.resolutionAuditId))
})

test('Operational Store — WhatsApp attention query reflects Dashboard resolution', () => {
  const initial = getFreshInitialState('premium-basket')

  // Querying WhatsApp before resolution reports 3 issues
  const beforeResult = processWhatsAppCommand('1', {
    companyData: initial,
    urgentActions: initial.urgentActions,
    channelStates: initial.channelStates,
  })
  assert.equal(beforeResult.intent, 'attention')
  assert.ok(beforeResult.reply.includes('Operational Exceptions Needing Attention (3)'))

  // Resolve action 1 from Dashboard
  const afterOne = resolveOperationalAction(initial, 'act-pb-01', { source: 'dashboard' })
  const middleResult = processWhatsAppCommand('1', {
    companyData: afterOne,
    urgentActions: afterOne.urgentActions,
    channelStates: afterOne.channelStates,
  })
  assert.equal(middleResult.intent, 'attention')
  assert.ok(middleResult.reply.includes('Operational Exceptions Needing Attention (2)'))
  assert.ok(!middleResult.reply.includes('act-pb-01'))

  // Resolve action 2 from Dashboard
  const afterTwo = resolveOperationalAction(afterOne, 'act-pb-02', { source: 'dashboard' })
  const secondResult = processWhatsAppCommand('1', {
    companyData: afterTwo,
    urgentActions: afterTwo.urgentActions,
    channelStates: afterTwo.channelStates,
  })
  assert.equal(secondResult.intent, 'attention')
  assert.ok(secondResult.reply.includes('Operational Exceptions Needing Attention (1)'))

  // Resolve action 3 from Dashboard
  const afterAll = resolveOperationalAction(afterTwo, 'act-pb-03', { source: 'dashboard' })
  const finalResult = processWhatsAppCommand('1', {
    companyData: afterAll,
    urgentActions: afterAll.urgentActions,
    channelStates: afterAll.channelStates,
  })
  assert.equal(finalResult.intent, 'attention')
  assert.ok(finalResult.reply.includes('All Clear'))
  assert.ok(finalResult.reply.includes('All urgent operational exceptions have been resolved'))
})

test('Operational Store — WhatsApp approval updates Dashboard urgent actions', () => {
  const initial = getFreshInitialState('ajanta-soya')
  const targetActionId = 'act-ajn-01'

  // Resolve from WhatsApp
  const resolvedState = resolveOperationalAction(initial, targetActionId, { source: 'whatsapp' })
  const targetAction = resolvedState.urgentActions.find((a) => a.id === targetActionId)

  assert.equal(targetAction.resolved, true)
  assert.equal(resolvedState.urgentActions.filter((a) => !a.resolved).length, 2) // 3 originally in Ajanta Soya

  // WhatsApp execution already presented UI animation, so no redundant dash-sync text appended
  const lastMsg = resolvedState.chatMessages[resolvedState.chatMessages.length - 1]
  assert.ok(!lastMsg?.text?.includes('Operations Command Center Sync'))
})

test('Operational Store — Channel degradation and reconnection cycle', () => {
  const initial = getFreshInitialState('premium-basket')
  assert.equal(initial.channelStates.every((c) => c.healthStatus === 'Healthy'), true)

  // 1. Degrade Amazon SP-API channel
  const degradedState = degradeChannelInState(initial, 'amazon')
  const amazonChannel = degradedState.channelStates.find((c) => c.id === 'amazon')
  assert.equal(amazonChannel.healthStatus, 'Degraded')
  assert.equal(amazonChannel.connectionStatus, 'Degraded')
  assert.equal(amazonChannel.latencyMs, 1840)

  const degradeAction = degradedState.urgentActions.find((a) => a.id === 'act-deg-amazon')
  assert.ok(degradeAction)
  assert.equal(degradeAction.resolved, false)

  // 2. Reconnect Amazon SP-API channel
  const restoredState = reconnectChannelInState(degradedState, 'amazon')
  const reconnectedAmazon = restoredState.channelStates.find((c) => c.id === 'amazon')
  assert.equal(reconnectedAmazon.healthStatus, 'Healthy')
  assert.equal(reconnectedAmazon.connectionStatus, 'Connected')
  assert.equal(reconnectedAmazon.latencyMs, 48)

  const reconnectedAction = restoredState.urgentActions.find((a) => a.id === 'act-deg-amazon')
  assert.equal(reconnectedAction.resolved, true)
})

test('Operational Store — Reset command and state restoration across companies', () => {
  // Check reset command parser
  assert.equal(isResetCommand('reset'), true)
  assert.equal(isResetCommand('Reset'), true)
  assert.equal(isResetCommand('RESET'), true)
  assert.equal(isResetCommand('reset demo'), true)
  assert.equal(isResetCommand('reset simulation'), true)
  assert.equal(isResetCommand('restart'), true)
  assert.equal(isResetCommand('menu'), false)

  // Test across all demo companies
  ALL_DEMO_COMPANIES.forEach((company) => {
    const initial = getFreshInitialState(company.id)
    const pendingCountOriginal = initial.urgentActions.filter((a) => !a.resolved).length

    // Resolve an action if pending exists
    if (pendingCountOriginal > 0) {
      const firstActionId = initial.urgentActions[0].id
      const mutated = resolveOperationalAction(initial, firstActionId, { source: 'dashboard' })
      assert.equal(mutated.urgentActions.filter((a) => !a.resolved).length, pendingCountOriginal - 1)

      // Reset
      const reset = resetCompanyOperationalState(company.id)
      assert.equal(reset.urgentActions.filter((a) => !a.resolved).length, pendingCountOriginal)
      assert.equal(reset.urgentActions[0].resolved, false)
    }

    // Process WhatsApp command "reset"
    const result = processWhatsAppCommand('reset', { companyData: initial })
    assert.equal(result.intent, 'reset')
    assert.equal(result.shouldReset, true)
    assert.ok(result.reply.includes('Demo Environment Reset Complete'))
  })
})
