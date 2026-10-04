# Copyright (c) 2026, Ombak Metal Works (demo) and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import add_days, cstr, date_diff, getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	data = get_data(filters)
	if not data:
		return columns, [], None, None, []

	on_time = sum(row.on_time for row in data)
	days_late = [row.days_late for row in data if not row.on_time]
	summary = [
		{"label": _("Completed Work Orders"), "value": len(data), "datatype": "Int", "indicator": "Blue"},
		{
			"label": _("On-Time Rate"),
			"value": round(on_time * 100 / len(data), 1),
			"datatype": "Percent",
			"indicator": "Green" if on_time == len(data) else "Orange",
		},
		{
			"label": _("Avg Days Late"),
			"value": round(sum(days_late) / len(days_late), 1) if days_late else 0.0,
			"datatype": "Float",
			"indicator": "Red" if days_late else "Green",
		},
	]
	chart = {
		"data": {
			"labels": [_("On Time"), _("Late")],
			"datasets": [{"name": _("Work Orders"), "values": [on_time, len(days_late)]}],
		},
		"type": "donut",
		"colors": ["#29CD42", "#E24C4C"],
	}
	return columns, data, None, chart, summary


def get_data(filters):
	wo = frappe.qb.DocType("Work Order")
	rows = (
		frappe.qb.from_(wo)
		.select(
			wo.name.as_("work_order"),
			wo.production_item,
			wo.item_name,
			wo.qty,
			wo.planned_end_date,
			wo.actual_end_date,
		)
		.where(
			(wo.docstatus == 1)
			& (wo.status == "Completed")
			& (wo.company == cstr(filters.company))
			& (wo.actual_end_date >= getdate(filters.from_date))
			& (wo.actual_end_date < add_days(getdate(filters.to_date), 1))
		)
		.orderby(wo.actual_end_date)
	).run(as_dict=True)

	for row in rows:
		# compared by calendar day: finishing later the same day still counts as on time
		row.days_late = max(date_diff(row.actual_end_date, row.planned_end_date), 0)
		row.on_time = int(row.days_late == 0)
	return rows


def get_columns():
	return [
		{"label": _("Work Order"), "fieldname": "work_order", "fieldtype": "Link", "options": "Work Order", "width": 170},
		{"label": _("Item"), "fieldname": "production_item", "fieldtype": "Link", "options": "Item", "width": 120},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 200},
		{"label": _("Qty"), "fieldname": "qty", "fieldtype": "Int", "width": 70},
		{"label": _("Planned End"), "fieldname": "planned_end_date", "fieldtype": "Datetime", "width": 160},
		{"label": _("Actual End"), "fieldname": "actual_end_date", "fieldtype": "Datetime", "width": 160},
		{"label": _("Days Late"), "fieldname": "days_late", "fieldtype": "Int", "width": 90},
		{"label": _("On Time"), "fieldname": "on_time", "fieldtype": "Check", "width": 80},
	]
