// Copyright (c) 2026, Ombak Metal Works (demo) and contributors
// For license information, please see license.txt

frappe.query_reports["Workstation Load"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "week_start",
			label: __("Week (any day in it)"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "load_pct" && data && data.bottleneck) {
			value = `<span class="text-danger">${value}</span>`;
		}
		return value;
	},
};
