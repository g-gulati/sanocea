import React, {useCallback, useEffect, useRef, useState} from 'react'
import {createRoot} from 'react-dom/client'
import './chat.css'

// Same production API this repo's other demo surface (website/src/demo/) uses - see that file's own
// comment for why this defaults to the real public origin rather than loopback.
const API_BASE = (import.meta.env.VITE_SANOCEA_API_BASE || 'https://api.sanocea.com').replace(/\/$/, '')
const LOGO = 'https://www.sanocea.com/sanocea-wordmark.png'
const SESSION_KEY = 'sanocea_whatsapp_demo_session'

const QUICK_REPLIES = ['What needs my attention?', 'Delivery issues', 'What needs my approval?', 'Menu']

function loadStoredSession() {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed.apiKey || !parsed.merchantId || !parsed.expiresAt) return null
    if (new Date(parsed.expiresAt).getTime() <= Date.now() + 10_000) return null
    return parsed
  } catch {
    return null
  }
}

function storeSession(session) {
  try {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(session))
  } catch {}
}

function clearStoredSession() {
  try {
    sessionStorage.removeItem(SESSION_KEY)
  } catch {}
}

async function createSession(whatsappNumber) {
  const res = await fetch(`${API_BASE}/demo/sessions`, {
    method: 'POST',
    headers: {Accept: 'application/json', 'Content-Type': 'application/json'},
    body: JSON.stringify({whatsapp_number: whatsappNumber}),
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail || detail
    } catch {}
    const err = new Error(detail)
    err.status = res.status
    throw err
  }
  const body = await res.json()
  return {
    merchantId: body.merchant_id,
    displayName: body.display_name,
    apiKey: body.api_key,
    expiresAt: body.expires_at,
  }
}

async function sendChatMessage(session, text) {
  const res = await fetch(`${API_BASE}/merchants/${session.merchantId}/chat`, {
    method: 'POST',
    headers: {Accept: 'application/json', 'Content-Type': 'application/json', Authorization: `Bearer ${session.apiKey}`},
    body: JSON.stringify({text}),
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail || detail
    } catch {}
    const err = new Error(detail)
    err.status = res.status
    throw err
  }
  return (await res.json()).replies || []
}

// ---- Intro screen (phone capture) --------------------------------------------------------------

function IntroScreen({onStart}) {
  const [phone, setPhone] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    if (!phone.trim()) {
      setError('Enter a WhatsApp number to continue.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await onStart(phone.trim())
    } catch (err) {
      if (err.status === 503) setError('Every demo environment is in use right now. Please try again in a couple of minutes.')
      else if (err.status === 429) setError('Too many people are starting demos at once — please wait a few seconds and try again.')
      else setError(err.message || 'Could not start the demo.')
      setBusy(false)
    }
  }

  return (
    <div className="wa-intro">
      <div className="wa-intro-card">
        <img src={LOGO} alt="Sanocea" />
        <h1>Chat with Sanocea</h1>
        <p>
          Enter your WhatsApp number and Sanocea will start watching a live, sandboxed commerce
          operation for you — the same conversation you'd have if this were running your business.
          This is a self-contained demo: no real WhatsApp message is sent, your number is only used
          for this demo session.
        </p>
        <form onSubmit={submit}>
          <div className="wa-phone-row">
            <input
              className="wa-input"
              type="tel"
              placeholder="+91 98765 43210"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              disabled={busy}
              autoFocus
            />
          </div>
          <p className="wa-hint">Any format works — we just need something that looks like a real number.</p>
          <button className="wa-btn" type="submit" disabled={busy}>
            {busy ? 'Starting…' : 'Start the conversation'}
          </button>
          {error && <p className="wa-error">{error}</p>}
        </form>
      </div>
    </div>
  )
}

// ---- Chat screen ---------------------------------------------------------------------------------

function useCountdown(expiresAt) {
  const [label, setLabel] = useState('')
  useEffect(() => {
    const tick = () => {
      const ms = new Date(expiresAt).getTime() - Date.now()
      if (ms <= 0) {
        setLabel('session ending…')
        return
      }
      setLabel(`~${Math.max(1, Math.round(ms / 60000))}m left`)
    }
    tick()
    const id = setInterval(tick, 30_000)
    return () => clearInterval(id)
  }, [expiresAt])
  return label
}

