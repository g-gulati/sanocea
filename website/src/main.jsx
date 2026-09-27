import React, {useState} from 'react'
import {createRoot} from 'react-dom/client'
import {MotionConfig, motion, useScroll, useSpring} from 'framer-motion'
import './styles.css'
import HomeProof from './homepage-proof/HomeProof.jsx'

const LOGO = import.meta.env.BASE_URL + 'sanocea-wordmark.png'
const MANPREET = import.meta.env.BASE_URL + 'manpreet-gulati.jpg'
const ICON = 'https://cdn.simpleicons.org'
const LOGOS = import.meta.env.BASE_URL + 'logos/'

const REVEAL_EASE = [0.16, 1, 0.3, 1]

const platforms = [
  {name: 'Shopify', slug: 'shopify', color: '7AB55C', logo: LOGOS + 'shopify.svg'},
  {name: 'Amazon', slug: 'amazon', color: 'FF9900', logo: LOGOS + 'amazon.svg'},
  {name: 'eBay', slug: 'ebay', color: 'E53238', logo: LOGOS + 'ebay.svg'},
  {name: 'Walmart', slug: 'walmart', color: '0071CE', logo: LOGOS + 'walmart.svg'},
  {name: 'Etsy', slug: 'etsy', color: 'F16521', logo: LOGOS + 'etsy.svg'},
  {name: 'WooCommerce', slug: 'woocommerce', color: '96588A', logo: LOGOS + 'woocommerce.svg'},
]

const channelExamples = [
  ...platforms,
  {name: 'BigCommerce', slug: 'bigcommerce', color: '121118', logo: LOGOS + 'bigcommerce.svg'},
  {name: 'Shopee', slug: 'shopee', color: 'EE4D2D', logo: LOGOS + 'shopee.svg'},
  {name: 'Mercado Libre', slug: 'mercadolibre', color: 'FFE600', logo: LOGOS + 'mercadolibre.svg'},
]

const platformMarkLibrary = {
  Amazon: {name: 'Amazon', slug: 'amazon', color: 'FF9900', short: 'a'},
  eBay: {name: 'eBay', slug: 'ebay', color: 'E53238', short: 'e'},
  Walmart: {name: 'Walmart', slug: 'walmart', color: '0071CE', short: 'W'},
  Etsy: {name: 'Etsy', slug: 'etsy', color: 'F16521', short: 'E'},
  Shopify: {name: 'Shopify', slug: 'shopify', color: '7AB55C', short: 'S'},
  WooCommerce: {name: 'WooCommerce', slug: 'woocommerce', color: '96588A', short: 'W'},
  BigCommerce: {name: 'BigCommerce', slug: 'bigcommerce', color: '121118', short: 'B'},
  Shopee: {name: 'Shopee', slug: 'shopee', color: 'EE4D2D', short: 'S'},
  'Mercado Libre': {name: 'Mercado Libre', slug: 'mercadolibre', color: 'FFE600', short: 'ML'},
  Rakuten: {name: 'Rakuten', color: 'BF0000', short: 'R', logo: LOGOS + 'rakuten.svg'},
  'Adobe Commerce': {name: 'Adobe Commerce', slug: 'adobe', color: 'FF0000', short: 'A'},
  Wix: {name: 'Wix', color: '0C6EFC', short: 'W', logo: LOGOS + 'wix.svg'},
  Flipkart: {name: 'Flipkart', color: '2874F0', short: 'f', logo: LOGOS + 'flipkart.png'},
  Meesho: {name: 'Meesho', color: '5C1D91', short: 'm', logo: LOGOS + 'meesho.png'},
  Myntra: {name: 'Myntra', color: 'FF3F6C', short: 'M', logo: LOGOS + 'myntra.png'},
  AJIO: {name: 'AJIO', color: '1E293B', short: 'A'},
  'Tata CLiQ': {name: 'Tata CLiQ', color: '7C3AED', short: 'T', logo: LOGOS + 'tata-cliq.png'},
  Nykaa: {name: 'Nykaa', color: 'E80071', short: 'N', logo: LOGOS + 'nykaa.png'},
  Blinkit: {name: 'Blinkit', color: 'F8D33A', short: 'b', logo: LOGOS + 'blinkit.png'},
  Zepto: {name: 'Zepto', color: '3B166B', short: 'Z'},
  Instamart: {name: 'Instamart', color: 'FC5B18', short: 'I', logo: LOGOS + 'instamart.png'},
  'Flipkart Minutes': {name: 'Flipkart Minutes', color: '2874F0', short: 'FM', logo: LOGOS + 'flipkart-minutes.png'},
  'Amazon Now': {name: 'Amazon Now', color: 'FF9900', short: 'a', logo: LOGOS + 'amazon.svg'},
}

const coveragePlatforms = [
  ['Global marketplaces', ['Amazon', 'eBay', 'Walmart', 'Etsy', 'Rakuten', 'Shopee', 'Mercado Libre']],
  ['Commerce storefronts', ['Shopify', 'WooCommerce', 'BigCommerce', 'Adobe Commerce', 'Wix']],
  ['Regional marketplaces', ['Flipkart', 'Meesho', 'Myntra', 'AJIO', 'Tata CLiQ', 'Nykaa']],
  ['Local commerce and fulfillment', ['Blinkit', 'Zepto', 'Instamart', 'Flipkart Minutes', 'Amazon Now']],
]

const accessModes = ['API access', 'Credentials', 'Exports', 'Webhooks', 'Private apps', 'Internal tools']

