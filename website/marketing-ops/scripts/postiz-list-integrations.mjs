import process from 'node:process'

const apiUrl = (process.env.POSTIZ_API_URL || 'https://api.postiz.com/public/v1').replace(/\/$/, '')
const apiKey = process.env.POSTIZ_API_KEY

if (!apiKey) {
  throw new Error('Missing POSTIZ_API_KEY')
}

const response = await fetch(`${apiUrl}/integrations`, {
  method: 'GET',
  headers: {
    Authorization: apiKey,
  },
})

const body = await response.text()

if (!response.ok) {
  throw new Error(`Postiz request failed (${response.status}): ${body}`)
}

const integrations = JSON.parse(body)

console.log(JSON.stringify(integrations, null, 2))
