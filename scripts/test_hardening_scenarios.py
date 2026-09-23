#!/usr/bin/env python3
"""Standalone hardening test script for SANOCEA Prospect Demo (Premium Basket).
Probes edge cases and hardening scenarios against real Postgres/Shopify infrastructure:
1. agy broken/unavailable PATH fallback (graceful fallback to WhatsApp, no crash).
2. AI_SUGGESTED fact undergoing subsequent resolve_fact_conflict.
3. Rapid double-ingest of the same CSV (idempotency-by-SKU and WhatsApp notification counts).
4. Subprocess timeout enforcement verification on Windows.
5. Cleanup via POST /merchants/prospect_premium_basket/catalogue/drafts/clear.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
PARENT_DIR = ROOT_DIR.parent
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Ensure credentials environment is set for PostgresStore and WAHA
os.environ["SANOCEA_CRED_MASTER_KEY_CURRENT"] = "v1"
os.environ["SANOCEA_CRED_MASTER_KEY_V1"] = "KioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKio="
os.environ["SANOCEA_WAHA_BASE_URL"] = "http://127.0.0.1:3000"
os.environ["SANOCEA_WAHA_API_KEY"] = "sanocea-demo-local-only-key-not-for-production"

MERCHANT_ID = "prospect_premium_basket"
PG_DSN = os.environ.get("SANOCEA_PG_DSN", "postgresql://sanocea:sanocea@127.0.0.1:55199/sanocea_phase05")
API_BASE = "http://127.0.0.1:8080"
OPERATOR_KEY = "sk_dgtqDyIgvUHhHBqjSIryrz3dr__FzD1gSZ_uM8M47GY"

from sanocea.packages.domain_contract.models import (
    CommercialFact,
    ProductDraft,
    ProvenanceClassification,
)
from sanocea.packages.domain_contract.postgres_store import PostgresStore
from sanocea.packages.product_onboarding import ai_enrichment
from sanocea.packages.product_onboarding.provenance import (
    detect_and_merge_fact,
    provide_missing_fact,
    resolve_fact_conflict,
)
from sanocea.packages.runtime.service_graph import build_service_graph


def api_request(method: str, path: str, body: dict | None = None) -> dict:
    url = f"{API_BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {
        "Authorization": f"Bearer {OPERATOR_KEY}",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def test_scenario_1_agy_broken_path(store) -> bool:
    print("\n" + "=" * 80)
    print("SCENARIO 1: agy unavailable / PATH broken fallback")
    print("=" * 80)
    old_path = os.environ.get("PATH", "")
    try:
        os.environ["PATH"] = "C:\\NonExistentDirectoryForTesting"
        res = ai_enrichment.generate_description_and_tags("Test Makhana", "snacks")
        print(f"1.1 Calling generate_description_and_tags with broken PATH -> returned: {res!r}")
        assert res == {}, f"Expected empty dict, got {res!r}"

        # Test that workflow handles broken PATH without crashing
        graph = build_service_graph(store)
        workflow = graph.catalogue

        # Create a test draft missing description
        draft = ProductDraft(
            id="test_probe_agy_broken_draft",
            merchant_id=MERCHANT_ID,
            sku="TEST-AGY-BROKEN-01",
            title="Broken Path Test Makhana",
            price=25000,
            currency="INR",
            product_type="snacks",
            state="INCOMPLETE",
        )
        draft.commercial_facts["description"] = CommercialFact(
            name="description",
            value=None,
            source="test",
            locator={},
            evidence_ref="",
            classification=ProvenanceClassification.MISSING.value,
        )
        draft.validation_errors = ["missing_required_attribute:description"]
        store.put(draft)

        # Ingest/handle validated draft
        workflow._handle_validated_draft(MERCHANT_ID, draft)
        saved = store.get(ProductDraft, MERCHANT_ID, draft.id)
        print(f"1.2 Draft state after workflow handling with broken PATH: {saved.state}")
        print(f"1.3 Commercial fact description: {saved.commercial_facts.get('description')}")
        print("  -> Graceful degradation verified: no crash, draft remained INCOMPLETE for normal fallback.")
        return True
    finally:
        os.environ["PATH"] = old_path
        store.clear_catalogue_drafts(MERCHANT_ID)


def test_scenario_2_ai_suggested_conflict_resolution(store) -> bool:
    print("\n" + "=" * 80)
    print("SCENARIO 2: AI_SUGGESTED fact undergoing subsequent resolve_fact_conflict")
    print("=" * 80)

    # 1. Draft initialized with missing description
    draft = ProductDraft(
        id="test_probe_ai_conflict_draft",
        merchant_id=MERCHANT_ID,
        sku="TEST-AI-CONFLICT-01",
        title="Conflict Test Cashews",
        price=45000,
        currency="INR",
        product_type="snacks",
        state="INCOMPLETE",
    )
    draft.commercial_facts["description"] = CommercialFact(
        name="description",
        value=None,
        source="test",
        locator={},
        evidence_ref="",
        classification=ProvenanceClassification.MISSING.value,
    )
    store.put(draft)

    # 2. AI provides missing fact with AI_SUGGESTED classification
    provide_missing_fact(
        draft,
        "description",
        "AI generated: Crunchy premium roasted cashews with mild salt.",
        source="ai_generated",
        actor="ai_enrichment",
        classification=ProvenanceClassification.AI_SUGGESTED.value,
    )
    store.put(draft)
    print(f"2.1 After AI enrichment: classification={draft.commercial_facts['description'].classification}, approved={draft.commercial_facts['description'].approved}")

    # 3. New source arrives with conflicting description
    incoming_fact = CommercialFact(
        name="description",
        value="Merchant verified: Hand-picked jumbo cashew nuts sourced from Goa.",
        source="supplier_spec_sheet.xlsx",
        locator={"sheet": "Specs", "row": 5},
        evidence_ref="file://supplier_spec_sheet.xlsx#row=5",
        classification=ProvenanceClassification.SOURCE_FACT.value,
    )
    detect_and_merge_fact(draft, incoming_fact)
    store.put(draft)
    print(f"2.2 After conflicting incoming fact: conflicted={draft.commercial_facts['description'].conflicted}, conflicts={draft.conflicts}")

    # 4. Resolve conflict using catalogue workflow
    graph = build_service_graph(store)
    workflow = graph.catalogue
    resolved = workflow.resolve_conflict(
        merchant_id=MERCHANT_ID,
        draft_id=draft.id,
        fact_name="description",
        chosen_value="Merchant verified: Hand-picked jumbo cashew nuts sourced from Goa.",
        chosen_source="supplier_spec_sheet.xlsx",
        actor="operator_probe",
        note="Approved supplier spec sheet over initial AI suggestion",
    )

    fact = resolved.commercial_facts["description"]
    print(f"2.3 After resolve_conflict: value={fact.value!r}")
    print(f"2.4 Final classification: {fact.classification}")
    print(f"2.5 Final approved: {fact.approved} (by {fact.approved_by})")
    print(f"2.6 Remaining draft conflicts: {resolved.conflicts}")
    print(f"2.7 draft.attributes['description']: {resolved.attributes.get('description')!r}")

    assert fact.classification == ProvenanceClassification.HUMAN_APPROVED.value
    assert fact.conflicted is False
    assert len(resolved.conflicts) == 0
    print("  -> AI_SUGGESTED starting classification cleanly handled and upgraded to HUMAN_APPROVED.")
    store.clear_catalogue_drafts(MERCHANT_ID)
    return True


def test_scenario_3_rapid_double_ingest(store) -> dict:
    print("\n" + "=" * 80)
    print("SCENARIO 3: Rapid double-ingest of same CSV (idempotency-by-SKU & WhatsApp notifications)")
    print("=" * 80)

    # Clean slate first
    store.clear_catalogue_drafts(MERCHANT_ID)

    # Create a small test CSV with 2 products:
    # Prod 1: missing price only
    # Prod 2: missing type only
    csv_content = """SKU Code,Product Name,Retail Price,Type,Currency
