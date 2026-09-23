from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AllocationRequirement:
    sku: str
    quantity: int


def rank_candidate_locations(
    ats_by_location: dict[str, dict[str, int]],
    requirements: list[AllocationRequirement],
    *,
    priority: list[str] | None = None,
) -> list[str]:
    """Step 3 - the smallest deterministic, explainable, single-location allocation policy. Pure
    function: no store access, no I/O, trivially unit-testable, and reusable unchanged by any future
    connector, since it consumes only canonical ATS numbers and SKU/quantity requirements - never a
    platform-specific field.

    OSS-first finding this adopts: Saleor's two named allocation strategies map directly onto this
    policy - PRIORITIZE_SORTING_ORDER (a merchant-configured priority-ordered candidate list) and
    PRIORITIZE_HIGH_STOCK (prefer the location with the most stock) - used here as PRIORITY-FIRST, then
    HIGHEST-ATS-AS-DETERMINISTIC-FALLBACK, exactly matching the review's own Scenario A/B/C expectations.
    One deliberate DEPARTURE from Saleor's documented default behavior: Saleor splits an order across
    warehouses when a single one has insufficient stock ("multiple allocations are created when there is
    insufficient available quantity in one stock"); this function NEVER does that - Step 3's explicit
    boundary is single-location-only, no split, so a location that cannot satisfy every requirement in
    full is excluded entirely, not partially used.

    Returns eligible location_refs in the order they should be ATTEMPTED (most preferred first) -
    "eligible" means this location's ats_by_location entry can satisfy EVERY requirement's quantity in
    full (whole-order-at-one-location). An empty list means no single location can satisfy the whole set
    of requirements - the caller must report a deterministic allocation failure, never split.

    Ranking, entirely by comparable, reproducible keys - never dict/store iteration order:
    1. Locations present in `priority` sort before any location not in `priority`.
    2. Among locations in `priority`, sort by their position in that list (lower index = more preferred).
    3. Among locations NOT in `priority` (or when `priority` is empty/None), sort by DESCENDING total ATS
       across the requirement SKUs (PRIORITIZE_HIGH_STOCK).
    4. Final tie-break, always: location_ref ascending (alphabetical) - guarantees the SAME input always
       produces the SAME output, regardless of dict ordering, ATS ties, or absent priority.
    """
    priority = priority or []
    priority_rank = {location_ref: index for index, location_ref in enumerate(priority)}

    eligible = [
        location_ref
        for location_ref, ats_by_sku in ats_by_location.items()
        if all(ats_by_sku.get(requirement.sku, 0) >= requirement.quantity for requirement in requirements)
    ]

    def sort_key(location_ref: str) -> tuple[int, int, int, str]:
        if location_ref in priority_rank:
            return (0, priority_rank[location_ref], 0, location_ref)
        total_ats = sum(ats_by_location[location_ref].get(requirement.sku, 0) for requirement in requirements)
        return (1, 0, -total_ats, location_ref)

    return sorted(eligible, key=sort_key)
