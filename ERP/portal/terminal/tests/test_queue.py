from django.urls import reverse

from terminal.tests.base import OperatorTestCase
from terminal.tests.fakes import STATIONS, card


class StationTests(OperatorTestCase):
    def test_defaults_to_operator_station(self):  # ST-1
        response = self.client.get(reverse("queue"))
        self.assertEqual(response.context["station"], "Welding Bay")
        for station in STATIONS:
            self.assertContains(response, f">{station}</option>")

    def test_choice_is_kept(self):  # ST-2
        self.client.get(reverse("queue"), {"workstation": "Laser Cutting"})
        self.assertEqual(self.client.get(reverse("queue")).context["station"], "Laser Cutting")
        self.assertEqual(self.erp.calls[-1], ("queue", "Laser Cutting"))

    def test_unknown_station_ignored(self):  # ST-3
        self.client.get(reverse("queue"), {"workstation": "Laser Cutting"})
        response = self.client.get(reverse("queue"), {"workstation": "Nope"})
        self.assertEqual(response.context["station"], "Laser Cutting")


class QueueTests(OperatorTestCase):
    def cards_by_name(self):
        return {c.name: c for c in self.client.get(reverse("queue")).context["cards"]}

    def test_ready_and_waiting(self):  # Q-1
        self.erp.rows["Welding Bay"] = [
            card("PO-JOB00041", 1, work_order="MFG-WO-2026-00017", operation="Laser Cutting"),
            card("PO-JOB00044", 2, work_order="MFG-WO-2026-00018", operation="Welding"),
        ]
        self.erp.sibling_rows = [
            {"name": "PO-JOB00043", "work_order": "MFG-WO-2026-00018", "operation": "Laser Cutting", "sequence_id": 1, "docstatus": 0},
            {"name": "PO-JOB00044", "work_order": "MFG-WO-2026-00018", "operation": "Welding", "sequence_id": 2, "docstatus": 0},
        ]  # fmt: skip
        cards = self.cards_by_name()
        self.assertEqual(cards["PO-JOB00041"].status, "ready")
        self.assertEqual(cards["PO-JOB00044"].status, "waiting")
        self.assertEqual(cards["PO-JOB00044"].waits_for, "Laser Cutting")
        self.assertContains(self.client.get(reverse("queue")), "Waits for Laser Cutting")

    def test_running_first_then_paused(self):  # Q-2
        self.erp.rows["Welding Bay"] = [
            card("PO-JOB00050", 1, work_order="MFG-WO-2026-00020"),
            card("PO-JOB00051", 1, work_order="MFG-WO-2026-00021", paused=1, status="On Hold"),
            card("PO-JOB00052", 1, work_order="MFG-WO-2026-00022", status="Work In Progress"),
        ]
        self.erp.docs["PO-JOB00052"] = {
            "total_time_in_mins": 30.0,
            "time_logs": [{"from_time": "2026-10-05 08:00:00", "to_time": None, "employee": "HR-EMP-00003"}],
        }
        cards = self.client.get(reverse("queue")).context["cards"]
        self.assertEqual([c.name for c in cards], ["PO-JOB00052", "PO-JOB00051", "PO-JOB00050"])
        self.assertEqual([c.status for c in cards], ["running", "paused", "ready"])

    def test_completed_never_listed(self):  # Q-3
        self.erp.rows["Welding Bay"] = [
            card("PO-JOB00060", 1, status="Completed"),
            card("PO-JOB00061", 1, status="Cancelled"),
        ]
        self.assertEqual(self.cards_by_name(), {})

    def test_empty_state(self):  # Q-4
        response = self.client.get(reverse("queue"))
        self.assertContains(response, "No jobs scheduled for Welding Bay")
        self.assertContains(response, 'name="workstation"')
