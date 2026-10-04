# Sprint Contract: Ombak Metal Works ERP (factory)

**ID:** 001
**Created:** 2026-10-04
**Status:** validated (shipped locally 2026-10-04)

---

## Goal

A reproducible ERPNext v16 demo of a make-to-order metal fabrication factory, plus a
custom Frappe app (`ombak_mfg`) that adds defect tracking, four production reports and
an overdue-work-order alert. It must run from `docker compose` on a clean machine and
show the full order-to-delivery flow with a month of realistic data. See `design.md`.

## Acceptance Criteria

**Infrastructure**

1. When `docker compose build && docker compose up -d` is run in `ERP/`, then within
   10 minutes http://localhost:8080 shows the ERPNext login and
   `bench --site localhost list-apps` lists `frappe`, `erpnext`, `ombak_mfg`.
2. When `bench --site localhost execute ombak_mfg.setup.demo.run` runs on a fresh site,
   then it creates company "Ombak Metal Works Sdn Bhd" (MYR), warehouses Raw Material /
   Work In Progress / Finished Goods / Rejected, 4 workstations with hour rates, >= 10
   raw-material items, 5 finished items each with a submitted default BOM that has
   operations; and running it a second time creates no duplicate records and exits 0.
3. When the same command finishes, then the demo month contains: >= 12 submitted sales
   orders across >= 4 customers; a work order per sales order line; job cards with time
   logs; >= 5 work orders completed on time and >= 3 completed late; >= 2 submitted work
   orders still open past their planned end date; every work order created from a
   Production Plan whose MRP raises the material requests (>= 2), and >= 1 purchase cycle
   (material request -> purchase order -> purchase receipt with incoming quality
   inspection); >= 1 rejected in-process inspection explaining a late order; outgoing
   quality inspections on finished goods; delivery notes; >= 2 delivery trips; sales
   invoices for delivered orders; >= 15 submitted defect logs across >= 4 reasons.

**Defect Log**

4. When a Defect Log is given a submitted Job Card, then work order, operation,
   workstation and production item are filled from that job card and are read-only.
5. When qty <= 0, then save fails with a validation error.
6. When the qty of submitted Defect Logs for a job card plus this log's qty exceeds the
   job card's completed quantity, then save fails and the message states the remaining
   allowed qty.
7. When the linked job card is draft or cancelled, then save fails.
8. When a Defect Log is cancelled, then it no longer counts toward the cap in AC6 or in
   any report.

**Reports**

9. Work Order On-Time Rate: given 3 completed work orders in range (2 finished on or
   before planned end date, 1 finished 3 days late), then it returns 3 rows with the
   correct on-time flag and days late, and the summary shows on-time 66.7% and average
   days late 3.0 (averaged over late orders only).
10. Workstation Load: for the selected week, scheduled minutes per workstation = the
    job card schedule (ERPNext capacity plan, `Job Card Scheduled Time`) falling in that
    week, excluding cancelled job cards and stopped/closed work orders; available = working
    hours x 6 days. Given 2,880 scheduled minutes on one workstation (8 h x 6 days), that
    row shows 100% and is flagged as a bottleneck (>= 90%); a workstation with 720 minutes
    shows 25% and is not flagged; minutes scheduled in the next week are not counted.
    *(Amended 2026-10-04: originally "operation planned start" and "> 100% flagged". With
    capacity planning on, ERPNext never schedules a workstation past 100%; extra work is
    pushed into later weeks, so the useful signal is a near-full bottleneck.)*
11. Operation Time Variance: given a completed job card with standard 60 min and actual
    75 min, then the row shows variance +15 min and +25.0%.
12. Defect Pareto: given submitted logs of 6, 3 and 1 units on three reasons, then rows
    are ordered 6, 3, 1 with 60.0 / 30.0 / 10.0 % and cumulative 60.0 / 90.0 / 100.0 %,
    and chart data is returned.
