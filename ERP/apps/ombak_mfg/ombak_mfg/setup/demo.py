"""One month of demo transactions for Ombak Metal Works.

bench --site localhost execute ombak_mfg.setup.demo.run

Dates are relative to the day it runs, so the demo always looks current. Safe to run
twice: masters are idempotent and transactions are skipped once demo sales orders exist.
"""

import math
import random
from collections import defaultdict
from datetime import datetime, time, timedelta

import frappe
from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
from erpnext.manufacturing.doctype.production_plan.production_plan import get_items_for_material_requests
from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry
from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note
from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice
from erpnext.stock.doctype.material_request.material_request import make_purchase_order
from frappe.utils import add_days, flt, get_datetime, getdate, nowdate

from ombak_mfg.setup.masters import ABBR, COMPANY, FINISHED_GOODS, RAW_MATERIALS, setup_masters

MARKER = "DEMO-"  # customer PO no. prefix on demo sales orders
INSPECTOR = "lim.weijie@ombakmetal.example"
RAW, FG = f"Raw Material - {ABBR}", f"Finished Goods - {ABBR}"
PURCHASED = "RM-GI-SH20"  # starts at zero stock, so MRP has a real shortage to buy for
STEEL = "Lintang Steel Supply Sdn Bhd"
SUPPLIER_OF = {
	**{rm: STEEL for rm in RAW_MATERIALS if rm.startswith(("RM-MS", "RM-GI", "RM-ANG", "RM-FLT", "RM-RHS"))},
	"RM-WW-08": "Wirafast Industrial Supplies Sdn Bhd",
	"RM-BN-M10": "Wirafast Industrial Supplies Sdn Bhd",
	"RM-PP-GRY": "Chromacoat Powder Coatings Sdn Bhd",
}

C1, C2, C3, C4, C5 = (
	"Tanjung Electrical Contractors Sdn Bhd",
	"Kulai Food Processing Sdn Bhd",
	"Seri Alam Logistics Sdn Bhd",
	"Mutiara Automation Sdn Bhd",
	"Harbourline Packaging Pte Ltd",
)

# (order day relative to today, customer, item, qty, outcome)
# outcome: "on_time" | ("late", days of rework past the plan) | ("open", operations done) | "planned"
ORDERS = [
	(-30, C1, "FG-CT-300", 40, "on_time"),
	(-29, C2, "FG-MG-1200", 8, "on_time"),
	(-27, C3, "FG-PR-UP3", 20, ("late", 2)),
	(-26, C4, "FG-EBF-1000", 4, "on_time"),
	(-25, C5, "FG-WB-150", 120, "on_time"),
	(-23, C1, "FG-CT-300", 60, ("late", 3)),
	(-21, C2, "FG-MG-1200", 10, "on_time"),
	(-19, C3, "FG-EBF-1000", 6, "on_time"),
	(-17, C4, "FG-PR-UP3", 24, ("late", 1)),
	(-15, C5, "FG-WB-150", 150, "on_time"),
	(-13, C1, "FG-MG-1200", 12, "on_time"),
	(-11, C2, "FG-CT-300", 50, "on_time"),
	(-8, C3, "FG-EBF-1000", 5, ("open", 2)),
	(-7, C4, "FG-PR-UP3", 16, ("open", 1)),
	(-3, C5, "FG-MG-1200", 10, ("open", 1)),
	(-1, C1, "FG-WB-150", 100, "planned"),
	(0, C2, "FG-EBF-1000", 6, "planned"),
	(0, C3, "FG-EBF-1000", 30, "planned"),  # these two load Welding Bay to ~85% next week
	(0, C5, "FG-MG-1200", 30, "planned"),
]

# operation: [(defect reason, weight)] -- weights give the Pareto chart a realistic shape
DEFECTS = {
	"Laser Cutting": [("BURR", 5), ("HOLE-POS", 2), ("MAT-DEF", 1)],
	"Press Brake Bending": [("DIM-OOT", 4), ("SCRATCH", 2)],
	"Welding": [("WELD-POR", 4), ("WELD-DIST", 2)],
	"Powder Coating": [("COAT-PEEL", 2), ("COAT-THIN", 2), ("SCRATCH", 1)],
}


