from unittest import mock

from django.test import Client, override_settings
from django.urls import reverse

from terminal.erpnext import ERPNextError, ERPNextUnavailable
from terminal.tests.base import OperatorTestCase
from terminal.tests.fakes import card

LOCAL_NOW = "2026-10-05 14:30:00"
RUNNING_LOG = {"from_time": "2026-10-05 08:00:00", "to_time": None, "employee": "HR-EMP-00003"}


def job_doc(**extra):
    return {
        "name": "PO-JOB00052", "docstatus": 0, "status": "Work In Progress", "is_paused": 0,
        "item_name": "Equipment Base Frame 1000x800", "operation": "Welding", "work_order": "MFG-WO-2026-00017",
        "for_quantity": 10.0, "total_completed_qty": 0.0, "total_time_in_mins": 42.0, "time_logs": [], **extra,
    }  # fmt: skip


class StartPauseResumeTests(OperatorTestCase):
    def setUp(self):
        super().setUp()
        self.erp.docs["PO-JOB00052"] = job_doc(status="Open")

    def post(self, action, name="PO-JOB00052"):
        return self.client.post(reverse(action, args=[name]))

    @mock.patch("terminal.queue.erp_now", return_value=LOCAL_NOW)
    def test_start_sends_employee_and_local_time(self, _now):  # ACT-1 (time conversion: test_queue_logic)
        response = self.post("start")
        self.assertRedirects(response, reverse("queue"), fetch_redirect_response=False)
        self.assertIn(("start", "PO-JOB00052", "HR-EMP-00003", "2026-10-05 14:30:00"), self.erp.calls)

    @mock.patch("terminal.queue.erp_now", return_value=LOCAL_NOW)
    def test_pause_and_resume(self, _now):  # ACT-2
        self.post("pause")
        self.erp.docs["PO-JOB00052"]["is_paused"] = 1
        self.post("resume")
        self.assertIn(("pause", "PO-JOB00052", "2026-10-05 14:30:00"), self.erp.calls)
        self.assertIn(("resume", "PO-JOB00052", "2026-10-05 14:30:00"), self.erp.calls)

    def test_erpnext_refusal_is_shown(self):  # ACT-6, ERR-2
        self.erp.fail["start"] = ERPNextError(
            "As per the sequence of the operations, complete the operation Laser Cutting before the operation Welding."
        )
        response = self.client.post(reverse("start", args=["PO-JOB00052"]), follow=True)
        self.assertContains(response, "complete the operation Laser Cutting before the operation Welding")
        self.assertNotContains(response, "<strong>")

    def test_get_is_not_allowed(self):  # ACT-7
        for action in ("start", "pause", "resume"):
            self.assertEqual(self.client.get(reverse(action, args=["PO-JOB00052"])).status_code, 405)
        self.assertEqual(self.erp.calls, [])

    def test_bad_names_never_reach_erpnext(self):  # ACT-8
        for path in ("/job/X-1/start/", "/job/..%2FUser%2FAdministrator/start/", "/job/PO-JOB1%2F..%2Fx/pause/"):
            self.assertEqual(self.client.post(path).status_code, 404, path)
        self.assertEqual(self.erp.calls, [])

    def test_csrf_enforced(self):  # SEC-1
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        self.assertEqual(strict.post(reverse("start", args=["PO-JOB00052"])).status_code, 403)
        self.assertEqual(self.erp.calls, [])

    def test_unavailable_during_action(self):  # ERR-1: the write may or may not have landed
        self.erp.fail["pause"] = ERPNextUnavailable("down")
        response = self.post("pause")
        self.assertEqual(response.status_code, 503)
        self.assertContains(response, "Not sure the save went through", status_code=503)


