# Sanocea Commerce OS: Engine Hardening & Control Plane Architecture

## Executive Summary
Sanocea's core commerce engine has been audited, strengthened, and verified against high-risk production failure modes:
1. **Canonical Schema & Multi-Location Stock**: Added first-class `Location` entities and rigorous, location-scoped inventory tracking (`sellable`, `reserved`, `quarantine`, `in_transit`) with authoritative Available-to-Sell (`ATS = max(sellable - reserved, 0)`).
2. **State Machine Integrity**: Replaced raw string states with typed enum transitions (`OrderState`, `ReturnState`, `OperationalRefundState`, `FinancialReconciliationState`, `ApprovalState`) and strict transition graph validation.
3. **Operational vs. Financial Separation**: Kept physical logistics/fulfillment states (`delivered`, `in_transit`, `returned`) decoupled from financial reconciliation states (`reconciled`, `payout_received`, `disputed`).
4. **Deterministic Policy & Approval Queue**: Governed sensitive mutations (refunds over threshold, live catalog unpublishing, price changes, inventory write-offs) through a deterministic policy engine and human-in-the-loop approval service.
5. **J.A.R.V.I.S. Read-First & Proposer Role**: Refactored the JARVIS interface to serve as an intelligent observer and proposer; it can explain data and propose actions into the approval queue, but is strictly prohibited from direct write mutations.

---

## Architecture & Verification Matrix

| Domain Area | Production Risk | Engine Defense Implemented | Verification Status |
| :--- | :--- | :--- | :--- |
| **Location & Stock** | Overselling across warehouses; stock drifting across physical stores | Location-scoped `Inventory` model with `Location(CanonicalEntity)`. Authoritative `ats` property. Row-locked atomic reservation & quarantine (`SELECT ... FOR UPDATE`). | Verified via unit tests (`test_inventory_ats_and_quarantine_transitions`) & Postgres store. |
| **Order & Return States** | Invalid skips (e.g. `delivered` -> `created`, `refunded` before inspection) | Strict transition graphs (`ORDER_TRANSITIONS`, `RETURN_TRANSITIONS`, `APPROVAL_TRANSITIONS`). `InvalidStateTransitionError` raised on illegal paths. | Verified (`test_state_machine_invalid_transition_rejected`). |
| **Finance vs Ops** | Marking orders completed before bank settlement or COD remittance | Separate `Order.status` and `Order.financial_reconciliation_status`; independent `Refund.status` vs gateway reconciliation status. | Verified (`test_operational_and_financial_status_separation`). |
| **Sensitive Actions** | LLM hallucinating price drops or unauthorized high-value refunds | `PolicyEngine.evaluate_with_reason()` enforces deterministic rules for refunds, price reductions, and catalog unpublishing. Sensitive actions generate `Approval` records. | Verified (`test_policy_engine_evaluates_thresholds`, `test_approval_service_resolution_dispatch`). |
| **J.A.R.V.I.S. Interface** | Direct unauthenticated write access from voice/UI | Multi-tenant authenticated routes (`/merchants/{id}/approvals`, `/merchants/{id}/propose-action`). JARVIS only reads and proposes. | Verified live via WebSocket bridge and REST endpoints. |

---

## Core Implementations

### 1. Location-Scoped Inventory & ATS
- **File**: [`packages/domain_contract/models.py`](file:///D:/Autonomous%20E-Commerce%20ERP/sanocea/packages/domain_contract/models.py)
```python
class Inventory(CanonicalEntity):
    sku: str
    location_ref: str = Field(default="default")
    quantity: int = Field(default=0, ge=0)
    sellable: int = Field(default=0, ge=0)
    reserved: int = Field(default=0, ge=0)
    quarantine: int = Field(default=0, ge=0)
    in_transit: int = Field(default=0, ge=0)

    @property
    def ats(self) -> int:
        """Available To Sell = max(sellable - reserved, 0)"""
        return max(self.sellable - self.reserved, 0)
```
- **Row-Locked Quarantine & Release**:
  - Implemented `quarantine_inventory_atomic()` and `release_quarantine_atomic()` in [`packages/domain_contract/store.py`](file:///D:/Autonomous%20E-Commerce%20ERP/sanocea/packages/domain_contract/store.py) and [`packages/domain_contract/postgres_store.py`](file:///D:/Autonomous%20E-Commerce%20ERP/sanocea/packages/domain_contract/postgres_store.py) using `SELECT ... FOR UPDATE`.
  - Added REST endpoints: `POST /merchants/{merchant_id}/inventory/quarantine` and `POST /merchants/{merchant_id}/inventory/release-quarantine`.

### 2. Deterministic State Machine Transition Guard
- **File**: [`packages/domain_contract/models.py`](file:///D:/Autonomous%20E-Commerce%20ERP/sanocea/packages/domain_contract/models.py)
```python
class InvalidStateTransitionError(ValueError):
    """Raised when an illegal lifecycle state transition is attempted."""

def validate_state_transition(current_state: str, next_state: str, allowed_transitions: dict[str, set[str]]) -> None:
    if next_state not in allowed_transitions.get(current_state, set()):
        raise InvalidStateTransitionError(
            f"Illegal state transition from '{current_state}' to '{next_state}'. Allowed: {sorted(allowed_transitions.get(current_state, set()))}"
        )
```

### 3. Policy Engine & Approval Queue
- **File**: [`packages/policy_engine/engine.py`](file:///D:/Autonomous%20E-Commerce%20ERP/sanocea/packages/policy_engine/engine.py)
  - `evaluate_with_reason()` validates rules deterministically:
    - **Refund**: Threshold check on amount and percentage of order total.
    - **Price Change**: Checks percentage drop against `price_drop_pct_threshold` and live storefront status.
    - **Catalog Unpublish**: Mandatory approval if item has sellable inventory.
    - **Inventory Write-off**: Mandatory approval above value threshold.
- **File**: [`packages/approvals/service.py`](file:///D:/Autonomous%20E-Commerce%20ERP/sanocea/packages/approvals/service.py)
  - `request_approval()` records structured rationale, audit logs, and evidence.
  - `resolve()` enforces approval state transitions (`PENDING -> APPROVED / REJECTED`) and dispatches business execution for refunds, price updates, and catalog status.

### 4. JARVIS Control Plane Interface
- **File**: [`D:\jarvis\bridge\server.mjs`](file:///D:/jarvis/bridge/server.mjs)
  - Configured multi-tenant operator authentication with `SANOCEA_API_KEY` and `SANOCEA_MERCHANT_ID`.
  - Added REST integration functions `getPendingApprovals()` and `proposeAction()`.
  - Added intent handlers and Gemini streaming tools for `get_pending_approvals` and `propose_action`.
  - Live tested in both English and Hindi:
    - *"Are there any pending approvals in Sanocea?"* -> Queries control plane, reports pending approval count.
    - *"क्या सनोशिया में कोई पेंडिंग अप्रूवल है?"* -> Direct intent invocation.

---

## Verification & Test Results
- **Pytest Unit Suite**: 384 tests passed in 4.60s ([`tests/unit/test_production_control_plane.py`](file:///D:/Autonomous%20E-Commerce%20ERP/sanocea/tests/unit/test_production_control_plane.py) included).
- **Knowledge Graph**: Rebuilt and synchronized via `graphify update .` (3,841 nodes, 9,966 edges across 215 communities).
- **Services Online**:
  - Sanocea API Server: Healthy on `http://127.0.0.1:8080` (FastAPI + PostgreSQL on port `55199`).
  - JARVIS Voice/Bridge: Active on `ws://127.0.0.1:8787` and UI on `http://localhost:5173`.
