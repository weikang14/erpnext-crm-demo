import frappe
from frappe.tests import IntegrationTestCase

from ombak_mfg.tests.factory import completed_job_card, job_cards, make_work_order

MFG_ROLES = {"System Manager", "Manufacturing Manager", "Manufacturing User"}


def make_reason(code="TEST-BURR"):
	if not frappe.db.exists("Defect Reason", code):
		frappe.get_doc(
			{"doctype": "Defect Reason", "reason_code": code, "category": "Cutting", "description": "Burr"}
		).insert()
	return code


def defect_log(job_card, qty, reason=None, submit=False):
	doc = frappe.get_doc(
		{"doctype": "Defect Log", "job_card": job_card, "defect_reason": reason or make_reason(), "qty": qty}
	)
	doc.insert()
	if submit:
		doc.submit()
	return doc


class TestDefectLog(IntegrationTestCase):
	def test_fields_fetched_from_job_card(self):  # DL-1
		jc = completed_job_card(qty=10)
		log = defect_log(jc.name, 1)
		self.assertEqual(log.work_order, jc.work_order)
		self.assertEqual(log.operation, jc.operation)
		self.assertEqual(log.workstation, jc.workstation)
		self.assertEqual(log.production_item, jc.production_item)
		self.assertEqual(log.company, jc.company)
		meta = frappe.get_meta("Defect Log")
		for f in ("work_order", "operation", "workstation", "production_item", "company"):
			self.assertTrue(meta.get_field(f).read_only, f)

	def test_qty_must_be_positive(self):  # DL-2
		jc = completed_job_card(qty=10)
		for qty in (0, -2):
			with self.assertRaises(frappe.ValidationError):
				defect_log(jc.name, qty)

	def test_cap_at_completed_qty(self):  # DL-3
		jc = completed_job_card(qty=10)
		defect_log(jc.name, 7, submit=True)
		with self.assertRaises(frappe.ValidationError) as ctx:
			defect_log(jc.name, 4)
		self.assertIn("Only 3 more", str(ctx.exception))
		defect_log(jc.name, 3)

	def test_resave_does_not_double_count(self):  # DL-4
		jc = completed_job_card(qty=10)
		defect_log(jc.name, 7, submit=True)
		draft = defect_log(jc.name, 3)
		draft.remarks = "edited"
		draft.save()
		draft.submit()

	def test_job_card_must_be_submitted(self):  # DL-5
		wo = make_work_order(qty=5)
		draft_jc = job_cards(wo.name)[0]
		with self.assertRaises(frappe.ValidationError):
			defect_log(draft_jc.name, 1)

		jc = completed_job_card(qty=5)
		jc.cancel()
		with self.assertRaises(frappe.ValidationError):
			defect_log(jc.name, 1)

	def test_cancelled_log_frees_quantity(self):  # DL-6
		jc = completed_job_card(qty=10)
		log = defect_log(jc.name, 8, submit=True)
		log.cancel()
		defect_log(jc.name, 10, submit=True)

	def test_roles_limited(self):  # PERM-1 (doctypes)
		for dt in ("Defect Log", "Defect Reason"):
			roles = {p.role for p in frappe.get_meta(dt).permissions}
			self.assertTrue(roles, dt)
			self.assertLessEqual(roles, MFG_ROLES, dt)
