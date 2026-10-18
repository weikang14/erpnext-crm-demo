# Open Questions (decisions that change the 004 design)

These merge the CRM and ERP chunk questions. Each one gives the options, the trade-off and a recommended default with its reason. The defaults are proposals for the user to confirm, not decisions.

## 1. When does the push happen, and does an ERP failure block Won? (includes the retry UX)
- **A. Synchronous, inside the Won transaction.** No Won ever exists without an SO. But the deal row lock is held for the whole HTTP call (up to gunicorn's 30 s, `CRM/Dockerfile:12`), and Won is impossible while ERPNext is down. A lost response rolls the CRM back while the SO exists in ERPNext: a ghost order. It also breaks preserved behavior 6 (reports depend only on the CRM DB).
- **B. After commit, in the same request** (`transaction.on_commit` or an explicit second step in `deal_won`). Won always commits. The outcome is stored on the deal (pending, sent or failed) and flashed as success or warning. The cost is that the response waits for the ERP call (bounded by a 10 s timeout, like `ERP/portal/portal/settings.py:19`). If the process dies between commit and push, the deal is left `pending`, so Retry must cover pending as well as failed.
- **C. Background worker** (celery/redis, or a cron container running a command). Won stays fast and retries are automatic, but it needs new infrastructure where the CRM has none (`CRM/Dockerfile:12`).
- **Retry UX:**
  - an "ERP order" row or panel on the deal page with a chip (pending amber, sent green with the SO name and Desk link, failed red with the safe message);
  - a "Send to ERPNext again" POST `.btn` while pending or failed;
  - Retry allowed for the deal owner and the manager (the same `access.opportunities` scope as Won);
  - Retry takes the deal row lock, **looks up the reference first**, then creates.
- **Default: B.** Won never depends on ERPNext, the rep sees the result immediately, and it needs no new infrastructure. The retry button covers the rare failure.

## 2. Accounts that aren't ERPNext customers
Today only the 5 seeded customers match by exact name, which covers **3 of 21** live won deals (crm chunk, live SQL).
- **A. Create the Customer on first Won** when the GET by exact name returns 404: `customer_type` Company, group `Commercial`, territory = `Account.country` ("Malaysia" and "Singapore" both exist live). The role needs Customer create. The cost is that junk or validator accounts (e.g. names with `<img …>`) become ERPNext customers, and near-duplicate spellings aren't detected.
  - **Address:** create one only when the CRM has `address` + `city`, which is true for 1 of 42 accounts. An SO saves without an address; Delivery Trips need one later (`demo.py:402`).
- **B. Refuse.** Won commits and the ERP status shows failed: "Customer X isn't in ERPNext; add it there, then retry." The ERP master stays curated and the role needs only read. The cost is that most Wins fail until someone keys customers in by hand.
- **C. Manual mapping.** A new `Account.erp_customer` field that the manager sets, falling back to the exact name. It survives renames, but it means another field, another admin step and more process.
- **Default: A, without Address.** Otherwise most Wins can't produce an order. The exact-name join is reliable: ERPNext names customers by `customer_name` (`cust_master_name`, live), and the CRM enforces case-insensitive unique names (`CRM/sales/models.py:67`). The CRM has almost no address data to send. Pick B if the ERP customer master must stay curated.

## 3. Draft or submitted Sales Order?
- **A. Submitted** (`"docstatus": 1` in the same POST, atomic). Planning sees it at once, because Production Plan pulls only `docstatus == 1` (`production_plan.py:1629-1630`), and it matches the demo flow (`demo.py:216`). The costs: qty is reserved immediately; a correction needs cancel + amend in ERPNext; the role needs submit.
- **B. Draft.** A person reviews tax, date and address in ERPNext first, and the role is narrower (no submit). But the order is invisible to MRP until someone submits it.
- **Default: A.** The intent is an order the factory can plan, and the fields a human would review are fixed by rules (questions 4 and 5).

## 4. Delivery date source (the CRM has none)
ERPNext refuses an SO without a delivery date or with one before `transaction_date` (`sales_order.py:425-445`).
- **A.** Won date + N days, as a named constant. The demo uses 12 days (`demo.py:204`).
- **B.** `Opportunity.expected_close`. It is often already past at Won, so ERPNext refuses it, and it means "deal close", not delivery.
- **C.** The rep enters a promised date at Won. That turns Won into a form with the 400 re-render pattern and changes preserved behavior 2 (one-click Won).
- **D.** A lead time per product (a new `Product` field).
- **Default: A** (`localdate(closed_at) + 12 days`). It needs no new UI, Won stays one click, and the planner adjusts the date in ERPNext.

## 5. Tax: "ERPNext adds SST" is false on this site
The site has no SST template, only the stale `Malaysia GST 6/5/10% - OMW` (GST 6 % is default). `add_taxes_from_taxes_and_charges_template = 0`, so REST inserts get **zero tax**. All 19 demo SOs have tax 0 (erp chunk, live). The CRM and README claim otherwise (`README.md:290`, 003 `design.md:88-89`).
- **A.** No tax rows on the SO, as today, and correct the README claim. Tax is applied at invoicing by accounts.
- **B.** Set up SST properly: an SST account plus a template in `setup_masters`, with explicit `taxes` rows (or `taxes_and_charges` and the site-wide setting flipped). This needs real tax rules: SST 5 % or 10 % by goods class, and none for the Singapore customer.
- **C.** Send the existing default GST 6 %. That tax was abolished in 2018. Rejected.
- **Default: A.** The tax rules are an accounting decision the CRM can't make, and REST already gives a consistent 0. Fix only the false claim. The cost is that the SO total is pre-tax.

## 6. Price and rounding: whose number wins?
The CRM rounds each **line total** half-up (`CRM/sales/rules.py:21-27`). ERPNext rounds the **unit rate** with Banker's rounding, multiplies by qty, then sets `rounded_total` to **whole ringgit** (MYR `smallest_currency_fraction_value = 0`; `frappe/utils/data.py:1365-1379`, `erpnext/controllers/taxes_and_totals.py:837-853`).
- Hand-computed examples (verify them in a contract test):
  - FG-CT-300 × 3 at 12.5 %: CRM 223.13, ERPNext 74.38 × 3 = 223.14;
  - × 3 at 7.5 %: CRM 235.88, ERPNext 78.62 or 78.63 × 3 = 235.86 or 235.89;
  - × 40 at 7.5 %: CRM 3145.00, ERPNext about 3145.20;
  - the drift grows to as much as about 0.005 × qty per line.
- ERPNext keeps an explicit `rate` when there are no Pricing Rules (none exist live; `taxes_and_totals.py:194-224`).
- **A.** Send each line's `rate` = the CRM's discounted unit price (CRM price wins over the Item Price). The total still drifts.
- **B.** Send `price_list_rate` = `unit_price` + `discount_percentage`. The discount is visible in the data, but the drift is the same.
- **C.** Send lines at the undiscounted `rate` = `unit_price` plus a header `discount_amount` = Σ(qty × unit_price) − `deal.amount`, with `apply_discount_on = "Net Total"`. Then `grand_total == deal.amount` exactly, with tax 0. The fields exist and are API-settable; their UI section is hidden by a Property Setter (live). The per-line discount isn't shown per line.
- **D.** Change the CRM rounding to match ERPNext. That breaks quote totals, the README example and the tests. Rejected.
- In every case, send `disable_rounded_total: 1`, or the SO shows 236.00 for 235.88.
- **Default: C + `disable_rounded_total`.** It is the only option where the ERPNext order total equals the deal value the customer was quoted and the reports use, without touching CRM money rules. Prove it in the first contract test, and fall back to A with both totals shown if the site refuses it.
- The CRM's quote `unit_price` snapshot wins over any drift in `Product.list_price` or the `Standard Selling` price. Currency is MYR for all customers, Singapore included (the demo SOs default to MYR).

## 7. Idempotency key
- **A. `po_no` = quote number** (`QT-2026-00133`, `CRM/sales/models.py:428-430`). It needs no ERP schema change, ERPNext already refuses the same customer + `po_no` with a 417 (`sales_order.py:359-385`), and v2 can filter on it. The costs:
  - it is not unique or indexed, and the guard is a race-unsafe SELECT;
  - it is `allow_on_submit = 1` (live), so a user edit makes the lookup miss;
  - it takes the field meant for the customer's real PO number.
- **B. A Custom Field on Sales Order**, e.g. `crm_reference` (Data, `unique`, `read_only`, `no_copy`), created idempotently via `_ensure` in `setup_masters` (house style; ombak_mfg has no fixtures). The DB unique index makes it race-safe, users can't edit it, and `po_no` stays free. The costs: it is ombak_mfg's first Custom Field, and the demo site needs `setup_masters` rerun.
- **C. Explicit SO `name`.** It breaks the `SAL-ORD-.YYYY.-` series. Rejected.
- Either way the value must not start with `DEMO-` (`demo.py:25,83-85`). The quote number comes from the pk, so it repeats after a CRM DB reseed; leftover ERPNext orders would then be matched wrongly. That is acceptable for a demo; say so in the contract. The CRM also stores the returned SO name, unique when set.
- **Default: B, with value = quote number.** It is the only DB-enforced guard against a duplicate production order, and it costs one idempotent `_ensure`.

## 8. Networking, and keeping contract tests off the demo site
`:8080` nginx forces site `localhost` (`ERP/docker-compose.yml:88`), so anything sent through it writes demo data.
- **A. The CRM `web` joins `erp_frappe_network` as `external`**, with `ERPNEXT_URL=http://backend:8000` and `ERPNEXT_SITE=localhost`. This is the portal's proven path (`ERP/docker-compose.yml:134-139`). Host picks the site, so CRM live contract tests can target `contract.localhost`, and it works on Linux. The costs:
  - CRM `up` fails if the ERP stack has never created the network;
  - the network name is derived, not pinned (`ERP/docker-compose.yml:187-189`);
  - it couples the two compose projects that 003 kept separate.
- **B. `host.docker.internal:8080`.** It works today (ping 200) with no coupling. But it is always the demo site, so a CRM live contract test is impossible; tests would have to move to the ERP side (`frappe.set_user` on `test.localhost`). It is Docker Desktop specific; Linux needs `extra_hosts: host-gateway`.
- **C. Publish backend `:8000` on the host.** It changes the ERP stack and bypasses nginx, for no real gain over A.
- **Default: A.** It is the only option where the real CRM client can be contract-tested against `contract.localhost` without touching demo data, and it reuses the portal's path.

## 9. Backfill the existing won deals?
The live CRM has 21 won deals. Only 3 have ERPNext customers, many are `VAL-` validator data, and their delivery dates would already be late.
- **A.** No backfill. Past wins show "Won before the ERPNext link" and get no button.
- **B.** An opt-in management command a manager runs for chosen deals.
- **C.** Auto-push everything on deploy.
- **Default: A.** Pushing would create junk customers and already-late orders in ERPNext. Add B when someone actually asks.

## 10. Expired quotes at Won
Won ignores `valid_until` today: 14 of 21 live won deals closed after it.
- **A.** Keep it: the SO is created anyway.
- **B.** Block Won on an expired quote. That is a CRM rule change and breaks preserved behavior 7.
- **C.** Win, but hold the push for review.
- **Default: A.** The rep accepted the price by clicking Won, and 004 is an integration, not a sales-rule change.

## 11. Least-privilege role for the CRM integration user
- **A.** A new role `CRM Integration` and user `crm.integration@ombakmetal.example`, mirroring 002 (`masters.py:124-135,491-527`). Keys come from site config `crm_api_key/secret`, set by compose `create-site`.
  - Perms: Sales Order read/create/submit (plus write if submit needs it; verify), Customer read (plus create if question 2 = A), and Item read. Customer Group, Territory and Price List read only if link validation or `set_missing_values` demands them; find out in the contract test.
  - Assert as denied: Sales Order cancel/delete, Sales Invoice, Work Order, Job Card.
- **B.** The standard `Sales User` role. No new code, but it grants Sales Order cancel/delete and Customer/Address/Contact write.
- **C.** Reuse the terminal user. That breaks CT-7. Rejected.
- **Default: A.** It is the same proven pattern, with tests (`test_setup_masters.py:89-108`, CT-7). The cost is that Custom DocPerms freeze the standard Sales Order and Customer perms (seen live on Employee, Job Card, Work Order and Workstation).
