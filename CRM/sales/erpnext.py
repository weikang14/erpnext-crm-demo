"""ERPNext REST v2 client on the standard library: the only module in the CRM that does HTTP.

Request and response shapes: .specship/completed/004-crm-erp-sales-order/artifacts/api-contract.md
Frappe errors carry a traceback field next to `message`; it is never read.
"""

import html
import http.client
import json
import urllib.error
import urllib.request
from urllib.parse import quote, urlencode

from django.conf import settings
from django.utils.html import strip_tags

PERMISSION_REFUSED = "ERPNext refused the integration user (permissions); ask the ERP admin."
UNEXPECTED_REPLY = "ERPNext sent an unexpected reply."
MAX_MESSAGE = 300
ORDER_FIELDS = ["name", "docstatus", "net_total", "grand_total"]
TAX_KEYS = ("charge_type", "account_head", "rate", "description")


class Unavailable(Exception):
    """Timeout, connection error, 401 or 5xx: the request may or may not have taken effect."""


class Refused(Exception):
    """ERPNext refused the request; str() is plain text without credentials, at most 300 characters."""


def _doc(doctype, name=None):
    path = quote(doctype)
    return path if name is None else f"{path}/{quote(name, safe='')}"  # "/", "#", "&", "'" and non-ASCII escaped


class Client:
    def __init__(self, url, site, key, secret, timeout=10):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.credentials = [value for value in (key, secret) if value]
        self.headers = {
            "Host": site,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"token {key}:{secret}",
        }

    def find_order(self, reference):
        """The live (draft or submitted) order with this crm_reference, or None."""
        filters = [["crm_reference", "=", reference], ["docstatus", "<", 2]]
        query = urlencode({"fields": json.dumps(ORDER_FIELDS), "filters": json.dumps(filters)}, quote_via=quote)
        rows = self._call("GET", f"{_doc('Sales Order')}?{query}", expect=list)
        return rows[0] if rows else None

    def get_customer(self, name):
        return self._call("GET", _doc("Customer", name), missing_ok=True)

    def create_customer(self, payload):
        return self._call("POST", _doc("Customer"), payload)

    def create_address(self, payload):
        return self._call("POST", _doc("Address"), payload)

    def tax_rows(self, template):
        taxes = self._call("GET", _doc("Sales Taxes and Charges Template", template)).get("taxes")
        if not isinstance(taxes, list):
            raise Refused(UNEXPECTED_REPLY)
        return [{key: row.get(key) for key in TAX_KEYS} for row in taxes]

    def create_order(self, payload):
        return self._call("POST", _doc("Sales Order"), payload)

    def submit_order(self, name):
        """Submit a draft order (call 5b). An order inserted already submitted keeps the status "Draft": ERPNext
        computes the status in validate, which skips new documents."""
        return self._call("PUT", _doc("Sales Order", name), {"docstatus": 1})

    # -- plumbing ------------------------------------------------------------------------

    def _call(self, method, path, body=None, expect=dict, missing_ok=False):
        data = None if body is None else json.dumps(body, default=float).encode()  # Decimal money → JSON number
        request = urllib.request.Request(f"{self.url}/api/v2/document/{path}", data, self.headers, method=method)
        # `from None` everywhere: no chained exception carries request details into a logged traceback
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and missing_ok:
                return None
            if exc.code == 401 or exc.code >= 500:
                raise Unavailable(f"ERPNext answered {exc.code}.") from None
            if exc.code == 403:
                raise Refused(PERMISSION_REFUSED) from None
            raise Refused(self._message(exc)) from None
        except (OSError, http.client.HTTPException, ValueError) as exc:  # URLError, timeout, reset, bad URL/header
            raise Unavailable(self._safe(f"ERPNext didn't answer: {exc}")) from None
        try:
            data = json.loads(raw)["data"]
        except (ValueError, TypeError, KeyError):
            data = None
        if not isinstance(data, expect):
            raise Refused(UNEXPECTED_REPLY)
        return data

    def _message(self, exc):
        try:
            errors = json.loads(exc.read())["errors"]
            text = " ".join(html.unescape(strip_tags(error.get("message", ""))) for error in errors)
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            text = ""
        return self._safe(" ".join(text.split())) or f"ERPNext rejected the request ({exc.code})."

    def _safe(self, text):
        """ERPNext may echo the request: drop the key and secret before the text leaves the client."""
        for value in self.credentials:
            text = text.replace(value, "***")
        return text[:MAX_MESSAGE]


def client_from_settings():
    url = (getattr(settings, "ERPNEXT_URL", "") or "").strip()
    if not url:
        return None
    return Client(
        url,
        getattr(settings, "ERPNEXT_SITE", ""),
        getattr(settings, "ERPNEXT_API_KEY", ""),
        getattr(settings, "ERPNEXT_API_SECRET", ""),
    )
