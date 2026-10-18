# Preserved Behaviors (004 must not regress)

## CRM
1. **The Won rule.** Won needs a sent quote. The quote becomes `accepted`; `deal.amount` = the quote total (the sum of half-up-rounded lines); `closed_at` = now; one `StageChange(→won)` is written. Refusals are "This deal is closed." and "Send a quote before marking the deal won."
   - Code: `CRM/sales/models.py:284-292`, `CRM/sales/rules.py:53-57`.
   - Tests: `WON-1` (`test_deals.py:94`), `WON-2` (`test_deals.py:102`, `test_rules.py:114`).
2. **Won is a one-click POST that always redirects to the deal with a flash.** The success text is `Won: {title}, MYR {amount:,.2f}.` (`CRM/sales/views/opportunities.py:146-155`).
3. **Won and Lost only through their own POSTs, never through Move** (`rules.py:47-48`, `MOVE-3` `test_deals.py:80`).
4. **A closed deal and its quotes are read-only, and closed deals can't be reopened.** The page shows "Won on {date}" and hides Move, Won, Edit, Reassign, Lost and New quote (`detail.html:10-27`, `models.py:297,307,320,442,448,484`; `CLOSED-1` `test_deals.py:125`, `test_rules.py:129`; `EDIT-4` `test_deals.py:218`).
5. **One deal row lock serialises Won, Lost, Send, Revise, Edit and Reassign.** A double Won gives "This deal is closed." and changes nothing (`models.py:266-267,460`).
6. **Won does not depend on anything outside the CRM DB.** Reports read `stage="won"`, `closed_at` and `amount`: win rate (`reports.py:37-57`), forecast "won in quarter" (`reports.py:61`) and "won this month" (`views/home.py:34-35`). If an ERP failure undid or delayed Won, all three would change.
7. **Won ignores leftover draft or pending quotes and `valid_until`.** Pending ones stay in the manager's approvals list (`views/quotes.py:129`).
8. **Access scoping.** A rep wins only their own deals, the manager any deal, and anything else answers 404 (`access.py:23-25,41-42`; AC19).
9. **Security.** CSRF and POST-only state changes; the sign-in lockout on all sign-in paths (`settings.py:76`); `GuardedUserAdmin`; CSP with no inline script or style and no `on*=` (`test_security.py:117-124`); the friendly 500 page with no traceback (`UI-2` `test_security.py:102`); field errors beside the field with focus moved to them (AC20, `app.js:7-11`).
10. **Money.** `Decimal` throughout, half-up per line, then summed; MYR only; quotes say "excluding SST" (`rules.py:21-32`, `README.md:245-246`, `quotes/detail.html:51`).
11. **Every page works without JS** (`app.js:1`), with 44 px controls.
12. **The full CRM suite stays green: 155 tests** (AC1-26).

## ERP
13. **Demo invariants on `localhost`.** `check_demo.check` passes 18/18 today. It requires ≥12 submitted SOs, **every SO grand_total > 0**, ≥4 customers, **every Work Order from a Production Plan**, plus the WO, MR, QI, DN, trip, invoice and defect counts (`ERP/apps/ombak_mfg/ombak_mfg/setup/check_demo.py:12-62`).
14. **`demo.run` stays idempotent** via the `po_no LIKE 'DEMO-%'` marker (`demo.py:25,83-85`). CRM references must not start with `DEMO-`.
15. **The 19 existing SOs** (SAL-ORD-2026-00001..00019, `DEMO-001..019`) are not edited.
16. **Planning stays manual.** Nothing auto-creates a Production Plan or Work Order from an SO (no `doc_events`, `hooks.py:147`). The 4 reports (Defect Log, Job Card, Work Order and JC Scheduled Time sources) and the daily overdue alert (`tasks.py:12-65`) are unchanged unless WOs are created.
17. **The Shop Floor Terminal role is not widened.** CT-7 still gets 403 on GET Sales Invoice and on POST Work Order (`ERP/portal/terminal/tests/test_contract.py:67-72`). Its user and `shopfloor_*` keys are unchanged (`masters.py:124-135,491-527`).
18. **`setup_masters` stays idempotent** (`test_second_run_adds_nothing`, `test_setup_masters.py:46-55`).
19. **Tests never write to the demo site.** `test.sh` uses `test.localhost`; `test-portal.sh` uses `contract.localhost` (guard at `contract.py:18`).
20. **Both ERP suites stay green: 32 + 63.**