class CompleteTests(OperatorTestCase):
    def actions(self):
        return [call for call in self.erp.calls if call[0] != "queue"]  # follow=True also loads the queue

    def setUp(self):
        super().setUp()
        self.erp.docs["PO-JOB00052"] = job_doc(total_completed_qty=4.0, time_logs=[RUNNING_LOG])
        self.url = reverse("complete", args=["PO-JOB00052"])

    def test_form_shows_remaining_qty(self):  # ACT-3
        response = self.client.get(self.url)
        self.assertEqual(response.context["remaining"], 6.0)
        self.assertContains(response, "Equipment Base Frame 1000x800")
        self.assertContains(response, 'name="reason_1"')
        self.assertContains(response, 'aria-label="Defect 1 quantity"')

    @mock.patch("terminal.queue.erp_now", return_value=LOCAL_NOW)
    def test_complete_then_defects(self, _now):  # ACT-4
        data = {"reason_1": "BURR", "qty_1": "2", "reason_2": "WELD-POR", "qty_2": "1", "reason_3": "", "qty_3": ""}
        response = self.client.post(self.url, data, follow=True)
        self.assertEqual(
            self.actions(),
            [
                ("complete", "PO-JOB00052", 6.0, "2026-10-05 14:30:00"),
                ("defect", "PO-JOB00052", "BURR", 2),
                ("defect", "PO-JOB00052", "WELD-POR", 1),
            ],
        )
        self.assertContains(response, "PO-JOB00052 completed: 6 done, 2 defect lines logged.")

    def test_rejected_defect_keeps_completion(self):  # ACT-5
        self.erp.fail["log_defect"] = ERPNextError("Only 3 more defective units can be logged against Job Card PO-JOB00052")
        response = self.client.post(self.url, {"reason_1": "BURR", "qty_1": "9"}, follow=True)
        self.assertEqual(self.erp.calls[0][0], "complete")
        self.assertContains(response, "PO-JOB00052 completed")
        self.assertContains(response, "Defect BURR x 9 was not saved: Only 3 more defective units")

    def test_qty_without_reason_is_rejected(self):  # form validation
        response = self.client.post(self.url, {"reason_1": "", "qty_1": "2"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pick a reason")
        self.assertEqual(self.erp.calls, [])

    def test_complete_refused_by_erpnext(self):  # ERR-2 on the complete path
        self.erp.fail["complete"] = ERPNextError("Submitted Job Card cannot be processed.")
        response = self.client.post(self.url, {}, follow=True)
        self.assertContains(response, "Submitted Job Card cannot be processed.")
        self.assertEqual([c[0] for c in self.actions()], ["complete"])


class ErrorPageTests(OperatorTestCase):
    def test_queue_unavailable_banner(self):  # ERR-1
        self.erp.fail["workstations"] = ERPNextUnavailable("connection refused")
        response = self.client.get(reverse("queue"))
        self.assertEqual(response.status_code, 503)
        self.assertContains(response, "Can't reach the ERP right now", status_code=503)
        self.assertContains(response, 'href="/"', status_code=503)
        self.assertNotContains(response, "Traceback", status_code=503)
        self.assertNotContains(response, "connection refused", status_code=503)

    def test_queue_refused_shows_message(self):  # ERR-3: e.g. a running card deleted mid-request
        self.erp.fail["queue"] = ERPNextError("Job Card PO-JOB00052 not found")
        response = self.client.get(reverse("queue"))
        self.assertEqual(response.status_code, 502)
        self.assertContains(response, "Job Card PO-JOB00052 not found", status_code=502)
        self.assertContains(response, 'href="/"', status_code=502)

    @override_settings(ERPNEXT_API_SECRET="s3cr3t-value-do-not-show")
    def test_secret_never_rendered(self):  # SEC-2
        self.erp.rows["Welding Bay"] = [card("PO-JOB00052", 1)]
        self.erp.docs["PO-JOB00052"] = job_doc()
        pages = [self.client.get(reverse("queue")), self.client.get(reverse("complete", args=["PO-JOB00052"]))]
        self.erp.fail["workstations"] = ERPNextUnavailable("x")
        pages.append(self.client.get(reverse("queue")))
        for page in pages:
            self.assertNotIn(b"s3cr3t-value-do-not-show", page.content)
