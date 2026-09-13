import React, {useState} from 'react'
import {createRoot} from 'react-dom/client'
import {MotionConfig, motion, useScroll, useSpring} from 'framer-motion'
import './styles.css'

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

const packet = [
  ['Problem spotted', 'A channel event comes in with its source, promise, stock and customer details.'],
  ['Sanocea figures out what it is', 'Routine work moves on its own; anything needing a judgment call gets flagged.'],
  ['Sent to the right place', 'Sanocea decides the next step, channel action, or which person should handle it.'],
  ['Proof stays attached', 'Notes, status and next steps travel with the case, so nothing gets lost.'],
]

const cockpit = [
  ['Quick-commerce stock delta', 'Replenishment risk across fast-moving channels', 'Prepare update'],
  ['Amazon SLA breach', 'Dispatch confirmation missing', 'Escalate with evidence'],
  ['Flipkart return hold', 'Policy mismatch', 'Merchant decision'],
  ['Myntra payout gap', 'Deduction variance', 'Build claim pack'],
]

const driftEvents = [
  ['Shopify', 'Catalogue edited', 'new copy'],
  ['Amazon', 'SLA clock running', 'manual check'],
  ['Blinkit', 'Stock changed', 'fast-moving'],
  ['Flipkart', 'Return held', 'policy mismatch'],
]

const heroSignals = [
  ['Input', 'A channel changes stock, promise, payout or return status.'],
  ['AI layer', 'Sanocea classifies the work and prepares the next action.'],
  ['Output', 'Your team gets a clear to-do list, not another manual chase.'],
]

const capabilities = [
  ['Know what the problem is', 'Understand whether an event is stock drift, an SLA risk, a payout issue, a return, or something a customer will feel.'],
  ['Send it to the right place', 'Move each task to the right workflow, approval path or person, with the proof already attached.'],
  ['Inventory accuracy', 'Track stock changes, channel drift and replenishment signals before they become oversells.'],
  ['Order and fulfilment operations', 'Route order work, SLA pressure and fulfilment exceptions to the right queue.'],
  ['Returns, refunds and payouts', 'Prepare policy context, variance checks and evidence before a decision is made.'],
  ['Spot what to automate next', 'Summarize patterns across channels so teams know what should be automated next.'],
]

const faqs = [
  ['Is AI the core feature of Sanocea?', 'Yes. Sanocea uses AI to classify operational signals, prepare next actions, summarize evidence and reduce manual coordination. The execution still follows merchant rules, permissions and approval boundaries.'],
  ['Which ecommerce platforms can Sanocea work with?', 'Sanocea can be configured around almost any marketplace, storefront, fulfillment partner or local channel where the merchant provides approved API access, credentials, exports, webhooks or operating permissions.'],
  ['What ecommerce operations can Sanocea automate?', 'Sanocea is designed for inventory drift, order exceptions, marketplace SLA checks, return and refund workflows, payout reconciliation, customer support handoffs and repeated channel follow-up.'],
  ['Is Sanocea useful for global commerce teams?', 'Yes. Sanocea is built for sellers operating across global marketplaces, regional channels, storefronts, fulfillment partners and internal tools.'],
  ['Does Sanocea replace an order management system?', 'Sanocea can support order operations and exception workflows, but the right architecture depends on the existing commerce stack, marketplace access and operational process.'],
  ['Do platform logos imply official partnerships?', 'No. Logos are example surfaces only. They do not imply partnership, certification or guaranteed integration availability.'],
]

const outcomes = [
  ['Inventory operations', 'Detect stock drift, oversell risk and replenishment pressure before teams discover it manually.'],
  ['Order exception management', 'Prepare the next action for delayed dispatch, fulfillment gaps and channel-specific SLA pressure.'],
  ['Returns and refunds', 'Summarize policy context, customer history and approval requirements before money moves.'],
  ['Payout reconciliation', 'Collect fee, refund, deduction and settlement evidence into a controlled review queue.'],
]

const useCases = [
  ['Marketplace operations automation', 'Turn repeated marketplace checks into AI-prepared workflows across Amazon, eBay, Walmart, Etsy, Shopee, Mercado Libre and regional channels.'],
  ['Multichannel inventory control', 'Keep storefront and marketplace availability aligned when stock changes faster than spreadsheets or manual updates.'],
  ['Ecommerce exception workflow', 'Route unusual orders, return disputes, payout gaps and fulfillment problems to the right person with evidence attached.'],
  ['AI ecommerce operations layer', 'Use AI to classify signals and prepare work, while the merchant keeps final authority over sensitive actions.'],
]

