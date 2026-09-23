"""
mock_tally_server.py
--------------------
Standalone mock Tally ERP server for demo purposes.

Listens on port 9000 (same port as real TallyPrime).
Accepts POST requests with Tally XML Sales Voucher envelopes and serves
a live HTML dashboard at GET http://localhost:9000/.

Usage:
    python scripts/mock_tally_server.py            # start server
    python scripts/mock_tally_server.py --test     # validate and exit
"""

import sys
import threading
import json
import io
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import xml.etree.ElementTree as ET
from datetime import datetime

# Force UTF-8 on Windows terminals so box-drawing chars in the banner render correctly
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf_8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ─── In-memory voucher store ─────────────────────────────────────────────────
_vouchers: list[dict] = []
_lock = threading.Lock()

# ─── XML Parsing ─────────────────────────────────────────────────────────────

def _text(el: ET.Element | None, default: str = "") -> str:
    """Return stripped text of an element, or default if None."""
    if el is None:
        return default
    return (el.text or "").strip()


def parse_tally_xml(raw_body: bytes) -> dict:
    """
    Parse a Tally Sales Voucher XML envelope and extract key fields.

    Returns a dict with: voucher_number, date, party_name, amount,
    items (list), narration, raw_xml, parse_error.
    """
    result = {
        "voucher_number": "",
        "date": "",
        "party_name": "",
        "amount": "",
        "items": [],
        "narration": "",
        "raw_xml": raw_body.decode("utf-8", errors="replace"),
        "parse_error": None,
        "received_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
    }

    try:
        root = ET.fromstring(raw_body)

        # Navigate to VOUCHER element
        voucher = root.find(".//VOUCHER")
        if voucher is None:
            result["parse_error"] = "No <VOUCHER> element found"
            return result

        result["voucher_number"] = _text(voucher.find("VOUCHERNUMBER"))
        result["party_name"] = _text(voucher.find("PARTYNAME")) or _text(
            voucher.find("PARTYLEDGERNAME")
        )
        result["narration"] = _text(voucher.find("NARRATION"))

        # Date: Tally format YYYYMMDD → human readable
        raw_date = _text(voucher.find("DATE"))
        if raw_date and len(raw_date) == 8:
            try:
                dt = datetime.strptime(raw_date, "%Y%m%d")
                result["date"] = dt.strftime("%d %b %Y")
            except ValueError:
                result["date"] = raw_date
        else:
            result["date"] = raw_date

        # Sale amount: find the ledger entry where ISDEEMEDPOSITIVE = Yes (debtor entry)
        for ledger in voucher.findall("ALLLEDGERENTRIES.LIST"):
            is_positive = _text(ledger.find("ISDEEMEDPOSITIVE")).lower()
            if is_positive == "yes":
                raw_amt = _text(ledger.find("AMOUNT"))
                # Amount is negative in Tally for debtor (e.g. -24900 paise → ₹249.00)
                try:
                    paise = abs(float(raw_amt))
                    result["amount"] = f"₹{paise / 100:,.2f}"
                except (ValueError, TypeError):
                    result["amount"] = raw_amt
                break

        # Inventory items
        for inv in voucher.findall("ALLINVENTORYENTRIES.LIST"):
            item_name = _text(inv.find("STOCKITEMNAME"))
            qty = _text(inv.find("BILLEDQTY"))
            rate_raw = _text(inv.find("RATE"))
            amt_raw = _text(inv.find("AMOUNT"))
            try:
                rate_str = f"₹{float(rate_raw) / 100:,.2f}"
            except (ValueError, TypeError):
                rate_str = rate_raw
            try:
                amt_str = f"₹{abs(float(amt_raw)) / 100:,.2f}"
            except (ValueError, TypeError):
                amt_str = amt_raw
            result["items"].append(
                {"name": item_name, "qty": qty, "rate": rate_str, "amount": amt_str}
            )

    except ET.ParseError as exc:
        result["parse_error"] = f"XML parse error: {exc}"

    return result

# ─── Terminal display ─────────────────────────────────────────────────────────

RESET   = "\033[0m"
BOLD    = "\033[1m"
GREEN   = "\033[92m"
CYAN    = "\033[96m"
YELLOW  = "\033[93m"
MAGENTA = "\033[95m"
WHITE   = "\033[97m"
DIM     = "\033[2m"


