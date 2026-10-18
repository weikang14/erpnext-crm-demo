# Business Flows

## F1. Mark a deal won (CRM, today)
1. On an open deal, the "Mark won" `btn btn-success` POST form (`CRM/sales/templates/sales/deals/detail.html:18-21`) is shown. It is disabled with `aria-describedby="won-hint"` when there is no sent quote, and the hint is at `:25`. There is no confirm step. `app.js:14-21` disables the button after the first click when JS runs.
2. `deal_won` (`CRM/sales/views/opportunities.py:146-155`) requires login and POST. It scopes the deal (another rep's deal answers 404), then calls `mark_won`. On success it flashes `Won: {title}, MYR {amount}`; on `RuleError` it flashes the error. It **always redirects**: Won has no form and no 400 re-render.
3. `mark_won` (`CRM/sales/models.py:284-292`) is one transaction:
   - it locks the deal row and takes `sent_quote()`, the first quote with status `sent` (`:263-264`);
   - `check_won` refuses with "This deal is closed." or "Send a quote before marking the deal won." (`rules.py:53-57`);
   - the quote becomes `accepted`;
   - `_set_stage(WON)` writes a `StageChange` and sets `stage`, `last_activity_at`, `amount = quote.total` and `closed_at = now`.
4. A second click waits on the row lock, then gets "This deal is closed." with nothing changed. No concurrency test covers this yet.
5. After Won the deal and its quotes are read-only, and a closed deal can't be reopened. The page shows "Won on {date}" (`detail.html:27`). Tests: `CLOSED-1` (`test_deals.py:125`), `EDIT-4` (`:218`).
6. Won does **not** touch other draft or pending quotes, activities, or `valid_until`. Live data shows 3 won deals with a leftover draft or pending quote, and 14 of 21 won deals closed after `valid_until` (crm chunk, live SQL).

## F2. Demo order to plan (ERP, today)
1. `create_order` (`ERP/apps/ombak_mfg/ombak_mfg/setup/demo.py:202-216`) inserts a Sales Order with `customer`, `company`, `transaction_date`, `delivery_date = order + 12 days`, `po_no = DEMO-NNN` and one item with `warehouse` set, then submits it.
2. The planner runs MRP: a Production Plan from the SO → Work Order + Material Request (`demo.py:218-250`). A Production Plan pulls **only submitted** SOs (`erpnext/manufacturing/doctype/production_plan/production_plan.py:1629-1630`).
3. `on_submit` reserves qty in `Finished Goods - OMW` (`sales_order.py:519-541`). Nothing creates plans or WOs automatically: there are no `doc_events`, Server Scripts, Webhooks or Notifications (erp chunk, live).

## F3. Won deal → ERPNext Sales Order (004, to be designed)
At Won the CRM has exactly one accepted quote (live: all 21 won deals) whose lines carry `product.item_code`, `qty`, `unit_price` (a snapshot) and `discount_pct`. It also has the account name, the deal owner, `closed_at` and `expected_close`. Field mapping is in `data-models.md`. Every open design choice is in `open-questions.md`.
