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


class TestTerminalMasters(IntegrationTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_operator_employees(self):  # OP-1
		masters.setup_masters()
		for workstation, (first, last, *_rest) in masters.OPERATORS.items():
			self.assertIn(workstation, masters.WORKSTATIONS)
			self.assertTrue(
				frappe.db.exists(
					"Employee", {"first_name": first, "last_name": last, "status": "Active", "company": masters.COMPANY}
				),
				workstation,
			)

	def test_integration_user_gets_keys_from_site_config(self):  # OP-2
		from frappe.utils.password import get_decrypted_password

		conf = {"shopfloor_api_key": "test-key-123", "shopfloor_api_secret": "test-secret-456"}
		saved = {k: frappe.conf.get(k) for k in conf}
		frappe.conf.update(conf)
		try:
			masters.setup_masters()
		finally:
			frappe.conf.update(saved)
		user = masters.INTEGRATION_USER
		self.assertIn(masters.TERMINAL_ROLE, frappe.get_roles(user))
		self.assertNotIn("Manufacturing User", frappe.get_roles(user))
		self.assertEqual(frappe.db.get_value("User", user, "api_key"), "test-key-123")
		self.assertEqual(get_decrypted_password("User", user, "api_secret"), "test-secret-456")

	def test_terminal_role_is_least_privilege(self):  # security MEDIUM: Manufacturing User was too broad
		masters.setup_masters()
		user = masters.INTEGRATION_USER
		allowed = [
			("Job Card", "read"), ("Job Card", "write"), ("Job Card", "submit"),
			("Defect Log", "create"), ("Defect Log", "submit"), ("Defect Reason", "read"),
			("Workstation", "read"), ("Employee", "read"), ("Work Order", "read"), ("Work Order", "write"),
			("Work Order", "submit"),
		]  # fmt: skip
		for doctype, ptype in allowed:
			self.assertTrue(frappe.has_permission(doctype, ptype, user=user), f"{doctype} {ptype}")
		denied = [
			("Work Order", "create"), ("Work Order", "cancel"), ("Work Order", "delete"),
			("Job Card", "cancel"), ("Job Card", "delete"), ("BOM", "write"),
			("Stock Entry", "create"), ("Sales Invoice", "read"), ("Account", "read"),
		]  # fmt: skip
		for doctype, ptype in denied:
			self.assertFalse(frappe.has_permission(doctype, ptype, user=user), f"{doctype} {ptype}")
		# every user may edit their own profile; never someone else's
		self.assertFalse(frappe.has_permission("User", "write", doc="Administrator", user=user))