def print_voucher_banner(v: dict) -> None:
    """Pretty-print a received Tally voucher to the terminal."""
    width = 60
    border = "═" * (width - 2)
    items_str = ", ".join(
        f"{i['name']} × {i['qty']}" for i in v["items"]
    ) or "(no items parsed)"

    channel = ""
    narration = v.get("narration", "")
    if "via" in narration:
        parts = narration.split("via", 1)
        if len(parts) > 1:
            channel = parts[1].split("|")[0].strip()

    print(f"\n{GREEN}{BOLD}╔{border}╗{RESET}")
    print(f"{GREEN}{BOLD}║{RESET}  🧾  {BOLD}{WHITE}Sales Voucher Created in Tally{RESET}{'':>{width - 37}}{GREEN}{BOLD}║{RESET}")
    print(f"{GREEN}{BOLD}╠{border}╣{RESET}")

    def row(label: str, value: str) -> None:
        label_col = f"  {CYAN}{label:<18}{RESET}"
        value_col = f"{WHITE}{value}{RESET}"
        # truncate value if too wide
        max_val = width - 22
        if len(value) > max_val:
            value = value[: max_val - 1] + "…"
            value_col = f"{WHITE}{value}{RESET}"
        padding = width - 22 - len(value)
        print(f"{GREEN}{BOLD}║{RESET}{label_col}{value_col}{' ' * padding} {GREEN}{BOLD}║{RESET}")

    row("Voucher #", v["voucher_number"] or "—")
    row("Date", v["date"] or "—")
    row("Party", v["party_name"] or "—")
    row("Amount", v["amount"] or "—")
    row("Channel", channel or "Shopify")
    row("Items", items_str)
    row("Received at", v["received_at"])
    if v.get("parse_error"):
        row("⚠ Parse Error", v["parse_error"])

    print(f"{GREEN}{BOLD}╚{border}╝{RESET}\n")

# ─── HTML Dashboard ───────────────────────────────────────────────────────────

