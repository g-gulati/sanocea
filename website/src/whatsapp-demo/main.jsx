import React, {useCallback, useEffect, useRef, useState} from 'react'
import {createRoot} from 'react-dom/client'
import './chat.css'
import Walkthrough from './Walkthrough.jsx'
import {API_BASE} from './api.js'

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
  const body = await res.json()
  return {replies: body.replies || [], expiresAt: body.expires_at || null}
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
  const [expiresAt, setExpiresAt] = useState(session.expiresAt)
  const bottomRef = useRef(null)
  const countdown = useCountdown(expiresAt)

  const inputRef = useRef(null)

  const scrollDown = useCallback(() => {
    requestAnimationFrame(() => bottomRef.current?.scrollIntoView({behavior: 'smooth'}))
  }, [])

  // Only ever called right after a message THIS user just sent finishes (success or error) - never on
  // any other event - so it can't steal focus from a control the user deliberately clicked instead
  // (e.g. the Operations Console link). requestAnimationFrame waits for the DOM update (input
  // re-enabled, response bubble rendered) before focusing, so it's never a no-op on a still-disabled
  // input. Caret goes to the end of whatever's left in the box, not the start.
  const refocusInput = useCallback(() => {
    requestAnimationFrame(() => {
      const el = inputRef.current
      if (!el) return
      el.focus()
      const end = el.value.length
      el.setSelectionRange(end, end)
    })
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
        if (briefing.expiresAt) setExpiresAt(briefing.expiresAt)
        setMessages([
          {from: 'sanocea', text: briefing.replies.join('\n\n') || "Good morning — I'm watching this operation now."},
          {from: 'sanocea', text: 'Ask me anything — "what needs my attention?", "show me the delivery issues", "resolve it" — or type *menu* any time to see structured options.'},
        ])
      } catch (err) {
        if (cancelled) return
        setMessages([{from: 'sanocea', text: "I couldn't load today's briefing, but you can still ask me questions."}])
      } finally {
        if (!cancelled) {
          setBooting(false)
          refocusInput()
        }
      }
    }
    boot()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(scrollDown, [messages, scrollDown])

  // Keep sessionStorage in sync with the real backend expiry (touch_lease slides it forward on every
  // message) - otherwise a page refresh mid-conversation would fall back to the ORIGINAL, shorter,
  // now-stale expiry and needlessly start a new session.
  useEffect(() => {
    if (expiresAt) storeSession({...session, expiresAt})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expiresAt])

  const send = async (text) => {
    const trimmed = text.trim()
    if (!trimmed || sending || ended) return
    setMessages((m) => [...m, {from: 'me', text: trimmed}])
    setInput('')
    setSending(true)
    try {
      const {replies, expiresAt: newExpiry} = await sendChatMessage(session, trimmed)
      if (newExpiry) setExpiresAt(newExpiry)
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
      refocusInput()
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
          ref={inputRef}
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

  const onSessionEnded = useCallback(() => {
    clearStoredSession()
  }, [])

  // The walkthrough already leased the tenant and (via attach-whatsapp) bound the phone number to it
  // WITHOUT resetting it - so the audit record/state the visitor just built in the walkthrough is still
  // there when they land in chat, not wiped by a fresh lease.
  const goToChat = useCallback((walkthroughSession) => {
    storeSession(walkthroughSession)
    setSession(walkthroughSession)
  }, [])

  if (session) return <ChatScreen session={session} onSessionEnded={onSessionEnded} />
  return <Walkthrough onGoToChat={goToChat} />
}

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
