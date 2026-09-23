import React, {useEffect, useState} from 'react'
import './story.css'

const LOGO = 'https://www.sanocea.com/sanocea-wordmark.png'

// Everything below reflects operational categories this demo's sandbox actually seeds for TPB/
// HealthVitals (packages/prospect_demo/scenarios.py) - inventory/stock, pricing, listing variance,
// shipment delay, NDR/RTO, payment reconciliation, approvals. No category shown here is invented for
// the story that the live demo can't then back up with real evidence.
const AUDIT_ITEMS = [
  'Shopify storefront', 'Amazon India & US', 'Flipkart', 'Blinkit & quick-commerce',
  'Inventory levels', 'Pricing & promotions', 'Listings & content', 'Order & fulfilment signals',
]

const FINDINGS = [
  {sev: '🔴', title: 'Inventory discrepancy', text: 'Blinkit stock differs from the operating inventory.'},
  {sev: '🟠', title: 'Pricing discrepancy', text: "Marketplace price doesn't match the approved price."},
  {sev: '🟠', title: 'Listing issue', text: 'Product information is inconsistent across channels.'},
  {sev: '🔴', title: 'Delivery exception', text: 'A shipment is approaching its SLA breach window.'},
  {sev: '🟠', title: 'NDR / RTO risk', text: 'Repeated delivery failure flagged for return-to-origin.'},
  {sev: '🟠', title: 'Reconciliation discrepancy', text: "Settlement amount doesn't match the order total."},
  {sev: '🟡', title: 'Approval required', text: 'A decision is pending your sign-off.'},
]

const CC_ROWS = [
  {tag: 'EXC-TPB-INV-001', text: "Blinkit OOS — 'Buttery Toffee Delight Makhana'", state: 'Evidence attached'},
  {tag: 'APR-TPB-018', text: 'Price correction pending approval', state: 'Awaiting sign-off'},
  {tag: 'EXC-DJH-5005', text: 'Order at RTO risk — 2 failed attempts', state: 'Evidence attached'},
]

const WA_LINES = [
  'Good morning. I found 3 things that need your attention.',
  '🔴 Blinkit inventory discrepancy — 18 units affected\n🟠 Amazon pricing discrepancy — ₹X variance\n🟠 1 shipment approaching RTO',
]

function Dots({step, total}) {
  return (
    <div className="story-progress">
      {Array.from({length: total}).map((_, i) => (
        <div key={i} className={`story-dot${i === step ? ' active' : ''}`} />
      ))}
    </div>
  )
}

export default function StorySequence({onFinish}) {
  const [step, setStep] = useState(0)
  const totalSteps = 6

  useEffect(() => {
    // Steps 0-3 auto-advance so it reads as something HAPPENING, not a page to scroll through.
    // Steps 4-5 (Command Centre reveal, WhatsApp payoff) wait for the visitor - those are the moments
    // worth letting someone actually read before moving on.
    const durations = {0: 2400, 1: 3600, 2: 4200, 3: 3600}
    if (step in durations) {
      const id = setTimeout(() => setStep((s) => s + 1), durations[step])
      return () => clearTimeout(id)
    }
  }, [step])

  return (
    <div className="story-shell">
      <button className="story-skip" onClick={onFinish}>Skip intro →</button>
      <div className="story-stage">
        <img className="story-logo" src={LOGO} alt="Sanocea" />

        {step === 0 && (
          <div className="story-fade">
            <h1 className="story-headline">Sanocea works.<br />Finds problems.<br />Prepares the work.</h1>
            <p className="story-sub">Watch it happen on a real, sandboxed commerce operation.</p>
          </div>
        )}

        {step === 1 && (
          <div className="story-fade">
            <h1 className="story-headline">Sanocea is auditing the operation…</h1>
            <div className="story-audit-list">
              {AUDIT_ITEMS.map((item, i) => (
                <AuditRow key={item} label={item} index={i} />
              ))}
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="story-fade">
            <h1 className="story-headline">Sanocea found 7 things that need attention.</h1>
            <div className="story-findings">
              {FINDINGS.map((f, i) => (
                <div key={f.title} className="story-card" style={{animationDelay: `${i * 0.18}s`}}>
                  <span>{f.sev}</span>
                  <span>
                    <strong>{f.title}</strong>
                    <span>{f.text}</span>
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="story-fade">
            <h1 className="story-headline">Your team shouldn't have to find these one platform at a time.</h1>
            <p className="story-sub">
              Sanocea continuously checks the operation, identifies the work, attaches the evidence,
              and prepares the next action.
            </p>
          </div>
        )}

        {step === 4 && (
          <div className="story-fade">
            <h1 className="story-headline">Every finding is organised here.</h1>
            <p className="story-sub">The Command Centre — the operating layer underneath everything Sanocea does.</p>
            <div className="story-cc-preview">
              <div className="story-cc-header"><span>Operations Console</span><span>illustrative preview</span></div>
              {CC_ROWS.map((r) => (
                <div key={r.tag} className="story-cc-row">
                  <div>
                    <div>{r.text}</div>
                    <div className="story-cc-tag">{r.tag}</div>
                  </div>
                  <div className="story-cc-tag">{r.state}</div>
                </div>
              ))}
            </div>
            <button className="story-next" style={{marginTop: 22}} onClick={() => setStep(5)}>Continue →</button>
          </div>
        )}

        {step === 5 && (
          <div className="story-fade">
            <h1 className="story-headline">But you don't need to sit in this dashboard.</h1>
            <p className="story-sub">Sanocea brings the work to you in WhatsApp.</p>
            <div className="story-wa-preview">
              {WA_LINES.map((line, i) => (
                <div key={i} className="story-wa-bubble" style={{animationDelay: `${0.3 + i * 0.5}s`}}>{line}</div>
              ))}
            </div>
            <p className="story-cc-caption">Illustrative preview — your live demo below runs on real sandboxed data.</p>
            <p className="story-sub" style={{marginTop: 18}}>Ask questions. Review the evidence. Approve actions. Resolve exceptions.</p>
            <div className="story-actions">
              <button className="story-cta" onClick={onFinish}>Try the live WhatsApp demo →</button>
            </div>
          </div>
        )}

        <Dots step={step} total={totalSteps} />
      </div>
    </div>
  )
}

function AuditRow({label, index}) {
  const [done, setDone] = useState(false)
  useEffect(() => {
    const id = setTimeout(() => setDone(true), 250 + index * 380)
    return () => clearTimeout(id)
  }, [index])
  return (
    <div className={`story-audit-row${done ? ' done' : ''}`} style={{animationDelay: `${index * 0.08}s`}}>
      <span className="story-audit-check">{done ? '✓' : ''}</span>
      <span>{label}</span>
    </div>
  )
}
