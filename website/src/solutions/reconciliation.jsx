import React, { useState } from 'react'
import { createRoot } from 'react-dom/client'
import { motion } from 'framer-motion'
import './reconciliation.css'

const LOGO = '/sanocea-wordmark.png'

const REVEAL_EASE = [0.16, 1, 0.3, 1]

function Reveal({ as = 'div', className, children, delay = 0, y = 18, ...rest }) {
  const MotionTag = motion[as] || motion.div
  return (
    <MotionTag
      className={className}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.15 }}
      transition={{ duration: 0.5, delay, ease: REVEAL_EASE }}
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
          <a href="#problems">Problem Vectors</a>
          <a href="#workflow">6-Stage Loop</a>
          <a href="#evidence">Evidence Dossier</a>
          <a href="#roadmap">Live vs Roadmap</a>
          <a href="#domains">7 Domains</a>
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
          <span className="sol-pulse-dot" />
          Domain 06 · Settlement & Payout Reconciliation
        </span>

        <h1>
          Stop Marketplace Payout Leakage Across Connected Commerce Channels
        </h1>

        <p className="sol-hero-lede">
          Sanocea reconciles settlement and payout data across connected marketplaces and commerce channels,
          with current integrations including Amazon, Flipkart, Blinkit and Shopify. Multichannel brands routinely lose 3% to 8% of gross
          revenue to silent commission tier creep, uncredited customer return deductions, and courier volumetric weight inflation.
          Sanocea automates continuous batch audit, investigates root-cause discrepancies, and prepares verified dispute dossiers
          for human sign-off — before claim windows expire. Sanocea can be connected to additional marketplaces and commerce systems
          where the required APIs, settlement files, exports, or data interfaces are available.
        </p>

        <div className="sol-hero-actions">
          <a
            className="button primary light"
            href="mailto:hello@sanocea.com?subject=Marketplace%20Settlement%20Audit"
          >
            Audit My Channel Settlements
          </a>
          <a className="button ghost" href="/demo.html" target="_blank" rel="noopener">
            Explore Live Interactive Demo ↗
          </a>
        </div>

        <div className="sol-stat-strip">
          <div className="sol-stat-card">
            <div className="sol-stat-val accent">3% – 8%</div>
            <p className="sol-stat-desc">
              Typical margin leakage recovered from silent commission tier reclassifications, courier weight errors, and uncredited return debits.
            </p>
          </div>
          <div className="sol-stat-card">
            <div className="sol-stat-val">Per Batch</div>
            <p className="sol-stat-desc">
              Ingestion and variance detection frequency — flagging fee creep as settlement remittance files post, not 45 days late at month-end.
            </p>
          </div>
          <div className="sol-stat-card">
            <div className="sol-stat-val">100% Governed</div>
            <p className="sol-stat-desc">
              Human operator approval gate via WhatsApp or Console before any financial dispute packet or ledger adjustment is authorized.
            </p>
          </div>
          <div className="sol-stat-card">
            <div className="sol-stat-val">0 Rip & Replace</div>
            <p className="sol-stat-desc">
              Operates above and around your existing OMS (Unicommerce, Vinculum, Shopify) and accounting ledger without migration disruption.
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}

