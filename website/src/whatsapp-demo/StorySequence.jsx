import React, {useCallback, useEffect} from 'react'
import './story.css'

const LOGO = 'https://www.sanocea.com/sanocea-wordmark.png'

// Everything below reflects operational categories this demo's sandbox actually seeds for TPB/
// HealthVitals (packages/prospect_demo/scenarios.py) - inventory/stock, pricing, listing variance,
// shipment delay, NDR/RTO, payment reconciliation, approvals. No category shown here is invented for
// the story that the live demo can't then back up with real evidence.
const AUDIT_ITEMS = [
  'Shopify storefront', 'Amazon India & US', 'Flipkart', 'Blinkit & quick-commerce',
  'Inventory levels', 'Pricing & promotions', 'Fulfilment signals',
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

const SLIDE_COUNT = 6

function Dots({step}) {
  return (
    <div className="story-progress">
      <span className="story-progress-count">{step + 1} / {SLIDE_COUNT}</span>
      <div className="story-progress-dots">
        {Array.from({length: SLIDE_COUNT}).map((_, i) => (
          <div key={i} className={`story-dot${i === step ? ' active' : ''}`} />
        ))}
      </div>
    </div>
  )
}

export default function StorySequence({onFinish}) {
  const [step, setStep] = React.useState(0)

  const next = useCallback(() => setStep((s) => Math.min(s + 1, SLIDE_COUNT - 1)), [])
  const back = useCallback(() => setStep((s) => Math.max(s - 1, 0)), [])

  // Visitor controls the pace entirely - no timers anywhere in this component. Arrow keys mirror the
  // on-screen arrows so a keyboard-first visitor never has to reach for the mouse.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'ArrowRight') next()
      else if (e.key === 'ArrowLeft') back()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [next, back])

  const isLast = step === SLIDE_COUNT - 1

  return (
    <div className="story-shell">
      <button className="story-skip" onClick={onFinish}>Skip intro →</button>

      {step > 0 && (
        <button className="story-arrow story-arrow-left" onClick={back} aria-label="Previous slide">‹</button>
      )}
      {!isLast && (
        <button className="story-arrow story-arrow-right" onClick={next} aria-label="Next slide">›</button>
      )}

      <div className="story-stage">
        <img className="story-logo" src={LOGO} alt="Sanocea" />

        {step === 0 && (
          <div className="story-fade" key={step}>
            <h1 className="story-headline">Sanocea works.</h1>
            <p className="story-sub">It connects to the commerce operation.</p>
          </div>
        )}

        {step === 1 && (
          <div className="story-fade" key={step}>
            <h1 className="story-headline">Sanocea checks it.</h1>
            <div className="story-audit-list">
              {AUDIT_ITEMS.map((item, i) => (
                <div key={item} className="story-audit-row done" style={{animationDelay: `${i * 0.06}s`}}>
                  <span className="story-audit-check">✓</span>
                  <span>{item}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="story-fade" key={step}>
            <h1 className="story-headline">Sanocea finds the problems.</h1>
            <div className="story-findings">
              {FINDINGS.map((f, i) => (
                <div key={f.title} className="story-card" style={{animationDelay: `${i * 0.06}s`}}>
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
          <div className="story-fade" key={step}>
            <h1 className="story-headline">Your operation, organised.</h1>
            <p className="story-sub">The Command Centre — what was found, and what needs action.</p>
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
          </div>
        )}

        {step === 4 && (
          <div className="story-fade" key={step}>
            <h1 className="story-headline">You don't need to sit in the dashboard.</h1>
            <p className="story-sub">Sanocea brings the work to you in WhatsApp.</p>
            <div className="story-wa-preview">
              {WA_LINES.map((line, i) => (
                <div key={i} className="story-wa-bubble" style={{animationDelay: `${i * 0.1}s`}}>{line}</div>
              ))}
            </div>
            <p className="story-cc-caption">Illustrative preview — your live demo runs on real sandboxed data.</p>
          </div>
        )}

        {step === 5 && (
          <div className="story-fade" key={step}>
            <h1 className="story-headline">Try it yourself.</h1>
            <p className="story-sub">Ask questions. Review the evidence. Approve actions. Resolve exceptions.</p>
            <div className="story-actions">
              <button className="story-cta" onClick={onFinish}>Try the live WhatsApp demo →</button>
            </div>
          </div>
        )}

        <Dots step={step} />
      </div>
    </div>
  )
}
