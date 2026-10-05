"""Fixture for the shop-floor terminal's contract tests (run on contract.localhost only):

bench --site contract.localhost execute ombak_mfg.setup.contract.fresh_job_cards
"""

import json

import frappe
from frappe.utils import now_datetime

from ombak_mfg.setup.masters import OPERATORS


def fresh_job_cards():
	"""A new work order whose job cards nobody has touched; prints what the tests need."""
	from ombak_mfg.tests.factory import job_cards, make_work_order

	if frappe.local.site != "contract.localhost":
		frappe.throw("Contract fixtures only run on contract.localhost")
	wo = make_work_order("FG-WB-150", qty=10, start=now_datetime())
	first, last, *_ = OPERATORS["Laser Cutting"]
	employee = frappe.db.get_value("Employee", {"first_name": first, "last_name": last})
	frappe.db.commit()
	print(json.dumps({"job_cards": [jc.name for jc in job_cards(wo.name)], "employee": employee}))
