"""Regression tests for the round-2 validator findings (code FAIL, design/alignment/security notes)."""

from datetime import UTC, datetime
from unittest import mock

from django.contrib.auth.models import User
from django.test import SimpleTestCase
from django.urls import reverse

from terminal import queue
from terminal.erpnext import ERPNextUnavailable, check_job_card
from terminal.tests.base import OperatorTestCase
from terminal.tests.fakes import card
from terminal.tests.test_actions import LOCAL_NOW, job_doc

OPEN_LOG = {"from_time": "2026-10-05 08:00:00", "to_time": None, "employee": "HR-EMP-00003"}
CLOSED_LOG = {"from_time": "2026-10-05 08:00:00", "to_time": "2026-10-05 09:00:00", "employee": "HR-EMP-00003"}


class ServerSideGuardTests(OperatorTestCase):
    def actions(self):
        return [c for c in self.erp.calls if c[0] != "queue"]

    def test_double_start_refused(self):  # FM2: a second start would open an overlapping log
        self.erp.docs["PO-JOB00052"] = job_doc(time_logs=[OPEN_LOG])
        response = self.client.post(reverse("start", args=["PO-JOB00052"]), follow=True)
        self.assertEqual(self.actions(), [])
        self.assertContains(response, "PO-JOB00052 is already running.")

    def test_resume_only_when_paused(self):
        self.erp.docs["PO-JOB00052"] = job_doc(is_paused=0, time_logs=[OPEN_LOG])
        response = self.client.post(reverse("resume", args=["PO-JOB00052"]), follow=True)
        self.assertEqual(self.actions(), [])
        self.assertContains(response, "PO-JOB00052 isn&#x27;t paused.")

    @mock.patch("terminal.queue.erp_now", return_value=LOCAL_NOW)
    def test_paused_card_is_resumed_then_completed(self, _now):  # code FAIL: AC7 for paused cards
        self.erp.docs["PO-JOB00052"] = job_doc(is_paused=1, status="On Hold", time_logs=[CLOSED_LOG])
        self.client.post(reverse("complete", args=["PO-JOB00052"]), {})
        self.assertEqual(
            self.actions(),
            [("resume", "PO-JOB00052", LOCAL_NOW), ("complete", "PO-JOB00052", 10.0, LOCAL_NOW)],
        )

    def test_complete_needs_a_linked_employee(self):
        User.objects.create_user("supervisor", password="pw-for-tests-only")
        self.client.force_login(User.objects.get(username="supervisor"))
        self.erp.docs["PO-JOB00052"] = job_doc()
        response = self.client.post(reverse("complete", args=["PO-JOB00052"]), {}, follow=True)
        self.assertEqual(self.actions(), [])
        self.assertContains(response, "isn&#x27;t linked to an ERPNext employee")

    def test_lost_connection_while_saving_says_check(self):
        self.erp.docs["PO-JOB00052"] = job_doc(time_logs=[OPEN_LOG])
        self.erp.fail["complete"] = ERPNextUnavailable("timeout")
        response = self.client.post(reverse("complete", args=["PO-JOB00052"]), {})
        self.assertEqual(response.status_code, 503)
        self.assertContains(response, "Check the job card in ERPNext", status_code=503)
        self.assertNotContains(response, "Nothing was changed", status_code=503)

    def test_start_refused_on_a_paused_card(self):  # code round 2: a stale page could start a paused card
        self.erp.docs["PO-JOB00052"] = job_doc(is_paused=1, status="On Hold", time_logs=[CLOSED_LOG])
        response = self.client.post(reverse("start", args=["PO-JOB00052"]), follow=True)
        self.assertEqual(self.actions(), [])
        self.assertContains(response, "PO-JOB00052 is paused: tap Resume.")

    def test_complete_refused_before_start(self):  # design round 2: a typed URL reached Complete
        self.erp.docs["PO-JOB00052"] = job_doc(status="Open", time_logs=[])
        for method in ("get", "post"):
            response = getattr(self.client, method)(reverse("complete", args=["PO-JOB00052"]), follow=True)
            self.assertContains(response, "Start PO-JOB00052 before completing it.")
        self.assertEqual(self.actions(), [])

    def test_error_text_is_linked_to_its_field(self):  # design round 2: aria-describedby pointed at nothing
        self.erp.docs["PO-JOB00052"] = job_doc(time_logs=[OPEN_LOG])
        response = self.client.post(reverse("complete", args=["PO-JOB00052"]), {"reason_1": "", "qty_1": "2"})
        self.assertContains(response, 'id="id_reason_1_error"')

    def test_running_needs_an_open_log(self):  # a card part-completed in Desk is not "running"
        self.erp.rows["Welding Bay"] = [card("PO-JOB00052", 1, status="Work In Progress")]
        self.erp.docs["PO-JOB00052"] = job_doc(time_logs=[CLOSED_LOG])
        cards = self.client.get(reverse("queue")).context["cards"]
        self.assertEqual(cards[0].status, "ready")

    def test_non_ascii_digits_rejected(self):  # security LOW: \d matched fullwidth digits
        for path in ("/job/PO-JOB%EF%BC%91/start/", "/job/PO-JOB%D9%A1/pause/"):
            self.assertEqual(self.client.post(path).status_code, 404, path)
        self.assertEqual(self.actions(), [])


