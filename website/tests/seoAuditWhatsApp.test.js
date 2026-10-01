import test from 'node:test'
import assert from 'node:assert/strict'
import {processWhatsAppCommand} from '../src/whatsapp-demo/whatsappCommandHandler.js'
import {getCompanyOperationalData} from '../src/whatsapp-demo/data/companyData.js'

test('SEO & Commerce Audit WhatsApp Flow — Waaree Energies (200+ findings with prioritization)', () => {
  const companyData = getCompanyOperationalData('waaree')
  const context = {
    companyData,
    urgentActions: companyData.urgentActions,
    channelStates: [],
    globalStatus: {connectedCount: 5, totalCount: 5, isHealthy: true},
  }

  // 1. Trigger via "seo"
  const res = processWhatsAppCommand('seo', context)
  assert.equal(res.intent, 'seo_audit')
  assert.match(res.reply, /SANOCEA SEO & Commerce Audit Engine/)
  assert.match(res.reply, /200\+ findings detected/)
  assert.match(res.reply, /Commercial Prioritization Summary/)
  assert.match(res.reply, /require immediate attention/)
  assert.match(res.reply, /require human approval/)
  assert.match(res.reply, /GMC Supplemental Feed/)
  assert.match(res.reply, /Storefront API/)
  assert.match(res.reply, /What SANOCEA Recommends Fixing First/)
  assert.match(res.reply, /Availability \/ Structured Data Conflict/)

  // 2. Verify quick action buttons exist
  assert.ok(Array.isArray(res.quickActions))
  assert.ok(res.quickActions.some(qa => qa.actionKey === 'SAN-WAAREE-P0-01'))

  // 3. Trigger via "5"
  const res5 = processWhatsAppCommand('5', context)
  assert.equal(res5.intent, 'seo_audit')
  assert.match(res5.reply, /200\+ findings detected/)

  // 4. Trigger via "what to fix first"
  const resFix = processWhatsAppCommand('what to fix first', context)
  assert.equal(resFix.intent, 'seo_audit')
  assert.match(resFix.reply, /What SANOCEA Recommends Fixing First/)
})

test('SEO & Commerce Audit WhatsApp Flow — Carzex Automotive (100+ findings with false-priority quarantine)', () => {
  const companyData = getCompanyOperationalData('carzex')
  const context = {
    companyData,
    urgentActions: companyData.urgentActions,
    channelStates: [],
    globalStatus: {connectedCount: 4, totalCount: 4, isHealthy: true},
  }

  const res = processWhatsAppCommand('audit', context)
  assert.equal(res.intent, 'seo_audit')
  assert.match(res.reply, /100\+ findings detected/)
  assert.match(res.reply, /Primary Category Self-Canonicalization Loop/)
})
