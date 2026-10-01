import test from 'node:test'
import assert from 'node:assert/strict'
import {
  processWhatsAppCommand,
  isMenuCommand,
  parseNumericChoice,
  WHATSAPP_MENU_TEXT,
} from '../src/whatsapp-demo/whatsappCommandHandler.js'
import {getCompanyOperationalData} from '../src/whatsapp-demo/data/companyData.js'

test('WhatsApp Menu Interaction — isMenuCommand parser', () => {
  assert.equal(isMenuCommand('menu'), true)
  assert.equal(isMenuCommand('Menu'), true)
  assert.equal(isMenuCommand('MENU'), true)
  assert.equal(isMenuCommand('  menu  '), true)
  assert.equal(isMenuCommand('help'), true)
  assert.equal(isMenuCommand('Help'), true)
  assert.equal(isMenuCommand('options'), true)
  assert.equal(isMenuCommand('0'), true)
  assert.equal(isMenuCommand('#menu'), true)
  assert.equal(isMenuCommand('/menu'), true)
  assert.equal(isMenuCommand('something else'), false)
})

test('WhatsApp Menu Interaction — parseNumericChoice parser', () => {
  // Option 1 variations
  assert.equal(parseNumericChoice('1'), 1)
  assert.equal(parseNumericChoice('1.'), 1)
  assert.equal(parseNumericChoice('option 1'), 1)
  assert.equal(parseNumericChoice('Option 1'), 1)
  assert.equal(parseNumericChoice('#1'), 1)
  assert.equal(parseNumericChoice('1️⃣'), 1)
  assert.equal(parseNumericChoice('one'), 1)
  assert.equal(parseNumericChoice('(1)'), 1)
  assert.equal(parseNumericChoice('[1]'), 1)

  // Option 2 variations
  assert.equal(parseNumericChoice('2'), 2)
  assert.equal(parseNumericChoice('2.'), 2)
  assert.equal(parseNumericChoice('option 2'), 2)
  assert.equal(parseNumericChoice('#2'), 2)
  assert.equal(parseNumericChoice('2️⃣'), 2)

  // Option 3 variations
  assert.equal(parseNumericChoice('3'), 3)
  assert.equal(parseNumericChoice('3.'), 3)
  assert.equal(parseNumericChoice('option 3'), 3)
  assert.equal(parseNumericChoice('#3'), 3)
  assert.equal(parseNumericChoice('3️⃣'), 3)

  // Option 4 variations
  assert.equal(parseNumericChoice('4'), 4)
  assert.equal(parseNumericChoice('4.'), 4)
  assert.equal(parseNumericChoice('option 4'), 4)
  assert.equal(parseNumericChoice('#4'), 4)
  assert.equal(parseNumericChoice('4️⃣'), 4)

  // Invalid numbers
  assert.equal(parseNumericChoice('5'), null)
  assert.equal(parseNumericChoice('0'), null)
  assert.equal(parseNumericChoice('hello'), null)
})

test('WhatsApp Menu Interaction — Site-wide numbered menu renders for The Premium Basket', () => {
  const companyData = getCompanyOperationalData('premium-basket')
  const context = {
    companyData,
    urgentActions: companyData.urgentActions,
    channelStates: [],
    globalStatus: {connectedCount: 4, totalCount: 4, isHealthy: true},
  }

  // 1. User types menu / Menu / MENU
  const resLower = processWhatsAppCommand('menu', context)
  assert.equal(resLower.intent, 'menu')
  assert.match(resLower.reply, /SANOCEA Commerce OS/)
  assert.match(resLower.reply, /What would you like to do\?/)
  assert.match(resLower.reply, /1\.\s+What needs my attention\?/)
  assert.match(resLower.reply, /2\.\s+Show channel connectivity/)
  assert.match(resLower.reply, /3\.\s+Show inventory health/)
  assert.match(resLower.reply, /4\.\s+Show channel GMV breakdown/)
  assert.match(resLower.reply, /Reply with 1–4/)

  const resCap = processWhatsAppCommand('Menu', context)
  assert.equal(resCap.intent, 'menu')
  assert.equal(resCap.reply, WHATSAPP_MENU_TEXT)

  const resUpper = processWhatsAppCommand('MENU', context)
  assert.equal(resUpper.intent, 'menu')
  assert.equal(resUpper.reply, WHATSAPP_MENU_TEXT)

  // 2. User enters "1" -> executes Option 1 (What needs my attention?)
  const res1 = processWhatsAppCommand('1', context)
  assert.equal(res1.intent, 'attention')
  assert.match(res1.reply, /Operational Exceptions Needing Attention/)
  assert.match(res1.reply, /Blinkit/)
  assert.match(res1.reply, /BBQ Almonds/)
  assert.match(res1.reply, /Type \*menu\* for more options/)

  // 3. User types "menu" again -> menu returns
  const resMenuAfter1 = processWhatsAppCommand('menu', context)
  assert.equal(resMenuAfter1.intent, 'menu')
  assert.equal(resMenuAfter1.reply, WHATSAPP_MENU_TEXT)

  // 4. User enters "2" -> executes Option 2 (Show channel connectivity)
  const res2 = processWhatsAppCommand('2', context)
  assert.equal(res2.intent, 'connectivity')
  assert.match(res2.reply, /Commerce Channels Connectivity/)
  assert.match(res2.reply, /Blinkit/)
  assert.match(res2.reply, /Shopify/)
  assert.match(res2.reply, /TLS 1\.3 Active/)
  assert.match(res2.reply, /Type \*menu\* for more options/)

  // 5. User enters "3" -> executes Option 3 (Show inventory health)
  const res3 = processWhatsAppCommand('3', context)
  assert.equal(res3.intent, 'inventory')
  assert.match(res3.reply, /Inventory Health Status/)
  assert.match(res3.reply, /BBQ Almonds/)
  assert.match(res3.reply, /Type \*menu\* for more options/)

  // 6. User enters "4" -> executes Option 4 (Show channel GMV breakdown)
  const res4 = processWhatsAppCommand('4', context)
  assert.equal(res4.intent, 'gmv')
  assert.match(res4.reply, /Channel Performance Snapshot/)
  assert.match(res4.reply, /Total GMV/)
  assert.match(res4.reply, /Blinkit/)
  assert.match(res4.reply, /₹7,42,800/)
  assert.match(res4.reply, /Type \*menu\* for more options/)
})