def run():
	setup_masters()
	from frappe.utils.scheduler import enable_scheduler

	enable_scheduler()
	if frappe.db.exists("Sales Order", {"po_no": ["like", f"{MARKER}%"]}):
		print("Demo transactions already exist, nothing to add.")
		return

	rng = random.Random(42)  # same demo every time
	today = getdate(nowdate())
	built = [o for o in ORDERS if o[4] == "on_time" or o[4][0] == "late"]

	opening_stock(today, built)
	plans = [create_order(today, n, *order) for n, order in enumerate(ORDERS, 1)]
	run_shop_floor(plans, rng)
	ship(plans)
	frappe.db.commit()
	print(f"Demo created: {len(plans)} sales orders.")


# -- purchasing -----------------------------------------------------------------------


def material_needed(orders):
	need = defaultdict(float)
	for _day, _customer, item, qty, _outcome in orders:
		for rm, per_unit in FINISHED_GOODS[item][2]:
			need[rm] += per_unit * qty
	return need


def opening_stock(today, built):
	need = material_needed(built)
	frappe.get_doc(
		{
			"doctype": "Stock Reconciliation",
			"purpose": "Opening Stock",
			"company": COMPANY,
			"posting_date": add_days(today, -32),
			"posting_time": "08:00:00",
			"set_posting_time": 1,
			"expense_account": f"Temporary Opening - {ABBR}",
			"items": [
				{
					"item_code": rm,
					"warehouse": RAW,
					"qty": math.ceil(need[rm] * 1.3) + 5,
					"valuation_rate": RAW_MATERIALS[rm][2],
				}
				for rm in RAW_MATERIALS
				if rm != PURCHASED
			],
		}
	).insert(ignore_permissions=True).submit()


def purchase(mr, today):
	"""Buyer orders the day after the request, one PO per supplier; goods arrive two days later
	and pass incoming inspection. Anything dated after today stays open, as it would."""
	order_day, receive_day = getdate(add_days(mr.transaction_date, 1)), getdate(add_days(mr.transaction_date, 3))
	if order_day > today:
		return
	for supplier in sorted({SUPPLIER_OF[row.item_code] for row in mr.items}):
		po = frappe.get_doc(make_purchase_order(mr.name))
		po.supplier = supplier
		po.set("items", [row for row in po.items if SUPPLIER_OF[row.item_code] == supplier])
		po.update({"transaction_date": order_day, "schedule_date": receive_day})
		for row in po.items:
			row.schedule_date = receive_day
		po.insert(ignore_permissions=True)
		po.submit()
		if receive_day > today:
			continue
		pr = frappe.get_doc(make_purchase_receipt(po.name))
		pr.update({"posting_date": receive_day, "posting_time": "10:00:00", "set_posting_time": 1})
		pr.insert(ignore_permissions=True)
		attach_inspections(pr, "Incoming")
		pr.submit()


def attach_inspections(doc, inspection_type):
	"""Create an accepted quality inspection for every item that requires one."""
	flag = "inspection_required_before_purchase" if inspection_type == "Incoming" else "inspection_required_before_delivery"
	inspections = {}
	for row in doc.items:
		if not frappe.db.get_value("Item", row.item_code, flag):
			continue
		qi = frappe.get_doc(
			{
				"doctype": "Quality Inspection",
				"inspection_type": inspection_type,
				"reference_type": doc.doctype,
				"reference_name": doc.name,
				"item_code": row.item_code,
				"sample_size": min(flt(row.qty), 5),
				"report_date": doc.posting_date,
				"inspected_by": INSPECTOR,
				"status": "Accepted",
				"quality_inspection_template": frappe.db.get_value(
					"Item", row.item_code, "quality_inspection_template"
				),
			}
		)
		qi.get_item_specification_details()
		for reading in qi.readings:
			if reading.numeric:
				reading.reading_1 = str((flt(reading.min_value) + flt(reading.max_value)) / 2)
			else:
				reading.reading_value = reading.value
		qi.insert(ignore_permissions=True)
		qi.submit()
		inspections[row.name] = qi.name
	doc.reload()  # submitting a QI writes its name back onto the reference row
	missing = [row for row in doc.items if row.name in inspections and not row.quality_inspection]
	for row in missing:
		row.quality_inspection = inspections[row.name]
	if missing:
		doc.save(ignore_permissions=True)


# -- orders and the shop floor --------------------------------------------------------


