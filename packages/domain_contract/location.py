from __future__ import annotations

# Step 2 Part G - the smallest generic, platform-neutral, merchant-configurable default-location
# resolution mechanism. Deliberately NOT a routing/allocation decision (that is Step 3+): this never
# chooses between multiple candidate locations for a given order - it only resolves what "no location
# was specified" should mean for a single call, exactly once, before any inventory mutation.

DEFAULT_LOCATION_REF = "default"


def resolve_location_ref(store, merchant_id: str, explicit: str | None = None) -> str:
    """Resolution order:

    1. An explicitly-supplied `location_ref` always wins - the caller knows best, and this is the
       primary mechanism Step 2 requires ("the caller may explicitly specify the location for this
       step").
    2. Otherwise, a merchant-configured default location
       (`config["inventory"]["default_location_ref"]`) is honored if set - the smallest possible way
       for a merchant to say "I have exactly one location and it's called X" without any
       warehouse/priority/routing configuration.
    3. Otherwise, falls back to the literal legacy `DEFAULT_LOCATION_REF` ("default"), so every
       existing merchant/fixture/test that has never configured anything keeps working completely
       unchanged - this is what makes single-location compatibility automatic rather than a special
       case callers have to remember.
    """
    if explicit:
        return explicit
    config = store.get_config(merchant_id)
    configured = (config.get("inventory") or {}).get("default_location_ref")
    if configured:
        return configured
    return DEFAULT_LOCATION_REF