const problemVectors = [
  {
    tag: 'Payout Divergence',
    vector: 'Vector 01',
    title: 'Marketplace Payout & Remittance Divergence',
    symptom: 'Gross sales report ₹10,00,000, but bank deposit arrives as ₹7,24,000 with opaque deduction batches.',
    cause: 'Marketplace settlements consolidate hundreds of line items with fluctuating commission schedules, reverse logistics debits, and delayed holding reserves.',
    rule: 'Per-batch remittance parsing matching each order line against contractual expected payout.',
    impact: 'Typical undetected variance: 2.0% to 4.5% of total merchandise sales.',
  },
  {
    tag: 'Fee Creep',
    vector: 'Vector 02',
    title: 'Commission & Category Fee Tier Drift',
    symptom: 'Profit margins erode on top-selling SKUs even when sales volume and list prices remain constant.',
    cause: 'Marketplaces silently shift product category classifications (e.g. moving a 12% pantry SKU to a 16.5% gourmet snack tier) or modify closing fee slabs.',
    rule: 'SKU-level rate card compliance audit comparing deducted fee percentages against signed vendor agreements.',
    impact: 'Margin drag: ₹25 to ₹95 per unit sold across misclassified categories.',
  },
  {
    tag: 'Uncredited Returns',
    vector: 'Vector 03',
    title: 'Uncredited Customer Return Deductions',
    symptom: 'Customer refund is debited from seller account immediately, but the physical item never arrives at warehouse.',
    cause: 'Courier loses parcel in reverse transit, or customer hands over empty parcel; marketplace refund debit remains permanent unless contested.',
    rule: 'Return SLA window tracker matching marketplace customer refund logs against physical warehouse WMS receipt scans.',
    impact: 'Direct inventory write-off: 100% of product cost plus reverse logistics fees.',
  },
  {
    tag: 'Weight Overcharges',
    vector: 'Vector 04',
    title: 'Volumetric-Weight Courier Overcharges',
    symptom: 'Shipping deduction lines suddenly double on compact, lightweight products.',
    cause: 'Hub sorter scanners capture oversized box dimensions or optical sensor glitches, billing a 320g product at 1.5kg volumetric weight.',
    rule: 'Continuous comparison of billed courier dimensions against master SKU packaging dimensions and dead-weight specifications.',
    impact: 'Excess shipping fees: ₹40 to ₹120 per misclassified outbound parcel.',
  },
  {
    tag: '3-Way Reconciliation',
    vector: 'Vector 05',
    title: 'Marketplace vs. Bank Settlement Reconciliation',
    symptom: 'Quarterly GST filings and finance audits stall due to unreconciled TCS, TDS, and payment gateway deductions.',
    cause: 'Marketplace remittance credit dates do not align with bank UTR deposit dates, compounded by rolling reserve withholdings and state tax variances.',
    rule: '3-way automated matching engine: Sales Orders ↔ Marketplace Settlement Remittance ↔ Bank Credit Statements.',
    impact: 'Working capital lockup: Trapped input tax credit and weeks of manual accountant reconciliation.',
  },
  {
    tag: 'Evidence Assembly',
    vector: 'Vector 06',
    title: 'Operational Evidence Preparation for Disputes',
    symptom: 'Dispute windows expire (typically 30–60 days) because gathering proof across 5 portals takes hours per claim.',
    cause: 'Marketplaces reject vague dispute tickets without attached proof: dead weight specs, courier manifests, and rate card clauses.',
    rule: 'Automated compilation of complete dispute dossiers (Order ID, SKU, weight slip, rate card contract) ready for portal filing.',
    impact: 'Recovery capture rate: 65% to 85% of verified overcharges successfully credited.',
  },
]

