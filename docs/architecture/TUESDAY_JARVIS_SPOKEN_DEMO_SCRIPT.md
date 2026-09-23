# Tuesday Executive Demo: JARVIS & Sanocea Commerce OS Presentation Guide

**Target Prospect:** The Premium Basket (thepremiumbasket.in)  
**Attendee:** Mariya Dalal (HR & Admin Executive) & Leadership  
**Demo Architecture:** Sanocea Commerce OS Hardened Engine (`http://127.0.0.1:8080`) + JARVIS AI Bridge (`ws://localhost:8787`) + WAHA WhatsApp Container (`http://127.0.0.1:3000`) + Shopify Sandbox (`sanocea-commerce-os-dev.myshopify.com`)  
**Safety Environment:** Password-protected sandbox (`sanocea`). Zero access to live merchant databases.

---

## 1. Safety Boundary & Operating Stance
- **Never claim access to real production systems:** Always state clearly that the demo runs against Sanocea's controlled sandbox and publicly observable catalogue patterns.
- **Fail-Closed Preflight:** JARVIS verifies API, Postgres, Shopify connector, and WhatsApp channel before proceeding. If any dependency fails, it explicitly announces it.
- **Bilingual Support:** Voice commands and spoken responses work seamlessly in both English and natural modern Hindi (Hindustani).

---

## 2. Quick-Start Commands & Verification

### A. Pre-Meeting Smoke Test
To verify the entire 10-step sequence, run:
```powershell
cd D:\jarvis
node scripts/smoke_test_tuesday_demo.mjs
```
*Expectation: All 10/10 steps pass, and the demo Shopify store is automatically armed in the anomalous baseline state.*

### B. Launching the Systems
If not already running, double-click:
```powershell
D:\Autonomous E-Commerce ERP\sanocea\START_DEMO.bat
```
And start JARVIS bridge:
```powershell
cd D:\jarvis
npm start
```
Open the JARVIS UI at: `http://localhost:5173/` and click **INITIALISE**.

---

## 3. Turn-by-Turn Spoken Demo Script

### Step 0: Baseline Reset (If Repeating Demo)
- **Presenter Cue:** *"JARVIS, reset the demo baseline."* (Or Hindi: *"जार्विस, डेमो रीसेट करो।"*)
- **JARVIS Response:**
  > *"Demo baseline reset successfully, sir. The Smoky Hickory BBQ Almonds 2-pack has been restored to ₹998 with compare-at ₹499 on the demo Shopify store, and a fresh approval request is armed. Ready for another run."*

---

### Step 1: Demo Start, Safety Disclaimer & Preflight Check
- **Presenter Cue:** *"JARVIS, start the Premium Basket demo."* (Or Hindi: *"जार्विस, प्रीमियम बास्केट डेमो शुरू करो।"*)
- **JARVIS Spoken Safety Boundary (Aloud):**
  > *"Demo mode active. This presentation uses Sanocea’s controlled sandbox and publicly observed catalogue patterns. It does not access The Premium Basket’s live systems, orders, inventory, customer data, or Shopify admin.*
  >
  > *All preflight checks passed: Sanocea API, PostgreSQL, Shopify live connector, and WhatsApp channel are healthy and authenticated."*
- **JARVIS Configurable Hinglish Opening (Munna Bhaiya Persona):**
  - **Option 1 (Active Default — Executive & Confident):**
    > *"Namaste! Sanocea system active hai aur back-office mein Munna Bhaiya aapka pura routine catalog, inventory aur reconciliation smoothly monitor kar rahe hain. Har routine kaam background mein chupchaap handle ho jata hai—sirf critical decisions hi aapke WhatsApp par aayenge. Kya hum morning executive briefing trigger karein?"*
  - **Option 2 (Warm & Reassuring — Operations Peace-of-Mind):**
    > *"Namaste! Sanocea control plane bilkul ready hai. Operational front par Munna Bhaiya background mein 95% routine kaam quietly sambhal rahe hain, taaki team ko manual tracking na karni pade. Jo genuine exceptions attention mangte hain, bas wahi seedhe aapke WhatsApp par aayenge. Kya briefing shuru karein?"*
  - **Option 3 (Crisp & Commercial — High-Impact):**
    > *"Namaste! Sanocea online hai. Backend operations aur catalog hygiene par Munna Bhaiya ki continuous nazar hai—routine sync silently chal raha hai aur zero operational noise hai. Decision-making ab 100% WhatsApp par hai. Kya morning briefing dispatch karein?"*

---

### Step 2: Executive WhatsApp Briefing
- **Presenter Cue:** *"Trigger the executive briefing."* (Or Hindi: *"एग्जीक्यूटिव ब्रीफिंग भेजो।"*)
- **JARVIS Action:** Dispatches WhatsApp morning briefing to presenter's phone via WAHA container.
- **JARVIS Response:**
  > *"Executive briefing dispatched to your WhatsApp, sir. The briefing summarizes overall store health: four active products, six inventory lines, and zero out-of-stock SKUs, but flags one critical pricing exception requiring executive sign-off: Smoky Hickory BBQ Almonds 2-pack has a severe price inversion. Say 'show me the details' to examine the unit economics."*
- **Presenter Action:** Hold up phone or project WhatsApp screen to show the clean, executive message.

---