test('WhatsApp Menu Interaction — Site-wide numbered menu renders for Ajanta Soya (Anchal)', () => {
  const companyData = getCompanyOperationalData('ajanta-soya')
  const context = {
    companyData,
    urgentActions: companyData.urgentActions,
    channelStates: [],
    globalStatus: {connectedCount: 4, totalCount: 4, isHealthy: true},
  }

  // 1. User types "Menu"
  const resMenu = processWhatsAppCommand('Menu', context)
  assert.equal(resMenu.intent, 'menu')
  assert.match(resMenu.reply, /1\.\s+What needs my attention\?/)
  assert.match(resMenu.reply, /2\.\s+Show channel connectivity/)
  assert.match(resMenu.reply, /3\.\s+Show inventory health/)
  assert.match(resMenu.reply, /4\.\s+Show channel GMV breakdown/)
  assert.match(resMenu.reply, /Reply with 1–4/)

  // 2. User enters "1" -> executes Option 1 with Ajanta Soya data
  const res1 = processWhatsAppCommand('1', context)
  assert.equal(res1.intent, 'attention')
  assert.match(res1.reply, /Ajanta Soya/)
  assert.match(res1.reply, /WooCommerce/)

  // 3. User enters "2" -> executes Option 2 with Ajanta Soya channels
  const res2 = processWhatsAppCommand('2', context)
  assert.equal(res2.intent, 'connectivity')
  assert.match(res2.reply, /Ajanta Soya/)
  assert.match(res2.reply, /D2C Store|WooCommerce/)

  // 4. User enters "3" -> executes Option 3 with Ajanta Soya inventory
  const res3 = processWhatsAppCommand('3', context)
  assert.equal(res3.intent, 'inventory')
  assert.match(res3.reply, /Ajanta Soya/)

  // 5. User enters "4" -> executes Option 4 with Ajanta Soya GMV breakdown
  const res4 = processWhatsAppCommand('4', context)
  assert.equal(res4.intent, 'gmv')
  assert.match(res4.reply, /Ajanta Soya/)
  assert.match(res4.reply, /₹48,20,000/) // WooCommerce GMV
  assert.match(res4.reply, /Type \*menu\* for more options/)

  // 6. User enters "menu" again -> successfully returns menu
  const resMenuAgain = processWhatsAppCommand('menu', context)
  assert.equal(resMenuAgain.intent, 'menu')
  assert.equal(resMenuAgain.reply, WHATSAPP_MENU_TEXT)
})

test('WhatsApp Menu Interaction — Site-wide numbered menu renders for Carzex Automotive', () => {
  const companyData = getCompanyOperationalData('carzex')
  const context = {
    companyData,
    urgentActions: companyData.urgentActions,
    channelStates: [],
    globalStatus: {connectedCount: 3, totalCount: 3, isHealthy: true},
  }

  // 1. User types "menu"
  const resMenu = processWhatsAppCommand('menu', context)
  assert.equal(resMenu.intent, 'menu')

  // 2. Numeric option 1 executes Carzex attention items
  const res1 = processWhatsAppCommand('1', context)
  assert.equal(res1.intent, 'attention')
  assert.match(res1.reply, /Carzex/)

  // 3. Numeric option 4 executes Carzex channel breakdown
  const res4 = processWhatsAppCommand('4', context)
  assert.equal(res4.intent, 'gmv')
  assert.match(res4.reply, /Carzex/)
  assert.match(res4.reply, /Flipkart Motors|Shopify D2C/)
})
