from __future__ import annotations

import os
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor

import pytest

from sanocea.packages.audit import AuditLedger
from sanocea.packages.domain_contract import PostgresStore, TenantAccessError
from sanocea.packages.domain_contract.models import AuditEvent, Merchant, Order


pytestmark = pytest.mark.skipif(
    not os.environ.get("SANOCEA_PG_DSN"),
    reason="requires real Postgres DSN in SANOCEA_PG_DSN",
)


def store() -> PostgresStore:
    s = PostgresStore(os.environ["SANOCEA_PG_DSN"])
    s.migrate()
    return s


def test_migrations_and_tenant_isolation_against_postgres():
    s = store()
    suffix = uuid4().hex
    mer_a = f"pg_mer_A_{suffix}"
    mer_b = f"pg_mer_B_{suffix}"
    order_id = f"pg_ord_A_{suffix}"
    s.put(Merchant(id=mer_a, merchant_id=mer_a, legal_name="A", display_name="A"))
    s.put(Merchant(id=mer_b, merchant_id=mer_b, legal_name="B", display_name="B"))
    order = Order(
        id=order_id,
        merchant_id=mer_a,
        channel_id="shopify",
        order_number="PG-1",
        status="PAID",
        total_amount=100,
        currency="INR",
    )
    s.put(order)
    assert s.get(Order, mer_a, order_id).status == "PAID"
    with pytest.raises(TenantAccessError):
        s.get(Order, mer_b, order_id)


def test_durable_idempotency_concurrency_is_database_enforced():
    s = store()
    scope = "pg_mer_A:webhook:shopify:orders_paid"
    key = f"same-concurrent-webhook-{uuid4().hex}"

    def reserve() -> bool:
        return s.reserve_idempotency(scope, key)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: reserve(), range(8)))

    assert results.count(True) == 1
    assert results.count(False) == 7


def test_audit_is_append_only_in_postgres():
    s = store()
    mer = f"pg_mer_audit_{uuid4().hex}"
    s.put(Merchant(id=mer, merchant_id=mer, legal_name="Audit", display_name="Audit"))
    event = AuditLedger(s).record(
        merchant_id=mer,
        actor="test",
        source="integration",
        action="created",
        object_type="Order",
        result="ok",
    )
    with s.connect() as conn, conn.cursor() as cur:
        with pytest.raises(Exception):
            cur.execute("UPDATE audit_events SET result = 'mutated' WHERE id = %s", (event.id,))
