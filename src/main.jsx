import React,{useEffect,useRef,useState} from 'react'
import {createRoot} from 'react-dom/client'
import {motion,useScroll,useReducedMotion,MotionConfig} from 'framer-motion'
import './styles.css'

const LOGO=import.meta.env.BASE_URL+'sanocea-logo.png'

const lifecycle=[
  ['01','Catalogue','Create, enrich and govern product data before it spreads downstream.'],
  ['02','Publish','Prepare and maintain channel-ready listings across selling surfaces.'],
  ['03','Inventory','Keep availability, exceptions and replenishment signals under control.'],
  ['04','Orders','Route operational work without losing ownership between systems.'],
  ['05','Fulfil','Track shipment, SLA, dispatch and exception states continuously.'],
  ['06','Support','Answer from operational truth rather than disconnected inboxes.'],
  ['07','Returns','Apply controlled return, cancellation and refund workflows.'],
  ['08','Reconcile','Match settlements, payments and discrepancies back to the order.'],
  ['09','Replenish','Surface what requires attention before stock or execution breaks.'],
]

const surfaceGroups=[
  ['Catalogue','Product operations that stay governed.','PRODUCT DATA'],
  ['Commerce','Execution across the order lifecycle.','ORDER FLOW'],
  ['Finance','Reconciliation without spreadsheet archaeology.','MONEY FLOW'],
  ['Support','Customer operations connected to truth.','CUSTOMER OPS'],
]

const channelLanes=[
  ['Storefronts',['Shopify','WooCommerce']],
  ['Marketplaces',['Amazon','Flipkart','Meesho','Myntra']],
  ['Quick-commerce',['Blinkit','Zepto','Instamart']],
]

const coreNodes=[
  ['Shopify',10,16],['WooCommerce',6,54],['Amazon',16,86],
  ['Flipkart',48,8],['Meesho',50,92],['Blinkit',30,68],
]

function Logo({compact=false}){
  return <a href="#top" className={'brand '+(compact?'compact':'')}>
    <img src={LOGO} alt="Sanocea"/>
    <span className="brand-word">Sanocea</span>
  </a>
}

function Header(){
  const[open,setOpen]=useState(false)
  return <header className="topbar">
    <div className="shell nav-shell">
      <Logo compact/>
      <nav className={'nav-links '+(open?'open':'')}>
        <a href="#system" onClick={()=>setOpen(false)}>System</a>
        <a href="#capabilities" onClick={()=>setOpen(false)}>Capabilities</a>
        <a href="#channels" onClick={()=>setOpen(false)}>Channels</a>
        <a href="#principles" onClick={()=>setOpen(false)}>Control</a>
        <a className="nav-cta" href="#contact" onClick={()=>setOpen(false)}>Discuss your operations</a>
      </nav>
      <button className="menu" aria-label="Menu" onClick={()=>setOpen(!open)}><span/><span/></button>
    </div>
  </header>
}

function OperatingCore(){
  const core=[74,50]
  const reduceMotion=useReducedMotion()
  return <div className="core-diagram">
    <svg className="core-lines" viewBox="0 0 100 100" preserveAspectRatio="none">
      {coreNodes.map((n,i)=><line key={n[0]} x1={core[0]} y1={core[1]} x2={n[1]} y2={n[2]} className={i%2?'ln ln-b':'ln'}/>)}
      {!reduceMotion && [0,1,2].map(i=>{const n=coreNodes[i*2];return <motion.circle key={i} r="1.1" className="packet-dot"
        animate={{cx:[core[0],n[1]],cy:[core[1],n[2]]}}
        transition={{duration:3.4,repeat:Infinity,repeatType:'reverse',ease:'easeInOut',delay:i*.6}}/>})}
    </svg>
    {coreNodes.map((n,i)=><motion.div className="core-tag" key={n[0]} style={{left:n[1]+'%',top:n[2]+'%'}}
      initial={{opacity:0,scale:.85}} whileInView={{opacity:1,scale:1}} viewport={{once:true}} transition={{delay:i*.07,duration:.5}}>{n[0]}</motion.div>)}
    <div className="core-mark" style={{left:core[0]+'%',top:core[1]+'%'}}>
      <span>OPERATING LAYER</span>
      <strong>SANOCEA</strong>
      <small>commerce truth + execution</small>
    </div>
  </div>
}