class TimingLabelTests(SimpleTestCase):  # alignment: overdue / today / later
    NOW = datetime(2026, 10, 5, 6, 30, tzinfo=UTC)  # 14:30 on 5 Oct in Kuala Lumpur

    def timing(self, start, end):
        row = card("PO-JOB00001", 1, expected_start_date=start, expected_end_date=end)
        return queue.build_cards([row], [], now=self.NOW)[0].timing

    def test_labels(self):
        self.assertEqual(self.timing("2026-09-28 16:37:00", "2026-09-29 09:45:00"), "overdue")
        self.assertEqual(self.timing("2026-10-05 08:00:00", "2026-10-05 11:00:00"), "overdue")
        self.assertEqual(self.timing("2026-10-05 13:00:00", "2026-10-05 17:00:00"), "today")
        self.assertEqual(self.timing("2026-10-05 16:00:00", "2026-10-06 09:00:00"), "today")
        self.assertEqual(self.timing("2026-10-06 08:00:00", "2026-10-06 11:00:00"), "later")

    def test_overdue_sorted_before_today(self):  # alignment round 2: not just an accident of start order
        long_job = card("PO-JOB00001", 1, work_order="WO-A",
                        expected_start_date="2026-10-04 08:00:00", expected_end_date="2026-10-07 17:00:00")
        late_job = card("PO-JOB00002", 1, work_order="WO-B",
                        expected_start_date="2026-10-04 09:00:00", expected_end_date="2026-10-04 17:00:00")
        later_job = card("PO-JOB00003", 1, work_order="WO-C",
                         expected_start_date="2026-10-08 08:00:00", expected_end_date="2026-10-08 12:00:00")
        running = card("PO-JOB00004", 1, work_order="WO-D", status="Work In Progress",
                       expected_start_date="2026-10-09 08:00:00", expected_end_date="2026-10-09 12:00:00")  # fmt: skip
        cards = queue.build_cards([long_job, late_job, later_job, running], [], now=self.NOW)
        self.assertEqual([c.name for c in cards], ["PO-JOB00004", "PO-JOB00002", "PO-JOB00001", "PO-JOB00003"])

    def test_job_card_names_ascii_only(self):
        for bad in ("PO-JOB１", "PO-JOB1\n", "PO-JOB١"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                check_job_card(bad)


class HardeningTests(OperatorTestCase):
    def test_csp_header(self):
        response = self.client.get(reverse("queue"))
        self.assertIn("default-src 'self'", response.headers.get("Content-Security-Policy", ""))

    def test_admin_removed(self):
        self.assertEqual(self.client.get("/admin/").status_code, 404)

    def test_overdue_label_shown(self):
        self.erp.rows["Welding Bay"] = [card("PO-JOB00052", 1, expected_end_date="2001-01-01 10:00:00")]
        self.assertContains(self.client.get(reverse("queue")), "Overdue")
