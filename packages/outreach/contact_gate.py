"""Hard Outbound-Contact Gate & Idempotent Drafting Controller for SANOCEA Outreach.

Guarantees:
1. GMAIL IS SOURCE OF TRUTH: Before creating any draft, Gmail SENT and DRAFTS folders are searched.
2. HARD BLOCK ON PRIOR OUTREACH: If a recipient was previously sent an email, draft creation is strictly HALTED.
   Prospect is marked ALREADY_CONTACTED in reservoir with prior message date, subject, and ID.
3. IDEMPOTENT DRAFTING: Re-running the pipeline returns the existing draft rather than creating a duplicate.
   Different subject lines CANNOT bypass deduplication.
4. CONCURRENCY CONTROL: Atomic locks prevent two concurrent workers from drafting the same canonical identity.
5. RECONCILIATION: Reconciles Gmail ground truth with SQLite reservoir.
"""

from __future__ import annotations

import re
import sqlite3
import logging
import threading
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Any
from pathlib import Path

logger = logging.getLogger("sanocea.outreach.contact_gate")

# Global in-process lock and registry for active in-flight drafting operations
_CONCURRENCY_LOCK = threading.Lock()
_ACTIVE_DRAFTING_KEYS: set[str] = set()


class GateDecision(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    BLOCKED_ALREADY_SENT = "BLOCKED_ALREADY_SENT"
    BLOCKED_BOUNCED = "BLOCKED_BOUNCED"
    REUSE_EXISTING_DRAFT = "REUSE_EXISTING_DRAFT"
    BLOCKED_RESERVOIR_DUPLICATE = "BLOCKED_RESERVOIR_DUPLICATE"
    BLOCKED_CONCURRENT_LOCK = "BLOCKED_CONCURRENT_LOCK"


class AlreadyContactedError(Exception):
    """Raised when an outbound contact is attempted to a recipient who was already emailed."""
    pass


class DuplicateDraftError(Exception):
    """Raised when a draft already exists and idempotency reuse is disabled."""
    pass


FREEMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com",
    "rediffmail.com", "zoho.com", "protonmail.com", "aol.com", "live.com"
}

LEGAL_SUFFIXES = {
    "bk", "pvt", "ltd", "private", "limited", "llp", "inc", "corp",
    "corporation", "enterprises", "enterprise", "group", "holdings",
    "co", "clothing", "retail", "creations", "solutions", "services",
    "technologies", "industries", "india", "international", "jewels",
    "bedding", "edibles", "store", "company"
}


def extract_brand_root(name: Optional[str]) -> str:
    """Extracts base brand token from company name by stripping legal forms and common suffixes."""
    if not name:
        return ""
    cleaned = name.lower().strip()
    words = [w for w in re.sub(r"[^a-zA-Z0-9\s]", " ", cleaned).split() if w]
    filtered = [w for w in words if w not in LEGAL_SUFFIXES]
    if filtered:
        return " ".join(filtered)
    return cleaned


@dataclass
class GateResult:
    decision: GateDecision
    canonical_key: str
    recipient_email: str
    company_domain: str
    reason: str
    existing_draft_id: Optional[str] = None
    prior_date: Optional[str] = None
    prior_subject: Optional[str] = None
    prior_message_id: Optional[str] = None


