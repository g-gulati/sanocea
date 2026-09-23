# Draft access request templates

**Not sent. Drafted for review only.** Each asks for legitimate direct technology-integration access —
none claims existing certification, none mentions replacing the platform's own systems, none references
reverse-engineering. Placeholders in `[brackets]` need filling in (company/contact details, merchant
identifiers) before any of these could actually be sent.

---

## 1. Blinkit

**To:** Blinkit partner/vendor integration team (via `partners.blinkit.com` or the vendor's own account
manager, whichever channel proves correct)
**Subject:** Technology integration partner access request — Sanocea Commerce OS

> Hello,
>
> We are Sanocea, a merchant commerce-operations platform, requesting direct technology-integration
> access to Blinkit's vendor systems on behalf of [merchant name / vendor code, if already onboarded].
>
> We would like to establish a direct, API/EDI-based integration covering:
> - Vendor PO ingestion
> - PO acknowledgement
> - ASN (advance shipment notice) submission
> - Facility/dark-store mapping
> - Catalogue and inventory synchronization
> - GRN / receipt discrepancy data (shortage, damage, rejection)
> - Settlement and reconciliation data
>
> Could you confirm:
> - Whether a sandbox/UAT environment is available for this integration
> - The exact technical specification (API, EDI, or webhook) for each of the above workflows
> - Whether Sanocea can be recognized as a technology/integration partner independently, or whether
>   access must be configured per individual vendor account
>
> We are happy to complete whatever technical or security review is required. Thank you for your time.

---

## 2. Flipkart Minutes

**To:** Flipkart seller/partner support (same channel as the existing HyperLocal Seller API partnership)
**Subject:** Flipkart Minutes (HyperLocal) operational lifecycle specification request

> Hello,
>
> Sanocea already has a working integration against Flipkart's documented HyperLocal catalogue,
> inventory, and pricing APIs (`/listings/v3/hyperlocal` and related endpoints) under our existing
> Seller API partner registration.
>
> We would now like to extend this integration to cover the full HyperLocal/Minutes operational
> lifecycle, specifically:
> - PO / replenishment requests
> - PO acknowledgement
> - Fulfilment confirmation
> - ASN / dispatch confirmation
> - GRN and discrepancy reporting
> - Returns / RTV
> - Settlement and reconciliation data
>
> Could you share the technical specification for these workflows, and confirm whether a sandbox/UAT
> environment is available to validate against before going live? Please let us know if this requires a
> separate application or enablement step beyond our existing Seller API partnership.
>
> Thank you.

---

## 3. Myntra

**To:** Myntra partner/account-manager contact (via `partnerportal.myntra.com` or the developer portal's
own sign-up at `mmip.myntrainfo.com`)
**Subject:** Technology integration partner access — catalogue, inventory, order, fulfilment, and
settlement operations

> Hello,
>
> We are Sanocea, a merchant commerce-operations platform. We understand that Myntra's PPMP/Omni and
> Listing Management APIs require account-manager enablement before technical access is shared.
>
> Before requesting enablement for a specific seller, we would like to first understand: can Sanocea be
> enabled as a technology/integration partner across multiple sellers under one relationship, or must
> API access be requested and configured separately for each individual seller account?
>
> Assuming a seller relationship is in place, we would appreciate the technical specification covering:
> - Catalogue (listing creation, attributes, images, QC/rejection handling)
> - Inventory (facility-wise stock, replenishment)
> - Orders (discovery, detail, RTD/hold/status lifecycle)
> - Fulfilment (dispatch, packet-level status updates)
> - Cancellations
> - Returns
> - Settlement / reporting
> - Authentication mechanism
> - Sandbox/UAT availability
>
> We are happy to go through whatever onboarding or technical review process is required. Thank you.

---

## 4. Meesho

**To:** `meesholink-integration@meesho.com`
**Subject:** Meesho technical/API documentation request — Sanocea integration

> Hello,
>
> We are Sanocea, a merchant commerce-operations platform, working on behalf of [merchant name / supplier
> location identifier(s)] to establish a direct technical integration with Meesho.
>
> Before or alongside credential issuance, we would specifically like to request **Meesho's own
> technical/API documentation** covering:
> - Catalogue (listing creation/update, attributes, images)
> - Inventory (stock sync, facility-wise updates)
> - Orders (discovery, detail, status lifecycle)
> - Fulfilment (label retrieval, dispatch confirmation)
> - Cancellation (window, request/response shape)
> - Returns / RTO
> - Settlement / payment reconciliation
> - Authentication (header construction, and specifically how the `security` header value is derived)
> - Sandbox/UAT environment details
> - Rate limits and error/status code enumerations
>
> If credentials are issued separately from this documentation, please let us know the process and
> timeline for obtaining the documentation itself, as that is our primary need at this stage.
>
> Supplier/location identifier(s) for this request: [to be provided].
>
> Thank you.