const fracture = [
  ['Catalogue changed', 'Shopify has the new PDP, marketplaces still carry yesterday copy.', 'PDP'],
  ['Stock drift', 'Fast-moving channel availability changes before the master sheet catches up.', 'INV'],
  ['SLA pressure', 'Amazon dispatch promise is now a decision, not a reminder.', 'SLA'],
  ['Return ambiguity', 'Policy says one thing, customer context says another.', 'RTN'],
  ['Payout gap', 'Fees, refunds and deductions need evidence before action.', 'FIN'],
]

const driftEvents = [
  ['Shopify', 'Catalogue edited', 'new copy'],
  ['Amazon', 'SLA clock running', 'manual check'],
  ['Blinkit', 'Stock changed', 'fast-moving'],
  ['Flipkart', 'Return held', 'policy mismatch'],
]

const operatingLoop = [
  {
    step: '01',
    badge: 'MONITOR',
    title: 'Find the problem',
    desc: 'Continuously monitors multi-channel signals: a Blinkit stock-out on a high-velocity SKU, an Amazon listing price drift, a Flipkart return discrepancy, or an impending dispatch SLA breach.',
  },
  {
    step: '02',
    badge: 'EVIDENCE',
    title: 'Investigate root cause',
    desc: 'Gathers cross-channel evidence automatically: correlates warehouse WMS stock, channel pricing policies, and courier logs to isolate why the exception occurred without manual spreadsheet work.',
  },
  {
    step: '03',
    badge: 'DRAFT',
    title: 'Prepare the action',
    desc: 'Drafts the precise remediation: stock rebalance update, MAP price correction, courier NDR reattempt ticket, or return dispute evidence pack — formatted and ready for review.',
  },
  {
    step: '04',
    badge: 'GOVERN',
    title: 'Approve where required',
    desc: 'Routes high-stakes decisions (pricing overrides, refund approvals, stock transfers) to the responsible operator with all evidence attached. Nothing sensitive executes without explicit sign-off.',
  },
  {
    step: '05',
    badge: 'EXECUTE',
    title: 'Execute safely',
    desc: 'Executes approved actions directly across target channels and tools via guarded, idempotent API mutations and workflow steps — eliminating manual portal logging.',
  },
  {
    step: '06',
    badge: 'AUDIT',
    title: 'Track the outcome',
    desc: 'Verifies that the channel reflected the update, confirms SLA compliance or stock replenishment, and records an immutable audit log of who approved and what changed.',
  },
]

const operationalDomains = [
  {
    id: 'domain-catalogue',
    icon: 'CAT',
    title: 'Catalogue & Listing Operations',
    tagline: 'Suppression Prevention & PDP Drift',
    catches: 'Missing mandatory marketplace attributes, unmapped category tags, broken image URLs, and title/bullet drift between Shopify master listings and Amazon/Flipkart portals.',
    action: 'Correlates master PIM data, validates compliance criteria against marketplace taxonomy, and drafts catalog fixes ready for bulk submission.',
    impact: 'Zero listing suppression downtime & uniform multi-channel PDPs',
  },
  {
    id: 'domain-inventory',
    icon: 'INV',
    title: 'Real-Time Inventory Drift & Stock Sync',
    tagline: 'Dark Store Buffers & Phantom Stock',
    catches: 'Stock divergence between warehouse WMS, dark store partners (Blinkit, Zepto, Instamart), and marketplaces before overselling happens.',
    action: 'Monitors real-time consumption velocity, calculates safety stock buffers per dark store, and prepares replenishment orders or safety freezes.',
    impact: 'Eliminates out-of-stock seller penalties & phantom inventory overselling',
  },
  {
    id: 'domain-pricing',
    icon: 'PRC',
    title: 'Competitive & Channel Pricing',
    tagline: 'Buy Box Protection & MAP Guardrails',
    catches: 'Unauthorized seller discounting, cross-channel price disparity (e.g. Blinkit cheaper than Amazon), unintended coupon stacking, and margin erosion.',
    action: 'Evaluates real-time net margin after commission and shipping fees, verifies minimum advertised price (MAP) rules, and drafts governed price adjustments.',
    impact: 'Protected gross margins & automated Buy Box price parity',
  },
  {
    id: 'domain-orders',
    icon: 'ORD',
    title: 'Order Operations & Stuck Triage',
    tagline: 'Stranded Orders & Split Dispatch',
    catches: 'Orders stuck in pending verification, unassigned warehouse lines, payment capture failures, and multi-line orders awaiting split dispatch.',
    action: 'Pinpoints the blocking bottleneck (payment gateway lag, unmapped SKU, courier unserviceability), re-routes to backup nodes, and clears stuck queues.',
    impact: 'Reduces manual order intervention by 80% & protects on-time dispatch SLAs',
  },
  {
    id: 'domain-fulfilment',
    icon: 'FUL',
    title: 'Fulfilment, SLA & RTO/NDR Management',
    tagline: 'Courier Escalation & Non-Delivery Triage',
    catches: 'Imminent dispatch SLA breaches, courier non-delivery reports (NDR) with false "customer unavailable" reasons, and high-risk RTO patterns.',
    action: 'Automates customer address validation via WhatsApp, triggers automated reattempts before return initiation, and files courier SLA violation disputes.',
    impact: 'Reduces RTO rates by up to 25% & safeguards top-tier seller badges',
  },
  {
    id: 'domain-reconciliation',
    icon: 'REC',
    title: 'Marketplace Fee & Payout Reconciliation',
    tagline: 'Settlement Audits & Deduction Claims',
    catches: 'Commission tier overcharging, volumetric vs dead weight courier discrepancies, uncredited return deductions, and missing bank remittances.',
    action: 'Audits remittance advice files line-by-line against agreed contract rate cards, generates dispute evidence packets with invoices/AWBs, and tracks dispute status.',
    impact: 'Recovers 2–5% in lost marketplace revenue from erroneous fee deductions',
  },
  {
    id: 'domain-exceptions',
    icon: 'EXP',
    title: 'Marketplace Exceptions & Account Health',
    tagline: 'Listing Health & Voice of Customer (VOC)',
    catches: 'Voice-of-the-customer (VOC) defect spikes, brand gating infringements, buyer-seller messaging policy violations, and account suspension alerts.',
    action: 'Synthesizes negative feedback signals, drafts root-cause action plans (POA), and alerts brand managers before platform strikes occur.',
    impact: 'Proactively protects account health metrics & avoids listing deactivation',
  },
]

