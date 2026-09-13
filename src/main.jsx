import React, {useState} from 'react'
import {createRoot} from 'react-dom/client'
import {MotionConfig, motion, useScroll, useSpring} from 'framer-motion'
import './styles.css'

const LOGO = import.meta.env.BASE_URL + 'sanocea-wordmark.png'
const MANPREET = import.meta.env.BASE_URL + 'manpreet-gulati.jpg'
const ICON = 'https://cdn.simpleicons.org'

const platforms = [
  {name: 'Shopify', slug: 'shopify', color: '7AB55C'},
  {name: 'Amazon', logo: 'https://www.amazon.com/favicon.ico'},
  {name: 'eBay', logo: 'https://www.google.com/s2/favicons?domain=ebay.com&sz=64'},
  {name: 'Walmart', logo: 'https://www.google.com/s2/favicons?domain=walmart.com&sz=64'},
  {name: 'Etsy', logo: 'https://www.google.com/s2/favicons?domain=etsy.com&sz=64'},
  {name: 'WooCommerce', slug: 'woocommerce', color: '96588A'},
]

const channelExamples = [
  ...platforms,
  {name: 'BigCommerce', logo: 'https://www.google.com/s2/favicons?domain=bigcommerce.com&sz=64'},
  {name: 'Shopee', logo: 'https://www.google.com/s2/favicons?domain=shopee.com&sz=64'},
  {name: 'Mercado Libre', logo: 'https://www.google.com/s2/favicons?domain=mercadolibre.com&sz=64'},
]

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
  ['Signal captured', 'Channel event enters with source, promise, stock and customer context.'],
  ['Work classified', 'The system separates routine execution from judgement-heavy exceptions.'],
  ['Route selected', 'Sanocea chooses the next workflow, channel action or human handoff.'],
  ['Evidence attached', 'Notes, status, account context and next action stay with the packet.'],
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

const proof = [
  ['AI operating layer', 'Signals are classified, routed and prepared before they become manual coordination work.'],
  ['Human work reduced', 'Teams spend time on decisions and approvals, not copy-paste channel checking.'],
  ['Bring any platform', 'Sanocea can work around approved APIs, exports, webhooks, credentials and operating access.'],
]

const capabilities = [
  ['AI signal classification', 'Understand whether an event is stock drift, SLA risk, payout variance, return pressure or customer-impacting work.'],
  ['AI-assisted routing', 'Move each task to the right workflow, approval path or human queue with evidence already attached.'],
  ['Inventory accuracy', 'Track stock changes, channel drift and replenishment signals before they become oversells.'],
  ['Order and fulfilment operations', 'Route order work, SLA pressure and fulfilment exceptions through a governed queue.'],
  ['Returns, refunds and payouts', 'Prepare policy context, variance checks, evidence packs and approval boundaries.'],
  ['Operational intelligence', 'Summarize patterns across channels so teams know what should be automated next.'],
]

const faqs = [
  ['Is AI the core feature of Sanocea?', 'Yes. Sanocea uses AI to classify operational signals, prepare next actions, summarize evidence and reduce manual coordination. The execution still follows merchant rules, permissions and approval boundaries.'],
  ['Which ecommerce platforms can Sanocea work with?', 'Sanocea can be configured around almost any marketplace, storefront, fulfillment partner or local channel where the merchant provides approved API access, credentials, exports, webhooks or operating permissions.'],
  ['Does Sanocea replace an order management system?', 'Sanocea can support order operations and exception workflows, but the right architecture depends on the existing commerce stack, marketplace access and operational process.'],
  ['Can Sanocea support global sellers?', 'Yes. The operating model is designed for global and regional commerce teams that sell across marketplaces, storefronts and fulfillment channels.'],
  ['Do platform logos imply official partnerships?', 'No. Logos are example surfaces only. They do not imply partnership, certification or guaranteed integration availability.'],
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
  const [failed, setFailed] = useState(false)
  const source = platform.logo || `${ICON}/${platform.slug}/${platform.color}`
  return (
    <span className="logo-pill">
      {!failed && (
        <img
          src={source}
          alt=""
          loading="lazy"
          onError={() => setFailed(true)}
        />
      )}
      {label && <span>{platform.name}</span>}
    </span>
  )
}

