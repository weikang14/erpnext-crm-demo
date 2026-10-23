"""Smoke check for the demo data (DEMO-3). Run after demo.run:

bench --site localhost execute ombak_mfg.setup.check_demo.check
"""

import frappe
from frappe.utils import date_diff, today

from ombak_mfg.setup.demo import MARKER
from ombak_mfg.setup.masters import COMPANY


def check():
	c = {"company": COMPANY, "docstatus": 1}
	sales_orders = frappe.get_all("Sales Order", filters=c, pluck="customer")
	# work orders people add later (by hand, or for CRM orders) don't count against the demo
	demo_orders = frappe.get_all("Sales Order", filters={**c, "po_no": ["like", f"{MARKER}%"]}, pluck="name")
	planned = frappe.get_all(
		"Work Order", filters={**c, "production_plan": ["is", "set"], "sales_order": ["in", demo_orders or [""]]}, pluck="sales_order"
	)
	completed = frappe.get_all(
		"Work Order", filters={**c, "status": "Completed"}, fields=["planned_end_date", "actual_end_date"]
	)
	late = [w for w in completed if date_diff(w.actual_end_date, w.planned_end_date) > 0]
	open_overdue = frappe.db.count(
		"Work Order",
		{**c, "status": ["not in", ["Completed", "Stopped", "Closed"]], "planned_end_date": ["<", today()]},
	)
	incoming_qi = frappe.db.count("Quality Inspection", {"docstatus": 1, "inspection_type": "Incoming"})
	defect_reasons = frappe.get_all("Defect Log", filters={"docstatus": 1}, pluck="defect_reason")

	results = {
		"sales orders >= 12": len(sales_orders) >= 12,
		"every sales order has a value": not frappe.db.count("Sales Order", {**c, "grand_total": ["<=", 0]}),
		"customers >= 4": len(set(sales_orders)) >= 4,
		"on-time work orders >= 5": len(completed) - len(late) >= 5,
		"late work orders >= 3": len(late) >= 3,
		"open overdue work orders >= 2": open_overdue >= 2,
		"production plans >= 12": frappe.db.count("Production Plan", c) >= 12,
		"every demo order has a work order from its production plan": bool(demo_orders)
		and set(demo_orders) <= set(planned),
		"MRP material requests >= 2": len(
			set(frappe.get_all("Material Request Item", filters={"docstatus": 1, "production_plan": ["is", "set"]}, pluck="parent"))
		)
		>= 2,
		"material request -> PO -> receipt": all(
			frappe.db.count(dt, c) >= 1 for dt in ("Material Request", "Purchase Order", "Purchase Receipt")
		),
		"rejected in-process QI >= 1": frappe.db.count(
			"Quality Inspection", {"docstatus": 1, "inspection_type": "In Process", "status": "Rejected"}
		)
		>= 1,
		"incoming QI >= 1": incoming_qi >= 1,
		"outgoing QI >= 1": frappe.db.count("Quality Inspection", {"docstatus": 1, "inspection_type": "Outgoing"})
		>= 1,
		"delivery notes >= 1": frappe.db.count("Delivery Note", c) >= 1,
		"delivery trips >= 2": frappe.db.count("Delivery Trip", c) >= 2,
		"sales invoices >= 1": frappe.db.count("Sales Invoice", c) >= 1,
		"defect logs >= 15": len(defect_reasons) >= 15,
		"defect reasons >= 4": len(set(defect_reasons)) >= 4,
	}
	for name, ok in results.items():
		print(("PASS " if ok else "FAIL ") + name)
	failed = [name for name, ok in results.items() if not ok]
	if failed:
		raise AssertionError(f"Demo data check failed: {failed}")
	print("All demo checks passed.")