const workflowExamples = [
  {
    issue: 'Oversell risk',
    signal: 'A fast-moving channel changes available stock before the storefront and marketplace counts agree.',
    prepares: ['Classifies inventory drift', 'Attaches SKU and channel context', 'Prepares controlled stock update'],
    result: 'Inventory workflow ready',
  },
  {
    issue: 'Return dispute',
    signal: 'Customer context, marketplace policy and warehouse status do not point to the same answer.',
    prepares: ['Summarizes policy context', 'Builds the evidence pack', 'Routes for approval'],
    result: 'Refund decision prepared',
  },
  {
    issue: 'Payout variance',
    signal: 'A settlement includes fees, deductions or refunds the team has to prove before closing accounts.',
    prepares: ['Collects order history', 'Matches deduction evidence', 'Queues finance review'],
    result: 'Claim pack assembled',
  },
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
    <a className="brand" href="#top" aria-label="Sanocea home">
      <img src={LOGO} alt="Sanocea" />
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
          <a href="#capabilities" onClick={() => setOpen(false)}>Capabilities</a>
          <a href="#intercept" onClick={() => setOpen(false)}>Workflow</a>
          <a href="#coverage" onClick={() => setOpen(false)}>Platforms</a>
          <a href="#cockpit" onClick={() => setOpen(false)}>Cockpit</a>
          <a className="nav-cta" href="#diagnostic" onClick={() => setOpen(false)}>Diagnose flow</a>
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
          <p className="eyebrow">AI commerce operations</p>
          <h1 aria-label="AI operations layer for every commerce channel.">
            AI operations.
            <br />
            Every channel.
          </h1>
          <p>
            Sanocea turns marketplace noise, inventory drift, order exceptions, returns and payout
            gaps into AI-prepared workflows across global marketplaces, storefronts, fulfillment
            partners and regional channels.
          </p>
          <div className="hero-actions">
            <a className="button primary" href="#fragment">Watch the breakage</a>
            <a className="button ghost" href="#diagnostic">Start diagnostic</a>
          </div>
          <div className="hero-signal-flow" aria-label="How Sanocea converts channel events into controlled work">
            {heroSignals.map((item, index) => (
              <RevealItem key={item[0]} index={index} delay={0.15}>
                <span>{item[0]}</span>
                <p>{item[1]}</p>
              </RevealItem>
            ))}
          </div>
          <div className="planet-strip" aria-label="Example commerce platforms">
            <span className="planet-strip-core">Global channels, regional channels, custom channels</span>
            <div className="planet-strip-window">
              <div className="planet-strip-track">
                {[...channelExamples.slice(0, 9), ...channelExamples.slice(0, 9)].map((p, index) => (
                  <PlatformLogo key={`${p.name}-${index}`} platform={p} />
                ))}
              </div>
            </div>
          </div>
          <small className="mark-note">
            Example surfaces only. Sanocea can be configured around the platforms and tools a merchant
            provides access to; no partnership or certification is implied.
          </small>
        </div>
        <CommerceField />
      </div>
    </section>
  )
}

function OutcomesScene() {
  return (
    <section className="outcomes-scene">
      <div className="shell outcomes-layout">
        <Reveal>
          <span className="chapter">What you get</span>
          <h2>Less channel chasing. More controlled commerce execution.</h2>
        </Reveal>
        <div className="outcomes-grid">
          {outcomes.map((item, index) => (
            <RevealItem key={item[0]} index={index}>
              <strong>{item[0]}</strong>
              <p>{item[1]}</p>
            </RevealItem>
          ))}
        </div>
      </div>
    </section>
  )
}

