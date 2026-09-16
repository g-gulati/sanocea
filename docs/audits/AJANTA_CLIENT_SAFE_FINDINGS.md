# Ajanta Soya Public Ecommerce Review - Client-Safe Findings

Date: 2026-09-16  
Scope: read-only review of publicly observable ecommerce/catalogue footprint  

## Summary

During a read-only review of the publicly observable Ajanta Soya / Anchal catalogue, we identified 5 verified official-site catalogue/control issues across the owned website, plus 2 marketplace observations requiring internal verification before they should be treated as defects.

The operation does not appear broadly broken. The verified issues are mostly catalogue-control and promotion-governance issues that can persist even in a human-operated multi-channel model.

This illustrates why increasing headcount alone does not necessarily remove repetitive control gaps. Systematic monitoring can check the full dataset continuously and route exceptions to the team for judgement.

## Verified Findings Safe To Discuss

1. A free-gift product is publicly exposed as a zero-price, in-stock, purchasable product on the official website.
   - Evidence: official Ajanta product page and public product data show `Sunflower Oil Offer`, price `Rs 0`, stock available, with add-to-cart and buy-now controls.
   - Why it matters: free-gift SKUs should normally be gated by qualifying paid offers, otherwise they can create customer confusion or fulfilment exceptions.

2. The official mustard oil variable product includes a malformed variation with no size value.
   - Evidence: official public WooCommerce product data exposes a variation id with `Size = null`, alongside valid 1L and 5L variants.
   - Why it matters: malformed variants can cause catalogue sync, feed, or variant-selection issues.

3. Some variable products show shared physical attributes despite multiple pack sizes.
   - Evidence: official pages expose 700gm/1L/5L variants while showing one parent weight/dimension set.
   - Why it matters: shipping and marketplace feeds should use variant-specific physical data. This should be verified internally before calling it an execution error.

4. A soyabean product includes sunflower-labelled image metadata.
   - Evidence: official public product data for Soyabean Oil includes image metadata saying "Anchal Sunflower oil is rich in omega-6 and is lightweight."
   - Why it matters: mismatched product media metadata can affect SEO, accessibility, feed quality, and automated content reuse.

5. Repeated official catalogue hygiene issues were visible.
   - Evidence: examples include `Coutry of Origin`, `Soyaben Oil Offer`, and `Byu Mustard Oil 1L Bottle`.
   - Why it matters: low direct commercial risk, but visible catalogue drift is easy to monitor and correct.

## Marketplace Footprint Notes

Confirmed active from direct public evidence:

- Official Ajanta website/store
- JioMart product pages for Anchal products

Search-discovered but not used for defect claims:

- Amazon India
- Flipkart
- Blinkit

Not confirmed active during this pass:

- BigBasket
- Zepto
- Swiggy Instamart
- Meesho
- ONDC-visible stores

## Management-Control Opportunity

SANOCEA-style monitoring could automatically check:

- zero-price purchasable SKUs
- malformed variants
- pack-size and physical-attribute completeness
- product/image metadata mismatches
- spelling/content hygiene
- marketplace structured-data completeness
- channel presence and stale listing signals

The right operating model is not "automation instead of people." It is systematic monitoring plus human judgement: software checks the repetitive rules, keeps evidence, and routes exceptions to the business team.

## Final Numbers

| Metric | Count |
|---|---:|
| Channels researched | 12 |
| Channels verified with direct active product evidence | 2 |
| Products/listing records observed | 16 |
| Variants/pack constructs observed | 13 |
| Product-family cross-channel matches | 2 |
| Verified official-site findings | 5 |
| Critical | 0 |
| High | 1 |
| Medium | 2 |
| Low | 2 |
| Marketplace observations requiring internal verification | 2 |
| False positives removed/downgraded | 6 |
| Automatable checks identified | 7 |
| Human-decision items | 5 |

## Suggested Discussion Framing

"During a read-only review of the publicly observable catalogue, we identified several verified catalogue-control exceptions on the official site and a small number of marketplace observations that merit internal verification. None of this suggests the operation is unmanaged; rather, it shows that repetitive catalogue checks are difficult to sustain manually across products, promotions and channels. A monitoring system can check these conditions continuously and route only exceptions to the team."
