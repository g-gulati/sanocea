import React, { useState } from 'react'
import { createRoot } from 'react-dom/client'
import { motion } from 'framer-motion'
import './reconciliation.css'

const LOGO = '/sanocea-wordmark.png'

const REVEAL_EASE = [0.16, 1, 0.3, 1]

function Reveal({ as = 'div', className, children, delay = 0, y = 20, ...rest }) {
  const MotionTag = motion[as] || motion.div
  return (
    <MotionTag
      className={className}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.2 }}
      transition={{ duration: 0.55, delay, ease: REVEAL_EASE }}
      {...rest}
    >
      {children}
    </MotionTag>
  )
}

function Nav() {
  return (
    <header className="sol-nav">
      <div className="sol-nav-shell">
        <a href="/" className="brand" aria-label="SANOCEA™ home">
          <img src={LOGO} alt="SANOCEA™ — AI-assisted ecommerce operations" style={{ height: 26, width: 'auto' }} />
        </a>
        <nav className="sol-nav-links" aria-label="Solution page navigation">
          <a href="#problem">The Problem</a>
          <a href="#how-it-works">6-Stage Loop</a>
          <a href="#capabilities">Live vs Roadmap</a>
          <a href="#faqs">FAQs</a>
          <a href="/demo.html" target="_blank" rel="noopener">Live Demo ↗</a>
          <a className="sol-nav-cta" href="mailto:hello@sanocea.com?subject=Marketplace%20Settlement%20Audit">
            Audit My Settlements
          </a>
        </nav>
      </div>
    </header>
  )
}