function FragmentScene() {
  return (
    <section id="fragment" className="scene fragment-scene">
      <div className="shell fragment-layout">
        <Reveal as="div" className="fragment-intro">
          <span className="chapter">01 / fragmentation</span>
          <h2>Commerce does not break all at once. It drifts.</h2>
          <p>
            One channel knows the order. Another has the stock. A third owns the customer promise.
            People end up joining the dots by hand.
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

function BottleneckScene() {
  return (
    <section className="scene bottleneck-scene">
      <div className="shell bottleneck-layout">
        <Reveal>
          <span className="chapter dark">02 / human bottleneck</span>
          <h2>Then the operator becomes the integration layer.</h2>
          <p>
            Check a marketplace SLA. Compare storefront stock. Verify a fulfillment update.
            Reply to support. Reconcile payout. Repeat until order volume grows faster than the human loop can keep up.
          </p>
        </Reveal>
        <div className="pressure-chamber">
          <div className="inbox-stack">
            {['Amazon SLA', 'Blinkit stock', 'Flipkart return', 'Payout gap'].map((item, index) => (
              <RevealItem as="div" className={`inbox-card q${index}`} key={item} index={index} y={16}>
                <span>0{index + 1}</span>
                <strong>{item}</strong>
                <small>{index === 1 ? 'needs stock truth' : 'waiting on human'}</small>
              </RevealItem>
            ))}
          </div>
          <div className="operator-core">
            <span>manual queue</span>
            <strong>87%</strong>
            <small>context switching</small>
          </div>
          <div className="human-loop">
            <span>copy</span>
            <span>check</span>
            <span>ask</span>
            <span>reply</span>
          </div>
          <div className="pressure-lines" />
        </div>
      </div>
    </section>
  )
}

function InterceptScene() {
  return (
    <section id="intercept" className="scene intercept-scene">
      <div className="shell split">
        <Reveal as="div" className="sticky-story">
          <span className="chapter">04 / interception</span>
          <h2>Sanocea uses AI to intercept work before it becomes a meeting.</h2>
          <p>
            Sanocea captures what happened, keeps the evidence attached and routes the next action —
            without pretending every channel is magically certified or universally integrated.
          </p>
        </Reveal>
        <div className="intercept-board" aria-label="Sanocea turns manual channel checks into prepared workflows">
          <div className="intercept-stage stage-before">
            <span>Manual loop</span>
            {[['Amazon SLA?', 'open tab'], ['Stock mismatch', 'check sheet'], ['Return dispute', 'ask team'], ['Payout gap', 'collect proof']].map(([title, note], index) => (
              <RevealItem key={title} index={index} y={14}>
                <b>{title}</b>
                <small>{note}</small>
              </RevealItem>
            ))}
          </div>
          <div className="intercept-processing">
            <div className="packet-chip">signal</div>
            <div className="processor-card">
              <img src={LOGO} alt="Sanocea" />
              <strong>What Sanocea does</strong>
              <div className="processor-steps">
                <span>Figure out what it is</span>
                <span>Attach the proof</span>
                <span>Send it onward</span>
              </div>
            </div>
          </div>
          <div className="intercept-stage stage-after">
            <span>Prepared queue</span>
            {[['SLA risk routed', 'owner assigned'], ['Stock workflow ready', 'evidence attached'], ['Return needs approval', 'policy included'], ['Payout review queued', 'claim pack ready']].map(([title, note], index) => (
              <RevealItem key={title} index={index} delay={0.25} y={14}>
                <b>{title}</b>
                <small>{note}</small>
              </RevealItem>
            ))}
          </div>
          <div className="intercept-track">
            <i />
          </div>
          <div className="intercept-caption">
            <span>Before: people join the dots</span>
            <span>After: Sanocea prepares the work</span>
          </div>
        </div>
      </div>
    </section>
  )
}

function CapabilitiesScene() {
  return (
    <section id="capabilities" className="scene capabilities-scene">
      <div className="shell">
        <Reveal as="div" className="section-head">
          <span className="chapter">03 / what Sanocea controls</span>
          <h2>AI workflows for the work behind multichannel growth.</h2>
          <p>
            Sanocea turns channel noise into prepared work: classify the signal, route the task,
            attach the evidence and keep human approval where the business needs it.
          </p>
        </Reveal>
        <div className="capability-grid">
          {capabilities.map((item, index) => (
            <RevealItem key={item[0]} index={index}>
              <span />
              <strong>{item[0]}</strong>
              <p>{item[1]}</p>
            </RevealItem>
          ))}
        </div>
      </div>
    </section>
  )
}

function PacketScene() {
  return (
    <section id="packet" className="scene packet-scene">
      <div className="shell">
        <Reveal as="div" className="section-head">
          <span className="chapter">05 / one case, start to finish</span>
          <h2>Follow one problem from alert to fix.</h2>
        </Reveal>
        <div className="packet-rail">
          <Reveal as="div" className="packet-card" delay={0.1}>
            <span>Order #4827</span>
            <strong>One case file</strong>
            <p>Everything about this order — the channel, the customer, the stock, the proof, and what happens next — stays together in one place.</p>
          </Reveal>
          <div className="rail-line">
            <i />
          </div>
          <div className="packet-steps">
            {packet.map((step, index) => (
              <RevealItem key={step[0]} index={index} delay={0.2}>
                <span>0{index + 1}</span>
                <strong>{step[0]}</strong>
                <p>{step[1]}</p>
              </RevealItem>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

function PlatformCoverageScene() {
  return (
    <section id="coverage" className="scene coverage-scene">
      <div className="shell">
        <Reveal as="div" className="section-head center">
          <span className="chapter">06 / platform coverage</span>
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
            <strong>If the merchant can provide access, Sanocea can design the AI operations layer around it.</strong>
          </div>
          <p>
            The point is not one logo. It is one operating model across the real stack a seller already has.
          </p>
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

function UseCaseScene() {
  return (
    <section className="scene usecase-scene">
      <div className="shell">
        <Reveal as="div" className="section-head">
          <span className="chapter">Searchable operations</span>
          <h2>Built for the ecommerce work buyers are actually searching to solve.</h2>
          <p>
            Sanocea is not a generic AI assistant. It is an AI ecommerce operations layer for the
            recurring work behind marketplace growth, multichannel inventory control, order exception
            handling, return workflows and payout reconciliation.
          </p>
        </Reveal>
        <div className="usecase-grid">
          {useCases.map((item, index) => (
            <RevealItem key={item[0]} index={index}>
              <span />
              <strong>{item[0]}</strong>
              <p>{item[1]}</p>
            </RevealItem>
          ))}
        </div>
      </div>
    </section>
  )
}

function WorkflowProofScene() {
  return (
    <section className="scene workflow-proof-scene">
      <div className="shell workflow-proof-layout">
        <Reveal as="div" className="section-head center">
          <span className="chapter">AI work preparation</span>
          <h2>What Sanocea actually does before your team opens another tab.</h2>
          <p>
            The AI advantage is not a chatbot on top of commerce. It is a prepared operating packet:
            the signal is classified, evidence is attached, risk is named and the next controlled workflow
            is ready for the person or rule that owns it.
          </p>
        </Reveal>
        <div className="workflow-film" aria-label="Example AI-prepared ecommerce workflows">
          {workflowExamples.map((item, index) => (
            <RevealItem className="workflow-example" key={item.issue} index={index} amount={0.25}>
              <div className="workflow-index">0{index + 1}</div>
              <div className="workflow-signal">
                <span>Incoming signal</span>
                <h3>{item.issue}</h3>
                <p>{item.signal}</p>
              </div>
              <div className="workflow-route" aria-hidden="true">
                <i />
                <i />
                <i />
              </div>
              <div className="workflow-prepares">
                <span>AI prepares</span>
                {item.prepares.map((step) => <b key={step}>{step}</b>)}
              </div>
              <div className="workflow-result">
                <span>Controlled output</span>
                <strong>{item.result}</strong>
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
    <section className="scene authority-scene">
      <div className="shell authority-layout">
        <Reveal>
          <span className="chapter dark">07 / who's allowed to act</span>
          <h2>AI does the prep work. You still make the final call.</h2>
          <p>
            Sanocea can sort, summarize and recommend. But inventory changes, refunds, payouts and anything
            that touches a customer still follow your rules and need your approval.
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

function CockpitScene() {
  return (
    <section id="cockpit" className="scene cockpit-scene">
      <div className="shell cockpit-layout">
        <Reveal>
          <span className="chapter">08 / today's problem list</span>
          <h2>This isn't just a dashboard. It's a ready-to-act list of what needs you today.</h2>
          <p>Routine work runs itself. The stuff that needs a person shows up with context, proof, and a suggested next step already attached.</p>
        </Reveal>
        <div className="cockpit-panel">
          <div className="panel-head">
            <span>open issues right now</span>
            <b>4 open</b>
          </div>
          {cockpit.map((row, index) => (
            <RevealItem key={row[0]} index={index} y={16}>
              <span>0{index + 1}</span>
              <strong>{row[0]}</strong>
              <p>{row[1]}</p>
              <small>{row[2]}</small>
            </RevealItem>
          ))}
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
          <span className="chapter dark">10 / diagnostic</span>
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
          <a className="button primary light" href="mailto:hello@sanocea.com?subject=Sanocea%20operations%20diagnostic">Request diagnostic</a>
          <a className="button ghost dark-btn" href="https://wa.me/919909360065" target="_blank" rel="noreferrer">Chat on WhatsApp</a>
        </div>
      </div>
    </section>
  )
}

function FAQScene() {
  return (
    <section className="scene faq-scene">
      <div className="shell faq-layout">
        <Reveal as="div" className="section-head center">
          <span className="chapter">09 / questions buyers ask</span>
          <h2>Frequently asked questions about commerce operations control.</h2>
        </Reveal>
        <div className="faq-list">
          {faqs.map((item, index) => (
            <RevealItem as="details" key={item[0]} index={index} y={14} amount={0.6}>
              <summary>{item[0]}</summary>
              <p>{item[1]}</p>
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
          <img src={MANPREET} alt="Manpreet Gulati" loading="lazy" />
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
          <p>AI commerce operations control for teams selling across channels.</p>
        </div>
        <div>
          <span>Sanocea, operated by Manpreet Gulati</span>
          <span>GSTIN 24CDUPG6401L1ZB</span>
          <span>Surat, Gujarat, India</span>
        </div>
        <div>
          <a href="mailto:hello@sanocea.com">hello@sanocea.com</a>
          <span>© 2026 Sanocea</span>
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
        <OutcomesScene />
        <FragmentScene />
        <BottleneckScene />
        <CapabilitiesScene />
        <InterceptScene />
        <PacketScene />
        <PlatformCoverageScene />
        <UseCaseScene />
        <WorkflowProofScene />
        <AuthorityScene />
        <CockpitScene />
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
