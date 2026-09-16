from __future__ import annotations

from typing import Any


def get_capability_manifest() -> dict[str, Any]:
    """Returns the authoritative capability manifest for the SANOCEA Reference Merchant tenant.
    Distinguishes certified production capabilities from simulated or unavailable ones.
    """
    return {
        "tenant": "ref_anchal_heritage",
        "display_name": "Anchal Heritage Organics",
        "engine_version": "SANOCEA ERP Core v1.0 (Stages 1-4 Certified)",
        "capabilities": {
            "CATALOGUE_INGESTION": {
                "status": "CERTIFIED",
                "evidence_stage": "STAGE_3_AND_4",
                "description": "Multi-format messy file ingestion (.csv, .xlsx, .pdf, images) with exact locators and fault-isolated ballast quarantine.",
                "supported_formats": ["CSV", "XLSX", "PDF (Docling/PyMuPDF)", "PNG", "JPEG"],
                "invariants": [
                    "Zero commercial fact invention (absence -> MISSING)",
                    "Honest formula preservation (text + cached value, no fake calculation engine)",
                    "Hidden sheet isolation (internal costs never leak)",
                    "Quarantine of corrupt ballast files (.DS_Store, corrupt binaries)",
                ],
            },
            "PRODUCT_IDENTITY_AND_VARIANTS": {
                "status": "CERTIFIED",
                "evidence_stage": "STAGE_4",
                "description": "Deterministic identity resolution and multi-variant matrix reconciliation.",
                "invariants": [
                    "Non-fuzzy identity boundary (fuzzy title/brand similarity generates candidates only, never auto-resolves)",
                    "Orthogonal identity_status (RESOLVED, AMBIGUOUS, UNRESOLVED, CONFLICT) vs validation state",
                    "Durable merchant-scoped operator disambiguation decisions (SAME/DIFFERENT) persisted in PostgreSQL",
                    "Variant lifecycle transitions (added -> ACTIVE, SKU/barcode changed -> ACTIVE, missing -> STALE)",
                ],
            },
            "GOVERNANCE_AND_APPROVALS": {
                "status": "CERTIFIED",
                "evidence_stage": "STAGE_3_AND_4",
                "description": "Formal policy gates, exception generation, and human-in-the-loop sign-off.",
                "invariants": [
                    "Fail-closed publication gate (blocks INCOMPLETE, CONFLICTED, or unapproved drafts)",
                    "Cross-source conflict detection and audited human resolution (HUMAN_APPROVED)",
                    "Operator approval trail with principal ID and timestamp",
                ],
            },
            "SHOPIFY_LIVE_CHANNEL": {
                "status": "CERTIFIED",
                "evidence_stage": "STAGE_2_AND_4",
                "description": "Direct live Shopify Admin GraphQL API integration with token management and read-back verification.",
                "live_target": "sanocea-commerce-os-dev.myshopify.com",
                "api_version": "2026-07",
                "invariants": [
                    "Encrypted AES-256-GCM credential vault in PostgreSQL",
                    "Multi-variant product publication via Admin GraphQL mutations",
                    "Immediate independent read-back verification of title, options, and variants",
                ],
            },
            "INVENTORY_ALLOCATION_AND_RESERVATIONS": {
                "status": "CERTIFIED",
                "evidence_stage": "STAGE_1_AND_CORE",
                "description": "Multi-location deterministic inventory allocation and atomic database reservations.",
                "locations": ["Delhi Central Hub", "Mumbai Bhiwandi Logistics Park", "Bengaluru South Node"],
                "invariants": [
                    "Atomic reservation (UPDATE ... WHERE available >= qty)",
                    "Idempotent reservation keys (prevents double-booking on replayed webhooks)",
                    "Priority-based warehouse routing with zero order splitting",
                ],
            },
            "POST_ORDER_OPERATIONS": {
                "status": "CERTIFIED",
                "evidence_stage": "STAGE_1_AND_CORE",
                "description": "Returns, exchanges, and policy-governed refund evaluations.",
                "invariants": [
                    "Return eligibility evaluation (7-day window, order verification)",
                    "Restock on return inspection grading",
                    "Refund financial discrepancy cap (strict max-order refund capacity)",
                ],
            },
            "AUDIT_LEDGER_AND_LINEAGE": {
                "status": "CERTIFIED",
                "evidence_stage": "STAGE_1_THROUGH_4",
                "description": "Tamper-proof append-only audit ledger with correlation IDs.",
                "invariants": [
                    "Database trigger prevent_audit_update_delete blocks any UPDATE or DELETE",
                    "Full end-to-end lineage from raw ingestion to publication and order settlement",
                ],
            },
            "MARKETPLACE_CONNECTORS_FLIPKART_AMAZON": {
                "status": "SIMULATED",
                "evidence_stage": "CORE_SIMULATED",
                "description": "In-memory simulated connector contract for multi-channel allocation testing.",
                "note": "Production live certification for Flipkart and Amazon pending live merchant credential provisioning.",
            },
            "LOGISTICS_3PL_DISPATCH": {
                "status": "SIMULATED",
                "evidence_stage": "CORE_SIMULATED",
                "description": "Simulated logistics connector minting tracking references and transit milestones.",
                "note": "Direct courier integration (Shiprocket/Delhivery/Bluedart) pending live merchant 3PL API keys.",
            },
            "GENERATIVE_AI_MARKETING_COPY": {
                "status": "UNAVAILABLE",
                "evidence_stage": "NOT_IMPLEMENTED",
                "description": "Automatic generative AI product title/description copywriting.",
                "reason": "Disabled by design under Zero-Invention commercial fact policy to guarantee zero hallucination.",
            },
            "DIRECT_WHATSAPP_BUYER_NOTIFICATIONS": {
                "status": "UNAVAILABLE",
                "evidence_stage": "NOT_IMPLEMENTED",
                "description": "Automated WhatsApp order updates and bot customer support.",
                "reason": "Out of scope for P0 remediation stages.",
            },
            "GRAPHICAL_WEB_DASHBOARD": {
                "status": "UNAVAILABLE",
                "evidence_stage": "NOT_IMPLEMENTED",
                "description": "Full drag-and-drop frontend control plane.",
                "reason": "P0 focus is headless, API-first and CLI-governed operational core.",
            },
        },
    }
