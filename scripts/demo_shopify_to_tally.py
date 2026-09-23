"""
demo_shopify_to_tally.py
------------------------
Demo trigger script: simulates a Shopify order arriving for the
prospect merchant "prospect_premium_basket" and pushes it into
Tally (or the mock server) as a Sales Voucher.

Usage::

    python scripts/demo_shopify_to_tally.py
    python scripts/demo_shopify_to_tally.py --product makhana
    python scripts/demo_shopify_to_tally.py --product dates
    python scripts/demo_shopify_to_tally.py --product nuts

Make sure the mock Tally server is running first::

    python scripts/mock_tally_server.py
"""

from __future__ import annotations

import argparse
import sys
import os
from datetime import datetime

# Force UTF-8 on Windows terminals (cp1252 default rejects box-drawing chars & emoji)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf_8"):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ─── Path setup so 'packages' is importable ───────────────────────────────────
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from packages.tally_integration.connector import TallyConnector  # noqa: E402

# ─── ANSI colours ─────────────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[92m"
CYAN   = "\033[96m"
YELLOW = "\033[93m"
RED    = "\033[91m"
WHITE  = "\033[97m"
DIM    = "\033[2m"
MAGENTA = "\033[95m"

# ─── Demo product catalogue (prices in paise, taxes in paise per line) ────────
#
#  These mirror the seeded products in the tenant config for
#  prospect_premium_basket.  Adjust quantities/amounts as needed.
#
PRODUCTS = {
    "makhana": {
        "sku": "TPB-MAKHANA-70G",
        "title": "Pure Roasted Makhana",
        "unit_amount": 24900,   # ₹249.00 in paise
        "tax_rate": 0.18,       # 18 % IGST
        "emoji": "🪷",
    },
    "dates": {
        "sku": "TPB-DATES-500G",
        "title": "Organic Medjool Dates",
        "unit_amount": 59900,   # ₹599.00 in paise
        "tax_rate": 0.18,
        "emoji": "🌴",
    },
    "nuts": {
        "sku": "TPB-NUTS-MIX-250G",
        "title": "Premium Mixed Nuts",
        "unit_amount": 44900,   # ₹449.00 in paise
        "tax_rate": 0.18,
        "emoji": "🥜",
    },
}

MERCHANT_ID = "prospect_premium_basket"
CHANNEL_ID  = "shopify_live"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _fmt_inr(paise: float) -> str:
    """Format a paise value as a ₹ string."""
    return f"₹{paise / 100:,.2f}"


def _make_order(product_key: str, qty: int = 2) -> tuple[dict, list[dict]]:
    """Build a mock order + order_lines dict pair for the demo."""
    product = PRODUCTS[product_key]
    unit   = product["unit_amount"]
    tax_rt = product["tax_rate"]
    line_subtotal = unit * qty
    tax_amount    = int(round(line_subtotal * tax_rt))
    grand_total   = line_subtotal + tax_amount

    # Order number: TPB-<timestamp-fragment>
    ts = datetime.now().strftime("%H%M%S")
    order_number = f"TPB-{ts}"

    order = {
        "order_number":   order_number,
        "total_amount":   grand_total,
        "currency":       "INR",
        "channel_id":     CHANNEL_ID,
        "status":         "confirmed",
        "payment_status": "paid",
        "customer_name":  "Shopify Customer",   # anonymous for demo
    }

    order_lines = [
        {
            "sku":         product["sku"],
            "title":       product["title"],
            "quantity":    qty,
            "unit_amount": unit,
            "tax_amount":  tax_amount,
        }
    ]

    return order, order_lines


def _print_section(title: str) -> None:
    print(f"\n{CYAN}{BOLD}── {title} {'─' * max(0, 50 - len(title))}{RESET}")


def _print_kv(label: str, value: str, colour: str = WHITE) -> None:
    print(f"  {DIM}{label:<22}{RESET}{colour}{value}{RESET}")


# ─── Main demo flow ───────────────────────────────────────────────────────────

def run_demo(product_key: str) -> None:
    product = PRODUCTS[product_key]
    qty = 2

    print(f"\n{GREEN}{BOLD}{'═' * 60}{RESET}")
    print(
        f"{GREEN}{BOLD}  🛒  Shopify → Tally  |  Demo Trigger{RESET}\n"
        f"  Merchant : {MAGENTA}{MERCHANT_ID}{RESET}\n"
        f"  Product  : {product['emoji']}  {BOLD}{product['title']}{RESET}"
    )
    print(f"{GREEN}{BOLD}{'═' * 60}{RESET}\n")

    # 1. Build the simulated order ─────────────────────────────────────────────
    _print_section("Step 1 — Simulating Shopify order")
    order, order_lines = _make_order(product_key, qty=qty)

    line = order_lines[0]
    _print_kv("Order number",    order["order_number"])
    _print_kv("Customer",        order["customer_name"])
    _print_kv("Channel",         order["channel_id"])
    _print_kv("SKU",             line["sku"])
    _print_kv("Product",         line["title"])
    _print_kv("Qty",             str(line["quantity"]))
    _print_kv("Unit price",      _fmt_inr(line["unit_amount"]))
    _print_kv("Tax (IGST 18%)",  _fmt_inr(line["tax_amount"]))
    _print_kv("Grand total",     _fmt_inr(order["total_amount"]), GREEN)

    # 2. Health check ──────────────────────────────────────────────────────────
    _print_section("Step 2 — Health-checking Tally server")
    tc = TallyConnector(
        tally_url="http://localhost:9000",
        company_name="The Premium Basket India",
    )
    hc = tc.health_check()
    status_icon = f"{GREEN}✓{RESET}" if hc["connected"] else f"{RED}✗{RESET}"
    print(f"  {status_icon}  {hc['message']}")

    if not hc["connected"]:
        print(
            f"\n  {YELLOW}{BOLD}⚠ Tally server is not reachable.{RESET}\n"
            f"  Start it first:\n"
            f"    {DIM}python scripts/mock_tally_server.py{RESET}\n"
        )
        sys.exit(1)

    # 3. Post voucher ──────────────────────────────────────────────────────────
    _print_section("Step 3 — Posting Sales Voucher to Tally")
    print(f"  {DIM}Building Tally XML envelope…{RESET}")
    result = tc.post_sales_voucher(order, order_lines)

    if result["success"]:
        print(
            f"\n  {GREEN}{BOLD}✓  Voucher created successfully!{RESET}\n"
            f"  Voucher # : {BOLD}{result['voucher_number']}{RESET}\n"
            f"\n  {DIM}Check the Tally dashboard:{RESET}"
            f"  {CYAN}http://localhost:9000/{RESET}\n"
        )
    else:
        print(
            f"\n  {RED}{BOLD}✗  Voucher creation failed.{RESET}\n"
            f"  Error: {result['error']}\n"
        )
        sys.exit(1)

    print(f"{GREEN}{BOLD}{'═' * 60}{RESET}\n")


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Demo: push a simulated Shopify order into Tally as a Sales Voucher.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/demo_shopify_to_tally.py\n"
            "  python scripts/demo_shopify_to_tally.py --product dates\n"
            "  python scripts/demo_shopify_to_tally.py --product nuts\n"
        ),
    )
    parser.add_argument(
        "--product",
        choices=list(PRODUCTS.keys()),
        default="makhana",
        help="Demo product to use (default: makhana)",
    )
    args = parser.parse_args()
    run_demo(args.product)


if __name__ == "__main__":
    main()
