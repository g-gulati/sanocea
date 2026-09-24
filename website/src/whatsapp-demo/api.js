// Shared by both the interactive walkthrough and the chat screen - one API_BASE, one fetch convention.
export const API_BASE = (import.meta.env.VITE_SANOCEA_API_BASE || 'https://api.sanocea.com').replace(/\/$/, '')

async function parseError(res) {
  let detail = res.statusText
  try {
    detail = (await res.json()).detail || detail
  } catch {}
  const err = new Error(detail)
  err.status = res.status
  return err
}

export async function apiFetch(path, {method = 'GET', body, apiKey} = {}) {
  const headers = {Accept: 'application/json'}
  if (apiKey) headers.Authorization = `Bearer ${apiKey}`
  if (body) headers['Content-Type'] = 'application/json'
  const res = await fetch(`${API_BASE}${path}`, {
    method, headers, cache: 'no-store', body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw await parseError(res)
  if (res.status === 204) return null
  return res.json()
}
