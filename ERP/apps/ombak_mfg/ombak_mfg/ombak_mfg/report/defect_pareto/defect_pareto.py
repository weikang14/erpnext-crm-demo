# Copyright (c) 2026, Ombak Metal Works (demo) and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder import Order
from frappe.query_builder.functions import Sum
from frappe.utils import cstr, flt, getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	data = get_data(filters)
	if not data:
		return columns, [], None, None, []

	total = sum(row.qty for row in data)
	running = 0
	for row in data:
		running += row.qty
		row.pct = round(row.qty * 100 / total, 1)
		row.cumulative_pct = round(running * 100 / total, 1)

	chart = {
		"data": {
			"labels": [row.defect_reason for row in data],
			"datasets": [
				# bars as % of total so they share the 0-100 axis with the cumulative line
				{"name": _("% of Total"), "values": [row.pct for row in data], "chartType": "bar"},
				{"name": _("Cumulative %"), "values": [row.cumulative_pct for row in data], "chartType": "line"},
			],
		},
		"type": "axis-mixed",
		"colors": ["#E24C4C", "#5E64FF"],
	}
	top = data[0]
	summary = [
		{"label": _("Defective Units"), "value": flt(total), "datatype": "Float", "indicator": "Red"},
		{"label": _("Top Reason"), "value": f"{top.defect_reason} ({top.pct}%)", "datatype": "Data"},
	]
	return columns, data, None, chart, summary


def get_data(filters):
	log = frappe.qb.DocType("Defect Log")
	reason = frappe.qb.DocType("Defect Reason")
	query = (
		frappe.qb.from_(log)
		.left_join(reason)
		.on(log.defect_reason == reason.name)
		.select(log.defect_reason, reason.category, Sum(log.qty).as_("qty"))
		.where(
			(log.docstatus == 1)
			& (log.company == cstr(filters.company))
			& (log.posting_date >= getdate(filters.from_date))
			& (log.posting_date <= getdate(filters.to_date))
		)
		.groupby(log.defect_reason, reason.category)
		.orderby(Sum(log.qty), order=Order.desc)
		.orderby(log.defect_reason)
	)
	if filters.workstation:
		query = query.where(log.workstation == cstr(filters.workstation))
	return query.run(as_dict=True)


def get_columns():
	return [
		{"label": _("Defect Reason"), "fieldname": "defect_reason", "fieldtype": "Link", "options": "Defect Reason", "width": 160},
		{"label": _("Category"), "fieldname": "category", "fieldtype": "Data", "width": 120},
		{"label": _("Defective Qty"), "fieldname": "qty", "fieldtype": "Int", "width": 120},
		{"label": _("% of Total"), "fieldname": "pct", "fieldtype": "Percent", "width": 110},
		{"label": _("Cumulative %"), "fieldname": "cumulative_pct", "fieldtype": "Percent", "width": 120},
	]
