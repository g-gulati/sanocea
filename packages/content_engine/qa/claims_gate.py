"""
Claims and factual accuracy QA gate for SANOCEA Content Engine.
Rejects fabricated statistics, unsubstantiated percentages, and generic AI SaaS hype.
"""

import re
from typing import List, Tuple
from packages.content_engine.models import ContentCopy, QACheckItem


class ClaimsGate:
    """Enforces zero fabricated claims, unverified statistics, or hyperbolic marketing language."""

    FORBIDDEN_HYPE_PATTERNS = [
        r"\b(?:guaranteed|instant)\s+(?:profit|roi|results|revenue)\b",
        r"\btrusted\s+by\s+\d+\+\s+(?:brands|customers|merchants)\b",
        r"\b\d+%\s+(?:guaranteed|instant|increase|boost|savings)\b",
        r"\b10x\s+(?:growth|roi|faster|revenue)\b",
        r"\brevolutionary\s+ai\b",
        r"\bmagic(?:ally)?\b",
        r"\bunlimited\s+growth\b",
        r"\bset\s+it\s+and\s+forget\s+it\b"
    ]

    DISALLOWED_SLOGANS = [
        "AUTOMATE | OPTIMISE | SCALE | GROW",
        "AUTOMATE | OPTIMIZE | SCALE | GROW",
        "ALL-IN-ONE ECOMMERCE SOLUTION"
    ]

    def validate(self, copy: ContentCopy) -> Tuple[bool, List[QACheckItem]]:
        checks = []
        passed = True
        combined_text = f"{copy.headline_hook} {copy.problem_narrative} {copy.mechanism_explanation} {copy.solution_narrative} {copy.call_to_action}"

        # 1. Check for forbidden hype patterns
        found_hype = []
        for pat in self.FORBIDDEN_HYPE_PATTERNS:
            matches = re.findall(pat, combined_text, re.IGNORECASE)
            if matches:
                found_hype.extend(matches)

        if found_hype:
            passed = False
            checks.append(QACheckItem(
                check_name="no_unsupported_hype",
                passed=False,
                details=f"Forbidden hype detected: {', '.join(found_hype)}"
            ))
        else:
            checks.append(QACheckItem(
                check_name="no_unsupported_hype",
                passed=True,
                details="No exaggerated or hyperbolic claims detected."
            ))

        # 2. Check for discarded slogan lockups
        found_slogans = []
        for slogan in self.DISALLOWED_SLOGANS:
            if slogan.lower() in combined_text.lower():
                found_slogans.append(slogan)

        if found_slogans:
            passed = False
            checks.append(QACheckItem(
                check_name="no_discarded_slogans",
                passed=False,
                details=f"Deprecated brand lockup detected: {', '.join(found_slogans)}"
            ))
        else:
            checks.append(QACheckItem(
                check_name="no_discarded_slogans",
                passed=True,
                details="No deprecated slogan lockups found."
            ))

        # 3. Check for unverified numerical statistics (e.g. saves 47% or 99.8%)
        stat_patterns = re.findall(r"\b\d{2,3}%\b", combined_text)
        # Note: 5% discount or 80% traffic drop in problem context is allowed, but suspicious claims are flagged
        suspicious_stats = [s for s in stat_patterns if any(w in combined_text.lower() for w in ["reduction", "savings", "efficiency", "boost"])]
        if suspicious_stats:
            passed = False
            checks.append(QACheckItem(
                check_name="no_fabricated_stats",
                passed=False,
                details=f"Unverified statistical claims detected: {', '.join(suspicious_stats)}"
            ))
        else:
            checks.append(QACheckItem(
                check_name="no_fabricated_stats",
                passed=True,
                details="No fabricated statistical proof claims detected."
            ))

        return passed, checks
