# Copyright (c) 2026, Ombak Metal Works (demo) and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder.functions import Sum
from frappe.utils import add_days, cstr, flt, getdate, nowdate

WORKING_DAYS = 6  # Monday to Saturday
DEFAULT_HOURS = 8  # used when a workstation has no working hours set
BOTTLENECK_PCT = 90


def execute(filters=None):
	filters = frappe._dict(filters or {})
	try:
		day = getdate(filters.week_start or nowdate()) or getdate()  # "0000-00-00" parses to None
	except frappe.ValidationError:
		day = getdate()
	week_start = add_days(day, -day.weekday())
	planned = get_planned_minutes(cstr(filters.company), week_start, add_days(week_start, 7))

	data = []
	for ws in frappe.get_all(
		"Workstation", filters={"disabled": 0}, fields=["name", "total_working_hours"], order_by="name"
	):
		available = (flt(ws.total_working_hours) or DEFAULT_HOURS) * 60 * WORKING_DAYS
		minutes = flt(planned.get(ws.name))
		load = round(minutes * 100 / available, 1)
		data.append(
			{
				"workstation": ws.name,
				"available_mins": available,
				"planned_mins": minutes,
				"load_pct": load,
				"bottleneck": int(load >= BOTTLENECK_PCT),
			}
		)

	chart = {
		"data": {
			"labels": [row["workstation"] for row in data],
			"datasets": [{"name": _("Load %"), "values": [row["load_pct"] for row in data]}],
			"yMarkers": [{"label": _("Capacity"), "value": 100}],
		},
		"type": "bar",
		"colors": ["#5E64FF"],
	}
	summary = [
		{
			"label": _("Week Starting"),
			"value": frappe.format(week_start, {"fieldtype": "Date"}),
			"datatype": "Data",
		},
		{
			"label": _("Bottlenecks (>= {0}%)").format(BOTTLENECK_PCT),
			"value": sum(row["bottleneck"] for row in data),
			"datatype": "Int",
			"indicator": "Red" if any(row["bottleneck"] for row in data) else "Green",
		},
	]
	return get_columns(), data, None, chart, summary


def get_planned_minutes(company, start, end):
	"""Minutes per workstation from ERPNext's capacity plan (job card schedule) in [start, end)."""
	wo = frappe.qb.DocType("Work Order")
	jc = frappe.qb.DocType("Job Card")
	slot = frappe.qb.DocType("Job Card Scheduled Time")
	rows = (
		frappe.qb.from_(slot)
		.join(jc)
		.on((slot.parent == jc.name) & (slot.parenttype == "Job Card"))
		.join(wo)
		.on(jc.work_order == wo.name)
		.select(jc.workstation, Sum(slot.time_in_mins))
		.where(
			(jc.docstatus < 2)
			& (wo.docstatus == 1)
			& (wo.status.notin(["Stopped", "Closed"]))
			& (jc.company == company)
			& (slot.from_time >= start)
			& (slot.from_time < end)
		)
		.groupby(jc.workstation)
	).run()
	return dict(rows)


def get_columns():
	return [
		{"label": _("Workstation"), "fieldname": "workstation", "fieldtype": "Link", "options": "Workstation", "width": 180},
		{"label": _("Available (min)"), "fieldname": "available_mins", "fieldtype": "Int", "width": 130},
		{"label": _("Scheduled (min)"), "fieldname": "planned_mins", "fieldtype": "Int", "width": 130},
		{"label": _("Load %"), "fieldname": "load_pct", "fieldtype": "Percent", "width": 100},
		{"label": _("Bottleneck"), "fieldname": "bottleneck", "fieldtype": "Check", "width": 100},
	]
