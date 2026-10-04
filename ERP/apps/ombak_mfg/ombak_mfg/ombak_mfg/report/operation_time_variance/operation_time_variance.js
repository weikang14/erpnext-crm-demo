// Copyright (c) 2026, Ombak Metal Works (demo) and contributors
// For license information, please see license.txt

frappe.query_reports["Operation Time Variance"] = {
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
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (["variance_mins", "variance_pct"].includes(column.fieldname) && data && data.variance_mins) {
			const cls = data.variance_mins > 0 ? "text-danger" : "text-success";
			value = `<span class="${cls}">${value}</span>`;
		}
		return value;
	},
};
