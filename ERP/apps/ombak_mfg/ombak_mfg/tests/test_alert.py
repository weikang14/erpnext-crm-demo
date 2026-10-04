from urllib.parse import unquote

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime, today

from ombak_mfg import tasks
from ombak_mfg.tests.factory import complete_work_order, make_work_order

MANAGER = "test.mfg.manager@ombakmetal.example"
DISABLED_MANAGER = "test.mfg.disabled@ombakmetal.example"


def make_manager(email, enabled=1):
	user = frappe.get_doc(
		{"doctype": "User", "email": email, "first_name": "Test", "send_welcome_email": 0, "enabled": enabled}
	)
	user.append_roles("Manufacturing Manager")
	user.insert(ignore_permissions=True)


def alerts(user):
	return frappe.get_all(
		"Notification Log",
		filters={"for_user": user, "subject": ["like", f"{tasks.SUBJECT}%"], "creation": [">=", today()]},
		pluck="subject",
	)


def overdue_work_order():
	return make_work_order(qty=2, start=add_to_date(now_datetime(), days=-20))


class TestOverdueAlert(IntegrationTestCase):
	def setUp(self):
		make_manager(MANAGER)
		make_manager(DISABLED_MANAGER, enabled=0)

	def tearDown(self):
		frappe.db.rollback()

	def test_one_summary_per_manager(self):  # ALR-1
		overdue_work_order()
		overdue_work_order()
		stopped = overdue_work_order()
		frappe.db.set_value("Work Order", stopped.name, "status", "Stopped")
		done = overdue_work_order()
		complete_work_order(done, add_to_date(now_datetime(), days=-19))
		draft = frappe.get_doc(
			{
				"doctype": "Work Order",
				"production_item": "FG-WB-150",
				"bom_no": frappe.db.get_value("Item", "FG-WB-150", "default_bom"),
				"qty": 1,
				"company": done.company,
				"planned_start_date": add_to_date(now_datetime(), days=-20),
			}
		)
		draft.get_items_and_operations_from_bom()
		draft.insert(ignore_permissions=True)

		tasks.notify_overdue_work_orders()

		subjects = alerts(MANAGER)
		self.assertEqual(len(subjects), 1)
		self.assertTrue(subjects[0].endswith(": 2"), subjects[0])
		self.assertEqual(alerts(DISABLED_MANAGER), [])
		self.assertEqual(len(alerts("Administrator")), 1)  # user name differs from email
		link = frappe.db.get_value("Notification Log", {"for_user": MANAGER}, "link")
		self.assertTrue(link.startswith("/desk/work-order?"), link)  # the overdue list, not one order
		self.assertIn("planned_end_date", unquote(link))

	def test_second_run_same_day_adds_nothing(self):  # ALR-2
		overdue_work_order()
		tasks.notify_overdue_work_orders()
		tasks.notify_overdue_work_orders()
		self.assertEqual(len(alerts(MANAGER)), 1)

	def test_nothing_overdue(self):  # ALR-3
		make_work_order(qty=2, start=add_to_date(now_datetime(), days=5))
		tasks.notify_overdue_work_orders()
		self.assertEqual(alerts(MANAGER), [])

	def test_registered_daily(self):  # HK-1
		self.assertIn(
			"ombak_mfg.tasks.notify_overdue_work_orders", frappe.get_hooks("scheduler_events")["daily"]
		)