def build_dashboard_html(vouchers: list[dict]) -> str:
    """Generate the HTML dashboard page showing all received vouchers."""

    rows_html = ""
    if not vouchers:
        rows_html = """
        <tr>
          <td colspan="7" class="empty">
            <div class="pulse-wrapper">
              <span class="dot"></span>
              <span>Waiting for orders from Shopify&hellip;</span>
            </div>
          </td>
        </tr>"""
    else:
        for idx, v in enumerate(reversed(vouchers), 1):
            items_str = "<br>".join(
                f"<span class='item-chip'>{i['name']} &times; {i['qty']} @ {i['rate']}</span>"
                for i in v["items"]
            ) or "<span class='na'>—</span>"

            channel = "Shopify"
            narration = v.get("narration", "")
            if "via" in narration:
                parts = narration.split("via", 1)
                if len(parts) > 1:
                    channel = parts[1].split("|")[0].strip()

            parse_err = v.get("parse_error")
            status_badge = (
                "<span class='badge err'>Parse Error</span>"
                if parse_err
                else "<span class='badge ok'>✓ Synced</span>"
            )

            rows_html += f"""
        <tr>
          <td class="mono">{v['voucher_number'] or '—'}</td>
          <td>{v['date'] or '—'}</td>
          <td>{v['party_name'] or '—'}</td>
          <td class="amount">{v['amount'] or '—'}</td>
          <td class="items-col">{items_str}</td>
          <td><span class="channel-chip">{channel}</span></td>
          <td class="ts">{v['received_at']}<br>{status_badge}</td>
        </tr>"""

    total_vouchers = len(vouchers)
    last_sync = vouchers[-1]["received_at"] if vouchers else "—"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="refresh" content="2">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Tally ERP — Live Voucher Log</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      background: #0d1117;
      color: #e6edf3;
      font-family: 'Segoe UI', system-ui, sans-serif;
      min-height: 100vh;
    }}

    header {{
      background: linear-gradient(135deg, #161b22 0%, #0d1117 100%);
      border-bottom: 1px solid #30363d;
      padding: 24px 40px;
      display: flex;
      align-items: center;
      gap: 20px;
      flex-wrap: wrap;
    }}

    .logo {{ font-size: 2.2rem; }}

    .header-text h1 {{
      font-size: 1.5rem;
      font-weight: 700;
      color: #ffffff;
      letter-spacing: -0.3px;
    }}

    .header-text .subtitle {{
      font-size: 0.875rem;
      color: #8b949e;
      margin-top: 4px;
    }}

    .live-badge {{
      margin-left: auto;
      display: flex;
      align-items: center;
      gap: 8px;
      background: #0f2a1a;
      border: 1px solid #238636;
      border-radius: 20px;
      padding: 6px 16px;
      font-size: 0.8rem;
      font-weight: 600;
      color: #3fb950;
      letter-spacing: 1px;
    }}

    .live-dot {{
      width: 9px;
      height: 9px;
      border-radius: 50%;
      background: #3fb950;
      animation: pulse-green 1.4s ease-in-out infinite;
    }}

    @keyframes pulse-green {{
      0%, 100% {{ box-shadow: 0 0 0 0 rgba(63, 185, 80, 0.6); }}
      50%        {{ box-shadow: 0 0 0 6px rgba(63, 185, 80, 0); }}
    }}

    .stats-bar {{
      background: #161b22;
      border-bottom: 1px solid #21262d;
      padding: 12px 40px;
      display: flex;
      gap: 40px;
      font-size: 0.83rem;
      color: #8b949e;
    }}

    .stats-bar .stat-val {{
      color: #3fb950;
      font-weight: 700;
      font-size: 1rem;
    }}

    .main {{ padding: 32px 40px; }}

    .table-wrapper {{
      overflow-x: auto;
      border-radius: 10px;
      border: 1px solid #30363d;
      background: #161b22;
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.875rem;
    }}

    thead {{
      background: #21262d;
    }}

    thead th {{
      padding: 12px 16px;
      text-align: left;
      font-size: 0.75rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.6px;
      color: #8b949e;
      border-bottom: 1px solid #30363d;
    }}

    tbody tr {{
      border-bottom: 1px solid #21262d;
      transition: background 0.15s;
    }}

    tbody tr:last-child {{ border-bottom: none; }}

    tbody tr:hover {{ background: #1c2128; }}

    tbody td {{
      padding: 14px 16px;
      vertical-align: top;
      color: #c9d1d9;
    }}

    td.mono {{
      font-family: 'Cascadia Code', 'Consolas', monospace;
      color: #79c0ff;
      font-weight: 600;
    }}

    td.amount {{
      color: #3fb950;
      font-weight: 700;
      white-space: nowrap;
    }}

    td.items-col {{ max-width: 280px; }}

    .item-chip {{
      display: inline-block;
      background: #0d2136;
      border: 1px solid #1f4e79;
      border-radius: 4px;
      padding: 2px 7px;
      font-size: 0.78rem;
      color: #79c0ff;
      margin-bottom: 4px;
      white-space: nowrap;
    }}

    .channel-chip {{
      background: #2d1b69;
      border: 1px solid #553098;
      border-radius: 12px;
      padding: 3px 10px;
      font-size: 0.75rem;
      color: #d2a8ff;
      white-space: nowrap;
    }}

    td.ts {{
      font-size: 0.78rem;
      color: #8b949e;
      white-space: nowrap;
    }}

    .badge {{
      display: inline-block;
      border-radius: 4px;
      padding: 2px 7px;
      font-size: 0.7rem;
      font-weight: 600;
      margin-top: 4px;
    }}

    .badge.ok {{
      background: #0f2a1a;
      border: 1px solid #238636;
      color: #3fb950;
    }}

    .badge.err {{
      background: #2d1b1b;
      border: 1px solid #8b1a1a;
      color: #f85149;
    }}

    .empty td {{
      text-align: center;
      padding: 60px 20px;
      color: #8b949e;
    }}

    .pulse-wrapper {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 12px;
      font-size: 1rem;
    }}

    .dot {{
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: #3fb950;
      animation: pulse-green 1.4s ease-in-out infinite;
    }}

    .na {{ color: #484f58; }}

    footer {{
      text-align: center;
      padding: 24px;
      font-size: 0.75rem;
      color: #484f58;
      border-top: 1px solid #21262d;
    }}
  </style>
</head>
<body>
  <header>
    <div class="logo">🧾</div>
    <div class="header-text">
      <h1>Tally ERP &mdash; Live Sales Voucher Log</h1>
      <div class="subtitle">Connected to: The Premium Basket India &mdash; Demo Company</div>
    </div>
    <div class="live-badge">
      <div class="live-dot"></div>
      LIVE
    </div>
  </header>

  <div class="stats-bar">
    <div>Vouchers received &nbsp;<span class="stat-val">{total_vouchers}</span></div>
    <div>Last sync &nbsp;<span class="stat-val">{last_sync}</span></div>
    <div>Auto-refresh every &nbsp;<span class="stat-val">2s</span></div>
  </div>

  <main class="main">
    <div class="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>Voucher #</th>
            <th>Date</th>
            <th>Party Name</th>
            <th>Amount (₹)</th>
            <th>Items</th>
            <th>Channel</th>
            <th>Received At</th>
          </tr>
        </thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>
    </div>
  </main>

  <footer>
    Mock Tally ERP Server &mdash; Demo Mode &nbsp;|&nbsp; Sanocea Autonomous E-Commerce ERP
  </footer>
</body>
</html>"""

# ─── Tally XML Success Response ───────────────────────────────────────────────

TALLY_SUCCESS_RESPONSE = (
    b"<ENVELOPE><BODY><DATA>"
    b"<LINEERROR></LINEERROR>"
    b"<CREATED>1</CREATED>"
    b"</DATA></BODY></ENVELOPE>"
)

# ─── HTTP Handler ─────────────────────────────────────────────────────────────

class TallyHandler(BaseHTTPRequestHandler):
    """HTTP request handler mimicking TallyPrime's XML import endpoint."""

    def log_message(self, fmt: str, *args) -> None:  # suppress default access log
        pass

    def do_GET(self) -> None:
        """Serve the live HTML dashboard."""
        parsed = urlparse(self.path)
        if parsed.path not in ("/", ""):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")
            return

        with _lock:
            snapshot = list(_vouchers)

        html = build_dashboard_html(snapshot)
        body = html.encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        """Accept a Tally XML Sales Voucher, store it, print to terminal."""
        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length) if length > 0 else b""

        voucher = parse_tally_xml(raw_body)

        with _lock:
            _vouchers.append(voucher)

        print_voucher_banner(voucher)

        self.send_response(200)
        self.send_header("Content-Type", "text/xml; charset=utf-8")
        self.send_header(
            "Content-Length", str(len(TALLY_SUCCESS_RESPONSE))
        )
        self.end_headers()
        self.wfile.write(TALLY_SUCCESS_RESPONSE)

# ─── Startup Banner ───────────────────────────────────────────────────────────

def print_startup_banner() -> None:
    print(f"\n{GREEN}{BOLD}╔══════════════════════════════════════════════╗{RESET}")
    print(f"{GREEN}{BOLD}║{RESET}   {BOLD}{WHITE}Mock Tally ERP Server — Demo Mode{RESET}          {GREEN}{BOLD}║{RESET}")
    print(f"{GREEN}{BOLD}║{RESET}   {CYAN}Listening on http://localhost:9000{RESET}         {GREEN}{BOLD}║{RESET}")
    print(f"{GREEN}{BOLD}║{RESET}   {DIM}Open in browser for live voucher dashboard{RESET} {GREEN}{BOLD}║{RESET}")
    print(f"{GREEN}{BOLD}╚══════════════════════════════════════════════╝{RESET}\n")

# ─── Entry Point ──────────────────────────────────────────────────────────────

def main() -> None:
    if "--test" in sys.argv:
        # Validate that the server can initialise without binding a real socket
        # by simply exercising the parse and HTML generation functions.
        sample_xml = b"""
        <ENVELOPE>
          <BODY><DATA><TALLYMESSAGE>
            <VOUCHER VCHTYPE="Sales">
              <VOUCHERNUMBER>TEST-001</VOUCHERNUMBER>
              <DATE>20260921</DATE>
              <PARTYNAME>Test Party</PARTYNAME>
              <NARRATION>Test narration via shopify_test | Sanocea</NARRATION>
              <ALLLEDGERENTRIES.LIST>
                <LEDGERNAME>Test Party</LEDGERNAME>
                <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
                <AMOUNT>-24900</AMOUNT>
              </ALLLEDGERENTRIES.LIST>
              <ALLINVENTORYENTRIES.LIST>
                <STOCKITEMNAME>Pure Roasted Makhana</STOCKITEMNAME>
                <BILLEDQTY>2 Nos</BILLEDQTY>
                <RATE>24900</RATE>
                <AMOUNT>-49800</AMOUNT>
              </ALLINVENTORYENTRIES.LIST>
            </VOUCHER>
          </TALLYMESSAGE></DATA></BODY>
        </ENVELOPE>"""
        v = parse_tally_xml(sample_xml)
        assert v["voucher_number"] == "TEST-001", f"Unexpected voucher_number: {v['voucher_number']}"
        assert v["date"] == "21 Sep 2026", f"Unexpected date: {v['date']}"
        assert v["parse_error"] is None, f"Unexpected parse_error: {v['parse_error']}"
        _ = build_dashboard_html([v])
        print("Mock Tally server OK")
        sys.exit(0)

    print_startup_banner()
    server = HTTPServer(("localhost", 9000), TallyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Server stopped.{RESET}\n")
        server.server_close()


if __name__ == "__main__":
    main()
