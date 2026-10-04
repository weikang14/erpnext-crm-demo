# Copyright (c) 2026, Ombak Metal Works (demo) and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class DefectLog(Document):
	def validate(self):
		if flt(self.qty) <= 0:
			frappe.throw(_("Defective Qty must be greater than zero."))

		job_card = frappe.db.get_value(
			"Job Card", self.job_card, ["docstatus", "total_completed_qty"], as_dict=True
		)
		if not job_card or job_card.docstatus != 1:
			frappe.throw(_("Job Card {0} must be submitted before logging defects.").format(self.job_card))

		self.validate_within_completed_qty(job_card.total_completed_qty)

	def validate_within_completed_qty(self, completed_qty):
		DefectLog = frappe.qb.DocType("Defect Log")
		already_logged = (
			frappe.qb.from_(DefectLog)
			.select(frappe.query_builder.functions.Sum(DefectLog.qty))
			.where(
				(DefectLog.job_card == self.job_card)
				& (DefectLog.docstatus == 1)
				& (DefectLog.name != (self.name or ""))
			)
		).run()[0][0] or 0

		remaining = flt(completed_qty) - flt(already_logged)
		if flt(self.qty) > remaining:
			frappe.throw(
				_(
					"Only {0} more defective units can be logged against Job Card {1} "
					"(completed {2}, already logged {3})."
				).format(f"{remaining:g}", self.job_card, f"{flt(completed_qty):g}", f"{flt(already_logged):g}")
			)
