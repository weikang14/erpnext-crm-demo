// Copyright (c) 2026, Ombak Metal Works (demo) and contributors
// For license information, please see license.txt

frappe.ui.form.on("Defect Log", {
	setup(frm) {
		// only submitted job cards have a completed quantity to log against
		frm.set_query("job_card", () => ({ filters: { docstatus: 1 } }));
		frm.set_query("defect_reason", () => ({ filters: { disabled: 0 } }));
	},
});