13. When any of the four reports is opened in the browser for a range with no data, then
    it shows an empty result without a server error; with the demo data it renders rows
    and a chart where defined.

**Overdue alert**

14. When the daily job runs and overdue work orders exist, then each enabled user with
    role Manufacturing Manager gets exactly one Notification Log that day stating the
    count and linking to the work order list; a second run the same day adds nothing; with
    no overdue work orders nothing is created; draft, Completed, Stopped, Closed and
    Cancelled work orders never count.
15. The job is registered under `scheduler_events["daily"]` in `hooks.py`.

**Workspace**

16. Workspace "Ombak Factory" shows shortcuts to the four reports, Defect Log, Work Order
    and Job Card, plus number cards Unfinished Work Orders (named so because ERPNext
    already ships an "Open Work Orders" card), Overdue Work Orders and Defects This Month.

**Tests**

17. `bench --site test.localhost run-tests --app ombak_mfg` exits 0 and covers AC4-AC12
    and AC14.

## Failure Modes

1. Setup script run twice duplicates masters or crashes on "already exists".
2. Demo transactions fail with negative-stock errors because receipts are posted after
   consumption, or posting dates are out of order.
3. A report crashes on empty data (division by zero in % columns).
4. The defect cap counts cancelled logs, or counts the document being edited twice.
5. The alert duplicates notifications, or includes draft / completed / stopped / closed /
   cancelled work orders.
6. Tests run against the demo site and pollute its data.
7. Customisation made in the UI but not exported to the app, so it is lost on a fresh
   install.
8. Report SQL built by string-formatting user filters (injection); all filters must be
   bound parameters.
9. Reports or Defect Log readable by every role; they must be limited to manufacturing
   and system manager roles.
10. Secrets committed: the only credentials in the repo are the documented local-demo
    defaults (`admin`/`admin` and the demo users' password `Ombak@2026`), never real keys;
    the demo port is bound to 127.0.0.1 only.

## Scope

**IN scope:** Docker setup, `ombak_mfg` app (2 doctypes, 4 reports, scheduler job,
workspace), demo-data script, tests, bilingual README at ship time.

**OUT of scope:** CRM and integration (contracts 002/003), email, HR/payroll, accounting
beyond ERPNext defaults, multi-currency, custom front-end outside ERPNext Desk,
production deployment/HTTPS, video recording (the owner records it).

## Design Spec

No custom UI is built. Everything renders in ERPNext Desk, so the design-system,
Lighthouse and 5-state UI rules do not apply; Desk supplies loading/empty/error states.
Reports use Frappe's built-in chart types (bar; bar + line for Pareto).

## Market Research Reference

Skipped: this is an addition to an existing platform (ERPNext) whose UI is the
platform's own; the domain scope was agreed with the owner in conversation. Marker:
`.specship/artifacts/market-research-skipped.txt`.

## Non-Functional Requirements

- **Performance:** each report returns in < 2 s on the demo data; setup script < 10 min.
- **Security:** parameterised SQL only; role-restricted doctypes and reports; demo
  credentials documented as local-only.
- **Testing:** Frappe integration tests on a separate test site (AC17).
- **Deployment:** local Docker only.

## Risks & Unknowns

- ERPNext v16 API details (job card completion, test base classes) must be checked in
  the image, not assumed from v15.
- Host drive C: has ~9 GB free and Docker's disk lives there; watch it during pulls.
- Bind mounts from a OneDrive folder can be slow; acceptable for a small app.

## Execution Config

```yaml
autonomy: guided   # owner said "build it directly": plan gate waived
```

## Pre-Generated Test Cases

See: `.specship/specs/001-erp-factory/artifacts/test-cases.md`

## Validation Results

| Validator | Result | Details |
|-----------|--------|---------|
| Code Review | pending | |
| Security | pending | |
| Browser | pending | |
| Alignment | pending | |

**Aggregate Verdict:** pending
