"""ERPNext REST v2 client: the only module in the portal that does HTTP.

Request and response shapes: .specship/specs/002-shopfloor-terminal/artifacts/api-contract.md
"""

import html
import json
import re
from urllib.parse import quote

import requests
from django.conf import settings
from django.utils.html import strip_tags

JOB_CARD_NAME = re.compile(r"PO-JOB[0-9]+")  # ASCII digits only; always used with fullmatch
QUEUE_FIELDS = [
    "name", "status", "is_paused", "work_order", "operation", "production_item", "item_name",
    "for_quantity", "total_completed_qty", "expected_start_date", "expected_end_date", "sequence_id",
]  # fmt: skip


class ERPNextError(Exception):
    """ERPNext refused the request; the message is safe to show to an operator."""


class ERPNextUnavailable(Exception):
    """ERPNext can't be reached, or doesn't accept the portal's credentials."""


def check_job_card(name):
    if not JOB_CARD_NAME.fullmatch(name or ""):
        raise ValueError(f"not a job card name: {name!r}")
    return name


class ERPNext:
    def __init__(self):
        self.url = settings.ERPNEXT_URL.rstrip("/")
        self.timeout = settings.ERPNEXT_TIMEOUT
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Host": settings.ERPNEXT_SITE,
                "Accept": "application/json",
                "Authorization": f"token {settings.ERPNEXT_API_KEY}:{settings.ERPNEXT_API_SECRET}",
            }
        )

    # -- reads ---------------------------------------------------------------------------

    def workstations(self):
        rows = self._list("Workstation", ["name"], [["disabled", "=", 0]], order_by="name asc")
        return [row["name"] for row in rows]

    def defect_reasons(self):
        return self._list("Defect Reason", ["name", "category"], [["disabled", "=", 0]], order_by="name asc")

    def queue(self, workstation):
        filters = [["workstation", "=", workstation], ["docstatus", "=", 0]]
        return self._list("Job Card", QUEUE_FIELDS, filters, order_by="expected_start_date asc", limit=50)

    def siblings(self, work_orders):
        """Every job card of these work orders, to tell which operations are done."""
        if not work_orders:
            return []
        fields = ["name", "work_order", "operation", "sequence_id", "docstatus"]
        filters = [["work_order", "in", sorted(work_orders)], ["docstatus", "<", 2]]
        return self._list("Job Card", fields, filters, limit=500)

    def job_card(self, name):
        return self._call("GET", f"document/Job%20Card/{quote(check_job_card(name))}")["data"]

    def employees(self):
        return self._list("Employee", ["name", "employee_name"], [["status", "=", "Active"]])

    # -- actions (times are naive site-local strings, see api-contract.md) --------------

    def start(self, name, employee, at):
        self._job_card_method(name, "start_timer", start_time=at, employees=employee)

    def pause(self, name, at):
        self._job_card_method(name, "pause_job", end_time=at)

    def resume(self, name, at):
        self._job_card_method(name, "resume_job", start_time=at)

    def complete(self, name, qty, at):
        """Book the final quantity and submit the job card in one call."""
        self._job_card_method(name, "complete_job_card", qty=qty, end_time=at, auto_submit=1)

    def log_defect(self, job_card, reason, qty):
        body = {"job_card": check_job_card(job_card), "defect_reason": reason, "qty": qty, "docstatus": 1}
        return self._call("POST", "document/Defect%20Log", json=body)["data"]["name"]

    # -- plumbing ------------------------------------------------------------------------

    def _job_card_method(self, name, method, **body):
        path = f"document/Job%20Card/{quote(check_job_card(name))}/method/{method}"
        return self._call("POST", path, json=body)

    def _list(self, doctype, fields, filters, order_by=None, limit=100):
        params = {"fields": json.dumps(fields), "filters": json.dumps(filters), "limit": limit}
        if order_by:
            params["order_by"] = order_by
        return self._call("GET", f"document/{quote(doctype)}", params=params)["data"]

    def _call(self, method, path, **kwargs):
        try:
            r = self.session.request(method, f"{self.url}/api/v2/{path}", timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise ERPNextUnavailable(f"cannot reach ERPNext: {exc}") from exc
        if r.status_code == 401 or r.status_code >= 500:
            raise ERPNextUnavailable(f"ERPNext answered {r.status_code}")
        if r.status_code == 403:  # reachable, but the terminal's ERPNext role can't do this: a setup problem
            raise ERPNextError("ERPNext doesn't allow the terminal to do this. Tell the supervisor.")
        if not r.ok:
            raise ERPNextError(self._message(r))
        return r.json()

    @staticmethod
    def _message(r):
        try:
            errors = r.json().get("errors") or []
        except ValueError:
            errors = []
        # ERPNext messages carry <strong>/<a> tags and entities; operators get plain text
        text = " ".join(html.unescape(strip_tags(e.get("message", ""))) for e in errors).strip()
        return text or f"ERPNext rejected the request ({r.status_code})."