function Hero(){
  const words=['operations','automation','execution','control']
  const[i,setI]=useState(0)
  const reduceMotion=useReducedMotion()
  useEffect(()=>{
    if(reduceMotion)return
    const t=setInterval(()=>setI(v=>(v+1)%words.length),2400)
    return()=>clearInterval(t)
  },[reduceMotion])
  return <section id="top" className="hero">
    <div className="shell hero-grid">
      <div className="hero-copy">
        <div className="badge"><span className="dot"/>AI AUTOMATION &amp; DIGITAL OPERATIONS</div>
        <h1>Ecommerce<br/><span className="rotating-word" key={i}>{words[i]}</span>, handled.</h1>
        <p className="hero-lead">One operating layer for the repetitive work behind storefronts, marketplaces and quick-commerce channels.</p>
        <div className="hero-actions">
          <a className="button primary" href="#contact">Discuss your operations <span>↗</span></a>
          <a className="button ghost" href="#system">See how it works</a>
        </div>
        <div className="trust-strip"><span>GST REGISTERED · INDIA</span><b/><span>SURAT · GUJARAT</span><b/><span>MANAGED EXECUTION</span></div>
      </div>
      <OperatingCore/>
    </div>
  </section>
}

function Flow(){
  const railRef=useRef(null)
  const {scrollXProgress}=useScroll({container:railRef})
  return <section id="system" className="section paper">
    <div className="shell">
      <div className="flow-head">
        <h2>From product data<br/>to money in the bank.</h2>
        <p>Sanocea connects repetitive ecommerce work into one controlled operating flow, so teams spend less time checking, copying, chasing and correcting.</p>
      </div>
    </div>
    <div className="flow-progress-track"><motion.div className="flow-progress-fill" style={{scaleX:scrollXProgress}}/></div>
    <div className="flow-rail" ref={railRef}>
      <div className="flow-track">
        <div className="flow-baseline">
          <span className="packet fp1"/><span className="packet fp2"/><span className="packet fp3"/>
        </div>
        {lifecycle.map((x,i)=><div className={'station '+(i%2?'station-down':'station-up')} key={x[1]}>
          <span className="station-connector"/>
          <span className="station-num">{x[0]}</span>
          <h3>{x[1]}</h3>
          <p>{x[2]}</p>
        </div>)}
      </div>
    </div>
    <p className="flow-hint shell">Drag to explore the pipeline — a live operating flow, not a static list.</p>
  </section>
}

function Capabilities(){
  return <section id="capabilities" className="section soft">
    <div className="shell">
      <div className="section-head">
        <h2>Broad under the hood.<br/>Specific at the surface.</h2>
        <p>Merchants see specific operational responsibility. Underneath, one shared execution layer runs it.</p>
      </div>
      <div className="cap-diagram">
        <div className="cap-surface">
          {surfaceGroups.map((g,i)=><motion.div className="cap-tile" key={g[0]} initial={{opacity:0,y:18}} whileInView={{opacity:1,y:0}} viewport={{once:true}} transition={{delay:i*.06}}>
            <em>{g[2]}</em><h3>{g[0]}</h3><p>{g[1]}</p>
          </motion.div>)}
        </div>
        <svg className="cap-links" viewBox="0 0 400 72" preserveAspectRatio="none">
          {[50,150,250,350].map((x,i)=><motion.path key={i} d={`M${x},0 C${x},34 200,34 200,72`}
            initial={{pathLength:0,opacity:0}} whileInView={{pathLength:1,opacity:1}} viewport={{once:true}} transition={{duration:.9,delay:.15+i*.08}}/>)}
        </svg>
        <div className="cap-core"><span>SHARED EXECUTION LAYER</span><strong>Sanocea Operating System</strong></div>
      </div>
    </div>
  </section>
}

function Channels(){
  return <section id="channels" className="section paper">
    <div className="shell">
      <div className="section-head">
        <h2>One operation. Many surfaces.</h2>
        <p>Storefronts, marketplaces and quick-commerce channels can be activated according to the merchant's existing access, permissions and available integration interfaces.</p>
      </div>
      <div className="lanes">
        {channelLanes.map((lane,i)=><motion.div className="lane" key={lane[0]} initial={{opacity:0,x:-14}} whileInView={{opacity:1,x:0}} viewport={{once:true}} transition={{delay:i*.08}}>
          <span className="lane-label">{lane[0]}</span>
          <div className="lane-chips">{lane[1].map(c=><span className="chip" key={c}>{c}</span>)}</div>
          <span className="lane-wire"/>
        </motion.div>)}
        <div className="lane-hub"><strong>SANOCEA</strong><small>operating layer</small></div>
      </div>
      <div className="channel-note"><b>i</b><span>Channel activation is scoped against the seller/vendor account, technical access and operating interfaces available to that merchant.</span></div>
    </div>
  </section>
}

