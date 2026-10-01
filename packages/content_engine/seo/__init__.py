"""SEO content workflow: approved opportunity -> content brief -> draft, built ON the existing content engine.

Reuses (does not duplicate): QACheckItem/QAResult (models), ClaimsGate (qa), DeduplicationEngine similarity (dedup),
the human-approval convention (review.approval), tenant ids and the JSON-file store convention. It stops at DRAFT:
no publishing, distribution or measurement lives here.
"""
