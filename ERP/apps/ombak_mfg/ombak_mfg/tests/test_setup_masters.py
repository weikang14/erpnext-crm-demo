import frappe
from frappe.utils import add_years, get_first_day, getdate, nowdate
from frappe.tests import IntegrationTestCase

from ombak_mfg.setup import masters


class TestSetupMasters(IntegrationTestCase):
	def test_masters_created(self):  # DEMO-1
		masters.setup_masters()

		self.assertEqual(frappe.db.get_value("Company", masters.COMPANY, "default_currency"), "MYR")
		for wh in ("Raw Material", "Work In Progress", "Finished Goods", "Rejected"):
			self.assertTrue(frappe.db.exists("Warehouse", f"{wh} - {masters.ABBR}"), wh)

		rates = frappe.get_all(
			"Workstation", filters={"name": ["in", list(masters.WORKSTATIONS)]}, pluck="hour_rate"
		)
		self.assertEqual(len(rates), 4)
		self.assertTrue(all(r > 0 for r in rates))

		self.assertGreaterEqual(
			frappe.db.count("Item", {"item_group": "Raw Material", "item_code": ["like", "RM-%"]}), 10
		)
		self.assertEqual(len(masters.FINISHED_GOODS), 5)
		for code in masters.FINISHED_GOODS:
			bom = frappe.db.get_value("Item", code, "default_bom")
			self.assertTrue(bom, code)
			self.assertEqual(frappe.db.get_value("BOM", bom, "docstatus"), 1)
			self.assertGreater(frappe.db.count("BOM Operation", {"parent": bom}), 0)

		self.assertGreaterEqual(frappe.db.count("Defect Reason", {"disabled": 0}), 6)
		# demo orders are back-dated up to a month (and into last year in January)
		last_year_start = add_years(get_first_day(nowdate()).replace(month=1), -1)
		for item, price_list in (("FG-CT-300", "Standard Selling"), ("RM-MS-PL3", "Standard Buying")):
			valid_from = frappe.db.get_value("Item Price", {"item_code": item, "price_list": price_list}, "valid_from")
			self.assertLessEqual(getdate(valid_from), getdate(last_year_start), item)
		for customer in masters.CUSTOMERS:  # delivery trips need a shipping address per stop
			self.assertTrue(
				frappe.db.exists(
					"Dynamic Link", {"parenttype": "Address", "link_doctype": "Customer", "link_name": customer}
				),
				customer,
			)

	def test_second_run_adds_nothing(self):  # DEMO-2
		masters.setup_masters()
		doctypes = [
			"Company", "Fiscal Year", "Warehouse", "Workstation", "Operation", "Item", "BOM",
			"Item Price", "Customer", "Supplier", "Quality Inspection Template", "Driver",
			"Vehicle", "User", "Holiday List", "Defect Reason", "Address",
		]  # fmt: skip
		before = {dt: frappe.db.count(dt) for dt in doctypes}
		masters.setup_masters()
		self.assertEqual(before, {dt: frappe.db.count(dt) for dt in doctypes})
