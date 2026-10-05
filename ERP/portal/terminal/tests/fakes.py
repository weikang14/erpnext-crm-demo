"""An in-memory stand-in for terminal.erpnext.ERPNext."""

from terminal.erpnext import check_job_card

STATIONS = ["CNC Press Brake", "Laser Cutting", "Powder Coating", "Welding Bay"]


def card(name, seq, work_order="MFG-WO-2026-00013", operation="Welding", status="Open", paused=0, **extra):
    return {
        "name": name, "status": status, "is_paused": paused, "work_order": work_order, "operation": operation,
        "production_item": "FG-EBF-1000", "item_name": "Equipment Base Frame 1000x800", "for_quantity": 6.0,
        "total_completed_qty": 0.0, "expected_start_date": "2026-10-05 08:00:00",
        "expected_end_date": "2026-10-05 14:00:00", "sequence_id": seq, **extra,
    }  # fmt: skip


class FakeERPNext:
    def __init__(self):
        self.rows = {}  # workstation -> queue rows
        self.sibling_rows = []
        self.docs = {}  # job card name -> full doc
        self.calls = []
        self.fail = {}  # method name -> exception to raise

    def _maybe_fail(self, method):
        if method in self.fail:
            raise self.fail[method]

    def workstations(self):
        self._maybe_fail("workstations")
        return list(STATIONS)

    def employees(self):
        return [
            {"name": "HR-EMP-00001", "employee_name": "Ahmad Faizal"},
            {"name": "HR-EMP-00002", "employee_name": "Mei Ling Tan"},
            {"name": "HR-EMP-00003", "employee_name": "Rajesh Kumar"},
        ]  # Nurul Aina deliberately missing

    def defect_reasons(self):
        return [{"name": "BURR", "category": "Cutting"}, {"name": "WELD-POR", "category": "Welding"}]

    def queue(self, workstation):
        self._maybe_fail("queue")
        self.calls.append(("queue", workstation))
        return list(self.rows.get(workstation, []))

    def siblings(self, work_orders):
        return [s for s in self.sibling_rows if s["work_order"] in work_orders]

    def job_card(self, name):
        return self.docs[check_job_card(name)]

    def start(self, name, employee, at):
        self.calls.append(("start", check_job_card(name), employee, at))
        self._maybe_fail("start")

    def pause(self, name, at):
        self.calls.append(("pause", check_job_card(name), at))
        self._maybe_fail("pause")

    def resume(self, name, at):
        self.calls.append(("resume", check_job_card(name), at))
        self._maybe_fail("resume")

    def complete(self, name, qty, at):
        self.calls.append(("complete", check_job_card(name), qty, at))
        self._maybe_fail("complete")

    def log_defect(self, job_card, reason, qty):
        self.calls.append(("defect", check_job_card(job_card), reason, qty))
        self._maybe_fail("log_defect")
        return "DL-2026-00099"
