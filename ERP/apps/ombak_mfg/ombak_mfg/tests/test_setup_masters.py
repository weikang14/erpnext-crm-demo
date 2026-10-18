import frappe
from frappe.utils import add_days, add_years, get_first_day, getdate, nowdate
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


class TestCrmMasters(IntegrationTestCase):
	"""004: what the CRM needs to create customers and submitted sales orders."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		masters.setup_masters()

	def tearDown(self):
		frappe.db.rollback()

	def test_sst_account(self):  # ERP-6
		fields = ["parent_account", "account_type", "company", "is_group"]
		account = frappe.db.get_value("Account", masters.SST_ACCOUNT, fields, as_dict=True)
		self.assertEqual(
			account,
			{
				"parent_account": f"Duties and Taxes - {masters.ABBR}",
				"account_type": "Tax",
				"company": masters.COMPANY,
				"is_group": 0,
			},
		)

	def test_sst_template(self):  # ERP-7
		template = frappe.get_doc("Sales Taxes and Charges Template", masters.SST_TEMPLATE)
		self.assertEqual((template.company, template.is_default, template.disabled), (masters.COMPANY, 0, 0))
		self.assertEqual(
			[(t.charge_type, t.account_head, t.rate) for t in template.taxes],
			[("On Net Total", masters.SST_ACCOUNT, 10)],
		)
		self.assertEqual(masters.SST_RATE, 10)

	def test_customer_group_and_territories_are_not_groups(self):  # ERP-8
		self.assertEqual(frappe.db.get_value("Customer Group", "Commercial", "is_group"), 0)
		for territory in ("Malaysia", "Singapore"):
			self.assertEqual(frappe.db.get_value("Territory", territory, "is_group"), 0, territory)

	def test_second_run_adds_nothing(self):  # ERP-9 (DEMO-2 covers the older doctypes)
		doctypes = [
			"Role", "User", "Custom Field", "Custom DocPerm", "Account", "Sales Taxes and Charges Template",
			"Customer Group", "Territory",
		]  # fmt: skip
		before = {dt: frappe.db.count(dt) for dt in doctypes}
		orders = frappe.get_all("Sales Order", fields=["name", "modified", "grand_total"], order_by="name")
		masters.setup_masters()
		self.assertEqual(before, {dt: frappe.db.count(dt) for dt in doctypes})
		self.assertEqual(
			orders, frappe.get_all("Sales Order", fields=["name", "modified", "grand_total"], order_by="name")
		)

	def test_default_sales_tax_template_unchanged(self):  # ERP-10
		def default():
			return frappe.get_all("Sales Taxes and Charges Template", {"is_default": 1}, pluck="name")

		before = default()
		masters.setup_masters()
		self.assertEqual(before, default())
		self.assertNotIn(masters.SST_TEMPLATE, before)

	def _order(self, **values):
		return frappe.get_doc(
			{
				"doctype": "Sales Order",
				"customer": next(iter(masters.CUSTOMERS)),
				"company": masters.COMPANY,
				"delivery_date": add_days(nowdate(), 14),
				"items": [{"item_code": "FG-CT-300", "qty": 1, "rate": 85}],  # default warehouse: FG
				**values,
			}
		)

	def test_crm_reference_field(self):  # ERP-3
		fields = ["fieldtype", "unique", "read_only", "no_copy", "insert_after", "label"]
		self.assertEqual(
			frappe.db.get_value("Custom Field", "Sales Order-crm_reference", fields, as_dict=True),
			{
				"fieldtype": "Data",
				"unique": 1,
				"read_only": 1,
				"no_copy": 1,
				"insert_after": "po_no",
				"label": "CRM reference",
			},
		)
		field = {"dt": "Sales Order", "fieldname": "crm_reference"}
		self.assertEqual(frappe.db.count("Custom Field", field), 1)
		# po_no is left alone: the demo marks its orders "DEMO-" there
		po_no = {"doc_type": "Sales Order", "field_name": "po_no"}
		self.assertFalse(frappe.db.exists("Property Setter", po_no))

	def test_crm_reference_is_unique(self):  # ERP-4
		order = self._order(crm_reference="QT-TEST-1").insert(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Sales Order", order.name, "crm_reference"), "QT-TEST-1")
		with self.assertRaises(frappe.UniqueValidationError):
			self._order(crm_reference="QT-TEST-1").insert(ignore_permissions=True)

	def test_crm_reference_is_not_copied(self):  # ERP-5
		order = self._order(crm_reference="QT-TEST-1").insert(ignore_permissions=True)
		for _ in range(2):  # a Duplicate keeps no reference, and empty ones never collide
			copy = frappe.copy_doc(order, ignore_no_copy=False)  # what Desk's Duplicate does
			self.assertFalse(copy.get("crm_reference"))
			copy.delivery_date = order.delivery_date  # also no_copy on Sales Order
			copy.insert(ignore_permissions=True)
			self.assertIsNone(frappe.db.get_value("Sales Order", copy.name, "crm_reference"))

	def test_crm_user_gets_keys_from_site_config(self):  # ERP-1
		from frappe.utils.password import get_decrypted_password

		conf = {"crm_api_key": "test-crm-key", "crm_api_secret": "test-crm-secret"}
		saved = {k: frappe.conf.get(k) for k in conf}
		frappe.conf.update(conf)
		try:
			masters.setup_masters()
		finally:
			frappe.conf.update(saved)
		user = masters.CRM_USER
		self.assertEqual(frappe.db.get_value("User", user, "enabled"), 1)
		self.assertIn(masters.CRM_ROLE, frappe.get_roles(user))
		self.assertEqual(frappe.db.get_value("User", user, "api_key"), "test-crm-key")
		self.assertEqual(get_decrypted_password("User", user, "api_secret"), "test-crm-secret")

	def test_crm_user_has_only_the_crm_role(self):  # ERP-2
		user = masters.CRM_USER
		roles = frappe.get_all("Has Role", {"parent": user, "parenttype": "User"}, pluck="role")
		self.assertEqual(roles, [masters.CRM_ROLE])
		broad = {
			"Sales Manager", "Sales User", "System Manager", "Accounts User", "Stock User", "Manufacturing User",
		}  # fmt: skip
		self.assertFalse(broad & set(frappe.get_roles(user)))

	def test_crm_role_has_exactly_its_permissions(self):  # PERM-1 (no stray rows)
		ptypes = ["select", "read", "write", "create", "submit", "cancel", "delete", "amend"]
		rows = frappe.get_all("Custom DocPerm", {"role": masters.CRM_ROLE}, ["parent", "permlevel", *ptypes])
		expected = [
			("Sales Order", "read"), ("Sales Order", "write"), ("Sales Order", "create"), ("Sales Order", "submit"),
			("Customer", "read"), ("Customer", "create"), ("Item", "read"), ("Sales Taxes and Charges Template", "read"),
			("Account", "select"), ("Address", "read"),
		]  # fmt: skip
		self.assertEqual(
			{(r.parent, r.permlevel, p) for r in rows for p in ptypes if r[p]},
			{(doctype, 0, p) for doctype, p in expected},
		)

	def test_crm_sales_order_rule_is_if_owner(self):  # PERM-6, AC20: also where the rule predates if_owner
		rule = {"parent": "Sales Order", "role": masters.CRM_ROLE, "permlevel": 0}
		frappe.db.set_value("Custom DocPerm", rule, "if_owner", 0)
		frappe.clear_cache(doctype="Sales Order")
		masters.setup_masters()
		self.assertEqual(frappe.db.count("Custom DocPerm", rule), 1)
		# only Sales Order: the CRM reads customers, addresses, items and the template other users created
		owner_only = frappe.get_all("Custom DocPerm", {"role": masters.CRM_ROLE, "if_owner": 1}, pluck="parent")
		self.assertEqual(owner_only, ["Sales Order"])

	def test_crm_user_touches_only_its_own_orders(self):  # PERM-6, AC20, FM12
		"""Read, write and submit apply to the orders the CRM user created: never a human's draft, nor a
		submitted order's allow-on-submit fields (po_no); and call 1 (the list) only sees its own."""
		theirs = self._order().insert(ignore_permissions=True)  # bench and tests run as Administrator
		submitted = self._order().insert(ignore_permissions=True)
		submitted.submit()
		self.assertEqual({theirs.owner, submitted.owner}, {"Administrator"})
		user = masters.CRM_USER
		with self.set_user(user):
			mine = self._order(crm_reference="QT-PERM-6").insert()
			mine.submit()
			frappe.get_doc("Sales Order", mine.name).check_permission("read")
			names = [theirs.name, submitted.name, mine.name]
			self.assertEqual(frappe.get_list("Sales Order", {"name": ["in", names]}, pluck="name"), [mine.name])
			for order in (theirs, submitted):
				doc = frappe.get_doc("Sales Order", order.name)
				with self.subTest(order=order.name, docstatus=order.docstatus):
					with self.assertRaises(frappe.PermissionError):
						doc.check_permission("read")
					doc.po_no = "CRM-EDIT"  # allowed on submit
					with self.assertRaises(frappe.PermissionError):
						doc.save()
			doc = frappe.get_doc("Sales Order", theirs.name)
			doc.docstatus = 1  # what PUT {"docstatus": 1} does
			with self.assertRaises(frappe.PermissionError):
				doc.save()
		self.assertEqual(frappe.db.get_value("Sales Order", mine.name, ["owner", "docstatus"]), (user, 1))
		for order in (theirs, submitted):
			unchanged = (order.po_no, order.docstatus)
			self.assertEqual(frappe.db.get_value("Sales Order", order.name, ["po_no", "docstatus"]), unchanged)
		for ptype in ("cancel", "delete", "amend"):
			self.assertFalse(frappe.has_permission("Sales Order", ptype, doc=mine.name, user=user), ptype)

	def test_crm_user_is_least_privilege(self):  # PERM-1, PERM-2
		user = masters.CRM_USER
		allowed = [
			("Sales Order", "read"), ("Sales Order", "create"),  # write, submit: on its own orders only (PERM-6)
			("Customer", "read"), ("Customer", "create"), ("Address", "create"), ("Address", "read"),
			("Item", "read"), ("Sales Taxes and Charges Template", "read"), ("Account", "select"),
		]  # fmt: skip
		for doctype, ptype in allowed:
			self.assertTrue(frappe.has_permission(doctype, ptype, user=user), f"{doctype} {ptype}")
		self.assertTrue(
			frappe.has_permission(
				"Sales Taxes and Charges Template", "read", doc=masters.SST_TEMPLATE, user=user
			)
		)
		denied = [
			("Sales Order", "write"), ("Sales Order", "submit"),  # without a document: no order of its own
			("Sales Order", "cancel"), ("Sales Order", "delete"), ("Sales Order", "amend"),
			("Customer", "write"), ("Customer", "delete"), ("Account", "read"),
			("Sales Invoice", "read"), ("Sales Invoice", "create"), ("Work Order", "read"),
			("Work Order", "create"), ("Job Card", "read"), ("Job Card", "create"),
		]  # fmt: skip
		for doctype, ptype in denied:
			self.assertFalse(frappe.has_permission(doctype, ptype, user=user), f"{doctype} {ptype}")

	def test_crm_user_creates_customer_address_and_submitted_order(self):  # PERM-1: api-contract 3, 4, 4b, 5
		with self.set_user(masters.CRM_USER):
			template = frappe.get_doc("Sales Taxes and Charges Template", masters.SST_TEMPLATE)
			template.check_permission("read")
			customer = frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "Perm Test Steel Sdn Bhd",
					"customer_type": "Company",
					"customer_group": "Commercial",
					"territory": "Malaysia",
				}
			).insert()
			frappe.get_doc(
				{
					"doctype": "Address",
					"address_title": customer.name,
					"address_type": "Billing",
					"address_line1": "Lot 5, Jalan SR 8/3",
					"city": "Seri Kembangan",
					"country": "Malaysia",
					"links": [{"link_doctype": "Customer", "link_name": customer.name}],
				}
			).insert()
			fields = ("charge_type", "account_head", "rate", "description")
			order = frappe.get_doc(
				{
					"doctype": "Sales Order",
					"customer": customer.name,
					"company": masters.COMPANY,
					"delivery_date": add_days(nowdate(), 14),
					"currency": "MYR",
					"crm_reference": "QT-PERM-1",
					"disable_rounded_total": 1,
					"apply_discount_on": "Net Total",
					"discount_amount": 19.12,
					"items": [{"item_code": "FG-CT-300", "qty": 3, "rate": 85}],
					"taxes_and_charges": masters.SST_TEMPLATE,
					"taxes": [{f: row.get(f) for f in fields} for row in template.taxes],
				}
			).insert()
			order.submit()  # api-contract 5b: a draft submitted, so ERPNext computes the status
		self.assertEqual(
			(order.docstatus, order.net_total, len(order.taxes), order.grand_total), (1, 235.88, 1, 259.47)
		)
		self.assertEqual(frappe.db.get_value("Sales Order", order.name, "status"), "To Deliver and Bill")

	def test_crm_user_reads_an_existing_customers_address(self):  # PERM-5, AC20
		"""ERPNext fills an order from the customer's primary address. The demo's customers and addresses are
		Administrator's, and the standard 'All' rule on Address is if_owner only, so the CRM role reads
		addresses itself; it still can't change or delete them."""
		customer = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": "Perm Existing Steel Sdn Bhd",
				"customer_type": "Company",
				"customer_group": "Commercial",
				"territory": "Johor",
			}
		).insert(ignore_permissions=True)
		address = frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": customer.name,
				"address_type": "Shipping",
				"address_line1": "Lot 3, Jalan Industri 1",
				"city": "Johor Bahru",
				"country": "Malaysia",
				"is_primary_address": 1,
				"is_shipping_address": 1,
				"links": [{"link_doctype": "Customer", "link_name": customer.name}],
			}
		).insert(ignore_permissions=True)
		self.assertEqual(address.owner, "Administrator")
		user = masters.CRM_USER
		self.assertTrue(frappe.has_permission("Address", "read", doc=address.name, user=user))
		for ptype in ("write", "delete"):
			self.assertFalse(frappe.has_permission("Address", ptype, doc=address.name, user=user), ptype)
		with self.set_user(user):
			order = self._order(customer=customer.name, crm_reference="QT-PERM-5", docstatus=1).insert()
		self.assertEqual((order.docstatus, order.shipping_address_name), (1, address.name))

	def _user_with(self, role):
		email = f"perm3.{frappe.scrub(role)}@ombakmetal.example"
		user = frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": role, "send_welcome_email": 0}
		)
		user.append_roles(role)
		user.insert(ignore_permissions=True)
		return email

	def test_standard_sales_roles_keep_their_access(self):  # PERM-3, EC-12
		order = [("Sales Order", "read"), ("Sales Order", "create"), ("Sales Order", "submit")]
		expected = {
			"Sales User": [*order, ("Customer", "read"), ("Customer", "create")],
			# standard ERPNext: Sales Manager only reads customers (Sales Master Manager creates them)
			"Sales Manager": [*order, ("Customer", "read")],
		}
		for role, perms in expected.items():
			user = self._user_with(role)
			for doctype, ptype in perms:
				self.assertTrue(
					frappe.has_permission(doctype, ptype, user=user), f"{role}: {doctype} {ptype}"
				)

	def test_terminal_user_still_has_no_sales_access(self):  # PERM-4
		for doctype in ("Sales Order", "Customer"):
			for ptype in ("read", "create"):
				allowed = frappe.has_permission(doctype, ptype, user=masters.INTEGRATION_USER)
				self.assertFalse(allowed, f"{doctype} {ptype}")