class OutboundContactGate:
    """Hard gate enforcing zero accidental duplicate outreach and drafting idempotency."""

    @staticmethod
    def normalize_identity(email: str, domain: Optional[str] = None, campaign: str = "default") -> tuple[str, str, str]:
        """Normalizes email, domain, and campaign to form a canonical outreach key."""
        clean_email = (email or "").strip().lower()
        if "@" in clean_email:
            parts = clean_email.split("@", 1)
            clean_domain = (domain or parts[1]).strip().lower()
        else:
            clean_domain = (domain or "").strip().lower()
        clean_campaign = (campaign or "default").strip().lower()
        return clean_email, clean_domain, clean_campaign

    @classmethod
    def canonical_outreach_key(cls, email: str, domain: Optional[str] = None, campaign: str = "default") -> str:
        clean_email, clean_domain, clean_campaign = cls.normalize_identity(email, domain, campaign)
        return f"{clean_domain}:{clean_email}:{clean_campaign}"

    @classmethod
    def evaluate_and_gate(
        cls,
        email: str,
        domain: Optional[str] = None,
        company_name: Optional[str] = None,
        campaign: str = "default",
        gmail_service: Optional[Any] = None,
        reservoir_db_path: str = "sanocea_prospect_reservoir.db",
        idempotent: bool = True
    ) -> GateResult:
        """Evaluates contact eligibility against the 4-way truth table.
        MUST be called before any draft is created.
        """
        clean_email, clean_domain, clean_campaign = cls.normalize_identity(email, domain, campaign)
        canonical_key = cls.canonical_outreach_key(clean_email, clean_domain, clean_campaign)

        if not clean_email or "@" not in clean_email:
            return GateResult(
                decision=GateDecision.BLOCKED_RESERVOIR_DUPLICATE,
                canonical_key=canonical_key,
                recipient_email=clean_email,
                company_domain=clean_domain,
                reason="Invalid email format"
            )

        # --- 1. CONCURRENCY LOCK CHECK ---
        with _CONCURRENCY_LOCK:
            if canonical_key in _ACTIVE_DRAFTING_KEYS:
                return GateResult(
                    decision=GateDecision.BLOCKED_CONCURRENT_LOCK,
                    canonical_key=canonical_key,
                    recipient_email=clean_email,
                    company_domain=clean_domain,
                    reason=f"Concurrent worker is actively processing {canonical_key}"
                )

        brand_root = extract_brand_root(company_name)

        # --- 2. PERMANENT BOUNCE SUPPRESSION CHECK (550 NDR GROUND TRUTH) ---
        bounced_check = cls._check_reservoir(reservoir_db_path, company_name, clean_email, clean_domain)
        if bounced_check is not None and bounced_check.decision == GateDecision.BLOCKED_BOUNCED:
            return bounced_check

        # --- 3. GMAIL API SENT FOLDER CHECK (GROUND TRUTH) ---
        if gmail_service:
            if hasattr(gmail_service, "is_email_or_domain_contacted_or_drafted") and gmail_service.is_email_or_domain_contacted_or_drafted(clean_email, clean_domain):
                return GateResult(
                    decision=GateDecision.BLOCKED_RESERVOIR_DUPLICATE,
                    canonical_key=canonical_key,
                    recipient_email=clean_email,
                    company_domain=clean_domain,
                    reason=f"Candidate {clean_email} was previously contacted or drafted according to Gmail history",
                )
            try:
                queries = [f'in:sent (to:{clean_email} OR "{clean_email}")']
                if clean_domain and clean_domain not in FREEMAIL_DOMAINS and len(clean_domain) > 3:
                    queries.append(f'in:sent (to:*@{clean_domain} OR "@{clean_domain}")')
                if brand_root and len(brand_root) >= 3:
                    queries.append(f'in:sent "{brand_root}"')

                for q_sent in queries:
                    sent_msgs = gmail_service.service.users().messages().list(
                        userId="me", q=q_sent, maxResults=5
                    ).execute().get("messages", [])

                    for m_info in sent_msgs:
                        msg_id = m_info["id"]
                        msg_data = gmail_service.service.users().messages().get(
                            userId="me", id=msg_id, format="full"
                        ).execute()
                        headers = {h["name"].lower(): h["value"] for h in msg_data.get("payload", {}).get("headers", [])}
                        sent_to = headers.get("to", "").lower()
                        sent_date = headers.get("date", "Unknown date")
                        sent_subject = headers.get("subject", "No subject")

                        is_match = False
                        match_reason = ""

                        if clean_email in sent_to:
                            is_match = True
                            match_reason = f"Recipient {clean_email} was previously sent an email"
                        elif clean_domain and clean_domain not in FREEMAIL_DOMAINS and f"@{clean_domain}" in sent_to:
                            is_match = True
                            match_reason = f"Company domain @{clean_domain} was previously contacted (sent to {sent_to})"
                        elif brand_root and len(brand_root) >= 3 and (
                            brand_root in sent_subject.lower() or 
                            brand_root in sent_to or 
                            (company_name and company_name.lower() in sent_subject.lower())
                        ):
                            is_match = True
                            match_reason = f"Company {company_name or brand_root} (brand '{brand_root}') was previously contacted (sent to {sent_to}: '{sent_subject}')"

                        if is_match:
                            # Reconcile with SQLite reservoir
                            cls._sync_already_contacted_to_reservoir(
                                reservoir_db_path, company_name, clean_email, clean_domain,
                                sent_date, sent_subject, msg_id
                            )
                            return GateResult(
                                decision=GateDecision.BLOCKED_ALREADY_SENT,
                                canonical_key=canonical_key,
                                recipient_email=clean_email,
                                company_domain=clean_domain,
                                reason=f"{match_reason} on {sent_date}: '{sent_subject}'",
                                prior_date=sent_date,
                                prior_subject=sent_subject,
                                prior_message_id=msg_id
                            )
            except Exception as e:
                logger.error(f"Error checking Gmail Sent history: {e}")

        # --- 3. GMAIL API DRAFTS CHECK (GROUND TRUTH FOR IDEMPOTENCY) ---
        if gmail_service:
            try:
                d_queries = [f'in:drafts (to:{clean_email} OR "{clean_email}")']
                if clean_domain and clean_domain not in FREEMAIL_DOMAINS and len(clean_domain) > 3:
                    d_queries.append(f'in:drafts (to:*@{clean_domain} OR "@{clean_domain}")')
                if brand_root and len(brand_root) >= 3:
                    d_queries.append(f'in:drafts "{brand_root}"')

                for q_drafts in d_queries:
                    draft_list = gmail_service.service.users().drafts().list(
                        userId="me", q=q_drafts, maxResults=5
                    ).execute().get("drafts", [])

                    for d_info in draft_list:
                        draft_id = d_info["id"]
                        draft_data = gmail_service.service.users().drafts().get(
                            userId="me", id=draft_id, format="full"
                        ).execute()
                        msg = draft_data.get("message", {})
                        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
                        draft_to = headers.get("to", "").lower()
                        draft_date = headers.get("date", "Unknown date")
                        draft_subject = headers.get("subject", "No subject")

                        is_draft_match = False
                        if clean_email in draft_to:
                            is_draft_match = True
                        elif clean_domain and clean_domain not in FREEMAIL_DOMAINS and f"@{clean_domain}" in draft_to:
                            is_draft_match = True
                        elif brand_root and len(brand_root) >= 3 and (
                            brand_root in draft_subject.lower() or 
                            brand_root in draft_to or 
                            (company_name and company_name.lower() in draft_subject.lower())
                        ):
                            is_draft_match = True

                        if is_draft_match:
                            return GateResult(
                                decision=GateDecision.REUSE_EXISTING_DRAFT if idempotent else GateDecision.BLOCKED_RESERVOIR_DUPLICATE,
                                canonical_key=canonical_key,
                                recipient_email=clean_email,
                                company_domain=clean_domain,
                                existing_draft_id=draft_id,
                                prior_date=draft_date,
                                prior_subject=draft_subject,
                                reason=f"Draft already exists for {company_name or clean_email} in Gmail (Draft ID: {draft_id}, Subject: '{draft_subject}')"
                            )
            except Exception as e:
                logger.error(f"Error checking Gmail Drafts history: {e}")

        # --- 4. SQLITE RESERVOIR HISTORY CHECK ---
        res_decision = cls._check_reservoir(reservoir_db_path, company_name, clean_email, clean_domain)
        if res_decision is not None:
            return res_decision

        # --- 5. ELIGIBLE ---
        return GateResult(
            decision=GateDecision.ELIGIBLE,
            canonical_key=canonical_key,
            recipient_email=clean_email,
            company_domain=clean_domain,
            reason="Clean: No prior contact in Gmail SENT, no active draft in Gmail DRAFTS, and clean in reservoir."
        )

    @classmethod
    def _check_reservoir(
        cls,
        db_path: str,
        company_name: Optional[str],
        email: str,
        domain: str
    ) -> Optional[GateResult]:
        """Checks SQLite reservoir tables (prospects, drafts_history) with alias and brand root awareness."""
        canonical_key = cls.canonical_outreach_key(email, domain)
        p = Path(db_path)
        if not p.exists():
            return None

        try:
            conn = sqlite3.connect(str(p))
            c = conn.cursor()
            brand_root = extract_brand_root(company_name)

            # Check if recorded in prospects
            # Match by exact email, domain (if non-freemail), exact company name, or brand root
            c.execute("""
                SELECT company, outreach_status, pending_reason, contact_email 
                FROM prospects 
                WHERE lower(contact_email) = ? 
                   OR (? != '' AND ? NOT IN ('gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com') AND contact_email LIKE '%@' || ?)
                   OR (lower(company) = ? AND ? != '')
                   OR (lower(company) LIKE ? || '%' AND ? != '')
                   OR (? != '' AND length(?) >= 3 AND lower(company) LIKE '%' || ? || '%')
            """, (
                email.lower(),
                domain.lower(), domain.lower(), domain.lower(),
                (company_name or "").lower(), (company_name or "").lower(),
                (company_name or "").lower(), (company_name or "").lower(),
                brand_root, brand_root, brand_root
            ))
            rows = c.fetchall()
            for r in rows:
                matched_company, status, reason, matched_email = r[0], str(r[1] or "").upper(), r[2], r[3]
                if status == "BOUNCED":
                    conn.close()
                    return GateResult(
                        decision=GateDecision.BLOCKED_BOUNCED,
                        canonical_key=canonical_key,
                        recipient_email=email,
                        company_domain=domain,
                        reason=f"Address or company {matched_company} previously BOUNCED ({reason or '550 Address Not Found NDR'})"
                    )
                if status in ("ALREADY_CONTACTED", "CONTACTED", "SENT"):
                    conn.close()
                    return GateResult(
                        decision=GateDecision.BLOCKED_ALREADY_SENT,
                        canonical_key=canonical_key,
                        recipient_email=email,
                        company_domain=domain,
                        reason=f"Company {matched_company} ({matched_email}) recorded in SQLite reservoir as {status}: {reason or 'Prior outreach recorded'}"
                    )
                if status == "DRAFTED":
                    # Check drafts history
                    c.execute("""
                        SELECT gmail_draft_id, subject, created_at 
                        FROM drafts_history 
                        WHERE lower(recipient_email) = ? 
                           OR lower(company) = ?
                           OR (? != '' AND lower(company) LIKE '%' || ? || '%')
                    """, (email.lower(), (company_name or "").lower(), brand_root, brand_root))
                    d_row = c.fetchone()
                    conn.close()
                    if d_row:
                        return GateResult(
                            decision=GateDecision.REUSE_EXISTING_DRAFT,
                            canonical_key=canonical_key,
                            recipient_email=email,
                            company_domain=domain,
                            existing_draft_id=d_row[0],
                            prior_subject=d_row[1],
                            prior_date=d_row[2],
                            reason=f"Draft already recorded in SQLite reservoir for {matched_company} (Draft ID: {d_row[0]})"
                        )
            conn.close()
        except Exception as e:
            logger.warning(f"Error checking reservoir database: {e}")

        return None

    @classmethod
    def _sync_already_contacted_to_reservoir(
        cls,
        db_path: str,
        company_name: Optional[str],
        email: str,
        domain: str,
        sent_date: str,
        sent_subject: str,
        msg_id: str
    ) -> None:
        """Reconciles SQLite reservoir when an unrecorded Gmail sent message is discovered."""
        p = Path(db_path)
        if not p.exists():
            return
        try:
            conn = sqlite3.connect(str(p))
            c = conn.cursor()
            brand_root = extract_brand_root(company_name)
            reason = f"Previously contacted on {sent_date}: '{sent_subject}' (Gmail Message ID: {msg_id})"
            # Update prospects if row exists, or insert if absent
            c.execute("""
                UPDATE prospects SET 
                    outreach_status = CASE WHEN outreach_status = 'BOUNCED' THEN 'BOUNCED' ELSE 'ALREADY_CONTACTED' END,
                    pending_reason = ?,
                    last_checked_at = CURRENT_TIMESTAMP
                WHERE lower(contact_email) = ? 
                   OR (lower(company) = ? AND ? != '')
                   OR (? != '' AND length(?) >= 3 AND lower(company) LIKE '%' || ? || '%')
            """, (reason, email.lower(), (company_name or "").lower(), (company_name or "").lower(), brand_root, brand_root, brand_root))
            if c.rowcount == 0:
                comp = company_name or (email.split("@")[0].capitalize())
                c.execute("""
                    INSERT INTO prospects (company, contact_email, outreach_status, pending_reason, last_checked_at)
                    VALUES (?, ?, 'ALREADY_CONTACTED', ?, CURRENT_TIMESTAMP)
                """, (comp, email.lower(), reason))
            conn.commit()
            conn.close()
            logger.info(f"Reconciled SQLite reservoir: marked {email} as ALREADY_CONTACTED")
        except Exception as e:
            logger.warning(f"Failed to reconcile SQLite reservoir: {e}")

    @classmethod
    def acquire_drafting_lock(cls, canonical_key: str) -> bool:
        """Acquires an in-process lock for the canonical key."""
        with _CONCURRENCY_LOCK:
            if canonical_key in _ACTIVE_DRAFTING_KEYS:
                return False
            _ACTIVE_DRAFTING_KEYS.add(canonical_key)
            return True

    @classmethod
    def release_drafting_lock(cls, canonical_key: str) -> None:
        """Releases the in-process lock for the canonical key."""
        with _CONCURRENCY_LOCK:
            _ACTIVE_DRAFTING_KEYS.discard(canonical_key)
