"""Fixtures for the contract tests (run on contract.localhost only):

bench --site contract.localhost execute ombak_mfg.setup.contract.fresh_job_cards
bench --site contract.localhost execute ombak_mfg.setup.contract.existing_customer
bench --site contract.localhost execute ombak_mfg.setup.contract.others_orders
"""

import json

import frappe
from frappe.utils import add_days, now_datetime, nowdate

from ombak_mfg.setup.masters import COMPANY, OPERATORS, _ensure

EXISTING_CUSTOMER = "Existing Fixture Steel Sdn Bhd"  # CRM/sales/tests/test_erp_contract.py uses this name
# CRM/sales/tests/test_erp_contract.py uses these references
OTHERS_ORDERS = {"draft": "QT-FIXTURE-OTHERS-DRAFT", "submitted": "QT-FIXTURE-OTHERS-SUBMITTED"}


def _contract_site_only():
	if frappe.local.site != "contract.localhost":
		frappe.throw("Contract fixtures only run on contract.localhost")


def fresh_job_cards():
	"""A new work order whose job cards nobody has touched; prints what the tests need."""
	from ombak_mfg.tests.factory import job_cards, make_work_order

	_contract_site_only()
	wo = make_work_order("FG-WB-150", qty=10, start=now_datetime())
	first, last, *_ = OPERATORS["Laser Cutting"]
	employee = frappe.db.get_value("Employee", {"first_name": first, "last_name": last})
	frappe.db.commit()
	print(json.dumps({"job_cards": [jc.name for jc in job_cards(wo.name)], "employee": employee}))


def existing_customer():
	"""004 CT-12: a customer the CRM didn't create, like the demo's: its primary address is Administrator's
	(bench execute runs as Administrator), so the CRM user reads it only through its own role. Idempotent."""
	_contract_site_only()
	_ensure(
		"Customer",
		EXISTING_CUSTOMER,
		{
			"customer_name": EXISTING_CUSTOMER,
			"customer_type": "Company",
			"customer_group": "Commercial",
			"territory": "Johor",
		},
	)
	link = {"parenttype": "Address", "link_doctype": "Customer", "link_name": EXISTING_CUSTOMER}
	if not frappe.db.exists("Dynamic Link", link):
		frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": EXISTING_CUSTOMER,
				"address_type": "Shipping",
				"address_line1": "Lot 3, Jalan Industri 1",
				"city": "Johor Bahru",
				"state": "Johor",
				"pincode": "81100",
				"country": "Malaysia",
				"is_primary_address": 1,
				"is_shipping_address": 1,
				"links": [{"link_doctype": "Customer", "link_name": EXISTING_CUSTOMER}],
			}
		).insert(ignore_permissions=True)
	frappe.db.commit()
	print(EXISTING_CUSTOMER)


def others_orders():
	"""004 CT-13: a draft and a submitted sales order the CRM didn't create (bench execute runs as Administrator), so
	the tests can show the CRM key can't read, find or change them. Idempotent; prints {"draft": name, ...}."""
	_contract_site_only()
	names = {}
	for state, reference in OTHERS_ORDERS.items():
		name = frappe.db.get_value("Sales Order", {"crm_reference": reference})
		if not name:
			order = frappe.get_doc(
				{
					"doctype": "Sales Order",
					"customer": EXISTING_CUSTOMER,
					"company": COMPANY,
					"delivery_date": add_days(nowdate(), 14),
					"crm_reference": reference,
					"items": [{"item_code": "FG-CT-300", "qty": 1, "rate": 85}],
				}
			).insert(ignore_permissions=True)
			if state == "submitted":
				order.submit()
			name = order.name
		names[state] = name
	frappe.db.commit()
	print(json.dumps(names))