### Step 3 & 4: Catalogue Exception & Unit Economics Deep-Dive
- **Presenter Cue:** *"JARVIS, show me the details."* (Or Hindi: *"डिटेल्स दिखाओ।"*)
- **JARVIS Response:**
  > *"Here are the details, sir. The single 100g pack sells at ₹249. However, the 2-pack is currently listed at ₹998 with a compare-at price of ₹499. A customer buying two individual packs pays ₹498, while the bundle costs ₹998—a 100% price penalty. Furthermore, the compare-at price was inverted during a bulk upload, showing an impossible negative discount. Sanocea has calculated the optimal corrected price at ₹449 with a compare-at price of ₹498, protecting a 42% contribution margin and eliminating customer drop-off. An approval request is waiting on your WhatsApp. Simply reply APPROVE to execute the correction on Shopify."*

---

### Step 5: Operator Sign-Off via WhatsApp
- **Presenter Action:** On your phone, reply to the WhatsApp message:
  ```text
  APPROVE PB-PRICE-001
  ```
  *(Note: You can also send `DETAILS PB-PRICE-001` to preview evidence, or `LATER PB-PRICE-001` to snooze).*
- **Presenter Cue:** *"JARVIS, confirm approval."* (Or Hindi: *"अप्रूवल चेक करो।"*)
- **JARVIS Response:**
  > *"Approval verified, sir! Authorized by operator via WhatsApp. Sanocea’s connector executed GraphQL bulk update on Shopify. The Smoky Hickory BBQ Almonds 2-pack is now live at ₹449 with compare-at ₹498. An immutable audit record has been logged in PostgreSQL with timestamp, operator ID, and Shopify response reference."*
- **Live Verification:** Refresh the demo Shopify storefront (`https://sanocea-commerce-os-dev.myshopify.com/products/smoky-hickory-barbecue-almonds-cashew`) to show the price dynamically changed to ₹449.00 with compare-at ₹498.00.

*(Voice Override Fallback: If WhatsApp phone is unreachable, say "JARVIS, execute approval now", and JARVIS will execute the correction directly).*

---

### Step 6: Structural Safeguards (ATS & Settlement Decoupling)
- **Presenter Cue:** *"JARVIS, explain ATS and inventory safeguards."* (Or Hindi: *"इन्वेंट्री सुरक्षा नियम समझाओ।"*)
- **JARVIS Response:**
  > *"Sanocea enforces two critical structural safeguards, sir. First, Available to Sell—or ATS—is strictly calculated as On-Hand minus Reserved orders minus Quarantine stock. Returns or damaged goods are immediately isolated in Quarantine so they can never oversell on Shopify. Second, operational delivery status is strictly decoupled from financial settlement. Just because a delivery partner marks a package delivered does not mean cash is in the bank. Sanocea maintains separate states for shipment transit and COD remittance reconciliation, preventing phantom revenue recognition."*

---

### Step 7: 3-Phase Real Merchant Pilot Plan
- **Presenter Cue:** *"What is the pilot plan for The Premium Basket?"* (Or Hindi: *"पायलट प्लान क्या है?"*)
- **JARVIS Response:**
  > *"For The Premium Basket, we propose a risk-free 3-phase pilot plan, sir. Phase 1 is a 14-day zero-risk shadow audit: Sanocea connects in read-only mode to audit catalogue health, inventory sync, and COD reconciliation without making any changes. Phase 2 introduces WhatsApp approvals: only genuine anomalies and high-value approvals are routed to leadership for one-tap sign-off. Phase 3 activates autonomous reconciliation and multi-channel ATS synchronization. This ensures immediate margin protection with zero disruption to daily fulfillment operations."*

---

## 4. Handling Challenging Meeting Questions (Q&A Guardrails)

| Prospect Question | Spoken Response Stance |
| :--- | :--- |
| **"Do you have access to our live store or customer data right now?"** | *"No, ma'am. Sanocea does not have access to The Premium Basket's live production systems, customer databases, or private Shopify admin. This demonstration runs exclusively within Sanocea's controlled sandbox using publicly observed catalogue patterns."* |
| **"Will this replace our existing warehouse or operations team?"** | *"Not at all. Sanocea acts as an autonomous operating copilot that absorbs 95% of routine spreadsheet reconciliation, duplicate SKU monitoring, and webhook synchronization. It frees your team from manual firefighting so they can focus on procurement and growth."* |
| **"How is this different from Unicommerce or EasyEcom?"** | *"Unicommerce is a passive dashboard that requires operators to sit at screens and search for errors. Sanocea is an autonomous operating system: it detects anomalies, calculates unit economics, and brings the final decision directly to your WhatsApp with one-tap execution."* |
| **"What if our internet drops or WhatsApp is offline?"** | Say *"JARVIS, run in fallback mode."* JARVIS immediately switches to local offline simulation, announces the simulation disclaimer, and guides the full workflow without network friction. |

---

## 5. Post-Demo Teardown
When the meeting finishes, reset the sandbox back to baseline anomaly:
```powershell
curl.exe -s -X POST -H "Authorization: Bearer sk_SrvHazh4J_s5qZAIxATJ-wpEYIhNyIjrNOhZigoQhOM" http://127.0.0.1:8080/merchants/prospect_premium_basket/demo-reset
```
Or simply say: *"JARVIS, reset the demo baseline."*
