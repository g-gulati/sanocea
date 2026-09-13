# Sanocea Marketing Ops Pilot

This pilot treats Sanocea as tenant 1 for a reusable marketing operations module. The goal is to prove the lifecycle before selling it as a client package.

## V1 Flow

1. Research content angle for the week.
2. Generate caption, creative brief and platform notes.
3. Create an approval item for the operator.
4. On approval, send the post to Postiz as a draft or scheduled Instagram post.
5. Track results through Instagram/Postiz analytics and website intent events in GA4.
6. Use results to improve the next content cycle.

## Primary Publisher

Postiz is the primary publishing adapter for V1.

Postiz responsibilities:
- Hold connected Instagram account.
- Store drafts and scheduled posts.
- Publish approved posts.
- Provide social performance data where available.

Sanocea responsibilities:
- Own tenant profile.
- Own content rules.
- Own approval state.
- Decide when a draft is approved.
- Track website lead intent with GA4 events.

## Backup Publisher

Shoutrrr stays as the fallback adapter if Postiz lacks a channel feature, deployment path or reliability we need later.

The business workflow should never depend directly on Postiz internals. Use an adapter boundary:

```text
Approved content item -> publisher adapter -> Postiz now, Shoutrrr later if needed
```

## Tenant Model

Each future client should have its own:

- Brand profile
- Audience profile
- Offer and CTA rules
- Prohibited claims
- Platforms
- Approval rules
- Publishing credentials
- Content history
- Reporting preferences

Sanocea is the first tenant and proof case.

## Events To Measure

Website events already configured in GA4:

- `diagnostic_email_click`
- `whatsapp_click`
- `footer_email_click`
- `diagnostic_cta_click`

For lead reporting, initially mark only these as GA4 key events:

- `diagnostic_email_click`
- `whatsapp_click`

## Postiz API Notes

Postiz public API base URLs:

- Cloud: `https://api.postiz.com/public/v1`
- Self-hosted: `https://{NEXT_PUBLIC_BACKEND_URL}/public/v1`

Create post endpoint:

```text
POST /posts
```

Post types:

- `draft`
- `schedule`
- `now`

Instagram settings need:

```json
{
  "__type": "instagram",
  "post_type": "post"
}
```

Keep publishing compliant with Meta authorization. Do not use scraping, password automation or bot posting.