function ProblemMatrix() {
  return (
    <section id="problems" className="sol-problem-scene">
      <div className="shell">
        <Reveal>
          <span className="chapter">01 / the operational reality</span>
          <h2>Where Marketplace Revenue Disappears Between Sales Orders and Bank Accounts</h2>
          <p className="section-intro" style={{ maxWidth: 780, color: 'var(--muted)', marginTop: 8 }}>
            Transactional ecommerce systems confirm when an order is packed and shipped.
            Sanocea audits the complex remittance files where marketplace deductions, courier penalties,
            and unverified return debits quietly eat your margins.
          </p>
        </Reveal>

        <div className="leakage-grid">
          {problemVectors.map((item, idx) => (
            <Reveal key={item.title} delay={idx * 0.06} className="leakage-card">
              <div className="leakage-top">
                <span className="leakage-tag">{item.tag}</span>
                <span className="leakage-vector-num">{item.vector}</span>
              </div>
              <h3>{item.title}</h3>
              <div className="leakage-detail-row">
                <span className="leakage-detail-label">Symptom:</span>
                <span className="leakage-detail-text">{item.symptom}</span>
              </div>
              <div className="leakage-detail-row">
                <span className="leakage-detail-label">Root Cause:</span>
                <span className="leakage-detail-text">{item.cause}</span>
              </div>
              <div className="leakage-detail-row">
                <span className="leakage-detail-label">Sanocea Rule:</span>
                <span className="leakage-detail-text" style={{ color: 'var(--ink)', fontWeight: 550 }}>{item.rule}</span>
              </div>
              <div className="leakage-impact">{item.impact}</div>
            </Reveal>
          ))}
        </div>

        <Reveal delay={0.2} className="oms-contrast-box">
          <div className="oms-contrast-col">
            <h3>Why Transactional OMS Systems Leave This to Spreadsheets</h3>
            <p>
              Platforms like Unicommerce, Vinculum, and Shopify manage order routing, inventory sync, and airway bill generation.
              They are transactional engines, not financial auditors. When a payout arrives with ₹48,000 in unexpected deductions,
              they leave your finance team to download CSV files across five seller portals and cross-reference rows manually in Excel.
            </p>
          </div>
          <div className="oms-contrast-col sanocea-col">
            <h3>How Sanocea Sits Above the Commerce Stack</h3>
            <p>
              Sanocea operates <em>above and around</em> your existing OMS. It continuously ingests settlement files,
              matches order lines against master rate cards and carrier weight logs, isolates fee creep,
              and prepares structured dispute dossiers for human approval. Zero system migration or rip-and-replace required.
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

const workflowStages = [
  {
    step: '01',
    name: 'Detect',
    role: 'Automated Continuous Engine',
    title: 'Catches Remittance Divergence Per Settlement Batch',
    desc: 'Continuously parses marketplace remittance and settlement files as they post. Evaluates every individual order line against contractual pricing, fee schedules, and tax rules to isolate fee divergence.',
    checks: [
      'Multi-channel ingestion across connected commerce channels (including Amazon, Flipkart, Blinkit, Shopify)',
      'Instant order-line variance calculation against master contract',
      'Flags fee creep as batches post — not 45 days late at month-end',
    ],
    terminalData: {
      title: 'Remittance Divergence Stream',
      badge: 'Batch AMZ-IN-SETTLE-2026-W38-B2',
      rows: [
        { label: 'Channel (Example)', val: 'Amazon India (FBA / MFN)' },
        { label: 'Batch Orders', val: '1,482 order lines processed' },
        { label: 'Flagged Variance', val: '₹28,450.00 across 41 order lines', alert: true },
        { label: 'Sample Order', val: '#408-9128491-1182701 (SKU: GC-MK-BLK-0050G-2P)' },
        { label: 'Expected Net', val: '₹1,420.00' },
        { label: 'Remitted Net', val: '₹1,188.10' },
        { label: 'Discrepancy', val: '-₹231.90 (Divergence Flagged)', alert: true },
      ],
    },
  },
  {
    step: '02',
    name: 'Investigate',
    role: 'Automated Root-Cause Correlation',
    title: 'Pinpoints the Exact Leakage Category with Proof',
    desc: 'Correlates the flagged variance against master SKU dead-weight specifications, warehouse packaging manifests, courier dimension logs, and published marketplace commission tier tables.',
    checks: [
      'Audits courier volumetric weight (L×W×H/5000) vs master dead weight',
      'Verifies marketplace category fee classification against rate card',
      'Checks return tracking SLA window against warehouse receipt logs',
    ],
    terminalData: {
      title: 'Root-Cause Multi-Factor Correlation',
      badge: 'Order #408-9128491-1182701',
      rows: [
        { label: 'Factor 01 (Fee)', val: 'Classified: Snack Special (16.5%) | Expected: Pantry (12.0%) → Overcharge +₹63.90', alert: true },
        { label: 'Factor 02 (Weight)', val: 'Carrier Volumetric: 1,500g | Master Dead Weight: 320g → Overcharge +₹98.00', alert: true },
        { label: 'Factor 03 (Return)', val: 'Return refund debited 18 days ago; 0 warehouse receipt scan → Overcharge +₹70.00', alert: true },
        { label: 'Carrier AWB', val: 'DEL-99120481 (Delhivary Sorter Hub 4B)' },
        { label: 'Total Verified', val: '₹231.90 (100% Grounded in Evidence)', success: true },
      ],
    },
  },
  {
    step: '03',
    name: 'Prepare',
    role: 'AI Operator Preparation',
    title: 'Compiles a Structured, Evidence-Backed Dispute Dossier',
    desc: 'Assembles the complete dispute packet: Order ID, SKU specifications, master weight verification, carrier manifest timestamps, contractual rate card reference, and pre-drafted claim justification.',
    checks: [
      'Pre-formats dispute justification citing specific policy clauses',
      'Attaches warehouse master SKU specifications and carrier logs',
      'Eliminates hours of manual CSV collation across separate portals',
    ],
    terminalData: {
      title: 'Dispute Dossier Assembly',
      badge: 'Dossier #DOS-2026-REC-0927-408',
      rows: [
        { label: 'Target Channel', val: 'Amazon Seller Support / SAFE-T Claim' },
        { label: 'Policy Reference', val: 'Amazon Fee Schedule 2026 Clause 14.3 (Pantry Goods)' },
        { label: 'Carrier Evidence', val: 'Hub Sorter Scan Manifest #DEL-99120481 attached' },
        { label: 'Product Proof', val: 'SKU Master Spec (Dead Weight 320g, Dimensions 18x12x4cm)' },
        { label: 'Staged Dossier', val: 'Complete & formatted for submission', success: true },
      ],
    },
  },
  {
    step: '04',
    name: 'Approve',
    role: 'Human Operator Sign-Off Gate',
    title: 'Pushes Finding to WhatsApp or Command Console',
    desc: 'Pushes a concise, structured briefing to the designated operator with variance evidence attached. No dispute packet is submitted or balance written off without explicit human authorization.',
    checks: [
      'Mobile-first WhatsApp approval card with 1-click authorization',
      'Desktop Command Console with full multi-line audit drilldown',
      'Role-based authority limits for financial write-offs and claims',
    ],
    terminalData: {
      title: 'Human-in-the-Loop Sign-Off Gate',
      badge: 'WhatsApp Priority Briefing',
      rows: [
        { label: 'Notification', val: 'Sent to Rajesh K. (Head of Finance) at 09:14 AM' },
        { label: 'Summary', val: 'Sanocea identified ₹231.90 overcharge on Order #408-9128491-1182701.' },
        { label: 'Breakdown', val: 'Category creep (₹63.90) + Weight error (₹98.00) + Uncredited return (₹70.00)' },
        { label: 'Evidence Attached', val: '3 verification documents included in packet' },
        { label: 'Operator Action', val: 'AUTHORIZE DISPUTE PACKET (1-Click Approved)', success: true },
      ],
    },
  },
  {
    step: '05',
    name: 'Execute',
    role: 'Governed Channel Action',
    title: 'Stages or Submits for Channel Claim Resolution',
    desc: 'The authorized dispute dossier is formatted ready for submission into marketplace seller support or carrier SLA claim portals. Pre-formatted copy-ready tables allow 1-step submission.',
    checks: [
      'Structured copy-ready dossier for Amazon SAFE-T & Flipkart SPF portals',
      'Direct CSV/JSON export ready for logistics carrier SLA claim upload',
      'Honest boundary: Direct API programmatic filing is in active roadmap',
    ],
    terminalData: {
      title: 'Governed Resolution Staging',
      badge: 'Portal Submission Ready',
      rows: [
        { label: 'Status', val: 'Staged & Formatted for Channel Portal' },
        { label: 'Portal Target', val: 'Amazon Seller Central > Performance > SAFE-T Claims' },
        { label: 'Clipboard Export', val: '1-Click copy formatted claim narrative and table', success: true },
        { label: 'Dispute Docket', val: 'DOCKET-AMZ-2026-0927-408' },
        { label: 'API Capability', val: 'Current: Staged Dossier. Roadmap: Direct API Injection.' },
      ],
    },
  },
  {
    step: '06',
    name: 'Track',
    role: 'Audit Trail & Outcome Verification',
    title: 'Tracks Reimbursement Credit in Future Settlement Batches',
    desc: 'Continuously monitors subsequent marketplace settlement remittance batches to confirm that the approved dispute credit actually arrives in your bank deposit, logging an immutable audit record.',
    checks: [
      'Monitors incoming settlement batches for credit adjustment IDs',
      'Verifies net bank deposit matches authorized recovery amount',
      'Maintains permanent immutable audit log with operator timestamps',
    ],
    terminalData: {
      title: 'Remittance Credit & Audit Verification',
      badge: 'Batch AMZ-IN-SETTLE-2026-W39-B1',
      rows: [
        { label: 'Resolution Batch', val: 'Batch AMZ-IN-SETTLE-2026-W39-B1 (7 Days Later)' },
        { label: 'Credit Credit Line', val: 'SAFE-T Reimbursement Ref #REC-408-9128491' },
        { label: 'Credit Realized', val: '+₹231.90 Bank Deposit Credit Verified', success: true },
        { label: 'Audit Record', val: 'Hash: 0x8a91f3c7b2... (Immutable Log Archived)' },
        { label: 'Final Status', val: 'RECOVERED & CLOSED', success: true },
      ],
    },
  },
]

function WorkflowConsole() {
  const [activeStage, setActiveStage] = useState(0)
  const current = workflowStages[activeStage]

  return (
    <section id="workflow" className="sol-workflow-scene">
      <div className="shell">
        <Reveal className="section-head center">
          <span className="chapter">02 / governed operating model</span>
          <h2>The 6-Stage Sanocea Reconciliation Lifecycle</h2>
          <p style={{ maxWidth: 740, margin: '12px auto 0', color: 'var(--muted)' }}>
            Every settlement discrepancy runs through a disciplined, verified workflow.
            Sanocea investigates with data evidence before any decision is made, keeping your operator in control.
          </p>
        </Reveal>

        <div className="workflow-tabs-strip">
          {workflowStages.map((stg, idx) => (
            <button
              key={stg.step}
              type="button"
              className={`workflow-tab-btn ${activeStage === idx ? 'active' : ''}`}
              onClick={() => setActiveStage(idx)}
            >
              <span className="workflow-tab-num">{stg.step} / {stg.name}</span>
              <span className="workflow-tab-name">{stg.role.split(' ')[0]}</span>
            </button>
          ))}
        </div>

        <div className="workflow-console-display">
          <div className="console-meta-col">
            <span className="console-stage-badge">
              Stage {current.step} · {current.name}
            </span>
            <div className="console-role-tag">{current.role}</div>
            <h3>{current.title}</h3>
            <p>{current.desc}</p>
            <div className="console-check-list">
              {current.checks.map((chk) => (
                <div key={chk} className="console-check-item">
                  <span className="icon">✓</span>
                  <span>{chk}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="console-terminal-col">
            <div className="terminal-header">
              <span className="terminal-title">{current.terminalData.title}</span>
              <span className="terminal-badge">{current.terminalData.badge}</span>
            </div>
            {current.terminalData.rows.map((row) => (
              <div key={row.label} className="terminal-row">
                <span className="terminal-label">{row.label}</span>
                <span className={`terminal-val ${row.alert ? 'alert' : ''} ${row.success ? 'success' : ''}`}>
                  {row.val}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

function EvidenceLab() {
  return (
    <section id="evidence" className="sol-evidence-scene">
      <div className="shell">
        <Reveal className="section-head center">
          <span className="chapter">03 / operational evidence specimen</span>
          <h2>Anatomy of a Sanocea Dispute Dossier</h2>
          <p style={{ maxWidth: 740, margin: '12px auto 0', color: 'var(--muted)' }}>
            Marketplaces reject vague dispute tickets. Sanocea compiles granular order-level evidence
            that proves fee drift, courier weight mismatches, and missing return credits without manual spreadsheet work.
          </p>
        </Reveal>

        <Reveal className="specimen-card">
          <div className="specimen-top">
            <div className="specimen-id-group">
              <span className="specimen-dossier-id">DOS-2026-REC-0927-408</span>
              <span className="specimen-channel-pill">Amazon India · SAFE-T Staged (Example Integration)</span>
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--muted)' }}>
              Order: #408-9128491-1182701 · SKU: GC-MK-BLK-0050G-2P
            </div>
          </div>

          <table className="specimen-table">
            <thead>
              <tr>
                <th>Deduction Item</th>
                <th>Contract / Master Baseline</th>
                <th>Marketplace Remittance Deduction</th>
                <th>Variance / Claim Amount</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Referral Commission Fee</td>
                <td>12.0% (Pantry Goods) = ₹170.40</td>
                <td>16.5% (Snacks Tier Creep) = ₹234.30</td>
                <td style={{ color: '#b91c1c', fontWeight: 600 }}>+₹63.90 (Fee Creep)</td>
              </tr>
              <tr>
                <td>Logistics Shipping Fee</td>
                <td>Dead Weight 320g = ₹82.00</td>
                <td>Volumetric 1,500g = ₹180.00</td>
                <td style={{ color: '#b91c1c', fontWeight: 600 }}>+₹98.00 (Weight Error)</td>
              </tr>
              <tr>
                <td>Reverse Return Fee</td>
                <td>₹0.00 (Customer Cancellation)</td>
                <td>₹70.00 (Courier Return Debit)</td>
                <td style={{ color: '#b91c1c', fontWeight: 600 }}>+₹70.00 (Ghost Return)</td>
              </tr>
              <tr className="total-row">
                <td colSpan="3">Total Recoverable Discrepancy Amount</td>
                <td style={{ color: '#0b8096', fontSize: 15 }}>₹231.90</td>
              </tr>
            </tbody>
          </table>

          <div style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 8, fontFamily: 'var(--font-mono)' }}>
            ATTACHED VERIFICATION PROOFS:
          </div>
          <div className="specimen-proofs">
            <span className="proof-tag">
              📄 SKU-Spec-Sheet-320g.pdf
            </span>
            <span className="proof-tag">
              📦 Courier-Hub-Manifest-DEL99120481.csv
            </span>
            <span className="proof-tag">
              📋 Amazon-Rate-Agreement-2026-Cl14.pdf
            </span>
            <span className="proof-tag">
              🏢 Warehouse-Inbound-Scan-Log-Empty.json
            </span>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

const liveCapabilities = [
  {
    title: 'Multi-Channel Settlement Ingestion',
    detail: 'Parses raw payment settlement and remittance files across connected marketplaces and commerce channels, currently including Amazon, Flipkart, Blinkit, and Shopify. Sanocea can be connected to additional marketplaces and commerce systems where the required APIs, settlement files, exports, or data interfaces are available.',
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
    <section id="roadmap" className="sol-transparency-scene">
      <div className="shell">
        <Reveal className="section-head center">
          <span className="chapter dark">04 / capability transparency</span>
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

const sevenDomains = [
  { num: 'Domain 01', title: 'Catalogue & Listing Health', link: '/#catalogue', desc: 'Syncs titles, attributes, and suppression fixes.' },
  { num: 'Domain 02', title: 'Inventory & Stock Drift', link: '/#inventory', desc: 'Prevents phantom stockouts across warehouses.' },
  { num: 'Domain 03', title: 'Pricing & Promotion Governance', link: '/#pricing', desc: 'Guards minimum margins against runaway discount stacking.' },
  { num: 'Domain 04', title: 'Order Exceptions & Routing', link: '/#orders', desc: 'Detects address issues and multi-channel routing splits.' },
  { num: 'Domain 05', title: 'Fulfilment, SLA & RTO/NDR', link: '/#fulfilment', desc: 'Intercepts non-delivery reports before return dispatch.' },
  { num: 'Domain 06', title: 'Settlement & Reconciliation', link: '/solutions/marketplace-reconciliation', desc: 'Recovers commission creep, uncredited returns, and weight fees.', active: true },
  { num: 'Domain 07', title: 'Marketplace Exceptions & Buy Box', link: '/#exceptions', desc: 'Protects account health metrics and Buy Box eligibility.' },
  { num: 'Architecture', title: 'Zero Rip-and-Replace Stack', link: '/#stack', desc: 'Sits cleanly above Unicommerce, Vinculum, and Shopify.' },
]

function SevenDomainsMap() {
  return (
    <section id="domains" className="sol-domains-scene">
      <div className="shell">
        <Reveal className="section-head center">
          <span className="chapter">05 / operational architecture</span>
          <h2>Part of Sanocea’s 7 Governed Commerce Domains</h2>
          <p style={{ maxWidth: 740, margin: '12px auto 0', color: 'var(--muted)' }}>
            Reconciliation is not an isolated spreadsheet problem — it connects directly to catalogue specifications,
            warehouse fulfilment, and return workflows. Explore how Sanocea governs the entire commerce operating stack.
          </p>
        </Reveal>

        <div className="domains-grid">
          {sevenDomains.map((dom) => (
            <a
              key={dom.num}
              href={dom.link}
              className={`domain-nav-card ${dom.active ? 'active' : ''}`}
            >
              <div>
                <div className="domain-card-num">{dom.num}</div>
                <div className="domain-card-title">{dom.title}</div>
                <p style={{ fontSize: 12.5, color: 'var(--muted)', margin: 0 }}>{dom.desc}</p>
              </div>
              <div className="domain-card-link">
                {dom.active ? '● Current Solution Page' : 'View Domain Architecture →'}
              </div>
            </a>
          ))}
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
    'Sanocea configures around your connected marketplaces and commerce channels using standard API read permissions, webhooks, or approved settlement file exports. Current supported integrations include Amazon, Flipkart, Blinkit, and Shopify, and Sanocea can be connected to additional marketplaces and commerce systems where the required APIs, settlement files, exports, or data interfaces are available. You do not need to migrate existing systems or change your order management software. Credentials are encrypted, and initial diagnostic audits can be run on historical settlement exports without touching live operations.',
  ],
]

function FAQScene() {
  const [openIdx, setOpenIdx] = useState(null)
  return (
    <section id="faqs" className="sol-faq-scene">
      <div className="shell">
        <Reveal className="section-head center">
          <span className="chapter">06 / buyer questions</span>
          <h2>Frequently Asked Questions About Marketplace Reconciliation</h2>
          <p style={{ maxWidth: 680, margin: '12px auto 0', color: 'var(--muted)' }}>
            Common questions from finance heads, founders, and marketplace operations managers.
          </p>
        </Reveal>

        <div className="faq-list" style={{ maxWidth: 860, margin: '36px auto 0' }}>
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
          <span className="chapter dark">Start With Grounded Evidence</span>
          <h2>Audit Your Marketplace & Channel Settlements in 24 Hours</h2>
          <p>
            Send us a sample settlement remittance file and agreed vendor rate card from any of your active commerce channels.
            We will map your fee divergence and isolate hidden leakage across commissions, shipping overcharges, and uncredited returns.
          </p>
          <div style={{ display: 'flex', justifyContent: 'center', gap: 14, flexWrap: 'wrap' }}>
            <a
              className="button primary light"
              href="mailto:hello@sanocea.com?subject=Marketplace%20Settlement%20Audit"
            >
              Request a Settlement Audit
            </a>
            <a className="button ghost dark-btn" href="https://wa.me/919909360065" target="_blank" rel="noopener">
              Chat Directly on WhatsApp
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
            AI-assisted ecommerce operations control for teams selling across multiple channels.
          </p>
        </div>
        <div>
          <strong style={{ display: 'block', fontSize: 12, fontFamily: 'var(--font-mono)', marginBottom: 8, color: 'var(--ink)' }}>SOLUTIONS</strong>
          <span style={{ display: 'block', fontSize: 13, color: 'var(--muted)' }}>Domain 06: Marketplace Reconciliation</span>
          <a href="/#operations" style={{ display: 'block', fontSize: 13, color: 'var(--muted)', marginTop: 4, textDecoration: 'none' }}>All 7 Operational Domains →</a>
          <a href="/#stack" style={{ display: 'block', fontSize: 13, color: 'var(--muted)', marginTop: 4, textDecoration: 'none' }}>Zero Rip-and-Replace OMS Stack →</a>
        </div>
        <div>
          <strong style={{ display: 'block', fontSize: 12, fontFamily: 'var(--font-mono)', marginBottom: 8, color: 'var(--ink)' }}>GOVERNANCE & CONTACT</strong>
          <a href="/#authority" style={{ display: 'block', fontSize: 13, color: 'var(--muted)', textDecoration: 'none' }}>Human Authority & Safeguards →</a>
          <a href="mailto:hello@sanocea.com" style={{ display: 'block', fontSize: 13, color: 'var(--muted)', marginTop: 4, textDecoration: 'none' }}>hello@sanocea.com</a>
          <span style={{ display: 'block', fontSize: 12, color: 'var(--muted)', marginTop: 4 }}>Surat, Gujarat, India · © 2026 SANOCEA™</span>
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
        <ProblemMatrix />
        <WorkflowConsole />
        <EvidenceLab />
        <TransparencyScene />
        <SevenDomainsMap />
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
