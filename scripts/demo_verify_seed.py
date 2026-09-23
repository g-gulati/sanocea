"""
demo_verify_seed.py — scratch verification script
Hits the RUNNING API to:
1. Reset the demo tenant
2. Check what was seeded via the API
3. Render the WhatsApp briefing (captured, not sent)
Run AFTER start_demo.ps1 has the API up on port 8080.
"""
import sys, os, json
sys.path.insert(0, "D:/Autonomous E-Commerce ERP")

import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8080"
MID  = "prospect_premium_basket"

def get(path):
    with urllib.request.urlopen(f"{BASE}{path}", timeout=10) as r:
        return json.loads(r.read())

def post(path, data=None):
    body = json.dumps(data or {}).encode()
    req = urllib.request.Request(f"{BASE}{path}", data=body,
                                  headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

# ── 1. Health check ───────────────────────────────────────────────────────
try:
    health = get("/health")
    print(f"API health: {health}")
except Exception as e:
    print(f"API not reachable: {e}")
    print("Start the demo first: run START_DEMO.bat")
    sys.exit(1)

# ── 2. Reset the demo tenant ──────────────────────────────────────────────
print("\n=== Resetting demo tenant ===")
try:
    reset = post(f"/merchants/{MID}/demo/reset")
    print("Reset result:", json.dumps(reset, indent=2))
except Exception as e:
    print(f"Reset failed: {e}")

# ── 3. Check seeded data ──────────────────────────────────────────────────
print("\n=== Seeded state ===")

try:
    inv = get(f"/merchants/{MID}/inventory")
    print(f"\nInventory ({len(inv)} lines):")
    for i in inv:
        print(f"  sku={i.get('sku')}  ats={i.get('ats')}  sellable={i.get('sellable')}  loc={i.get('location_ref')}")
except Exception as e:
    print(f"Inventory: {e}")

try:
    approvals = get(f"/merchants/{MID}/approvals")
    pending = [a for a in approvals if a.get("status") == "pending"]
    print(f"\nPending approvals ({len(pending)}):")
    for a in pending:
        print(f"  [{a.get('reference')}] {a.get('action')}: {(a.get('summary') or '')[:70]}")
except Exception as e:
    print(f"Approvals: {e}")

try:
    exceptions = get(f"/merchants/{MID}/exceptions")
    print(f"\nExceptions ({len(exceptions)}):")
    for ex in exceptions[:5]:
        print(f"  [{ex.get('severity','?').upper()}] {ex.get('category')}: {(ex.get('message') or '')[:70]}")
except Exception as e:
    print(f"Exceptions: {e}")

# ── 4. Trigger daily briefing (captured, prints to terminal) ──────────────
print("\n=== WhatsApp Daily Briefing (preview) ===")
print("(to send for real, hit /merchants/{mid}/approvals/{id}/send-whatsapp or reply '1' in WhatsApp)\n")

# We can't easily capture the briefing without running it — 
# so render it locally using the same logic
os.environ["SANOCEA_USE_IN_MEMORY_STORE"] = "0"  # real DB
try:
    # Use the preflight route if available
    pf = get(f"/merchants/{MID}/demo-preflight")
    print("Demo preflight:", json.dumps(pf, indent=2))
except Exception as e:
    print(f"Preflight: {e}")
