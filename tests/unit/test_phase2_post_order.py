from __future__ import annotations

from pathlib import Path

from sanocea.connectors.logistics import SimulatedLogisticsConnector
from sanocea.connectors.payments import SimulatedPaymentConnector
from sanocea.connectors.chatwoot import ChatwootConnector
from sanocea.packages.domain_contract.models import Order, Shipment
from sanocea.packages.domain_contract.models import Inventory, SupportConversation, Refund
from sanocea.packages.post_order import PostOrderOperationsService
from sanocea.packages.support import SupportWorkflowService
from sanocea.workers.ingestion import DoclingExtractor


def test_shipment_create_reuses_order_business_key_after_retry(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    logistics = SimulatedLogisticsConnector(store)
    service = PostOrderOperationsService(store, shopify, logistics)
    order = Order(merchant_id="mer_A", channel_id="chn_A_shopify", order_number="2001", status="PAID", payment_status="paid", total_amount=120000, currency="INR")
    store.put(order)
    first_status, first_ref = service.create_or_observe_shipment("mer_A", order)
    second_status, second_ref = service.create_or_observe_shipment("mer_A", order, simulate="timeout_after_mutation")
    assert first_status == "created"
    assert second_status == "existing"
    assert first_ref == second_ref
    assert len(store.list(Shipment, "mer_A")) == 1


def test_inventory_divergence_creates_reconciliation_exception(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    service = PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store))
    assert service.observe_inventory("mer_A", "SKU-DIV", 5, 2) == "exception"
    assert any(item.category == "inventory_conflict" for item in store.list(__import__("sanocea.packages.domain_contract.models", fromlist=["ExceptionRecord"]).ExceptionRecord, "mer_A"))


def test_pdf_text_layer_extraction_is_cached_without_docling():
    path = Path("sanocea/tests/fixtures/phase11_merchant/generated/unit_catalog_cache.pdf")
    path.parent.mkdir(parents=True, exist_ok=True)
    from sanocea.scripts.run_phase11_simulation import write_simple_pdf

    write_simple_pdf(path, ["Supplier", "NST-TOP-1 | Northstar Blue Tee | INR 1000 | Blue | M | cotton | img.png"])
    extractor = DoclingExtractor(min_text_chars=10)
    first = extractor.extract(path)
    second = extractor.extract(path)
    assert first.extractor == "pdf_text_layer"
    assert second.cached is True
    assert "NST-TOP-1" in second.text


def test_refund_lost_response_recovers_without_duplicate_external_mutation(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    payments = SimulatedPaymentConnector(store)
    service = PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store), payments)
    store.set_config("mer_A", {"refunds": {"automatic_limit": 100000, "above_limit": "REQUIRE_APPROVAL"}})
    order = Order(merchant_id="mer_A", channel_id="chn_A_shopify", order_number="R-1", status="PAID", payment_status="paid", total_amount=90000, currency="INR")
    store.put(order)
    refund = service.evaluate_refund("mer_A", order, 50000)
    assert refund.status == "permitted"
    first = service.execute_refund("mer_A", refund.id, "damaged", simulate="timeout_after_mutation")
    second = service.execute_refund("mer_A", first.id, "damaged", simulate="timeout_after_mutation")
    assert second.status == "completed"
    assert len(payments.refunds) == 1


def test_return_lifecycle_and_exchange_reservation(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    store.set_config("mer_A", {"returns": {"window_days": 7, "auto_authorize": True}, "exchanges": {"auto_reserve": True}})
    service = PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store), SimulatedPaymentConnector(store))
    order = Order(merchant_id="mer_A", channel_id="chn_A_shopify", order_number="RX-1", status="PAID", payment_status="paid", total_amount=100000, currency="INR")
    store.put(order)
    ret = service.evaluate_return("mer_A", order, "size_issue")
    assert ret.status == "authorized"
    for event in ["pickup_requested", "picked_up", "received", "inspection_passed", "closed"]:
        ret = service.progress_return("mer_A", ret.id, event)
    assert ret.status == "completed"
    store.put(Inventory(merchant_id="mer_A", sku="SKU-NEW", location_ref="default", quantity=2, available=2))
    exchange = service.evaluate_exchange("mer_A", order, "SKU-NEW")
    assert exchange.status == "reserved"
    assert service.complete_exchange("mer_A", exchange.id).status == "completed"


def test_support_reads_refund_status_from_canonical_state(phase0):
    store, _workflow, _shopify, _chatwoot = phase0
    order = Order(merchant_id="mer_A", channel_id="chn_A_shopify", order_number="S-1", status="PAID", payment_status="paid", total_amount=100000, currency="INR")
    store.put(order)
    store.put(Refund(merchant_id="mer_A", order_id=order.id, amount=50000, currency="INR", status="completed"))
    conv = SupportConversation(merchant_id="mer_A", channel_id="chn_A_chatwoot", order_id=order.id, last_message="Where is my refund?")
    store.put(conv)
    action = SupportWorkflowService(store, ChatwootConnector(store)).handle_conversation("mer_A", conv.id)
    assert action.handling_mode == "AUTOMATIC"
    assert "completed" in action.response_text
