from __future__ import annotations

"""Step 9Q.3 Part G - status mapping, built ONLY from Amazon's own confirmed, fully-enumerated
OrderStatus values (fetched directly from the primary ordersV0.json model this step - not from memory,
not inferred). Unlike Step 9Q.2's Flipkart connector (where the shipment-state vocabulary was never
fully enumerated in what primary documentation was reached, forcing a deliberately partial map), Amazon's
Orders API documents its COMPLETE OrderStatus enum, so this table covers every currently-documented
value with confidence.

This does NOT remove the safety net: Amazon can add a new enum value in a future API revision, so any
status NOT in this table is still preserved VERBATIM on Order.status and raises
ExceptionCategory.UNMAPPED_CHANNEL_STATUS - see connectors/amazon/connector.py. "Complete today" and
"permanently complete" are different claims; only the first is made here.
"""

# AmazonOrderStatus -> (canonical Order.status, Order.fulfillment_status)
ORDER_STATUS_MAP: dict[str, tuple[str, str | None]] = {
    "PendingAvailability": ("PENDING", "pending"),
    "Pending": ("PENDING", "pending"),
    "Unshipped": ("PAID", "pending"),
    "PartiallyShipped": ("PAID", "partially_fulfilled"),
    "Shipped": ("PAID", "fulfilled"),
    # India-specific: an order held for GST invoice confirmation before it can proceed - otherwise
    # equivalent to Unshipped (paid, not yet dispatched).
    "InvoiceUnconfirmed": ("PAID", "pending"),
    "Canceled": ("CANCELLED", "cancelled"),
    "Unfulfillable": ("PAID", "failed"),
}

# Amazon's async-job processing status (identical enum shape confirmed for BOTH Feeds and Reports APIs)
# -> Sanocea's existing ConnectorCommand.status Literal (packages/domain_contract/models.py). Reusing
# the EXISTING field rather than inventing a parallel status model, per Step 9Q.3 Part D.
ASYNC_JOB_STATUS_MAP: dict[str, str] = {
    "IN_QUEUE": "executing",
    "IN_PROGRESS": "executing",
    "DONE": "succeeded",
    "CANCELLED": "failed",
    "FATAL": "failed",
}