const comparisonPoints = [
  {
    dimension: 'Core purpose',
    agency: 'Manual services & outsourced staff',
    oms: 'Transaction & order sync plumbing',
    genericAi: 'Text generation & conversational chat',
    sanocea: 'AI-assisted operational exception automation',
  },
  {
    dimension: 'System relationship',
    agency: 'Replaces your time with human billables',
    oms: 'Core connectivity layer (orders, catalog sync)',
    genericAi: 'Isolated tool with no commerce context',
    sanocea: 'Operates on top of your existing OMS & channels',
  },
  {
    dimension: 'Exception resolution',
    agency: 'Manual portal clicking during office hours',
    oms: 'Flags errors in log files for you to solve',
    genericAi: 'Unverified suggestions without real data',
    sanocea: 'Finds, investigates, drafts, and executes fixes',
  },
  {
    dimension: 'Human control & governance',
    agency: 'Varies by individual human worker skill',
    oms: 'Strict rule-based binary switches',
    genericAi: 'Autonomous hallucinations or zero safety gates',
    sanocea: 'Configurable approval boundaries & full audit trails',
  },
  {
    dimension: 'Coverage across channels',
    agency: 'Limited to dedicated portal managers',
    oms: 'Marketplaces and webstores only',
    genericAi: 'Generic web prompts',
    sanocea: 'Global & regional marketplaces, quick commerce, storefronts',
  },
  {
    dimension: 'Response speed',
    agency: 'Hours or days (business hours)',
    oms: 'Batch sync cycles (no decision layer)',
    genericAi: 'Instant text, zero operational action',
    sanocea: 'Continuous 24/7 monitoring & instant prep',
  },
]

const faqs = [
  [
    'Does Sanocea replace our order management system (like Unicommerce)?',
    'No. Sanocea is explicitly built not to replace your existing commerce systems. Platforms such as Unicommerce, Vinculum, and Shopify manage your transaction routing, inventory broadcast, and shipping label generation. Sanocea sits above and around them as an intelligent operations layer — finding operational exceptions, investigating root causes, preparing verified remediations, and executing approved fixes directly across your channels.',
    '#stack',
    'View Strategic Architecture →',
  ],
  [
    'Why do marketplace payouts diverge from actual bank settlements, and how does Sanocea reconcile them?',
    'Marketplace settlements routinely diverge from expected bank remittances due to hidden commission tier creep, closing fee reclassifications, courier weight overcharging (charging volumetric weight over actual dead weight), and uncredited customer return deductions. Sanocea automatically ingests your marketplace settlement files, reconciles every order line against your agreed master rate cards and WMS weight logs, flags overcharges, and compiles dispute evidence packets to recover lost revenue.',
    '#domain-reconciliation',
    'Explore Payout Reconciliation →',
  ],
  [
    'How can Sanocea automate ecommerce operations across Amazon, Flipkart, and Blinkit in India?',
    'Sanocea bridges global marketplaces (Amazon), regional channels (Flipkart, Myntra, Nykaa), quick-commerce dark stores (Blinkit, Zepto, Instamart), and storefront platforms like Shopify. Sanocea can connect to additional marketplaces and commerce systems wherever standard APIs, webhooks, or settlement exports are available. It continuously watches for stockout drift, suppressed listings, SLA countdown risks, and price discrepancies across your channels. When an issue occurs, Sanocea assembles the evidence and prepares the exact remediation for your team to approve via WhatsApp or Console.',
    '#coverage',
    'See Supported Platforms →',
  ],
  [
    'How does Sanocea reduce RTO (Return to Origin) and resolve courier NDR exceptions?',
    'When a courier logs an NDR (Non-Delivery Report)—frequently claiming "customer not available" or "incomplete address"—Sanocea immediately initiates automated customer verification via WhatsApp to confirm landmark details and reschedule preferred delivery windows before courier return workflows trigger. If an NDR reason is confirmed fraudulent or delayed by carrier negligence, Sanocea auto-generates SLA dispute tickets.',
    '#domain-fulfilment',
    'See Fulfilment & NDR Management →',
  ],
  [
    'How does Sanocea prevent phantom stock and stockouts across quick-commerce dark stores (Blinkit, Zepto, Instamart)?',
    'Quick-commerce channels experience rapid, localized demand spikes that traditional hourly sync jobs miss, leading to phantom stock or stockouts. Sanocea tracks SKU run-rates per dark store, flags warehouse stock mismatches in real time, and alerts your team with prepared stock transfers or safe buffer adjustments before platform out-of-stock penalties hit.',
    '#domain-inventory',
    'Explore Inventory Sync →',
  ],
  [
    'What causes Amazon and Flipkart listing suppressions, and how does Sanocea prevent lost sales?',
    'Listings are commonly suppressed due to missing mandatory regulatory attributes (country of origin, manufacturer pack details, GTIN exemption tags), non-compliant main image backgrounds, or character count limits altered during marketplace taxonomy updates. Sanocea flags suppression warnings instantly, extracts required values from your master catalogue, and formats the listing fix ready for one-click re-submission.',
    '#domain-catalogue',
    'Explore Catalogue Operations →',
  ],
  [
    'Why choose AI-assisted operations instead of hiring an ecommerce operations agency?',
    'Traditional ecommerce agencies rely on outsourced human staff manually logging into seller portals, toggling spreadsheets, and working limited office hours with high monthly retainers. Sanocea operates 24/7, detects cross-channel drift in real time, investigates root causes with data evidence, and drafts actions for your approval — allowing a lean internal team to handle 10x the operational volume without hiring additional staff.',
    '#comparison',
    'View Sanocea vs Agency Comparison →',
  ],
  [
    'How does Sanocea keep humans in control of sensitive inventory and financial decisions?',
    'Sanocea enforces strict policy boundaries. Routine background checks and data correlations occur automatically, but sensitive actions — such as price adjustments exceeding defined thresholds, dark store stock transfers, and refund approvals — require explicit human sign-off via WhatsApp or the Console. Nothing executes without authority, and every action leaves an immutable audit trail.',
    '#authority',
    'Review Governance & Authority →',
  ],
  [
    'How does AI reduce marketplace operations work without making hallucinated errors?',
    'Sanocea does not use generic AI chatbots to make unverified changes. Instead, deterministic domain logic and specialized models classify operational signals, correlate evidence across channel APIs and sheets, and prepare standardized remediations. Execution is governed by deterministic business policies and human approval boundaries, preventing hallucinations.',
    '#loop',
    'Review the 6-Stage Loop →',
  ],
  [
    'What ecommerce operations does Sanocea automate?',
    'Sanocea automates seven core operational domains: 1) Catalogue and listing operations, 2) Real-time inventory drift and stock sync, 3) Competitive and channel pricing, 4) Order operations and stuck order triage, 5) Fulfilment, SLA tracking, and RTO/NDR management, 6) Marketplace fee and payout reconciliation, and 7) Marketplace exceptions and listing suppression remediation.',
    '#operations',
    'Browse All 7 Operational Domains →',
  ],
  [
    'What happens when an exception cannot be resolved automatically?',
    'Nothing is silently dropped or queued indefinitely. Every unresolved exception is surfaced with the evidence already collected and routed to the designated operator. Approvals have time boundaries and escalate if unanswered. Where Sanocea acts on a live connection, it retries only when safe, and escalates to a person the moment manual intervention is required.',
    '#cockpit',
    'See Real Exception Handling →',
  ],
  [
    'What does getting started with Sanocea actually require?',
    'Sanocea configures around your existing channels and tools using approved API keys, webhooks, or export permissions. It works alongside your current OMS, warehouse software, or spreadsheets without requiring you to migrate systems. Credentials are encrypted and validated before anything goes live.',
    '#diagnostic',
    'Start an Operations Diagnostic →',
  ],
]

