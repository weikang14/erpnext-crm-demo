import json
from unittest import mock

import requests
from django.test import SimpleTestCase, override_settings

from terminal.erpnext import ERPNext, ERPNextError, ERPNextUnavailable


def response(status=200, body=None):
    r = requests.Response()
    r.status_code = status
    r._content = json.dumps(body if body is not None else {"data": []}).encode()
    return r


@override_settings(
    ERPNEXT_URL="http://erp:8000", ERPNEXT_SITE="factory.test", ERPNEXT_API_KEY="k", ERPNEXT_API_SECRET="s"
)
class ClientTests(SimpleTestCase):
    def setUp(self):
        self.client_ = ERPNext()
        patcher = mock.patch.object(self.client_.session, "request", return_value=response())
        self.request = patcher.start()
        self.addCleanup(patcher.stop)

    def sent(self):
        method, url = self.request.call_args.args
        return method, url, self.request.call_args.kwargs

    def test_headers(self):  # CL-1
        headers = self.client_.session.headers
        self.assertEqual(headers["Host"], "factory.test")
        self.assertEqual(headers["Authorization"], "token k:s")
        self.assertEqual(headers["Accept"], "application/json")

    def test_rejection_message_without_html(self):  # CL-2
        self.request.return_value = response(
            417, {"errors": [{"type": "ValidationError", "message": "<strong>Job</strong> &amp; <a href='x'>card</a>"}]}
        )
        with self.assertRaisesMessage(ERPNextError, "Job & card"):
            self.client_.pause("PO-JOB00001", "2026-10-05 08:00:00")

    def test_permission_refused_is_a_message(self):  # CL-3: 403 is a setup problem, not an outage
        self.request.return_value = response(403, {"errors": [{"message": "Not permitted"}]})
        with self.assertRaisesMessage(ERPNextError, "Tell the supervisor"):
            self.client_.workstations()

    def test_unavailable(self):  # CL-3
        for status in (401, 500, 502):
            self.request.return_value = response(status, {})
            with self.assertRaises(ERPNextUnavailable, msg=status):
                self.client_.workstations()
        for exc in (requests.ConnectionError("down"), requests.Timeout("slow")):
            self.request.side_effect = exc
            with self.assertRaises(ERPNextUnavailable):
                self.client_.workstations()

    def test_job_card_methods(self):  # CL-4
        at = "2026-10-05 14:30:00"
        calls = [
            (lambda: self.client_.start("PO-JOB00007", "HR-EMP-00003", at), "start_timer",
             {"start_time": at, "employees": "HR-EMP-00003"}),
            (lambda: self.client_.pause("PO-JOB00007", at), "pause_job", {"end_time": at}),
            (lambda: self.client_.resume("PO-JOB00007", at), "resume_job", {"start_time": at}),
            (lambda: self.client_.complete("PO-JOB00007", 10, at), "complete_job_card",
             {"qty": 10, "end_time": at, "auto_submit": 1}),
        ]  # fmt: skip
        for call, method, body in calls:
            self.request.return_value = response(200, {"docs": [{}]})
            call()
            verb, url, kwargs = self.sent()
            self.assertEqual(verb, "POST")
            self.assertEqual(url, f"http://erp:8000/api/v2/document/Job%20Card/PO-JOB00007/method/{method}")
            self.assertEqual(kwargs["json"], body)

    def test_defect_log_is_inserted_submitted(self):  # CL-4
        self.request.return_value = response(200, {"data": {"name": "DL-2026-00031", "docstatus": 1}})
        self.assertEqual(self.client_.log_defect("PO-JOB00007", "BURR", 2), "DL-2026-00031")
        verb, url, kwargs = self.sent()
        self.assertEqual((verb, url), ("POST", "http://erp:8000/api/v2/document/Defect%20Log"))
        self.assertEqual(kwargs["json"], {"job_card": "PO-JOB00007", "defect_reason": "BURR", "qty": 2, "docstatus": 1})

    def test_queue_request(self):  # CL-4
        self.client_.queue("Welding Bay")
        verb, url, kwargs = self.sent()
        self.assertEqual((verb, url), ("GET", "http://erp:8000/api/v2/document/Job%20Card"))
        self.assertEqual(
            json.loads(kwargs["params"]["filters"]), [["workstation", "=", "Welding Bay"], ["docstatus", "=", 0]]
        )
        self.assertIn("expected_start_date", json.loads(kwargs["params"]["fields"]))
        self.assertEqual(kwargs["params"]["order_by"], "expected_start_date asc")

    def test_invalid_job_card_names_never_sent(self):  # CL-5
        for bad in ("../User/Administrator", "PO-JOB1/../x", "", "PO-JOB", "po-job001"):
            with self.assertRaises(ValueError, msg=bad):
                self.client_.start(bad, "HR-EMP-00001", "2026-10-05 08:00:00")
        self.request.assert_not_called()
