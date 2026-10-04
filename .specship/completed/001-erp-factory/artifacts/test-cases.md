# Test Cases: 001-erp-factory

Written before implementation. Automated cases run with
`bench --site test.localhost run-tests --app ombak_mfg`; each builds its own fixtures
(company, items, workstations, work orders, job cards) and rolls back.

## Unit / integration (automated)

| ID | AC | Given | Expect | Red signal |
|---|---|---|---|---|
| DL-1 | 4 | submitted job card JC for WO, op "Welding", ws "Welding Bay" | new Defect Log with job_card=JC has work_order, operation, workstation, production_item equal to JC's | any field empty or different |
| DL-2 | 5 | qty = 0, then qty = -2 | `frappe.ValidationError` both times | insert succeeds |
| DL-3 | 6 | JC completed qty 10; submitted log qty 7 | new log qty 4 raises ValidationError mentioning "3"; qty 3 succeeds | 4 accepted, or 3 rejected |
| DL-4 | 6 / FM4 | submitted log qty 7 on JC (completed 10); a draft log qty 3 is saved twice | second save succeeds (own qty not double counted) | ValidationError on re-save |
| DL-5 | 7 | draft job card; cancelled job card | ValidationError for both | insert succeeds |
| DL-6 | 8 | JC completed 10; log qty 8 submitted then cancelled | new log qty 10 succeeds | ValidationError |
| RPT-OT-1 | 9 | 3 completed WOs: actual end = planned-1d, = planned, = planned+3d | 3 rows; on_time flags [1,1,0]; days_late [0,0,3]; report summary on-time 66.7, avg days late 3.0 | wrong counts/flags/summary |
| RPT-OT-2 | 13 / FM3 | range with no completed WOs | columns returned, data == [], no exception, summary shows 0 / blank | ZeroDivisionError |
| RPT-WL-1 | 10 | Welding Bay job card scheduled 6 x 480 min Mon-Sat of week W; Laser job card 720 min in W; 8h days | Welding available 2880, scheduled 2880, load 100.0, bottleneck 1; Laser 25.0, bottleneck 0; CNC Press Brake 0.0 | other values |
| RPT-WL-2 | 10 | as WL-1 plus 120 min on Welding Bay next Monday; a cancelled job card with 600 min in W | Welding still 2880 | 3000 or 3480 |
| RPT-WL-3 | 10 | report run | chart type bar, one label per workstation | missing chart |
| RPT-TV-1 | 11 | completed JC: WO operation time_in_mins 60, JC total_time_in_mins 75 | variance_mins 15, variance_pct 25.0 | other values |
| RPT-TV-2 | 13 / FM3 | completed JC with standard 0 min | variance_pct is None/0, no exception | ZeroDivisionError |
| RPT-DP-1 | 12 | submitted logs: reason A 6, B 3, C 1 | order A,B,C; pct 60/30/10; cum 60/90/100; chart has labels [A,B,C] | wrong order or numbers |
| RPT-DP-2 | 8 / 12 | as DP-1 plus a cancelled log reason C qty 5 | C still 1 | C = 6 |
| RPT-DP-3 | 13 | empty range | data == [], chart None, no exception | exception |
| RPT-SEC-1 | FM8 | filter value `x' OR '1'='1` for company | no extra rows, no SQL error | rows leak or SQL error |
| ALR-1 | 14 | 2 overdue submitted WOs; 1 completed WO past date; 1 draft WO past date; 2 users with Manufacturing Manager (1 disabled) | exactly 1 Notification Log for the enabled manager, text contains "2" | count != 1 or text has 4 |
| ALR-2 | 14 | run job twice same day | still 1 log for that user | 2 logs |
| ALR-3 | 14 | no overdue WOs | 0 logs | any log |
| HK-1 | 15 | import hooks | `"ombak_mfg.tasks.notify_overdue_work_orders"` in `scheduler_events["daily"]` | missing |
| PERM-1 | FM9 | Defect Log and the 4 reports | roles limited to Manufacturing Manager / Manufacturing User / System Manager | other roles present |

## Setup / demo data (scripted smoke check, run on `frontend`)

| ID | AC | Check | Expect |
|---|---|---|---|
| DEMO-1 | 2 | after `demo.run`: company, 4 warehouses, 4 workstations, >= 10 raw items, 5 finished items with default submitted BOM having operations | all true |
| DEMO-2 | 2 / FM1 | run `demo.run` a second time; compare doctype counts before/after | exit 0, counts unchanged |
| DEMO-3 | 3 | counts: SO >= 12 (>= 4 customers), on-time WOs >= 5, late WOs >= 3, open overdue WOs >= 2, PR with QI >= 1, outgoing QI >= 1, DN >= 1, Delivery Trip >= 2, SI >= 1, Defect Log submitted >= 15 across >= 4 reasons | all true |

## Browser flows (validator, on http://localhost:8080 as Administrator)

1. Defect Log: new -> pick a submitted job card -> fetched fields appear read-only ->
   qty larger than allowed -> error shown -> fix qty -> save -> submit -> cancel ->
   duplicate -> save copy -> delete copy -> original still listed.
2. Each of the 4 reports opens from the Ombak Factory workspace with the demo data and
   shows rows (+ chart for On-Time, Workstation Load, Pareto); a future empty range shows
   "Nothing to show" without an error toast.
3. Workspace shows the 3 number cards with non-error values.
4. Bell icon shows the overdue-work-order notification after the job is run.

## Infrastructure (manual/scripted)

| ID | AC | Check |
|---|---|---|
| INF-1 | 1 | `curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/api/method/ping` = 200 |
| INF-2 | 1 | `bench --site frontend list-apps` contains ombak_mfg |
| INF-3 | 17 | test run exits 0 |
