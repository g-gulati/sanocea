# Marketing Ops

This folder starts the Sanocea Instagram pilot as a reusable marketing operations module.

## Files

- `tenants/sanocea.json`: Sanocea tenant and brand rules.
- `content/sanocea-instagram-pilot.json`: first pilot post draft.
- `scripts/postiz-create-draft.mjs`: Postiz adapter script for creating a draft or scheduled post.

## Required Environment Variables

```text
POSTIZ_API_URL=https://api.postiz.com/public/v1
POSTIZ_API_KEY=your-postiz-api-key
POSTIZ_INSTAGRAM_INTEGRATION_ID=your-connected-instagram-integration-id
```

Optional:

```text
POSTIZ_POST_TYPE=draft
POSTIZ_POST_DATE=2026-09-20T10:00:00.000Z
```

Use `POSTIZ_POST_TYPE=schedule` only when `POSTIZ_POST_DATE` is set and the item has been approved.

## Run

```bash
node marketing-ops/scripts/postiz-create-draft.mjs marketing-ops/content/sanocea-instagram-pilot.json
```

The script prints the Postiz response JSON.