const diagnosticSteps = [
  ['Map', 'Identify where your team still checks channels manually every day.'],
  ['Prioritize', 'Separate routine automation from judgement-heavy approval work.'],
  ['Design', 'Turn one repeated intervention into a governed AI-prepared workflow.'],
]

const trustPoints = [
  ['Access-based setup', 'Integrations depend on the accounts, credentials, APIs, exports or permissions a merchant can provide.'],
  ['No false platform claims', 'Platform marks are examples only and do not imply partnership, certification or guaranteed availability.'],
  ['Operator-led AI', 'AI prepares the work; sensitive inventory, refund, payout and customer-impacting actions stay controlled.'],
]

function orbitTrack(index, count) {
  const steps = 8
  const angleOffset = (index / count) * Math.PI * 2 - Math.PI / 2
  const radiusX = 31
  const radiusY = 29

  return Array.from({length: steps + 1}, (_, step) => {
    const angle = angleOffset + (step / steps) * Math.PI * 2
    return {
      left: `${50 + Math.cos(angle) * radiusX}%`,
      top: `${50 + Math.sin(angle) * radiusY}%`,
    }
  })
}

function Logo() {
  return (
    <a className="brand" href="#top" aria-label="SANOCEA™ home">
      <img src={LOGO} alt="SANOCEA™ — AI-assisted ecommerce operations" />
    </a>
  )
}

function Reveal({as = 'div', className, children, delay = 0, amount = 0.35, y = 26, duration = 0.62, ...rest}) {
  const MotionTag = motion[as] || motion.div
  return (
    <MotionTag
      className={className}
      initial={{opacity: 0, y}}
      whileInView={{opacity: 1, y: 0}}
      viewport={{once: true, amount}}
      transition={{duration, delay, ease: REVEAL_EASE}}
      {...rest}
    >
      {children}
    </MotionTag>
  )
}

function RevealItem({as = 'article', className, children, index = 0, stagger = 0.07, amount = 0.4, y = 22, ...rest}) {
  const MotionTag = motion[as] || motion.article
  return (
    <MotionTag
      className={className}
      initial={{opacity: 0, y}}
      whileInView={{opacity: 1, y: 0}}
      viewport={{once: true, amount}}
      transition={{duration: 0.5, delay: index * stagger, ease: REVEAL_EASE}}
      {...rest}
    >
      {children}
    </MotionTag>
  )
}

function Header() {
  const [open, setOpen] = useState(false)
  return (
    <header className="topbar">
      <div className="shell nav-shell">
        <Logo />
        <nav className={open ? 'nav-links open' : 'nav-links'} aria-label="Primary navigation">
          <a href="#fragment" onClick={() => setOpen(false)}>Problem</a>
          <a href="#stack" onClick={() => setOpen(false)}>OMS Integration</a>
          <a href="#loop" onClick={() => setOpen(false)}>Workflow</a>
          <a href="#operations" onClick={() => setOpen(false)}>Operations</a>
          <a href="#cockpit" onClick={() => setOpen(false)}>Live Proof</a>
          <a href="#comparison" onClick={() => setOpen(false)}>Comparison</a>
          <a href="#coverage" onClick={() => setOpen(false)}>Platforms</a>
          <a href="/demo.html" target="_blank" rel="noopener" onClick={() => setOpen(false)}>Live demo ↗</a>
          <a className="nav-cta" href="#diagnostic" onClick={() => setOpen(false)}>Audit my operation</a>
        </nav>
        <button className="menu" type="button" aria-label="Toggle menu" onClick={() => setOpen(!open)}>
          <span />
          <span />
        </button>
      </div>
    </header>
  )
}

