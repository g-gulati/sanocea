"""
connector.py
------------
TallyConnector: posts Shopify orders to Tally (real or mock) as
XML Sales Vouchers via Tally's HTTP/XML import interface.

Typical usage::

    from packages.tally_integration.connector import TallyConnector

    tc = TallyConnector()
    result = tc.post_sales_voucher(order, order_lines)
    # → {"success": True, "voucher_number": "TPB-4001", "error": None}
"""

from __future__ import annotations

import urllib.request
import urllib.error
from datetime import datetime
from typing import Optional


class TallyConnector:
    """
    Connects the Sanocea platform to TallyPrime (or a mock server)
    and posts Sales Vouchers via Tally's XML import interface.

    Parameters
    ----------
    tally_url : str
        Base URL of the Tally/mock server.  Defaults to
        ``"http://localhost:9000"`` (TallyPrime default port).
    company_name : str
        Tally company to target.  Defaults to
        ``"The Premium Basket India"``.
    timeout : int
        HTTP request timeout in seconds.  Defaults to 10.
    """

    def __init__(
        self,
        tally_url: str = "http://localhost:9000",
        company_name: str = "The Premium Basket India",
        timeout: int = 10,
    ) -> None:
        self.tally_url = tally_url.rstrip("/")
        self.company_name = company_name
        self.timeout = timeout

    # ─── Public API ───────────────────────────────────────────────────────────

    def health_check(self) -> dict:
        """
        Check whether the Tally server is reachable.

        Sends a minimal *Export* request asking Tally to list companies.
        This is safe to call at any time and does not create any data.

        Returns
        -------
        dict
            ``{"connected": bool, "message": str}``
        """
        xml = (
            "<ENVELOPE>"
            "<HEADER>"
            "<VERSION>1</VERSION>"
            "<TALLYREQUEST>Export</TALLYREQUEST>"
            "<TYPE>Collection</TYPE>"
            "<ID>List of Companies</ID>"
            "</HEADER>"
            "<BODY><DESC></DESC></BODY>"
            "</ENVELOPE>"
        )
        try:
            self._post_xml(xml)
            return {
                "connected": True,
                "message": f"Tally server reachable at {self.tally_url}",
            }
        except urllib.error.URLError as exc:
            return {
                "connected": False,
                "message": f"Cannot reach Tally at {self.tally_url}: {exc.reason}",
            }
        except Exception as exc:  # noqa: BLE001
            return {"connected": False, "message": str(exc)}

    def post_sales_voucher(
        self,
        order: dict,
        order_lines: list[dict],
    ) -> dict:
        """
        Build and POST a Tally Sales Voucher XML for a Shopify order.

        Parameters
        ----------
        order : dict
            Must contain at minimum:
              - ``order_number`` (str) – e.g. ``"TPB-4001"``
              - ``total_amount`` (int|float) – amount **in paise**
              - ``currency`` (str) – e.g. ``"INR"``
              - ``channel_id`` (str) – e.g. ``"shopify_live"``
              - ``status`` (str)
              - ``payment_status`` (str)
            Optional keys: ``customer_name``.

        order_lines : list[dict]
            Each line must contain:
              - ``sku`` (str)
              - ``title`` (str) – stock item name in Tally
              - ``quantity`` (int)
              - ``unit_amount`` (int|float) – **in paise**
              - ``tax_amount`` (int|float) – **in paise**

        Returns
        -------
        dict
            ``{"success": bool, "voucher_number": str, "error": str | None}``
        """
        voucher_number: str = str(order.get("order_number", ""))
        xml: str = self._build_sales_voucher_xml(order, order_lines)

        try:
            response_bytes = self._post_xml(xml)
            response_text = response_bytes.decode("utf-8", errors="replace")

            # A successful Tally import contains <CREATED>1</CREATED>
            if "<CREATED>1</CREATED>" in response_text or "<CREATED>" in response_text:
                return {
                    "success": True,
                    "voucher_number": voucher_number,
                    "error": None,
                }
            else:
                # Extract <LINEERROR> if present
                import xml.etree.ElementTree as ET  # noqa: PLC0415
                try:
                    root = ET.fromstring(response_text)
                    line_error = (root.findtext(".//LINEERROR") or "").strip()
                    error_msg = line_error or f"Unexpected response: {response_text[:200]}"
                except ET.ParseError:
                    error_msg = f"Non-XML response: {response_text[:200]}"
                return {
                    "success": False,
                    "voucher_number": voucher_number,
                    "error": error_msg,
                }

        except urllib.error.URLError as exc:
            return {
                "success": False,
                "voucher_number": voucher_number,
                "error": f"Connection error: {exc.reason}",
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "success": False,
                "voucher_number": voucher_number,
                "error": str(exc),
            }

    # ─── XML Builder ──────────────────────────────────────────────────────────

    def _build_sales_voucher_xml(
        self,
        order: dict,
        order_lines: list[dict],
    ) -> str:
        """
        Construct the full Tally Sales Voucher XML envelope.

        Amounts are stored in **paise** in Sanocea's data model.
        Tally expects amounts in **paise** too (integer), so we pass
        them through as-is.  The human-readable ₹ value shown in the
        dashboard is computed separately.

        IGST @ 18 % is used for simplicity (inter-state demo).
        """
        date_str: str = datetime.now().strftime("%Y%m%d")
        party_name: str = order.get("customer_name", "Shopify Customer")
        channel_id: str = order.get("channel_id", "shopify_live")
        order_number: str = str(order.get("order_number", ""))
        narration: str = (
            f"Shopify Order #{order_number} via {channel_id} "
            f"| Auto-synced by Sanocea"
        )

        # ── Compute totals (all values in paise) ──────────────────────────────
        line_total_paise: float = sum(
            float(line.get("unit_amount", 0)) * int(line.get("quantity", 1))
            for line in order_lines
        )
        total_tax_paise: float = sum(
            float(line.get("tax_amount", 0)) for line in order_lines
        )
        grand_total_paise: float = line_total_paise + total_tax_paise

        # Use IGST @ 18 % for demo; compute from tax collected
        igst_paise = int(round(total_tax_paise))

        # Debtor entry: grand total as negative (Tally convention for debtors)
        debtor_amount = -int(round(grand_total_paise))

        # ── Inventory entries ─────────────────────────────────────────────────
        inventory_xml_parts: list[str] = []
        for line in order_lines:
            item_name: str = line.get("title", line.get("sku", "Unknown Item"))
            qty: int = int(line.get("quantity", 1))
            unit_paise: float = float(line.get("unit_amount", 0))
            line_paise: int = int(round(unit_paise * qty))

            # Allocate sales portion (excluding GST) to Sales Account
            # For IGST 18 %: sales_net = line_paise / 1.18
            sales_net_paise: int = int(round(line_paise / 1.18))

            inventory_xml_parts.append(
                f"<ALLINVENTORYENTRIES.LIST>"
                f"<STOCKITEMNAME>{_esc(item_name)}</STOCKITEMNAME>"
                f"<ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>"
                f"<RATE>{int(round(unit_paise))}</RATE>"
                f"<AMOUNT>{line_paise}</AMOUNT>"
                f"<BILLEDQTY>{qty} Nos</BILLEDQTY>"
                f"<ACTUALQTY>{qty} Nos</ACTUALQTY>"
                f"<ACCOUNTINGALLOCATIONS.LIST>"
                f"<LEDGERNAME>Sales Account</LEDGERNAME>"
                f"<ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>"
                f"<AMOUNT>{sales_net_paise}</AMOUNT>"
                f"</ACCOUNTINGALLOCATIONS.LIST>"
                f"</ALLINVENTORYENTRIES.LIST>"
            )

        inventory_xml: str = "".join(inventory_xml_parts)

        # ── Full envelope ─────────────────────────────────────────────────────
        xml = (
            f"<ENVELOPE>"
            f"<HEADER>"
            f"<VERSION>1</VERSION>"
            f"<TALLYREQUEST>Import</TALLYREQUEST>"
            f"<TYPE>Data</TYPE>"
            f"<ID>Vouchers</ID>"
            f"</HEADER>"
            f"<BODY>"
            f"<DESC>"
            f"<STATICVARIABLES>"
            f"<SVCURRENTCOMPANY>{_esc(self.company_name)}</SVCURRENTCOMPANY>"
            f"</STATICVARIABLES>"
            f"</DESC>"
            f"<DATA>"
            f'<TALLYMESSAGE xmlns:UDF="TallyUDF">'
            f'<VOUCHER VCHTYPE="Sales" ACTION="Create">'
            f"<DATE>{date_str}</DATE>"
            f"<VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>"
            f"<VOUCHERNUMBER>{_esc(order_number)}</VOUCHERNUMBER>"
            f"<PARTYLEDGERNAME>{_esc(party_name)}</PARTYLEDGERNAME>"
            f"<PARTYNAME>{_esc(party_name)}</PARTYNAME>"
            f"<NARRATION>{_esc(narration)}</NARRATION>"
            # Debtor ledger entry
            f"<ALLLEDGERENTRIES.LIST>"
            f"<LEDGERNAME>{_esc(party_name)}</LEDGERNAME>"
            f"<ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>"
            f"<AMOUNT>{debtor_amount}</AMOUNT>"
            f"</ALLLEDGERENTRIES.LIST>"
            # IGST ledger entry
            f"<ALLLEDGERENTRIES.LIST>"
            f"<LEDGERNAME>IGST</LEDGERNAME>"
            f"<ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>"
            f"<AMOUNT>{igst_paise}</AMOUNT>"
            f"</ALLLEDGERENTRIES.LIST>"
            f"{inventory_xml}"
            f"</VOUCHER>"
            f"</TALLYMESSAGE>"
            f"</DATA>"
            f"</BODY>"
            f"</ENVELOPE>"
        )
        return xml

    # ─── HTTP helper ──────────────────────────────────────────────────────────

    def _post_xml(self, xml: str) -> bytes:
        """
        POST *xml* to the Tally server and return the raw response bytes.

        Raises ``urllib.error.URLError`` on connection failure.
        """
        body: bytes = xml.encode("utf-8")
        req = urllib.request.Request(
            self.tally_url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "Content-Length": str(len(body)),
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return resp.read()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _esc(value: str) -> str:
    """Minimal XML-escape for element text content."""
    return (
        value
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
