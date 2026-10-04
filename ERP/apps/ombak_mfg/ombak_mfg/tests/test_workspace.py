import json

import frappe
from frappe.desk.doctype.number_card.number_card import get_result
from frappe.tests import IntegrationTestCase

from ombak_mfg.tests.test_reports import REPORTS

NUMBER_CARDS = ("Unfinished Work Orders", "Overdue Work Orders", "Defects This Month")


class TestWorkspace(IntegrationTestCase):
	def test_shortcuts_and_cards(self):  # AC16
		ws = frappe.get_doc("Workspace", "Ombak Factory")
		self.assertTrue(ws.public)
		targets = {s.link_to for s in ws.shortcuts}
		self.assertLessEqual({*REPORTS, "Defect Log", "Work Order", "Job Card"}, targets)
		self.assertEqual({c.number_card_name for c in ws.number_cards}, set(NUMBER_CARDS))
		blocks = {b["type"] for b in json.loads(ws.content)}
		self.assertLessEqual({"number_card", "shortcut"}, blocks)

	def test_number_cards_evaluate(self):  # AC16
		for name in NUMBER_CARDS:
			card = frappe.get_doc("Number Card", name)
			self.assertEqual(card.module, "Ombak Mfg")
			self.assertFalse(card.currency, f"{name} is a count/quantity, not money")
			filters = json.loads(card.filters_json or "[]")
			self.assertIsInstance(get_result(card.as_dict(), json.dumps(filters)), int | float, name)

	def test_sidebar_and_desktop_icon(self):
		self.assertTrue(frappe.db.exists("Workspace Sidebar", "Ombak Factory"))
		self.assertEqual(frappe.db.get_value("Desktop Icon", "Ombak Factory", "link_to"), "Ombak Factory")