function Hero() {
  return (
    <section className="sol-hero">
      <div className="shell">
        <nav className="sol-breadcrumb" aria-label="Breadcrumb">
          <a href="/">Home</a>
          <span>/</span>
          <a href="/#operations">Solutions</a>
          <span>/</span>
          <span style={{ color: 'var(--ink)' }}>Marketplace Settlement & Payout Reconciliation</span>
        </nav>

        <span className="sol-domain-badge">
          Domain 06 · Settlement & Payout Reconciliation
        </span>

        <h1>
          Stop Marketplace Payout Leakage Across Amazon, Flipkart, Blinkit & Shopify
        </h1>

        <p className="sol-hero-lede">
          Most multichannel brands lose 3% to 8% of their gross revenue to hidden commission tier creep,
          uncredited customer return deductions, and courier volumetric weight mismatches.
          Sanocea automates the investigation and prepares verified dispute dossiers before claim deadlines expire — with complete human sign-off.
        </p>

        <div className="sol-hero-actions">
          <a
            className="button primary light"
            href="mailto:hello@sanocea.com?subject=Marketplace%20Settlement%20Audit"
          >
            Audit My Channel Settlements
          </a>
          <a className="button ghost" href="/demo.html" target="_blank" rel="noopener">
            Test Live Demo (WhatsApp) ↗
          </a>
        </div>

        <div className="sol-stat-strip">
          <div className="sol-stat-card">
            <div className="sol-stat-val accent">3% – 8%</div>
            <p className="sol-stat-desc">
              Average marketplace revenue lost to undetected deduction leakage, volumetric weight overcharges, and uncredited returns.
            </p>
          </div>
          <div className="sol-stat-card">
            <div className="sol-stat-val">Per Batch</div>
            <p className="sol-stat-desc">
              Frequency of Sanocea variance detection — catching fee creep as settlements post, rather than 45 days later at month-end close.
            </p>
          </div>
          <div className="sol-stat-card">
            <div className="sol-stat-val">100% Governed</div>
            <p className="sol-stat-desc">
              Human operator approval required before any financial dispute packet or channel balance adjustment is authorized.
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}

const leakages = [
  {
    tag: 'Commission Creep',
    title: 'Hidden Referral & Closing Fee Creep',
    desc: 'Marketplaces routinely update commission tier classifications or closing fee thresholds. When categories shift silently, order deductions climb without proactive notice to the seller.',
    impact: 'Typical margin leakage: 1.5% to 3.0% of order gross merchandise value.',
  },
  {
    tag: 'Weight Overcharges',
    title: 'Courier Volumetric Weight Mismatches',
    desc: 'Logistics carriers charge based on volumetric dimensions rather than dead weight. Hub sorters frequently scan oversized box measurements, billing 1.5 kg on a 350g item.',
    impact: 'Excess shipping fees: ₹40 to ₹120 per misclassified parcel.',
  },
  {
    tag: 'Uncredited Returns',
    title: 'Customer Refund Deducted, Physical Item Never Returned',
    desc: 'A customer return is initiated and the marketplace balance is immediately debited. If the courier loses the package or the customer fails to hand over the item, the reimbursement is often forgotten unless explicitly audited.',
    impact: 'Direct inventory loss: 100% of product cost + reverse shipping fees.',
  },
  {
    tag: 'TCS & Tax Drag',
    title: 'GST-TCS & Payment Gateway Divergence',
    desc: 'Tax Collected at Source (TCS) and payment processing deductions diverge from state-wise sales return registers, leading to reconciliation errors during quarterly GST filings.',
    impact: 'Working capital lockup: Unreconciled input tax credits and audit friction.',
  },
]

function ProblemScene() {
  return (
    <section id="problem" className="sol-problem-scene">
      <div className="shell">
        <Reveal>
          <span className="chapter">01 / the operational reality</span>
          <h2>Where Marketplace Money Disappears Between Sales and Bank Accounts</h2>
          <p className="section-intro" style={{ maxWidth: 740, color: 'var(--muted)' }}>
            Existing commerce systems log successful sales orders. Sanocea inspects the remittance files
            where marketplace fees, courier deductions, and delayed returns quietly erode your realized profit.
          </p>
        </Reveal>

        <div className="leakage-grid">
          {leakages.map((item, idx) => (
            <Reveal key={item.title} delay={idx * 0.08} className="leakage-card">
              <span className="leakage-tag">{item.tag}</span>
              <strong>{item.title}</strong>
              <p>{item.desc}</p>
              <div className="leakage-impact">{item.impact}</div>
            </Reveal>
          ))}
        </div>

        <Reveal delay={0.2} className="oms-contrast-box">
          <div className="oms-contrast-col">
            <h3>Why Core OMS Platforms Leave This to Spreadsheets</h3>
            <p>
              Systems like Unicommerce, Vinculum, and Shopify manage order routing, inventory sync, and label generation.
              They are transactional engines, not financial auditors. When a payout arrives with ₹48,000 in unexpected deductions,
              they leave your operations team to download CSVs across five portals and match rows by hand.
            </p>
          </div>
          <div className="oms-contrast-col sanocea-col">
            <h3>How Sanocea Sits Above the Stack</h3>
            <p>
              Sanocea operates <em>above and around</em> your existing OMS. It continuously ingests settlement files,
              matches order lines against master rate cards and carrier weight logs, isolates fee creep,
              and prepares the dispute dossier for human approval. Zero system rip-and-replace required.
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

const loopStages = [
  {
    step: '01 / Detect',
    role: 'Automated Continuous Engine',
    title: 'Catches Remittance Divergence Per Batch',
    desc: 'Continuously parses marketplace settlement remittance files as they post. Flags any order line where net realized payout deviates from the agreed master contract rate.',
  },
  {
    step: '02 / Investigate',
    role: 'Automated Root-Cause Correlation',
    title: 'Pinpoints the Exact Leakage Category',
    desc: 'Cross-references carrier scan dimensions against warehouse packaging specifications, verifies return tracking numbers, and checks marketplace category commission schedules.',
  },
  {
    step: '03 / Prepare',
    role: 'AI Operator Preparation',
    title: 'Drafts a Structured Dispute Dossier',
    desc: 'Assembles the complete dispute packet: Order ID, SKU details, expected fee breakdown, actual deduction, calculated overcharge, and attached courier manifest records.',
  },
  {
    step: '04 / Approve',
    role: 'Human Operator Sign-Off Gate',
    title: 'Pushes Finding to WhatsApp or Console',
    desc: 'Sends a concise notification to the merchant’s operator with variance proof attached. High-value claims or ledger write-offs require explicit human authorization.',
  },
  {
    step: '05 / Execute',
    role: 'Governed Channel Action',
    title: 'Submits or Stages for Channel Resolution',
    desc: 'The approved claim packet is formatted ready for submission into marketplace seller support or carrier SLA dispute channels. (See Live vs. Roadmap for API specifics).',
  },
  {
    step: '06 / Track',
    role: 'Audit Trail & Outcome Verification',
    title: 'Tracks Reimbursement Credit in Future Payouts',
    desc: 'Monitors subsequent settlement batches to verify that the approved dispute credit actually arrives in the bank deposit, logging an immutable audit record.',
  },
]

function LoopScene() {
  return (
    <section id="how-it-works" className="sol-loop-scene">
      <div className="shell">
        <Reveal className="section-head center">
          <span className="chapter">02 / governed operating model</span>
          <h2>The 6-Stage Sanocea Reconciliation Lifecycle</h2>
          <p style={{ maxWidth: 700, margin: '12px auto 0', color: 'var(--muted)' }}>
            Every settlement discrepancy runs through a disciplined, verified workflow.
            Sanocea investigates with data evidence before any decision is made, keeping your operator in control.
          </p>
        </Reveal>

        <div className="loop-stages-container">
          {loopStages.map((stage, idx) => (
            <Reveal key={stage.step} delay={idx * 0.07} className="loop-stage-card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span className="stage-num-badge">{stage.step}</span>
                <span className="stage-role-pill">{stage.role}</span>
              </div>
              <strong>{stage.title}</strong>
              <p>{stage.desc}</p>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}

const liveCapabilities = [
  {
    title: 'Multi-Channel Settlement Ingestion',
    detail: 'Parses raw payment settlement and remittance files across Amazon, Flipkart, Blinkit, and Shopify.',
  },
  {
    title: 'Order-Level Fee Breakdown & Variance',
    detail: 'Isolates deductions by category: referral fees, fixed closing fees, shipping weight charges, return fees, and taxes.',
  },
  {
    title: 'Master Rate Card Compliance Verification',
    detail: 'Audits actual deducted fee percentages against agreed contract rates to catch unannounced fee tier creep.',
  },
  {
    title: 'Uncredited Return Window Tracking',
    detail: 'Correlates customer refund debits with warehouse return receipt logs to identify missing parcels exceeding SLA windows.',
  },
  {
    title: 'Structured Dispute Dossier Formatting',
    detail: 'Compiles formatted evidence packs (order IDs, SKU specifications, fee variance calculation) ready for seller portal case submission.',
  },
  {
    title: 'WhatsApp & Console Human Approval Gate',
    detail: 'Delivers proposed dispute summaries to the operator’s mobile device or desktop console for 1-click authorization.',
  },
  {
    title: 'Immutable Financial Audit Trail',
    detail: 'Logs every detected discrepancy, operator decision, and variance observation with full timestamp history.',
  },
]

const roadmapCapabilities = [
  {
    title: 'Direct API Dispute Injection (SAFE-T & SPF)',
    detail: 'Direct programmatic API submission of claims into Amazon SAFE-T and Flipkart Seller Protection Fund. Currently, Sanocea provides pre-formatted copy-ready dossiers for 1-step portal submission.',
  },
  {
    title: 'Automated Packing Video Stream Sync',
    detail: 'Integration with warehouse CCTV/packing camera footage for visual unboxing dispute proof. Currently uses carrier weight logs and dead-weight specifications.',
  },
  {
    title: 'Automated ERP Journal Ledger Sync',
    detail: 'Bidirectional automated journal entries into SAP/NetSuite/Tally. Currently provides structured CSV/JSON variance exports.',
  },
]

function TransparencyScene() {
  return (
    <section id="capabilities" className="sol-transparency-scene">
      <div className="shell">
        <Reveal className="section-head center">
          <span className="chapter dark">03 / capability transparency</span>
          <h2>Live Capabilities vs. Active Roadmap</h2>
          <p style={{ maxWidth: 700, margin: '12px auto 0', color: 'var(--muted-dark)' }}>
            We believe in complete commercial transparency. Here is exactly what Sanocea executes today,
            and what is currently in active product development.
          </p>
        </Reveal>

        <div className="transparency-grid">
          <Reveal className="transparency-col">
            <div className="transparency-header">
              <h3 style={{ margin: 0, fontSize: 18, color: 'var(--white)' }}>Live in Sanocea Today</h3>
              <span className="status-badge live">Live & Operational</span>
            </div>
            <ul className="feature-list">
              {liveCapabilities.map((item) => (
                <li key={item.title} className="feature-item">
                  <strong>✓ {item.title}</strong>
                  <span>{item.detail}</span>
                </li>
              ))}
            </ul>
          </Reveal>

          <Reveal delay={0.1} className="transparency-col">
            <div className="transparency-header">
              <h3 style={{ margin: 0, fontSize: 18, color: 'var(--white)' }}>Product Roadmap</h3>
              <span className="status-badge roadmap">In Active Development</span>
            </div>
            <ul className="feature-list">
              {roadmapCapabilities.map((item) => (
                <li key={item.title} className="feature-item">
                  <strong style={{ color: 'var(--cyan)' }}>◷ {item.title}</strong>
                  <span>{item.detail}</span>
                </li>
              ))}
            </ul>
          </Reveal>
        </div>
      </div>
    </section>
  )
}

const faqs = [
  [
    'Does Sanocea replace our accounting software like Tally, Zoho Books, or QuickBooks?',
    'No. Sanocea is not an accounting general ledger or tax filing software. Accounting systems record high-level financial totals and bank feeds, but they cannot audit whether Amazon overcharged you ₹48 on volumetric weight or Flipkart misclassified a commission tier. Sanocea acts as the specialized operational reconciliation layer, isolating SKU-level fee leakage and feeding verified net variances to your accounting workflow.',
  ],
  [
    'Why do marketplace payouts diverge from actual bank deposits?',
    'Payout divergence occurs because marketplace settlement batches bundle hundreds of order lines with varying fee schedules, delayed refund debits, courier shipping weight adjustments, and TCS tax deductions. When marketplaces adjust category fee tiers or couriers bill volumetric weight over dead weight, standard bank deposits no longer match gross order expectations.',
  ],
  [
    'How does Sanocea detect courier volumetric weight overcharging?',
    'Sanocea stores master dead weight and packaging dimension specifications for each SKU. When logistics invoices or settlement lines post with volumetric weight charges, Sanocea compares the billed weight against master specifications. If a courier bills 1.5 kg for a 350g item, Sanocea flags the discrepancy and calculates the exact overcharged fee difference.',
  ],
  [
    'What happens when a customer return is refunded but never reaches our warehouse?',
    'Marketplaces frequently refund customers immediately upon return pickup. If the package is lost in transit by the carrier or delayed past the marketplace return SLA, your balance remains debited. Sanocea tracks the return SLA window; if the item does not register a warehouse receipt scan within the required timeframe, Sanocea flags it for a lost-return reimbursement claim.',
  ],
  [
    'How does the operator approval step work in practice?',
    'Sanocea never makes unilateral financial changes without authority. When a discrepancy is verified, Sanocea sends a structured briefing to the designated operator via WhatsApp or the Command Console. The operator reviews the discrepancy, fee breakdown, and attached proof, and authorizes the action with a single click before the dispute dossier is submitted or exported.',
  ],
  [
    'What credentials or permissions are required to get started?',
    'Sanocea configures around your existing channels using standard API read permissions or approved settlement file exports. You do not need to migrate existing systems or change your order management software. Credentials are encrypted, and initial diagnostic audits can be run on historical settlement exports without touching live operations.',
  ],
]

function FAQScene() {
  const [openIdx, setOpenIdx] = useState(null)
  return (
    <section id="faqs" className="sol-faq-scene">
      <div className="shell">
        <Reveal className="section-head center">
          <span className="chapter">04 / buyer questions</span>
          <h2>Frequently Asked Questions About Marketplace Reconciliation</h2>
          <p style={{ maxWidth: 680, margin: '12px auto 0', color: 'var(--muted)' }}>
            Common questions from finance heads, founders, and marketplace operations managers.
          </p>
        </Reveal>

        <div className="faq-list" style={{ maxWidth: 840, margin: '36px auto 0' }}>
          {faqs.map((faq, idx) => (
            <Reveal as="details" key={faq[0]} open={openIdx === idx} onClick={(e) => { e.preventDefault(); setOpenIdx(openIdx === idx ? null : idx) }}>
              <summary>{faq[0]}</summary>
              <div className="faq-answer-wrap">
                <p>{faq[1]}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}

function CTASection() {
  return (
    <section className="sol-cta-scene">
      <div className="shell">
        <Reveal className="sol-cta-box">
          <span className="chapter dark">Start With Evidence</span>
          <h2>Audit Your Marketplace Settlements in 24 Hours</h2>
          <p>
            Send us a sample settlement remittance file and agreed rate card.
            We will map your fee divergence and isolate hidden leakage across commissions, shipping, and uncredited returns.
          </p>
          <div style={{ display: 'flex', justifyContent: 'center', gap: 14, flexWrap: 'wrap' }}>
            <a
              className="button primary light"
              href="mailto:hello@sanocea.com?subject=Marketplace%20Settlement%20Audit"
            >
              Request a Settlement Audit
            </a>
            <a className="button ghost dark-btn" href="https://wa.me/919909360065" target="_blank" rel="noopener">
              Chat on WhatsApp
            </a>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

function Footer() {
  return (
    <footer className="footer">
      <div className="shell footer-grid">
        <div>
          <a href="/" className="brand" aria-label="SANOCEA™ home">
            <img src={LOGO} alt="SANOCEA™" style={{ height: 24, width: 'auto' }} />
          </a>
          <p style={{ fontSize: 13, marginTop: 8, color: 'var(--muted)' }}>
            AI-assisted ecommerce operations control for teams selling across channels.
          </p>
        </div>
        <div>
          <strong style={{ display: 'block', fontSize: 12, fontFamily: 'var(--font-mono)', marginBottom: 8, color: 'var(--ink)' }}>SOLUTIONS</strong>
          <span style={{ display: 'block', fontSize: 13, color: 'var(--muted)' }}>Marketplace Settlement Reconciliation</span>
          <a href="/#operations" style={{ display: 'block', fontSize: 13, color: 'var(--muted)', marginTop: 4, textDecoration: 'none' }}>All 7 Operational Domains →</a>
          <a href="/#stack" style={{ display: 'block', fontSize: 13, color: 'var(--muted)', marginTop: 4, textDecoration: 'none' }}>OMS Architecture →</a>
        </div>
        <div>
          <strong style={{ display: 'block', fontSize: 12, fontFamily: 'var(--font-mono)', marginBottom: 8, color: 'var(--ink)' }}>CONTACT</strong>
          <a href="mailto:hello@sanocea.com" style={{ display: 'block', fontSize: 13, color: 'var(--muted)', textDecoration: 'none' }}>hello@sanocea.com</a>
          <span style={{ display: 'block', fontSize: 12, color: 'var(--muted)', marginTop: 4 }}>Surat, Gujarat, India</span>
          <span style={{ display: 'block', fontSize: 12, color: 'var(--muted)', marginTop: 8 }}>© 2026 SANOCEA™</span>
        </div>
      </div>
    </footer>
  )
}

function App() {
  return (
    <div className="sol-page">
      <Nav />
      <main>
        <Hero />
        <ProblemScene />
        <LoopScene />
        <TransparencyScene />
        <FAQScene />
        <CTASection />
      </main>
      <Footer />
    </div>
  )
}

const rootEl = document.getElementById('root')
if (rootEl) {
  createRoot(rootEl).render(<App />)
}
