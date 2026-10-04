# Plan: 001-erp-factory

Test command (inside backend container):
`bench --site test.localhost run-tests --app ombak_mfg`
Every task: write the test from `artifacts/test-cases.md` -> run, see RED -> implement ->
GREEN -> commit `[specship] <task>`.

## Milestone 0: Scaffold + verify it runs

### Task 0.1: Dockerfile + docker-compose.yml
`ERP/Dockerfile` FROM frappe/erpnext:v16.37.0, copies `apps/ombak_mfg`, `pip install -e`.
`ERP/docker-compose.yml` from frappe_docker `pwd.yml`: custom image, `./apps/ombak_mfg`
bind-mounted into every bench service, `create-site` also installs `ombak_mfg`.
Verify: INF-1, INF-2.

### Task 0.2: Scaffold app with `bench new-app ombak_mfg` (throwaway container), module
"Ombak Manufacturing". Verify: app imports, `list-apps` shows it.

### Task 0.3: Test site `test.localhost` (allow_tests, erpnext + ombak_mfg, setup
wizard completed by the test bootstrap). First smoke test passes (INF-3).

## Milestone 1: Master data (setup script, part 1)

### Task 1.1: `ombak_mfg/setup/masters.py::setup_masters()` -- setup wizard (company
Ombak Metal Works Sdn Bhd, MYR, Malaysia, FY), warehouses, workstations (hour rates,
working hours 08:00-17:00), operations, UOMs, item groups, 10 raw + 5 finished items,
BOMs with operations (submitted, default), customers, suppliers, QI templates, driver,
vehicle, Manufacturing Manager demo user. Idempotent.
Tests: DEMO-1, DEMO-2 on test site.

### Task 1.2: Test helpers `ombak_mfg/tests/factory.py`: `make_work_order`,
`make_job_card(completed_qty, actual_mins, ...)`, `complete_work_order(actual_end)`.

## Milestone 2: Defect tracking

### Task 2.1: DocType Defect Reason (name = reason code, category, description; roles).
### Task 2.2: DocType Defect Log (submittable; job_card + fetched fields; validations).
Tests: DL-1..DL-6, PERM-1 (doctype part).

## Milestone 3: Reports

### Task 3.1: Work Order On-Time Rate -- RPT-OT-1, RPT-OT-2.
### Task 3.2: Workstation Load -- RPT-WL-1..3.
### Task 3.3: Operation Time Variance -- RPT-TV-1, RPT-TV-2.
### Task 3.4: Defect Pareto -- RPT-DP-1..3, RPT-SEC-1.
### Task 3.5: Report roles -- PERM-1 (report part).

## Milestone 4: Alert + workspace

### Task 4.1: `ombak_mfg/tasks.py::notify_overdue_work_orders` + hook -- ALR-1..3, HK-1.
### Task 4.2: Workspace "Ombak Factory" + 3 Number Cards (exported with the app).

## Milestone 5: Demo transactions (setup script, part 2)

### Task 5.1: `ombak_mfg/setup/demo.py::run()` = setup_masters() + transactions over the
30 days before today: purchase cycle with incoming QI, opening stock, sales orders,
work orders, job cards with time logs (on-time / late / open-overdue mix), defect logs,
manufacture entries, outgoing QI, delivery notes, delivery trips, sales invoices.
Guarded so a second run adds nothing. Tests: DEMO-3 (+ DEMO-2 again) on `frontend`.
### Task 5.2: Run on `localhost`, verify counts, open each report/workspace in browser.

## Milestone 6: Ship docs (ship phase only)

### Task 6.1 (SHIP phase, not counted in build tasks): Bilingual README (setup, demo login, flow diagram, screenshots).