function Principles(){
  return <section id="principles" className="section dark">
    <div className="shell principle-grid">
      <div>
        <h2>AI where judgement helps.<br/>Deterministic systems where truth matters.</h2>
        <p>Sanocea uses automation to reduce repetitive intervention without allowing AI to invent inventory, payment, shipment or commercial truth.</p>
      </div>
      <div className="board">
        <div className="col">
          <label>AI LAYER</label>
          {['Interpret','Diagnose','Classify','Recommend'].map((x,i)=><motion.div className="row" key={x} initial={{opacity:0,x:-18}} whileInView={{opacity:1,x:0}} viewport={{once:true}} transition={{delay:i*.08}}>
            <small>0{i+1}</small><strong>{x}</strong></motion.div>)}
        </div>
        <div className="bridge"><i/><b>POLICY<br/>+<br/>TRUTH</b><i/></div>
        <div className="col">
          <label>CONTROLLED EXECUTION</label>
          {['Inventory','Orders','Refunds','Reconciliation'].map((x,i)=><motion.div className="row" key={x} initial={{opacity:0,x:18}} whileInView={{opacity:1,x:0}} viewport={{once:true}} transition={{delay:i*.08}}>
            <span className="status"/><strong>{x}</strong></motion.div>)}
        </div>
      </div>
    </div>
  </section>
}

function Proof(){
  const steps=[
    ['Routine execution','Handled through defined workflows','handled'],
    ['Exceptions','Surfaced with context and evidence','surfaced'],
    ['Judgement calls','Escalated to the merchant','escalated'],
    ['Operational truth','Persisted and traceable','recorded'],
  ]
  return <section className="section soft">
    <div className="shell proof">
      <div>
        <h2>Not another dashboard.<br/>Work actually gets handled.</h2>
        <p>Sanocea is designed around operational ownership: recurring work enters a structured queue, controlled execution happens against defined rules, and genuine judgement is escalated.</p>
      </div>
      <div className="proof-chain">
        {steps.map((x,i)=><motion.div className="proof-step" key={x[0]} initial={{opacity:0,y:16}} whileInView={{opacity:1,y:0}} viewport={{once:true}} transition={{delay:i*.08}}>
          <span className={'glyph g-'+x[2]}/>
          <strong>{x[0]}</strong>
          <small>{x[1]}</small>
          {i<steps.length-1 && <i className="proof-arrow"/>}
        </motion.div>)}
      </div>
    </div>
  </section>
}

function Contact(){
  return <section id="contact" className="section cta">
    <div className="shell cta-shell">
      <span className="cta-kicker">START WITH THE BOTTLENECK</span>
      <h2>Where does your ecommerce operation<br/>still require someone to intervene every day?</h2>
      <div className="cta-row">
        <a className="button primary large" href="mailto:hello@sanocea.com?subject=Discuss%20our%20ecommerce%20operations">Discuss Your Operations <span>↗</span></a>
        <div className="cta-contacts">
          <a href="mailto:hello@sanocea.com">hello@sanocea.com</a>
          <a href="https://wa.me/919909360065">WhatsApp +91 99093 60065</a>
        </div>
      </div>
    </div>
  </section>
}

function Footer(){
  return <footer><div className="shell footer-grid">
    <div><Logo compact/><p>AI Automation &amp; Digital Operations</p></div>
    <div className="meta"><span>Sanocea · Operated by Manpreet Gulati · GST Registered · India</span><span>GSTIN 24CDUPG6401L1ZB</span><span>Surat, Gujarat, India</span></div>
    <div className="right"><a href="mailto:hello@sanocea.com">hello@sanocea.com</a><span>© 2026 Sanocea</span></div>
  </div></footer>
}

function App(){
  return <>
    <Header/>
    <main><Hero/><Flow/><Capabilities/><Channels/><Principles/><Proof/><Contact/></main>
    <Footer/>
  </>
}

createRoot(document.getElementById('root')).render(<MotionConfig reducedMotion="user"><App/></MotionConfig>)