def create_order(today, n, day, customer, item, qty, outcome):
	order_date = add_days(today, day)
	delivery = add_days(order_date, 12)
	so = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"customer": customer,
			"company": COMPANY,
			"transaction_date": order_date,
			"delivery_date": delivery,
			"po_no": f"{MARKER}{n:03d}",
			"items": [{"item_code": item, "qty": qty, "delivery_date": delivery, "warehouse": FG}],
		}
	).insert(ignore_permissions=True)
	so.submit()

	# planner runs MRP for the order: work order + material requests for whatever is short
	pp = frappe.new_doc("Production Plan")
	pp.update({"company": COMPANY, "posting_date": order_date, "get_items_from": "Sales Order", "for_warehouse": RAW})
	pp.append(
		"sales_orders",
		{"sales_order": so.name, "sales_order_date": order_date, "customer": customer, "grand_total": so.grand_total},
	)
	pp.get_items()
	for row in pp.po_items:
		row.planned_start_date = datetime.combine(add_days(order_date, 1), time(8))
	pp.set("mr_items", get_items_for_material_requests(pp.as_dict()))
	pp.insert(ignore_permissions=True)
	pp.submit()
	pp.make_work_order()
	if pp.mr_items:
		pp.make_material_request()

	wo = frappe.get_doc("Work Order", {"production_plan": pp.name})
	wo.update({"skip_transfer": 1, "source_warehouse": RAW, "fg_warehouse": FG, "expected_delivery_date": delivery})
	wo.save(ignore_permissions=True)
	wo.submit()

	requests = frappe.get_all(
		"Material Request Item", filters={"production_plan": pp.name, "docstatus": 0}, pluck="parent"
	)
	for name in sorted(set(requests)):
		mr = frappe.get_doc("Material Request", name)
		mr.transaction_date = order_date
		for row in mr.items:
			row.schedule_date = add_days(order_date, 3)
		mr.save(ignore_permissions=True)
		mr.submit()
		purchase(mr, today)
	return frappe._dict(so=so, wo=wo, outcome=outcome)


class Overtime:
	"""After-hours slots (from 17:30) per workstation and day, so extra work never overlaps."""

	def __init__(self):
		self.next_free = {}

	def book(self, workstation, day, minutes):
		day = getdate(day)
		while day.weekday() == 6:  # no work on Sundays
			day = add_days(day, 1)
		start = self.next_free.get((workstation, day), datetime.combine(day, time(17, 30)))
		end = start + timedelta(minutes=minutes)
		self.next_free[(workstation, day)] = end + timedelta(minutes=10)
		return {"from_time": start, "to_time": end}


def run_shop_floor(plans, rng):
	overtime = Overtime()
	for plan in plans:
		cards = frappe.get_all(
			"Job Card", filters={"work_order": plan.wo.name}, order_by="operation_row_id", pluck="name"
		)
		outcome = plan.outcome
		done = len(cards) if outcome == "on_time" or outcome[0] == "late" else 0
		if isinstance(outcome, tuple) and outcome[0] == "open":
			done = outcome[1]

		for idx, name in enumerate(cards[:done]):
			jc = frappe.get_doc("Job Card", name)
			late_days = outcome[1] if idx == len(cards) - 1 and outcome[0] == "late" else 0
			logs = actual_time_logs(jc, rng, overtime, late_days, plan.wo.planned_end_date)
			jc.set("time_logs", [])
			for log in logs:
				jc.append("time_logs", log)
			jc.save(ignore_permissions=True)
			jc.submit()
			log_defects(jc, getdate(logs[-1]["to_time"]), rng)
			if late_days:
				reject_at_inspection(jc, getdate(plan.wo.planned_end_date))


def actual_time_logs(jc, rng, overtime, late_days, planned_end):
	"""Follow ERPNext's capacity plan, then run a bit short or long; late jobs get rework days."""
	slots = sorted(jc.scheduled_time_logs, key=lambda s: s.from_time)
	logs = [{"from_time": get_datetime(s.from_time), "to_time": get_datetime(s.to_time)} for s in slots]
	extra = round(flt(jc.time_required) * (rng.uniform(0.85, 1.2) - 1))
	last = logs[-1]
	if extra < 0:
		last["to_time"] = max(last["from_time"] + timedelta(minutes=5), last["to_time"] + timedelta(minutes=extra))
	elif extra > 0:
		logs.append(overtime.book(jc.workstation, last["to_time"], extra))
	for day in range(1, late_days + 1):  # e.g. coating rejected at final inspection and redone
		logs.append(overtime.book(jc.workstation, add_days(planned_end, day), 120))
	for log in logs:
		log["completed_qty"] = 0
	logs[-1]["completed_qty"] = jc.for_quantity
	return logs


