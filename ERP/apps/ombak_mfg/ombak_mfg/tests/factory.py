"""Test fixtures built on the Ombak masters: stock, work orders, job cards."""

import frappe
from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry
from frappe.utils import add_to_date, get_datetime, now_datetime

from ombak_mfg.setup.masters import ABBR, COMPANY, FINISHED_GOODS


def receive_materials(item_code, qty):
	"""Receive enough raw material to build `qty` units of a finished good."""
	materials = FINISHED_GOODS[item_code][2]
	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Receipt",
			"company": COMPANY,
			"items": [
				{"item_code": rm, "qty": per_unit * qty, "t_warehouse": f"Raw Material - {ABBR}", "basic_rate": 10}
				for rm, per_unit in materials
			],
		}
	)
	se.insert(ignore_permissions=True)
	se.submit()


def make_work_order(item_code="FG-WB-150", qty=10, start=None):
	wo = frappe.get_doc(
		{
			"doctype": "Work Order",
			"production_item": item_code,
			"bom_no": frappe.db.get_value("Item", item_code, "default_bom"),
			"qty": qty,
			"company": COMPANY,
			"skip_transfer": 1,
			"source_warehouse": f"Raw Material - {ABBR}",
			"planned_start_date": start or now_datetime(),
		}
	)
	wo.get_items_and_operations_from_bom()
	wo.insert(ignore_permissions=True)
	wo.submit()
	return wo


_cursor = []


def next_slot(minutes):
	"""Start of a free time slot. Workstations run one job at a time, so fixtures must not overlap."""
	if not _cursor:
		_cursor.append(add_to_date(now_datetime(), days=-60))
	_cursor[0] = add_to_date(_cursor[0], minutes=-(minutes + 5))
	return _cursor[0]


def job_cards(work_order):
	"""Job cards of a work order in operation sequence."""
	names = frappe.get_all(
		"Job Card", filters={"work_order": work_order}, order_by="operation_row_id", pluck="name"
	)
	return [frappe.get_doc("Job Card", n) for n in names]


def complete_job_card(jc, minutes=30, start=None, qty=None):
	start = get_datetime(start or next_slot(minutes))
	jc.append(
		"time_logs",
		{
			"from_time": start,
			"to_time": add_to_date(start, minutes=minutes),
			"completed_qty": jc.for_quantity if qty is None else qty,
		},
	)
	jc.save(ignore_permissions=True)
	jc.submit()
	return jc


def completed_job_card(item_code="FG-WB-150", qty=10, minutes=30, start=None):
	"""A work order whose first operation's job card is submitted."""
	wo = make_work_order(item_code, qty, start=start)
	return complete_job_card(job_cards(wo.name)[0], minutes=minutes, start=start)


def complete_work_order(wo, finish_at, minutes_per_op=30):
	"""Run every operation back to back so the last one ends at `finish_at`, then manufacture."""
	cards = job_cards(wo.name)
	t = add_to_date(get_datetime(finish_at), minutes=-minutes_per_op * len(cards))
	for jc in cards:
		complete_job_card(jc, minutes=minutes_per_op, start=t)
		t = add_to_date(t, minutes=minutes_per_op)
	receive_materials(wo.production_item, wo.qty)
	se = frappe.get_doc(make_stock_entry(wo.name, "Manufacture", wo.qty))
	se.insert(ignore_permissions=True)
	se.submit()
	wo.reload()
	return wo
