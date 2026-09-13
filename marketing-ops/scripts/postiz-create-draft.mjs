import {readFile} from 'node:fs/promises'
import process from 'node:process'

const contentPath = process.argv[2] || 'marketing-ops/content/sanocea-instagram-pilot.json'
const apiUrl = (process.env.POSTIZ_API_URL || 'https://api.postiz.com/public/v1').replace(/\/$/, '')
const apiKey = process.env.POSTIZ_API_KEY
const integrationId = process.env.POSTIZ_INSTAGRAM_INTEGRATION_ID
const postType = process.env.POSTIZ_POST_TYPE || 'draft'
const postDate = process.env.POSTIZ_POST_DATE || new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString()

if (!apiKey) {
  throw new Error('Missing POSTIZ_API_KEY')
}

if (!integrationId) {
  throw new Error('Missing POSTIZ_INSTAGRAM_INTEGRATION_ID')
}

const content = JSON.parse(await readFile(contentPath, 'utf8'))

if (content.platform !== 'instagram') {
  throw new Error(`Unsupported platform for this script: ${content.platform}`)
}

const captionParts = [content.caption, ...(content.hashtags || []).map((tag) => `#${tag}`)]
const payload = {
  type: postType,
  date: postDate,
  shortLink: false,
  tags: [{value: content.tenant_id || 'sanocea'}],
  posts: [
    {
      integration: {
        id: integrationId,
      },
      value: [
        {
          content: captionParts.join('\n\n'),
          image: content.media || [],
        },
      ],
      settings: {
        __type: 'instagram',
        post_type: content.post_type || 'post',
      },
    },
  ],
}

const response = await fetch(`${apiUrl}/posts`, {
  method: 'POST',
  headers: {
    Authorization: apiKey,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify(payload),
})

const body = await response.text()

if (!response.ok) {
  throw new Error(`Postiz request failed (${response.status}): ${body}`)
}

console.log(body)