def reject_at_inspection(jc, day):
	"""The in-process inspection that explains why a late order needed rework."""
	failing = "Coating Thickness (micron)" if jc.operation == "Powder Coating" else "Dimension Deviation (mm)"
	qi = frappe.get_doc(
		{
			"doctype": "Quality Inspection",
			"inspection_type": "In Process",
			"reference_type": "Job Card",
			"reference_name": jc.name,
			"item_code": jc.production_item,
			"sample_size": 5,
			"report_date": day,
			"inspected_by": INSPECTOR,
			"status": "Rejected",
			"quality_inspection_template": "Final Inspection",
			"remarks": f"{failing} out of specification; batch sent back for rework",
		}
	)
	qi.get_item_specification_details()
	for reading in qi.readings:
		if reading.specification == failing:
			reading.reading_1 = str(flt(reading.min_value) - 15 if "Coating" in failing else flt(reading.max_value) + 0.8)
		elif reading.numeric:
			reading.reading_1 = str((flt(reading.min_value) + flt(reading.max_value)) / 2)
		else:
			reading.reading_value = reading.value
	qi.insert(ignore_permissions=True)
	qi.submit()


def log_defects(jc, day, rng):
	if rng.random() > 0.6:
		return
	reasons, weights = zip(*DEFECTS[jc.operation], strict=True)
	frappe.get_doc(
		{
			"doctype": "Defect Log",
			"job_card": jc.name,
			"defect_reason": rng.choices(reasons, weights)[0],
			"qty": rng.randint(1, max(1, int(jc.for_quantity * 0.05))),
			"posting_date": day,
			"remarks": "Found at operator self-check",
		}
	).insert(ignore_permissions=True).submit()


# -- stock, delivery, invoicing -------------------------------------------------------


def ship(plans):
	"""Post manufacture and delivery entries in time order so stock never goes negative."""
	finished = [p for p in plans if p.outcome == "on_time" or p.outcome[0] == "late"]
	events = []
	for plan in finished:
		plan.wo.reload()
		made_at = get_datetime(plan.wo.actual_end_date) + timedelta(minutes=20)
		ship_day = add_days(made_at.date(), 1)
		while ship_day.weekday() == 6:
			ship_day = add_days(ship_day, 1)
		events.append((made_at, 0, plan))
		events.append((datetime.combine(ship_day, time(9, 30)), 1, plan))

	trips = defaultdict(list)
	for at, kind, plan in sorted(events, key=lambda e: (e[0], e[1])):
		if kind == 0:
			se = frappe.get_doc(make_stock_entry(plan.wo.name, "Manufacture", plan.wo.qty))
			se.update({"posting_date": at.date(), "posting_time": at.time(), "set_posting_time": 1})
			se.insert(ignore_permissions=True)
			se.submit()
		else:
			dn = frappe.get_doc(make_delivery_note(plan.so.name))
			dn.update({"posting_date": at.date(), "posting_time": at.time(), "set_posting_time": 1})
			dn.insert(ignore_permissions=True)
			attach_inspections(dn, "Outgoing")
			dn.submit()
			trips[at.date()].append(dn)

	driver = frappe.db.get_value("Driver", {"full_name": "Rahim bin Osman"})
	for day, notes in sorted(trips.items()):
		frappe.get_doc(
			{
				"doctype": "Delivery Trip",
				"company": COMPANY,
				"driver": driver,
				"vehicle": "JTA 8821",
				"departure_time": datetime.combine(day, time(10, 30)),
				"delivery_stops": [
					{
						"customer": dn.customer,
						"address": dn.shipping_address_name or dn.customer_address,
						"delivery_note": dn.name,
						"visited": 1,
					}
					for dn in notes
				],
			}
		).insert(ignore_permissions=True).submit()
		for dn in notes:
			si = frappe.get_doc(make_sales_invoice(dn.name))
			si.update({"posting_date": day, "set_posting_time": 1, "due_date": add_days(day, 30)})
			si.insert(ignore_permissions=True)
			si.submit()