function LogoMark({name}) {
  const domainMap = {
    AJIO: 'ajio.com',
    'Tata CLiQ': 'tatacliq.com',
    Nykaa: 'nykaa.com',
    'Flipkart Minutes': 'flipkart.com',
    'Amazon Now': 'amazon.in',
    BigCommerce: 'bigcommerce.com',
    'Adobe Commerce': 'business.adobe.com',
    Wix: 'wix.com',
    eBay: 'ebay.com',
    Walmart: 'walmart.com',
    Etsy: 'etsy.com',
    Rakuten: 'rakuten.com',
    Shopee: 'shopee.com',
    'Mercado Libre': 'mercadolibre.com',
  }
  const platform = channelExamples.find((item) => item.name === name) || {
    name,
    logo: `https://www.google.com/s2/favicons?domain=${domainMap[name] || `${name.toLowerCase().replaceAll(' ', '')}.com`}&sz=64`,
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
        <b>continuity layer</b>
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
            logo: `https://www.google.com/s2/favicons?domain=${event[0].toLowerCase()}.com&sz=64`,
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
          <h1 aria-label="AI work layer for every commerce channel.">
            AI work layer.
            <br />
            Every channel.
          </h1>
          <p>
            Sanocea uses AI to classify, route and prepare the daily work behind inventory,
            orders, returns, payouts and exceptions across global marketplaces, storefronts,
            fulfillment partners and regional channels.
          </p>
          <div className="hero-actions">
            <a className="button primary" href="#fragment">Watch the breakage</a>
            <a className="button ghost" href="#diagnostic">Start diagnostic</a>
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

function ProofScene() {
  return (
    <section className="proof-scene" aria-label="Sanocea operating advantages">
      <div className="shell proof-grid">
        {proof.map((item) => (
          <article key={item[0]}>
            <strong>{item[0]}</strong>
            <p>{item[1]}</p>
          </article>
        ))}
      </div>
    </section>
  )
}

function FragmentScene() {
  return (
    <section id="fragment" className="scene fragment-scene">
      <div className="shell fragment-layout">
        <div className="fragment-intro">
          <span className="chapter">01 / fragmentation</span>
          <h2>Commerce does not break all at once. It drifts.</h2>
          <p>
            One channel knows the order. Another has the stock. A third owns the customer promise.
            People end up joining the dots by hand.
          </p>
        </div>
        <div className="fragment-grid">
          <ManualDriftBoard />
          <div className="fracture-list">
            {fracture.map((item, index) => (
              <motion.article
                key={item[0]}
                className="fracture-item"
                initial={{opacity: 0, y: 24}}
                whileInView={{opacity: 1, y: 0}}
                viewport={{once: true, amount: 0.45}}
                transition={{delay: index * 0.06}}
              >
                <span>{item[2]}</span>
                <strong>{item[0]}</strong>
                <p>{item[1]}</p>
              </motion.article>
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
        <div>
          <span className="chapter dark">02 / human bottleneck</span>
          <h2>Then the operator becomes the integration layer.</h2>
          <p>
            Check a marketplace SLA. Compare storefront stock. Verify a fulfillment update.
            Reply to support. Reconcile payout. Repeat until order volume grows faster than the human loop can keep up.
          </p>
        </div>
        <div className="pressure-chamber">
          <div className="inbox-stack">
            {['Amazon SLA', 'Blinkit stock', 'Flipkart return', 'Payout gap'].map((item, index) => (
              <div className={`inbox-card q${index}`} key={item}>
                <span>0{index + 1}</span>
                <strong>{item}</strong>
                <small>{index === 1 ? 'needs stock truth' : 'waiting on human'}</small>
              </div>
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
        <div className="sticky-story">
          <span className="chapter">04 / interception</span>
          <h2>Sanocea uses AI to intercept work before it becomes a meeting.</h2>
          <p>
            The AI operating layer captures what happened, keeps the evidence attached and routes the
            next action without pretending every channel is magically certified or universally integrated.
          </p>
        </div>
        <CommerceField mode="active" />
      </div>
    </section>
  )
}

function CapabilitiesScene() {
  return (
    <section id="capabilities" className="scene capabilities-scene">
      <div className="shell">
        <div className="section-head">
          <span className="chapter">03 / what Sanocea controls</span>
          <h2>AI workflows for the work behind multichannel growth.</h2>
          <p>
            Sanocea turns channel noise into prepared work: classify the signal, route the task,
            attach the evidence and keep human approval where the business needs it.
          </p>
        </div>
        <div className="capability-grid">
          {capabilities.map((item) => (
            <article key={item[0]}>
              <span />
              <strong>{item[0]}</strong>
              <p>{item[1]}</p>
            </article>
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
        <div className="section-head">
          <span className="chapter">05 / continuity packet</span>
          <h2>Follow one packet from signal to resolution.</h2>
        </div>
        <div className="packet-rail">
          <div className="packet-card">
            <span>ORD-4827</span>
            <strong>Continuity packet</strong>
            <p>One operational object carries channel, customer, inventory, evidence and next action.</p>
          </div>
          <div className="rail-line">
            <i />
          </div>
          <div className="packet-steps">
            {packet.map((step, index) => (
              <article key={step[0]}>
                <span>0{index + 1}</span>
                <strong>{step[0]}</strong>
                <p>{step[1]}</p>
              </article>
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
        <div className="section-head center">
          <span className="chapter">06 / platform coverage</span>
          <h2>Bring the platforms you use. Sanocea builds the operating layer around them.</h2>
          <p>
            Whether the platform is global, regional, marketplace, storefront, fulfillment, quick-commerce
            or internal, Sanocea can work around approved API access, credentials, exports, webhooks or
            operating permissions. No partnership or certification is implied.
          </p>
        </div>
        <div className="coverage-anywhere">
          <div>
            <span>Any workable surface</span>
            <strong>If the merchant can provide access, Sanocea can design the AI work layer around it.</strong>
          </div>
          <p>
            The point is not one logo. It is one operating model across the real stack a seller already has.
          </p>
          <div className="coverage-access" aria-label="Supported access patterns">
            {accessModes.map((mode) => <span key={mode}>{mode}</span>)}
          </div>
        </div>
        <div className="coverage-grid">
          {coveragePlatforms.map((group) => (
            <article key={group[0]} className="coverage-card">
              <span>{group[0]}</span>
              <div>
                {group[1].map((name) => <LogoMark key={name} name={name} />)}
              </div>
            </article>
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
        <div>
          <span className="chapter dark">07 / authority boundary</span>
          <h2>AI prepares the work. Authority stays controlled.</h2>
          <p>
            Sanocea can classify, summarize, recommend and prepare actions. Inventory, refunds, payouts
            and customer-impacting work still follow merchant rules, evidence and approval boundaries.
          </p>
        </div>
        <div className="authority-console">
          <div className="authority-panel ai-panel">
            <label>AI prepares</label>
            <article>
              <span>Signal</span>
              <strong>Return looks policy-sensitive</strong>
            </article>
            <article>
              <span>Recommendation</span>
              <strong>Draft response, request evidence, hold refund</strong>
            </article>
          </div>
          <div className="policy-gate">
            <span>operating authority</span>
            <b>human / rule approval</b>
          </div>
          <div className="authority-panel execution-panel">
            <label>controlled execution</label>
            <article>
              <span>Allowed</span>
              <strong>Attach evidence pack</strong>
            </article>
            <article>
              <span>Blocked</span>
              <strong>No refund without authority</strong>
            </article>
          </div>
        </div>
      </div>
    </section>
  )
}

function CockpitScene() {
  return (
    <section id="cockpit" className="scene cockpit-scene">
      <div className="shell cockpit-layout">
        <div>
          <span className="chapter">08 / exception cockpit</span>
          <h2>The final screen is not a dashboard. It is an AI-prepared decision queue.</h2>
          <p>Routine work keeps moving. Exceptions arrive with context, evidence and an AI-prepared next action.</p>
        </div>
        <div className="cockpit-panel">
          <div className="panel-head">
            <span>live exception queue</span>
            <b>4 open</b>
          </div>
          {cockpit.map((row, index) => (
            <article key={row[0]}>
              <span>0{index + 1}</span>
              <strong>{row[0]}</strong>
              <p>{row[1]}</p>
              <small>{row[2]}</small>
            </article>
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
        <span className="chapter dark">10 / diagnostic</span>
        <h2>Find the daily intervention that should become a governed workflow.</h2>
        <p>
          Start with the bottleneck that still needs a person every day: inventory drift, marketplace
          exceptions, returns, support handoffs or reconciliation.
        </p>
        <div className="hero-actions">
          <a className="button primary light" href="mailto:hello@sanocea.com?subject=Sanocea%20operations%20diagnostic">Email Sanocea</a>
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
        <div className="section-head center">
          <span className="chapter">09 / questions buyers ask</span>
          <h2>Frequently asked questions about commerce operations control.</h2>
        </div>
        <div className="faq-list">
          {faqs.map((item) => (
            <details key={item[0]}>
              <summary>{item[0]}</summary>
              <p>{item[1]}</p>
            </details>
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
        <div className="founder-copy">
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
        </div>
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
        <ProofScene />
        <FragmentScene />
        <BottleneckScene />
        <CapabilitiesScene />
        <InterceptScene />
        <PacketScene />
        <PlatformCoverageScene />
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
