# Marketing Ops

This folder starts the Sanocea Instagram pilot as a reusable marketing operations module.

## Files

- `tenants/sanocea.json`: Sanocea tenant and brand rules.
- `content/sanocea-instagram-pilot.json`: first pilot post draft.
- `scripts/postiz-create-draft.mjs`: Postiz adapter script for creating a draft or scheduled post.
- `scripts/postiz-list-integrations.mjs`: helper script to find the connected Instagram integration ID.

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
POSTIZ_DRY_RUN=1
```

Use `POSTIZ_POST_TYPE=schedule` only when `POSTIZ_POST_DATE` is set and the item has been approved.

## Step 1: Find Instagram Integration ID

After connecting Instagram in Postiz, run:

```bash
node marketing-ops/scripts/postiz-list-integrations.mjs
```

Find the Instagram integration in the JSON response and copy its `id` into:

```text
POSTIZ_INSTAGRAM_INTEGRATION_ID=...
```

## Step 2: Dry Run The Payload

Before sending anything to Postiz:

```bash
set POSTIZ_DRY_RUN=1
node marketing-ops/scripts/postiz-create-draft.mjs marketing-ops/content/sanocea-instagram-pilot.json
```

This prints the exact payload and does not call Postiz.

## Step 3: Create A Postiz Draft

```bash
set POSTIZ_DRY_RUN=
node marketing-ops/scripts/postiz-create-draft.mjs marketing-ops/content/sanocea-instagram-pilot.json
```

The script prints the Postiz response JSON.

## Approval Rule

Keep `POSTIZ_POST_TYPE=draft` until the item is approved. Use `schedule` or `now` only after approval.