function ChatScreen({session, onSessionEnded}) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [booting, setBooting] = useState(true)
  const [ended, setEnded] = useState(false)
  const bottomRef = useRef(null)
  const countdown = useCountdown(session.expiresAt)

  const scrollDown = useCallback(() => {
    requestAnimationFrame(() => bottomRef.current?.scrollIntoView({behavior: 'smooth'}))
  }, [])

  useEffect(() => {
    let cancelled = false
    async function boot() {
      try {
        // Silently open the menu, then ask for today's briefing - a real, data-grounded opening
        // message ("I found N things that need attention...") built from the SAME conversation engine
        // every other reply comes from, not a scripted string.
        await sendChatMessage(session, 'menu')
        const briefing = await sendChatMessage(session, '1')
        if (cancelled) return
        setMessages([
          {from: 'sanocea', text: briefing.join('\n\n') || "Good morning — I'm watching this operation now."},
          {from: 'sanocea', text: 'Ask me anything — "what needs my attention?", "show me the delivery issues", "resolve it" — or type *menu* any time to see structured options.'},
        ])
      } catch (err) {
        if (cancelled) return
        setMessages([{from: 'sanocea', text: "I couldn't load today's briefing, but you can still ask me questions."}])
      } finally {
        if (!cancelled) setBooting(false)
      }
    }
    boot()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(scrollDown, [messages, scrollDown])

  const send = async (text) => {
    const trimmed = text.trim()
    if (!trimmed || sending || ended) return
    setMessages((m) => [...m, {from: 'me', text: trimmed}])
    setInput('')
    setSending(true)
    try {
      const replies = await sendChatMessage(session, trimmed)
      setMessages((m) => [...m, ...replies.map((r) => ({from: 'sanocea', text: r}))])
      if (replies.length === 0) {
        setMessages((m) => [...m, {from: 'sanocea', text: '…'}])
      }
    } catch (err) {
      if (err.status === 409) {
        setEnded(true)
        setMessages((m) => [...m, {from: 'sanocea', text: 'This demo session has ended. Refresh the page to start a new one.'}])
        onSessionEnded()
      } else {
        setMessages((m) => [...m, {from: 'sanocea', text: `Something went wrong: ${err.message}`}])
      }
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="wa-shell">
      <div className="wa-header">
        <img src={LOGO} alt="Sanocea" />
        <div>
          <div className="wa-header-name">Sanocea</div>
          <div className="wa-header-sub">{session.displayName}</div>
        </div>
        <div className="wa-header-right">
          <span>{countdown}</span>
          <a className="wa-console-link" href="/console.html" target="_blank" rel="noopener">
            Open Operations Console ↗
          </a>
        </div>
      </div>
      <div className="wa-messages">
        {messages.map((m, i) => (
          <div key={i} className={`wa-bubble-row ${m.from === 'me' ? 'out' : 'in'}`}>
            <div className="wa-bubble">{m.text}</div>
          </div>
        ))}
        {(booting || sending) && <div className="wa-typing">Sanocea is typing…</div>}
        <div ref={bottomRef} />
      </div>
      {!booting && !ended && (
        <div className="wa-quick-replies">
          {QUICK_REPLIES.map((q) => (
            <button key={q} className="wa-chip" onClick={() => send(q)} disabled={sending}>
              {q}
            </button>
          ))}
        </div>
      )}
      <div className="wa-composer">
        <input
          className="wa-composer-input"
          placeholder={ended ? 'Session ended' : 'Message Sanocea…'}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send(input)}
          disabled={sending || ended || booting}
        />
        <button className="wa-send" onClick={() => send(input)} disabled={sending || ended || booting}>
          ➤
        </button>
      </div>
      <div className="wa-footer-link">
        Want to see the underlying records instead? <a href="/console.html" target="_blank" rel="noopener">Open Operations Console</a>
      </div>
    </div>
  )
}

// ---- Root ---------------------------------------------------------------------------------------

function App() {
  const [session, setSession] = useState(() => loadStoredSession())

  const start = useCallback(async (phone) => {
    const s = await createSession(phone)
    storeSession(s)
    setSession(s)
  }, [])

  const onSessionEnded = useCallback(() => {
    clearStoredSession()
  }, [])

  if (!session) return <IntroScreen onStart={start} />
  return <ChatScreen session={session} onSessionEnded={onSessionEnded} />
}

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