function PlatformLogo({platform, label = true}) {
  const [imgFailed, setImgFailed] = useState(false)
  const source = platform.logo || (platform.slug ? `${ICON}/${platform.slug}/${platform.color}` : '')
  const initials = platform.short || platform.name.split(' ').map((word) => word[0]).join('').slice(0, 2)
  const showImage = Boolean(source) && !imgFailed
  return (
    <span className="logo-pill">
      <span
        className={showImage ? 'logo-mark logo-mark--image' : 'logo-mark'}
        style={{'--mark-color': platform.color ? `#${platform.color}` : '#11c6dc'}}
      >
        {showImage ? (
          <img
            src={source}
            alt={`${platform.name} logo`}
            loading="lazy"
            className="logo-mark-svg"
            onError={() => setImgFailed(true)}
          />
        ) : (
          <span aria-hidden="true">{initials}</span>
        )}
      </span>
      {label && <span>{platform.name}</span>}
    </span>
  )
}

function LogoMark({name}) {
  const platform = channelExamples.find((item) => item.name === name) || platformMarkLibrary[name] || {
    name,
    color: '11C6DC',
    short: name.slice(0, 2),
  }

  return <PlatformLogo platform={platform} />
}

function StoryRail() {
  const {scrollYProgress} = useScroll()
  const scaleY = useSpring(scrollYProgress, {stiffness: 120, damping: 24})
  return (
    <aside className="story-rail" aria-hidden="true">
      <span>calm</span>
      <motion.i style={{scaleY}} />
      <span>controlled</span>
    </aside>
  )
}

function CommerceField({mode = 'calm'}) {
  const active = mode === 'active'
  const orbitDuration = active ? 22 : 28
  return (
    <div className={`commerce-field ${mode}`}>
      <div className="field-topline">
        <span>{active ? 'interception layer active' : 'multi-channel field'}</span>
        <b>{active ? 'routing' : 'calm'}</b>
      </div>
      <div className="field-grid" />
      <div className="field-orbit o1" />
      <div className="field-orbit o2" />
      <div className="field-orbit o3" />
      <div className="orbit-signal s1" />
      <div className="orbit-signal s2" />
      <div className="orbit-signal s3" />
      {channelExamples.map((platform, i) => {
        const track = orbitTrack(i, channelExamples.length)
        return (
          <motion.div
            className="platform-node"
            key={platform.name}
            style={track[0]}
            animate={{
              left: track.map((point) => point.left),
              top: track.map((point) => point.top),
            }}
            transition={{
              duration: orbitDuration,
              repeat: Infinity,
              ease: 'linear',
              delay: -orbitDuration * (i / channelExamples.length),
            }}
          >
            <PlatformLogo platform={platform} />
          </motion.div>
        )
      })}
      <div className="core-node">
        <img src={LOGO} alt="Sanocea" />
        <b>keeps it all together</b>
      </div>
      <div className="field-readout">
        <span>Catalogue</span>
        <span>Inventory</span>
        <span>Orders</span>
        <span>Payouts</span>
      </div>
    </div>
  )
}

function ManualDriftBoard() {
  return (
    <div className="manual-drift" aria-label="Manual ecommerce operations drifting out of sync">
      <div className="manual-topline">
        <span>without automation</span>
        <b>truth drift in progress</b>
      </div>
      <div className="manual-lanes">
        {driftEvents.map((event, index) => {
          const platform = channelExamples.find((item) => item.name === event[0]) || {
            name: event[0],
            ...(platformMarkLibrary[event[0]] || {color: '11C6DC', short: event[0].slice(0, 2)}),
          }
          return (
            <article className={`manual-card d${index}`} key={event[0]}>
              <PlatformLogo platform={platform} />
              <strong>{event[1]}</strong>
              <span>{event[2]}</span>
            </article>
          )
        })}
      </div>
      <div className="manual-sheet" aria-hidden="true">
        <div className="sheet-head">
          <span>shared sheet</span>
          <b>last touched 14 min ago</b>
        </div>
        {['SKU-118 stock: 23', 'Amazon promise: today', 'Blinkit stock: 0?', 'Return: waiting'].map((row, index) => (
          <div className={`sheet-row r${index}`} key={row}>
            <span>{row}</span>
            <i>{index === 2 ? 'conflict' : 'stale'}</i>
          </div>
        ))}
      </div>
      <div className="manual-cursor">
        <span>copy</span>
      </div>
      <div className="manual-thread t1">ask fulfilment</div>
      <div className="manual-thread t2">check payout</div>
      <div className="manual-thread t3">reply support</div>
    </div>
  )
}

