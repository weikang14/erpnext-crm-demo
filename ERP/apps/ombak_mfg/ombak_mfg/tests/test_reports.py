import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_to_date, get_datetime, getdate, now_datetime

from ombak_mfg.ombak_mfg.report.defect_pareto import defect_pareto
from ombak_mfg.ombak_mfg.report.operation_time_variance import operation_time_variance
from ombak_mfg.ombak_mfg.report.work_order_on_time_rate import work_order_on_time_rate
from ombak_mfg.ombak_mfg.report.workstation_load import workstation_load
from ombak_mfg.setup.masters import COMPANY
from ombak_mfg.tests.factory import complete_job_card, complete_work_order, job_cards, make_work_order
from ombak_mfg.tests.test_defect_log import MFG_ROLES, defect_log, make_reason

REPORTS = {
	"Work Order On-Time Rate": work_order_on_time_rate,
	"Workstation Load": workstation_load,
	"Operation Time Variance": operation_time_variance,
	"Defect Pareto": defect_pareto,
}


def run(module, **filters):
	"""Call a report's execute() and name the parts of its return value."""
	columns, data, _message, chart, summary = module.execute(frappe._dict(company=COMPANY, **filters))
	return frappe._dict(columns=columns, data=data, chart=chart, summary=summary)


def monday(weeks_ago):
	today = getdate(now_datetime())
	return add_days(today, -today.weekday() - 7 * weeks_ago)


class TestOnTimeRate(IntegrationTestCase):
	def test_rows_and_summary(self):  # RPT-OT-1
		finished = {}
		for i, offset_days in enumerate((-1, 0, 3)):
			wo = make_work_order("FG-WB-150", qty=5, start=add_to_date(now_datetime(), days=-40 + 7 * i))
			finished[wo.name] = offset_days
			complete_work_order(wo, add_to_date(get_datetime(wo.planned_end_date), days=offset_days))

		r = run(
			work_order_on_time_rate, from_date=add_days(now_datetime(), -60), to_date=getdate(now_datetime())
		)
		rows = {row["work_order"]: row for row in r.data if row["work_order"] in finished}
		self.assertEqual(len(rows), 3)
		for name, offset in finished.items():
			self.assertEqual(rows[name]["on_time"], int(offset <= 0), name)
			self.assertEqual(rows[name]["days_late"], max(offset, 0), name)

		summary = {s["label"]: s["value"] for s in r.summary}
		self.assertEqual(summary["On-Time Rate"], 66.7)
		self.assertEqual(summary["Avg Days Late"], 3.0)
		self.assertEqual(r.chart["data"]["datasets"][0]["values"], [2, 1])

	def test_empty_range(self):  # RPT-OT-2
		r = run(work_order_on_time_rate, from_date="2001-01-01", to_date="2001-01-31")
		self.assertEqual(r.data, [])
		self.assertTrue(r.columns)
		self.assertIsNone(r.chart)


def set_schedule(job_card, chunks):
	"""Replace ERPNext's capacity plan for a job card with fixed (start, minutes) chunks."""
	frappe.db.delete("Job Card Scheduled Time", {"parent": job_card})
	for idx, (start, minutes) in enumerate(chunks, 1):
		frappe.get_doc(
			{
				"doctype": "Job Card Scheduled Time",
				"parent": job_card,
				"parenttype": "Job Card",
				"parentfield": "scheduled_time_logs",
				"idx": idx,
				"from_time": start,
				"to_time": add_to_date(start, minutes=minutes),
				"time_in_mins": minutes,
			}
		).db_insert()


def at(day, time="08:00:00"):
	return get_datetime(f"{day} {time}")


