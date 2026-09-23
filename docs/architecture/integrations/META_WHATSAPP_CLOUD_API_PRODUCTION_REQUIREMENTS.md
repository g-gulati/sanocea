# Meta WhatsApp Cloud API — production/demo requirements (researched Sept 2026)

Research only. Official Meta documentation used as primary authority wherever it could be directly
fetched (developers.facebook.com); where Meta's own current pages did not state a specific number,
that is flagged explicitly and corroborated only from Meta Business Partner / platform-support sources
(WANotifier, Vonage — both operate on Meta's actual platform and document its real limits), never from
GitHub or a random blog.

## 1. Test number recipient limit

Meta's own current developer docs (`.../cloud-api/overview`, `.../get-started`) confirm the *concept* —
"test WhatsApp Business accounts and test phone numbers... have relaxed messaging limits and don't
require a payment method on file" — but do not state the exact number in the pages fetched. Multiple
independent Meta Business Partner sources (WANotifier's own help docs, Vonage's WhatsApp platform
support docs, Meta's own developer community forum threads) consistently and specifically state: **a
test number is limited to 5 recipient phone numbers, each individually added via the Meta App
Dashboard**. This is a hard allow-list, not an OTP-per-message step — once added, the recipient number
work indefinitely until removed.

## 2. Business verification

Meta's own docs: "Business portfolios can be verified, and verification status factors into improved
functionality, such as higher throughput and Official Business Account status." Verification is **not**
mandatory to send any message at all, but **is** required to move past test-number-only limits and to
raise messaging throughput tiers. Timeline, per Meta Business Partner documentation: typically same-day
to ~14 working days depending on document review load; **Partner-led Business Verification (PLBV)**
through an existing WhatsApp Business Solution Provider is the fastest path and can unlock full API
capability from day one, versus the slower self-service "Classic" verification route. Realistic
planning assumption: **not a same-morning-of-the-meeting task**, but achievable within a business week
if started early via a partner.

## 3. Message templates

Confirmed directly from Meta's own docs (`.../messages/template-messages`, `.../messages/send-messages`):
**a pre-approved template is required for any message sent OUTSIDE an open customer service window** —
i.e. the first message to a number that has never messaged the business. Template review/approval is a
separate Meta process (not instant); plan for it to exist and be approved *before* the meeting, not
created live in it.

## 4. The 24-hour customer service window

Confirmed directly: once a user sends the business ANY message, a customer service window opens, and
**"Service messages are free-form messages... unlike template messages, service messages do not require
pre-approval"** for the duration of that window. This matters for message design: if the prospect
messages SANOCEA's number FIRST (even just "hi"), the business can then reply free-form (no template)
for the next 24 hours. The very first outbound contact to a number that has never written in, however,
still needs a template regardless of window state.

## 5. Opt-in

Confirmed directly from Meta's own opt-in policy page: three requirements — (1) clearly state the
person is opting in to receive messages, (2) clearly state the business name, (3) comply with local
law. Critically, **Meta's own policy explicitly lists "In person or on paper" as a supported, compliant
opt-in method** — there is no mandated digital/written flow. A salesperson verbally asking consent and
manually entering the prospect's number, stating who is messaging them, satisfies Meta's *platform*
opt-in bar as documented. The residual risk is not policy rejection at send-time but **account quality
rating** — if a recipient reports/blocks the message, it dings the sending number's quality score, which
matters over repeated use, not for one message.

## 6. Pricing

Materially outdated in general internet commentary: **Meta deprecated conversation-based pricing on
July 1, 2025**, replacing it with **per-message pricing** across template categories (marketing,
utility, authentication). Confirmed directly: **"All non-template messages are free within an open
customer service window"** — so once the prospect has replied (opening the window), the resulting
free-form back-and-forth (including SANOCEA's own APPROVE-processing replies) costs nothing. Only the
initial template-category outbound message is billed. India-specific: Meta requires eligible WABAs to
migrate billing to INR by Dec 31, 2026 — an account-currency requirement, not a demo blocker. No
India-specific regulatory (TRAI) restriction was found layered on top of Meta's own policy for this use
case in the sources checked.

## 7. Webhooks

Confirmed directly: a webhook endpoint must be created and subscribed to specific fields via the App
Dashboard, requiring the `whatsapp_business_messaging` permission. Meta's docs note **"some webhooks
will not be sent if your app is in Dev mode"** — a real, confirmed difference between test and
production tiers worth planning around (a webhook that appears to work with the test number may not
fully represent production behavior). Verify-token handshake and payload signature verification
(`X-Hub-Signature-256`) are standard Graph API webhook mechanics, consistent across dev/production tiers.

---

## Decision block

```
DEVELOPMENT TEST NUMBER LIMITATION = Meta's free test number can message at most 5 individually
  pre-added recipient numbers (added once via the App Dashboard, no per-message OTP) - confirmed by
  Meta's own "relaxed limits" language plus consistent corroboration from Meta Business Partner docs;
  the exact "5" figure is not stated on the specific official pages fetched this pass.

PRODUCTION DEMO REQUIREMENT = A live/production WhatsApp Business phone number (not the free test
  number) is needed to message an ARBITRARY, not-pre-registered prospect number. That requires:
  business verification (same-day to ~2 weeks, faster via a Partner/PLBV route), at least one
  pre-approved message template for the very first outbound "Approval Required" message, and a
  production-tier webhook endpoint. None of this needs to happen per-meeting - it is a one-time setup.

CAN MANPREET ENTER A NEW CONSENTING PROSPECT NUMBER DURING A MEETING AND IMMEDIATELY SEND AN APPROVAL
  MESSAGE = CONDITIONAL - yes, but only once SANOCEA already holds (a) a verified production number and
  (b) an already-approved "Approval Required" template. Under the free TEST number, no - only the 5
  numbers pre-registered in the Meta dashboard can ever receive a message, so a genuinely new prospect
  number cannot work live in a meeting on the test tier at all.
```

**Single most commercially important fact:** the test-number path is fundamentally incompatible with
the "arbitrary consenting prospect number, live in the room" sales motion described — it isn't a matter
of it being slow or clunky, it structurally cannot message a number that wasn't pre-registered in Meta's
dashboard beforehand. The test tier is only usable for rehearsing with Manpreet's own (and up to 4 other
pre-registered) numbers. Reaching the actual "type the prospect's number in live and send" capability
requires the one-time production setup (verification + one approved template), after which per-meeting
friction is genuinely zero — no per-prospect Meta dashboard step is needed once on the production tier.
