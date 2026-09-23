from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from sanocea.packages.domain_contract.models import (
    Approval,
    Channel,
    ConnectorCommand,
    CustomerSupportAction,
    ExceptionRecord,
    ListingVerification,
    Merchant,
    ProductDraft,
    Publication,
    WorkflowExecution,
)
from sanocea.packages.domain_contract.postgres_store import PostgresStore
from sanocea.packages.domain_contract.store import Phase0Store


def create_dashboard(store: Phase0Store | PostgresStore | None = None) -> FastAPI:
    if store is None:
        if os.environ.get("SANOCEA_USE_IN_MEMORY_STORE") == "1":
            store = Phase0Store()
        else:
            dsn = os.environ.get("SANOCEA_PG_DSN")
            if not dsn:
                raise RuntimeError(
                    "SANOCEA_PG_DSN is required. Set SANOCEA_USE_IN_MEMORY_STORE=1 only for unit harnesses."
                )
            store = PostgresStore(dsn)
            store.migrate()
    app = FastAPI(title="Sanocea Operator Dashboard")

    @app.get("/", response_class=HTMLResponse)
    def index(merchant_id: str = "system") -> str:
        sections = {
            "Merchants": store.list(Merchant, merchant_id),
            "Channels": store.list(Channel, merchant_id),
            "Products Needing Approval": [
                item for item in store.list(ProductDraft, merchant_id)
                if item.state == "NEEDS_APPROVAL" or item.approved_for_publication is False
            ],
            "Incomplete/Conflicted Product Drafts": [
                item for item in store.list(ProductDraft, merchant_id)
                if item.state in ("INCOMPLETE", "CONFLICTED", "INVALID")
            ],
            "Publications": store.list(Publication, merchant_id),
            "Publication Failures/Mismatches": [
                item for item in store.list(ListingVerification, merchant_id)
                if item.outcome in ("MISMATCH", "FAILED", "UNKNOWN")
            ],
            "Workflows": store.list(WorkflowExecution, merchant_id),
            "Approvals": store.list(Approval, merchant_id),
            "Exceptions": store.list(ExceptionRecord, merchant_id),
            "Support Escalations": [
                item for item in store.list(CustomerSupportAction, merchant_id)
                if item.handling_mode in ("APPROVAL-GATED", "EXCEPTION-ONLY", "MANUAL")
            ],
            "Connector Commands": store.list(ConnectorCommand, merchant_id),
        }
        audit = store.list_audit(merchant_id)
        html = ["<html><body><h1>Sanocea Phase 0 Operator Dashboard</h1>"]
        for title, items in sections.items():
            html.append(f"<h2>{title}</h2><pre>{[i.model_dump(mode='json') for i in items]}</pre>")
        html.append(f"<h2>Audit Events</h2><pre>{[a.model_dump(mode='json') for a in audit]}</pre>")
        html.append("</body></html>")
        return "\n".join(html)

    return app