class TestWorkstationLoad(IntegrationTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def schedule_week(self, week):
		"""Welding Bay: 6 x 480 min Mon-Sat plus 120 min next Monday; Laser: 720 min on Tuesday."""
		wo = make_work_order("FG-EBF-1000", qty=24, start=at(week))
		cards = {jc.workstation: jc.name for jc in job_cards(wo.name)}
		for name in cards.values():
			set_schedule(name, [])
		set_schedule(
			cards["Welding Bay"], [(at(add_days(week, d)), 480) for d in range(6)] + [(at(add_days(week, 7)), 120)]
		)
		set_schedule(cards["Laser Cutting"], [(at(add_days(week, 1)), 720)])

	def test_load_percentages(self):  # RPT-WL-1, RPT-WL-3
		week = monday(weeks_ago=10)
		self.schedule_week(week)
		r = run(workstation_load, week_start=add_days(week, 3))  # any day picks its week
		rows = {row["workstation"]: row for row in r.data}
		self.assertEqual(rows["Welding Bay"]["available_mins"], 2880)
		self.assertEqual(rows["Welding Bay"]["planned_mins"], 2880)
		self.assertEqual(rows["Welding Bay"]["load_pct"], 100.0)
		self.assertEqual(rows["Welding Bay"]["bottleneck"], 1)
		self.assertEqual(rows["Laser Cutting"]["load_pct"], 25.0)
		self.assertEqual(rows["Laser Cutting"]["bottleneck"], 0)
		self.assertEqual(rows["CNC Press Brake"]["load_pct"], 0.0)
		self.assertEqual(r.chart["type"], "bar")
		self.assertEqual(r.chart["data"]["labels"], [row["workstation"] for row in r.data])

	def test_cancelled_and_next_week_excluded(self):  # RPT-WL-2
		week = monday(weeks_ago=12)
		self.schedule_week(week)
		wo = make_work_order("FG-EBF-1000", qty=10, start=at(week))
		welding = next(jc.name for jc in job_cards(wo.name) if jc.workstation == "Welding Bay")
		set_schedule(welding, [(at(week), 600)])
		frappe.db.set_value("Job Card", welding, "docstatus", 2)
		rows = {row["workstation"]: row for row in run(workstation_load, week_start=week).data}
		self.assertEqual(rows["Welding Bay"]["planned_mins"], 2880)


class TestOperationTimeVariance(IntegrationTestCase):
	def test_variance(self):  # RPT-TV-1
		# Wall bracket: laser 2 min per unit -> 30 units = 60 min standard
		wo = make_work_order("FG-WB-150", qty=30)
		jc = complete_job_card(job_cards(wo.name)[0], minutes=75)
		r = run(
			operation_time_variance, from_date=add_days(now_datetime(), -400), to_date=getdate(now_datetime())
		)
		row = next(row for row in r.data if row["job_card"] == jc.name)
		self.assertEqual(row["standard_mins"], 60)
		self.assertEqual(row["actual_mins"], 75)
		self.assertEqual(row["variance_mins"], 15)
		self.assertEqual(row["variance_pct"], 25.0)

	def test_zero_standard(self):  # RPT-TV-2
		self.assertEqual(operation_time_variance.variance(0, 30), (30, None))
		self.assertEqual(operation_time_variance.variance(60, 45), (-15, -25.0))


class TestDefectPareto(IntegrationTestCase):
	def setUp(self):
		wo = make_work_order("FG-WB-150", qty=20)
		self.jc = complete_job_card(job_cards(wo.name)[0], minutes=40)
		for code, qty in (("TEST-A", 6), ("TEST-B", 3), ("TEST-C", 1)):
			defect_log(self.jc.name, qty, reason=make_reason(code), submit=True)

	def tearDown(self):
		frappe.db.rollback()  # each test starts from exactly one set of logs

	def report(self, **filters):
		r = run(defect_pareto, from_date=add_days(now_datetime(), -1), to_date=getdate(now_datetime()), **filters)
		r.data = [row for row in r.data if row["defect_reason"].startswith("TEST-")]
		return r

	def test_pareto(self):  # RPT-DP-1
		r = self.report()
		self.assertEqual([row["defect_reason"] for row in r.data], ["TEST-A", "TEST-B", "TEST-C"])
		self.assertEqual([row["pct"] for row in r.data], [60.0, 30.0, 10.0])
		self.assertEqual([row["cumulative_pct"] for row in r.data], [60.0, 90.0, 100.0])
		self.assertEqual(r.chart["data"]["labels"][:3], ["TEST-A", "TEST-B", "TEST-C"])

	def test_cancelled_excluded(self):  # RPT-DP-2
		frappe.get_doc("Defect Log", {"job_card": self.jc.name, "defect_reason": "TEST-C"}).cancel()
		defect_log(self.jc.name, 5, reason="TEST-C", submit=True).cancel()
		self.assertEqual([row["defect_reason"] for row in self.report().data], ["TEST-A", "TEST-B"])

	def test_empty_range(self):  # RPT-DP-3
		r = run(defect_pareto, from_date="2001-01-01", to_date="2001-01-31")
		self.assertEqual(r.data, [])
		self.assertIsNone(r.chart)

	def test_filter_is_not_injectable(self):  # RPT-SEC-1
		_columns, data, *_ = defect_pareto.execute(
			frappe._dict(company="x' OR '1'='1", from_date="2001-01-01", to_date="2099-12-31")
		)
		self.assertEqual(data, [])


class TestMalformedFilters(IntegrationTestCase):
	def test_reports_survive_bad_filters(self):  # RPT-SEC-2
		bad = frappe._dict(
			company={"a": "b"}, workstation=["x"], from_date="2001-01-01", to_date="2001-01-31", week_start="0000-00-00"
		)
		for name, module in REPORTS.items():
			_columns, data, *_ = module.execute(frappe._dict(bad))
			if name != "Workstation Load":  # always lists every workstation
				self.assertEqual(data, [], name)


class TestReportRoles(IntegrationTestCase):
	def test_roles_limited(self):  # PERM-1 (reports)
		for name in REPORTS:
			roles = {r.role for r in frappe.get_doc("Report", name).roles}
			self.assertTrue(roles, name)
			self.assertLessEqual(roles, MFG_ROLES, name)