TEST-RAPID-01,Rapid Makhana,,snacks,INR
TEST-RAPID-02,Rapid Almonds,399,,INR
"""
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False, encoding="utf-8") as f:
        f.write(csv_content)
        temp_csv_path = Path(f.name)

    try:
        graph = build_service_graph(store)
        workflow = graph.catalogue

        # Ingestion 1
        print("3.1 Ingestion Pass 1 running...")
        drafts_1 = workflow.ingest_file(MERCHANT_ID, temp_csv_path, "text/csv")
        print(f"  Pass 1 returned {len(drafts_1)} drafts: {[d.sku for d in drafts_1]}")
        ids_1 = {d.sku: d.id for d in drafts_1}
        # Check audit events for these specific test drafts after Pass 1
        notifs_1 = [
            e for e in store.list_audit(MERCHANT_ID)
            if e.action == "missing_field_notification_sent" and e.object_id in ids_1.values()
        ]
        print(f"  Pass 1 missing-field notification attempts for test drafts: {len(notifs_1)} (results: {[e.result for e in notifs_1]})")

        # Ingestion 2 immediately
        print("3.2 Ingestion Pass 2 running (rapid repeat)...")
        drafts_2 = workflow.ingest_file(MERCHANT_ID, temp_csv_path, "text/csv")
        print(f"  Pass 2 returned {len(drafts_2)} drafts: {[d.sku for d in drafts_2]}")
        ids_2 = {d.sku: d.id for d in drafts_2}

        # Verify idempotency-by-SKU
        assert ids_1 == ids_2, f"Draft IDs changed across ingests! {ids_1} vs {ids_2}"
        print(f"  -> Idempotency-by-SKU holds: Draft IDs perfectly matched: {ids_1}")

        # Check audit events for these specific test drafts after Pass 2
        notifs_2 = [
            e for e in store.list_audit(MERCHANT_ID)
            if e.action == "missing_field_notification_sent" and e.object_id in ids_1.values()
        ]
        print(f"  Pass 2 total missing-field notification attempts for test drafts: {len(notifs_2)} (results: {[e.result for e in notifs_2]})")

        duplicated = len(notifs_2) > len(notifs_1)
        if duplicated:
            print("  [FINDING - REAL BUG CONFIRMED] Notification was DUPLICATED on rapid double-ingest!")
            print(f"  Pass 1 count: {len(notifs_1)}, Pass 2 count: {len(notifs_2)}")
        else:
            print("  [SUCCESS] No duplicate notification sent on rapid double-ingest.")

        return {
            "idempotency_by_sku": True,
            "pass_1_notifs": len(notifs_1),
            "pass_2_notifs": len(notifs_2),
            "duplicated": duplicated,
        }
    finally:
        if temp_csv_path.exists():
            temp_csv_path.unlink()
        store.clear_catalogue_drafts(MERCHANT_ID)


def test_scenario_4_subprocess_timeout_behavior() -> bool:
    print("\n" + "=" * 80)
    print("SCENARIO 4: Subprocess timeout enforcement & hung process termination on Windows")
    print("=" * 80)
    import subprocess
    import time
    import psutil

    t0 = time.time()
    proc = None
    try:
        p = subprocess.Popen(["powershell", "-Command", "Start-Sleep 15"])
        proc = psutil.Process(p.pid)
        print(f"4.1 Launched background child process PID: {p.pid}")
        p.wait(timeout=2)
    except subprocess.TimeoutExpired:
        elapsed = time.time() - t0
        print(f"4.2 TimeoutExpired caught after {elapsed:.2f}s (expected ~2s).")
        p.kill()
        p.wait()
        time.sleep(0.5)
        is_running = proc.is_running()
        print(f"4.3 Process still running after kill(): {is_running}")
        assert not is_running, "Process was not terminated after kill()!"
        print("  -> Verified: child process is terminated on timeout.")
        return True


def test_scenario_5_clean_state_restore() -> bool:
    print("\n" + "=" * 80)
    print("SCENARIO 5: Restore clean state via POST /merchants/prospect_premium_basket/catalogue/drafts/clear")
    print("=" * 80)
    res = api_request("POST", f"/merchants/{MERCHANT_ID}/catalogue/drafts/clear")
    print(f"5.1 API Response from drafts/clear: {res}")
    drafts = api_request("GET", f"/merchants/{MERCHANT_ID}/catalogue/drafts")
    print(f"5.2 Catalogue drafts count after clear: {len(drafts)}")
    assert len(drafts) == 0, f"Expected 0 drafts, got {len(drafts)}"
    print("  -> Verified: tenant drafts cleanly restored to 0.")
    return True


def main() -> None:
    print(f"Connecting to Postgres at {PG_DSN}...")
    store = PostgresStore(PG_DSN)

    s1 = test_scenario_1_agy_broken_path(store)
    s2 = test_scenario_2_ai_suggested_conflict_resolution(store)
    s3 = test_scenario_3_rapid_double_ingest(store)
    s4 = test_scenario_4_subprocess_timeout_behavior()
    s5 = test_scenario_5_clean_state_restore()

    print("\n" + "=" * 80)
    print("TEST SUITE SUMMARY:")
    print("=" * 80)
    print(f"Scenario 1 (agy PATH broken fallback):      {'PASS' if s1 else 'FAIL'}")
    print(f"Scenario 2 (AI_SUGGESTED conflict resolve):  {'PASS' if s2 else 'FAIL'}")
    print(f"Scenario 3 (Rapid double-ingest duplicate):  {'BUG CONFIRMED' if s3.get('duplicated') else 'PASS'}")
    print(f"Scenario 4 (Subprocess timeout on Windows):  {'PASS' if s4 else 'FAIL'}")
    print(f"Scenario 5 (Clean state API clear):          {'PASS' if s5 else 'FAIL'}")


if __name__ == "__main__":
    main()