function Hero() {
  return (
    <section id="top" className="hero scene">
      <div className="shell hero-grid">
        <div className="hero-copy">
          <div className="hero-eyebrow">
            <span className="hero-eyebrow-dot" />
            <span>AI-ASSISTED ECOMMERCE OPERATIONS</span>
          </div>
          <h1>
            AI-assisted ecommerce operations.
            <br />
            Automate the repetitive work — with humans in control.
          </h1>
          <p className="hero-lead">
            SANOCEA™ helps ecommerce businesses automate repetitive operational work across catalogue,
            inventory, pricing, orders, fulfilment, reconciliation, and marketplace exceptions —
            while keeping your team in control of every important decision.
          </p>
          <div className="hero-actions">
            <a className="button primary" href="#diagnostic">Audit my commerce operation</a>
            <a className="button ghost" href="/demo.html" target="_blank" rel="noopener">Experience live demo ↗</a>
          </div>
          <div className="hero-clarity-strip" aria-label="SANOCEA core positioning summary">
            <div className="clarity-col">
              <span className="clarity-label">What it is</span>
              <strong>AI-assisted operations layer</strong>
            </div>
            <div className="clarity-col">
              <span className="clarity-label">Who it is for</span>
              <strong>Multichannel brands & marketplace sellers</strong>
            </div>
            <div className="clarity-col">
              <span className="clarity-label">What it automates</span>
              <strong>Catalogue, inventory, pricing, orders & reconciliation</strong>
            </div>
            <div className="clarity-col">
              <span className="clarity-label">Stack relationship</span>
              <strong>Augments existing OMS (e.g. Unicommerce) — no migration</strong>
            </div>
          </div>
          <div className="planet-strip" aria-label="Connected commerce channels and marketplaces">
            <span className="planet-strip-core">Connects across marketplaces, storefronts, and quick commerce</span>
            <div className="planet-strip-window">
              <div className="planet-strip-track">
                {[...channelExamples.slice(0, 9), ...channelExamples.slice(0, 9)].map((p, index) => (
                  <PlatformLogo key={`${p.name}-${index}`} platform={p} />
                ))}
              </div>
            </div>
          </div>
          <small className="mark-note">
            Example surfaces only. Sanocea configures around the platforms, OMS, and tools a merchant
            provides access to; no partnership or certification is implied.
          </small>
        </div>
        <CommerceField />
      </div>
    </section>
  )
}

