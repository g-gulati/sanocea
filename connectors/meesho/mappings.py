from __future__ import annotations

"""Step 9Q.4 Part F - deliberately near-empty. No source reached during this step's research (official
or secondhand) enumerated Meesho's actual order-status value strings - only generic supplier-panel tab
names (Pending/Shipped/Cancelled/Delivered/RTO) appear in consumer-facing seller-guide blogs, which are
UI labels, not confirmed API enum values, and "do not guess based on names" (Part F) applies precisely
here: a UI tab labelled "Cancelled" does not tell us what string the API actually returns for that
state, or whether the API's vocabulary matches the UI's at all.

ORDER_STATUS_MAP is therefore empty on purpose - every real Meesho status this connector ever
encounters will fall through to the safety net (preserve verbatim + raise UNMAPPED_CHANNEL_STATUS,
never guess), until a real onboarded integration reveals actual API response values to populate this
table with genuine confidence, exactly like connectors/flipkart/connector.py's own honestly-partial
table and connectors/amazon/mappings.py's honestly-complete one - this one is honestly EMPTY.
"""

ORDER_STATUS_MAP: dict[str, tuple[str, str | None]] = {}
