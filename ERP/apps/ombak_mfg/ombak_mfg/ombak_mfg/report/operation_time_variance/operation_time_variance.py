# Copyright (c) 2026, Ombak Metal Works (demo) and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import add_days, cstr, flt, getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	data = get_data(filters)
	if not data:
		return columns, [], None, None, []

	standard = sum(row.standard_mins for row in data)
	actual = sum(row.actual_mins for row in data)
	summary = [
		{"label": _("Standard Hours"), "value": round(standard / 60, 1), "datatype": "Float"},
		{"label": _("Actual Hours"), "value": round(actual / 60, 1), "datatype": "Float"},
		{
			"label": _("Efficiency"),
			"value": round(standard * 100 / actual, 1) if actual else 0.0,
			"datatype": "Percent",
			"indicator": "Green" if actual <= standard else "Orange",
		},
	]
	return columns, data, None, None, summary


def variance(standard, actual):
	"""(variance in minutes, variance as % of standard, or None when there is no standard)."""
	diff = flt(actual) - flt(standard)
	return diff, (round(diff * 100 / flt(standard), 1) if flt(standard) else None)


def get_data(filters):
	jc = frappe.qb.DocType("Job Card")
	op = frappe.qb.DocType("Work Order Operation")
	rows = (
		frappe.qb.from_(jc)
		.join(op)
		.on(jc.operation_id == op.name)
		.select(
			jc.name.as_("job_card"),
			jc.work_order,
			jc.operation,
			jc.workstation,
			jc.production_item,
			jc.for_quantity.as_("qty"),
			op.time_in_mins.as_("standard_mins"),
			jc.total_time_in_mins.as_("actual_mins"),
			jc.actual_end_date,
		)
		.where(
			(jc.docstatus == 1)
			& (jc.status == "Completed")
			& (jc.company == cstr(filters.company))
			& (jc.actual_end_date >= getdate(filters.from_date))
			& (jc.actual_end_date < add_days(getdate(filters.to_date), 1))
		)
		.orderby(jc.actual_end_date)
	).run(as_dict=True)

	for row in rows:
		row.variance_mins, row.variance_pct = variance(row.standard_mins, row.actual_mins)
	return rows


def get_columns():
	return [
		{"label": _("Job Card"), "fieldname": "job_card", "fieldtype": "Link", "options": "Job Card", "width": 140},
		{"label": _("Work Order"), "fieldname": "work_order", "fieldtype": "Link", "options": "Work Order", "width": 170},
		{"label": _("Operation"), "fieldname": "operation", "fieldtype": "Link", "options": "Operation", "width": 160},
		{"label": _("Workstation"), "fieldname": "workstation", "fieldtype": "Link", "options": "Workstation", "width": 140},
		{"label": _("Item"), "fieldname": "production_item", "fieldtype": "Link", "options": "Item", "width": 120},
		{"label": _("Qty"), "fieldname": "qty", "fieldtype": "Int", "width": 70},
		{"label": _("Standard (min)"), "fieldname": "standard_mins", "fieldtype": "Int", "width": 120},
		{"label": _("Actual (min)"), "fieldname": "actual_mins", "fieldtype": "Int", "width": 110},
		{"label": _("Variance (min)"), "fieldname": "variance_mins", "fieldtype": "Int", "width": 120},
		{"label": _("Variance %"), "fieldname": "variance_pct", "fieldtype": "Percent", "width": 100},
		{"label": _("Finished"), "fieldname": "actual_end_date", "fieldtype": "Datetime", "width": 160},
	]