function FragmentScene() {
  return (
    <section id="fragment" className="scene fragment-scene">
      <div className="shell fragment-layout">
        <Reveal as="div" className="fragment-intro">
          <span className="chapter">01 / operational fragmentation</span>
          <h2>Commerce does not break all at once. It drifts.</h2>
          <p>
            One channel knows the order. Another has the stock. A third owns the customer promise.
            People end up joining the dots by hand across tabs and spreadsheets.
          </p>
          <p className="fragment-punch">
            The problem isn't lack of software — it's that teams spend 80% of their time manually investigating
            and fixing exceptions across channels one portal at a time.
          </p>
          <p className="fragment-punch">
            You don't usually find out from a dashboard. You find out from an angry customer, a suppressed listing,
            or an unexpected marketplace deduction.
          </p>
        </Reveal>
        <div className="fragment-grid">
          <ManualDriftBoard />
          <div className="fracture-list">
            {fracture.map((item, index) => (
              <RevealItem key={item[0]} className="fracture-item" index={index}>
                <span>{item[2]}</span>
                <strong>{item[0]}</strong>
                <p>{item[1]}</p>
              </RevealItem>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

function StackScene() {
  return (
    <section id="stack" className="scene stack-scene">
      <div className="shell">
        <Reveal as="div" className="section-head center">
          <span className="chapter">02 / strategic architecture</span>
          <h2>Existing commerce systems handle transactions.<br />Sanocea automates the operational work and decisions around them.</h2>
          <p className="stack-lede">
            Sanocea does <strong>not</strong> replace your order management system (OMS), ERP, or store connectivity.
            Platforms like Unicommerce, Shopify, and Vinculum route orders, broadcast inventory, and generate shipping labels.
            Sanocea operates <em>above and around them</em> — catching exceptions, investigating root causes,
            preparing verified remediations, and asking for human sign-off before executing.
          </p>
        </Reveal>
        <Reveal as="div" className="stack-architecture-diagram" delay={0.1}>
          <div className="arch-tier tier-channels">
            <div className="tier-header">
              <span className="tier-num">01</span>
              <strong>Sales & Demand Channels</strong>
              <span>Amazon · Flipkart · Blinkit · Instamart · Zepto · Shopify · Myntra · Nykaa</span>
            </div>
            <p>Where customer promises and sales happen across marketplaces, storefronts, and dark stores.</p>
          </div>
          <div className="arch-connector-line">
            <span>transactions, catalog push, order routing</span>
          </div>
          <div className="arch-tier tier-oms">
            <div className="tier-header">
              <span className="tier-num">02</span>
              <strong>Core Transaction & Connectivity Systems</strong>
              <span>Unicommerce · Vinculum · Shopify Backend · Custom ERP / WMS</span>
            </div>
            <p>Systems of record that maintain inventory ledgers, sync orders, and produce courier shipping labels.</p>
          </div>
          <div className="arch-connector-line accent">
            <span>continuous exception detection, root-cause investigation, prepared remediations</span>
          </div>
          <div className="arch-tier tier-sanocea">
            <div className="tier-header">
              <span className="tier-badge">INTELLIGENCE & ACTION</span>
              <strong>SANOCEA™ AI-Assisted Operations Layer</strong>
              <span>Find → Investigate → Prepare → Approve → Execute → Track</span>
            </div>
            <div className="sanocea-arch-grid">
              <div className="sanocea-arch-col">
                <b>Catches Drift</b>
                <span>Dark store stockout, MAP price drop, stranded order, deduction mismatch</span>
              </div>
              <div className="sanocea-arch-col">
                <b>Investigates Cause</b>
                <span>Queries WMS, compares fee schedules, inspects courier NDR events</span>
              </div>
              <div className="sanocea-arch-col">
                <b>Governs Decision</b>
                <span>Prepares fix with attached proof; operator approves in WhatsApp or Console</span>
              </div>
              <div className="sanocea-arch-col">
                <b>Executes & Audits</b>
                <span>Triggers idempotent channel mutation and leaves complete audit trail</span>
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

function OperatingLoopScene() {
  return (
    <section id="loop" className="scene loop-scene">
      <div className="shell">
        <Reveal as="div" className="section-head center">
          <span className="chapter">03 / operational workflow</span>
          <h2>The 6-stage AI-assisted operations loop.</h2>
          <p>
            Every operational exception runs through a disciplined, verified lifecycle.
            Sanocea investigates with data evidence before any decision is made, keeping humans in control where it matters.
          </p>
          <div className="workflow-sequence-strip" aria-hidden="true">
            <span>Find</span> → <span>Investigate</span> → <span>Prepare</span> → <span>Approve</span> → <span>Execute</span> → <span>Track</span>
          </div>
        </Reveal>
        <div className="loop-grid-6">
          {operatingLoop.map((item, index) => (
            <RevealItem className="loop-card-v2" key={item.step} index={index}>
              <div className="loop-card-top">
                <span className="loop-step-badge">{item.step}</span>
                <span className="loop-type-pill">{item.badge}</span>
              </div>
              <strong>{item.title}</strong>
              <p>{item.desc}</p>
            </RevealItem>
          ))}
        </div>
      </div>
    </section>
  )
}

function OperationalDomainsScene() {
  return (
    <section id="operations" className="scene domains-scene">
      <div className="shell">
        <Reveal as="div" className="section-head center">
          <span className="chapter">04 / operational coverage</span>
          <h2>Seven operational domains automated across your commerce channels.</h2>
          <p>
            From quick-commerce dark stores to global marketplaces, Sanocea removes manual drudgery
            across every critical pillar of ecommerce operations.
          </p>
          <div className="domains-quick-nav" aria-label="Operational domains quick navigation">
            {operationalDomains.map((d) => (
              <a key={d.id} href={`#${d.id}`} className="domains-quick-pill">
                {d.icon} · {d.title.split('&')[0].trim()}
              </a>
            ))}
          </div>
        </Reveal>
        <div className="domains-grid">
          {operationalDomains.map((domain, index) => (
            <RevealItem className="domain-card" key={domain.title} index={index} id={domain.id}>
              <div className="domain-card-head">
                <span className="domain-tag">{domain.icon}</span>
                <div>
                  <strong>{domain.title}</strong>
                  <span className="domain-tagline">{domain.tagline}</span>
                </div>
              </div>
              <div className="domain-detail-block">
                <span className="domain-detail-label">What Sanocea catches</span>
                <p>{domain.catches}</p>
              </div>
              <div className="domain-detail-block">
                <span className="domain-detail-label">Prepared action</span>
                <p>{domain.action}</p>
              </div>
              <div className="domain-impact">
                <span className="impact-dot" />
                <span>{domain.impact}</span>
              </div>
              <a href="#loop" className="domain-link">See how this runs in the 6-stage workflow →</a>
            </RevealItem>
          ))}
        </div>
      </div>
    </section>
  )
}

function ComparisonScene() {
  return (
    <section id="comparison" className="scene comparison-scene">
      <div className="shell">
        <Reveal as="div" className="section-head center">
          <span className="chapter dark">06 / clear differentiation</span>
          <h2>How Sanocea compares to alternative approaches.</h2>
          <p className="dark-sub">
            Why AI-assisted operations is fundamentally different from hiring an ecommerce agency,
            buying an all-in-one OMS, or running generic AI chatbots.
          </p>
        </Reveal>
        <Reveal as="div" className="comparison-table-wrapper" delay={0.1}>
          <table className="comparison-table">
            <thead>
              <tr>
                <th>Operational Dimension</th>
                <th>Traditional Agency</th>
                <th>Commerce OMS (e.g. Unicommerce)</th>
                <th>Generic AI / Chatbots</th>
                <th className="highlight-col">SANOCEA™</th>
              </tr>
            </thead>
            <tbody>
              {comparisonPoints.map((row, index) => (
                <tr key={index}>
                  <td className="comp-dim">{row.dimension}</td>
                  <td>{row.agency}</td>
                  <td>{row.oms}</td>
                  <td>{row.genericAi}</td>
                  <td className="highlight-cell">{row.sanocea}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Reveal>
      </div>
    </section>
  )
}

function PlatformCoverageScene() {
  return (
    <section id="coverage" className="scene coverage-scene">
      <div className="shell">
        <Reveal as="div" className="section-head center">
          <span className="chapter">07 / platform coverage</span>
          <h2>Bring the platforms you use. Sanocea builds the operating layer around them.</h2>
          <p>
            Whether the platform is global, regional, marketplace, storefront, fulfillment, quick-commerce
            or internal, Sanocea can work around approved API access, credentials, exports, webhooks or
            operating permissions. No partnership or certification is implied.
          </p>
        </Reveal>
        <Reveal as="div" className="coverage-anywhere" delay={0.1}>
          <div>
            <span>Any workable surface</span>
            <strong>The point is not one logo. It is one operating model across the real stack a seller already has.</strong>
          </div>
          <div className="coverage-access" aria-label="Supported access patterns">
            {accessModes.map((mode) => <span key={mode}>{mode}</span>)}
          </div>
        </Reveal>
        <div className="coverage-grid">
          {coveragePlatforms.map((group, index) => (
            <RevealItem key={group[0]} className="coverage-card" index={index}>
              <span>{group[0]}</span>
              <div>
                {group[1].map((name) => <LogoMark key={name} name={name} />)}
              </div>
            </RevealItem>
          ))}
        </div>
      </div>
    </section>
  )
}

function AuthorityScene() {
  return (
    <section id="authority" className="scene authority-scene">
      <div className="shell authority-layout">
        <Reveal>
          <span className="chapter dark">08 / governance & authority</span>
          <h2>AI does the prep work. You still make the final call.</h2>
          <p>
            Sanocea can sort, summarize and recommend. But inventory changes, refunds, payouts and anything
            that touches a customer still get escalated to the right authority &mdash; your warehouse team,
            key account manager or management &mdash; and need approval before anything moves.
          </p>
        </Reveal>
        <div className="authority-console">
          <Reveal as="div" className="authority-panel ai-panel" delay={0.1}>
            <label>AI prepares</label>
            <article>
              <span>Signal</span>
              <strong>Return looks policy-sensitive</strong>
            </article>
            <article>
              <span>Recommendation</span>
              <strong>Draft response, request evidence, hold refund</strong>
            </article>
          </Reveal>
          <div className="policy-gate">
            <span>who decides</span>
            <b>you (or your rules) do</b>
          </div>
          <Reveal as="div" className="authority-panel execution-panel" delay={0.2}>
            <label>what actually happens</label>
            <article>
              <span>Allowed</span>
              <strong>Attach evidence pack</strong>
            </article>
            <article>
              <span>Blocked</span>
              <strong>No refund without authority</strong>
            </article>
          </Reveal>
        </div>
      </div>
    </section>
  )
}

function Diagnostic() {
  return (
    <section id="diagnostic" className="scene diagnostic-scene">
      <div className="shell diagnostic-box">
        <Reveal as="div">
          <span className="chapter dark">10 / audit my commerce operation</span>
          <h2>Find one daily intervention worth automating first.</h2>
          <p>
            Start with the repeated work that still needs a person every day: inventory drift, marketplace
            exceptions, returns, support handoffs or reconciliation.
          </p>
        </Reveal>
        <div className="diagnostic-steps">
          {diagnosticSteps.map((step, index) => (
            <RevealItem key={step[0]} index={index} delay={0.15}>
              <span>{step[0]}</span>
              <p>{step[1]}</p>
            </RevealItem>
          ))}
        </div>
        <div className="hero-actions">
          <a
            className="button primary light"
            href="mailto:hello@sanocea.com?subject=Sanocea%20operations%20diagnostic"
          >
            Audit my commerce operation
          </a>
          <a className="button ghost dark-btn" href="https://wa.me/919909360065" target="_blank" rel="noreferrer">Chat on WhatsApp</a>
        </div>
      </div>
    </section>
  )
}

function FAQScene() {
  return (
    <section id="faq" className="scene faq-scene">
      <div className="shell faq-layout">
        <Reveal as="div" className="section-head center">
          <span className="chapter">09 / buyer & ai search questions</span>
          <h2>Frequently asked questions about commerce operations control.</h2>
          <p className="faq-subhead">
            Common questions from ecommerce founders, operations heads, and multichannel marketplace sellers.
          </p>
        </Reveal>
        <div className="faq-list">
          {faqs.map((item, index) => (
            <RevealItem as="details" key={item[0]} index={index} y={14} amount={0.6}>
              <summary>{item[0]}</summary>
              <div className="faq-answer-wrap">
                <p>{item[1]}</p>
                {item[2] && (
                  <a href={item[2]} className="faq-internal-link">
                    {item[3] || 'Learn more →'}
                  </a>
                )}
              </div>
            </RevealItem>
          ))}
        </div>
      </div>
    </section>
  )
}

function FounderProfile() {
  return (
    <section className="founder-section">
      <div className="shell founder-card">
        <div className="founder-image">
          <img src={MANPREET} alt="Manpreet Gulati, Founder of Sanocea" loading="lazy" />
        </div>
        <Reveal as="div" className="founder-copy" delay={0.1}>
          <span className="chapter">Founder profile</span>
          <h2>Manpreet Gulati</h2>
          <p>
            Manpreet leads Sanocea with a focus on practical AI for commerce operations: the daily work behind
            inventory, orders, returns, payouts and channel exceptions that should become easier as teams grow.
          </p>
          <p>
            Sanocea is built for operators who want AI to reduce manual follow-up across marketplaces,
            storefronts and regional channels while keeping business authority under control.
          </p>
          <div className="trust-grid">
            {trustPoints.map((item, index) => (
              <RevealItem key={item[0]} index={index} delay={0.2} y={14}>
                <strong>{item[0]}</strong>
                <p>{item[1]}</p>
              </RevealItem>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  )
}

function Footer() {
  return (
    <footer>
      <div className="shell footer-grid">
        <div>
          <Logo />
          <p>AI-assisted ecommerce operations control for teams selling across channels.</p>
        </div>
        <div>
          <span>SANOCEA™, operated by Manpreet Gulati</span>
          <span>GSTIN 24CDUPG6401L1ZB</span>
          <span>Surat, Gujarat, India</span>
        </div>
        <div>
          <a href="mailto:hello@sanocea.com">
            hello@sanocea.com
          </a>
          <span>© 2026 SANOCEA™</span>
        </div>
      </div>
    </footer>
  )
}

function Progress() {
  const {scrollYProgress} = useScroll()
  const scaleX = useSpring(scrollYProgress, {stiffness: 130, damping: 24})
  return <motion.div className="scroll-progress" style={{scaleX}} />
}

function App() {
  return (
    <>
      <StoryRail />
      <Progress />
      <Header />
      <main>
        <Hero />
        <FragmentScene />
        <StackScene />
        <OperatingLoopScene />
        <OperationalDomainsScene />
        <HomeProof />
        <ComparisonScene />
        <PlatformCoverageScene />
        <AuthorityScene />
        <FAQScene />
        <Diagnostic />
        <FounderProfile />
      </main>
      <Footer />
    </>
  )
}

createRoot(document.getElementById('root')).render(
  <MotionConfig reducedMotion="never">
    <App />
  </MotionConfig>,
)
