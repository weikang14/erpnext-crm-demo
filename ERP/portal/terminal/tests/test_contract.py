"""Contract tests: the real ERPNext answers the way api-contract.md says. Needs the fixture
that scripts/test-portal.sh passes in; skipped otherwise."""

import json
import os
import unittest
from datetime import timedelta

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from terminal.erpnext import ERPNext, ERPNextError, ERPNextUnavailable

FIXTURE = os.environ.get("CONTRACT_FIXTURE")


def erp_time(seconds_ago):
    # seconds, not minutes: each run must not overlap the previous run's logs for the same
    # employee (ERPNext: "currently working on another workstation"); runs are > 1 min apart
    return (timezone.localtime() - timedelta(seconds=seconds_ago)).strftime("%Y-%m-%d %H:%M:%S")


@unittest.skipUnless(FIXTURE, "run via scripts/test-portal.sh")
@override_settings(ERPNEXT_SITE=os.environ.get("CONTRACT_SITE", ""))
class ContractTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        fixture = json.loads(FIXTURE)
        cls.cards, cls.employee = fixture["job_cards"], fixture["employee"]

    def test_workstations(self):  # CT-1
        self.assertEqual(
            sorted(ERPNext().workstations()), ["CNC Press Brake", "Laser Cutting", "Powder Coating", "Welding Bay"]
        )

    def test_queue_rows_have_every_field(self):  # CT-2
        from terminal.erpnext import QUEUE_FIELDS

        # any open card will do: earlier runs leave cards behind, so ours may be past row 50
        rows = ERPNext().queue("CNC Press Brake")
        self.assertTrue(rows)
        for row in rows:
            self.assertLessEqual(set(QUEUE_FIELDS), set(row))

    def test_full_cycle_and_defects(self):  # CT-3, CT-4
        erp, card = ERPNext(), self.cards[0]
        erp.start(card, self.employee, erp_time(40))
        erp.pause(card, erp_time(30))
        # what the terminal does when Complete is tapped on a paused card: resume, then complete at once
        erp.resume(card, erp_time(20))
        erp.complete(card, 10, erp_time(20))
        doc = erp.job_card(card)
        self.assertEqual((doc["docstatus"], doc["status"]), (1, "Completed"))
        self.assertEqual(len(doc["time_logs"]), 2)
        self.assertTrue(all(log["employee"] == self.employee for log in doc["time_logs"]))
        self.assertEqual(doc["time_logs"][-1]["completed_qty"], 10)

        self.assertTrue(erp.log_defect(card, "BURR", 2).startswith("DL-"))
        with self.assertRaisesMessage(ERPNextError, "Only 8 more"):
            erp.log_defect(card, "BURR", 50)

    def test_sequence_enforced(self):  # CT-5
        with self.assertRaisesMessage(ERPNextError, "before the operation"):
            ERPNext().start(self.cards[2], self.employee, erp_time(5))

    def test_token_is_least_privilege(self):  # CT-7: the terminal's ERPNext role can't touch other data
        erp = ERPNext()
        with self.assertRaisesMessage(ERPNextError, "Tell the supervisor"):
            erp._call("GET", "document/Sales%20Invoice")
        with self.assertRaisesMessage(ERPNextError, "Tell the supervisor"):
            erp._call("POST", "document/Work%20Order", json={"production_item": "FG-WB-150", "qty": 1})

    @override_settings(ERPNEXT_API_SECRET="wrong")
    def test_bad_token(self):  # CT-6
        with self.assertRaises(ERPNextUnavailable):
            ERPNext().workstations()
