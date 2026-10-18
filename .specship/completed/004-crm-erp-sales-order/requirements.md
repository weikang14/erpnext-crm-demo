# Sprint Contract: won deal → ERPNext sales order

**ID:** 004
**Created:** 2026-10-14
**Status:** validated (shipped 2026-10-18)

## Goal
When a rep marks a deal Won in the Django CRM (`CRM/`), ERPNext (`ERP/`) gets a submitted
sales order for the accepted quote: right customer (created if missing), products, quantities
and prices, a net total equal to the quote to the sen, SST for Malaysian customers, and the
delivery date the rep entered. Won never depends on ERPNext; a failed send is visible on the
deal and can be resent without ever creating a second order. Design and decisions:
`design.md`. Brownfield recon: `artifacts/reverse-engineering/source.txt`.

## Acceptance Criteria

### Won and the delivery date
1. The Won form on an open deal has a required "Requested delivery date" (default today + 14
   days, Kuala Lumpur date, not before today, at most 365 days ahead). A missing, past or
   too-late date re-renders the deal page
   with 400, the error next to the field and focus on it, and the deal stays open. A valid
   date stores `delivery_date` and does everything 003's Won does (quote Accepted, deal amount
   = quote total, closed, history row, deal read-only).
2. Won commits before any ERPNext call. Whatever happens in ERPNext afterwards (refusal,
   timeout, not configured), the deal stays Won and reports count it as before.
3. Right after the Won commits, in the same request, the CRM sends the order and shows the
   outcome as a flash: "Sales order SAL-ORD-… created in ERPNext." or a warning with the
   reason.

### Customer
4. When ERPNext has a customer whose name equals the account name, the order uses it and no
   customer is created.
5. When it doesn't, the CRM creates one: `customer_name` = account name, `customer_type`
   Company, `customer_group` Commercial, `territory` Malaysia or Singapore from the account's
   state, `tax_id` = SSM/UEN no. (if any). An Address (line 1, city, state, postcode, country,
   phone) is created and linked only when the account has address and city. The next order
   for that account reuses the customer.

### The sales order
6. The order is submitted (`docstatus` 1, ERPNext status "To Deliver and Bill", not "Draft") with: the customer, company Ombak Metal Works Sdn
   Bhd, `transaction_date` = the send date (Kuala Lumpur), `delivery_date` = the deal's
   delivery date, currency MYR, `crm_reference` = the accepted quote's number,
   `disable_rounded_total` 1.
7. It has one item per line of the deal's **accepted** quote, in order: item code, qty,
   `rate` = the line's list-price snapshot, the delivery date, warehouse Finished Goods - OMW.
   Draft, pending, declined or superseded quotes on the deal are ignored.
8. The order's net total equals the deal amount exactly: no line discounts, and a header
   discount on Net Total = Σ(qty × list price) − deal amount. Example: 3 × 85.00 at 7.5 % →
   quote 235.88 → order net total 235.88 (discount 19.12), not 235.86/235.89 or 236.00.
   After creating or adopting an order the CRM compares ERPNext's net total with the deal
   amount; if they differ, the deal keeps the order name but shows the warning "ERPNext order
   <name> totals MYR X, the quote MYR Y; check it in ERPNext."
9. A Malaysian customer's order has `taxes_and_charges` "Malaysia SST - OMW" and the
   template's tax row(s) copied from ERPNext at send time (charge type, account, rate,
   description), so the rate lives only in the template: one row, 10 % on net total, tax =
   net total × 10 % rounded to the sen. A Singapore customer's order (assumed exported, K2)
   has no tax rows and grand total = net total.
10. A quote whose total is 0 is not sent: the deal shows failed with "The accepted quote is
    zero; ERPNext needs an order with a value." and ERPNext is not called.

### Status, idempotency, resend
11. Each deal stores `erp_status` (not sent / sending / sent / failed), `erp_order` (not
    unique in the CRM: ERPNext order names are only unique per site; `crm_reference` guards
    duplicates), `erp_error` and `erp_attempted_at` (last attempt); deals won before 004 migrate
    as not sent. These fields never change the deal's stage, amount or reports.
12. Before creating anything, the CRM looks up a sales order with this `crm_reference`; if one
    exists it is adopted (status sent, its name stored) and nothing new is created. The lookup
    sees only orders the integration user created (`if_owner`, AC20).
13. ERPNext holds at most one sales order per `crm_reference` (unique field). If a create is
    refused because one appeared meanwhile, the CRM looks it up again and adopts it. An order
    with that reference created by another user is never adopted: the deal fails with
    ERPNext's duplicate message.
14. A timeout or connection error (10 s limit) marks the deal failed with "ERPNext didn't
    answer. The order may or may not exist; sending again checks first, so it can't be
    duplicated." An ERPNext refusal marks it failed with ERPNext's message, HTML stripped,
    at most 300 characters. No traceback, exception class or secret is ever shown or stored.
15. The deal owner or the manager can resend a Won deal that isn't sent, from a form with the
    delivery date prefilled (the stored date, or today + 14 if none or already past). Sending
    first claims the deal by a conditional update to "sending" (only from not sent, failed, or
    a "sending" older than 2 minutes), then calls ERPNext with no row lock held, so two clicks
    can't send twice and a slow ERPNext never blocks other requests. Another rep gets 404, a
    sent deal is refused, the route is POST only with CSRF.
16. Without ERP settings (`ERPNEXT_URL` unset) no network call is made, Won works as in 003,
    and won deals show "ERP link not configured".

### Screens
17. A won deal shows an "ERP order" panel: a status chip (sent, with the order name linking to
    it in ERPNext Desk and the send date and time; failed, with the reason and the time of the
    attempt; not sent; not configured) and the send form
    where the viewer may send. It uses the existing CRM classes, 44 px controls, no inline
    style or script, and works without JavaScript.
18. My day has an "ERP orders not created" panel listing failed sends with a link to each
    deal: the user's own deals, the manager's whole team. With none, the panel is not shown.

### ERP side
19. `setup_masters` (idempotent; running it twice changes nothing) creates: the role "CRM
    Integration" and user `crm.integration@ombakmetal.example` with the API key/secret from
    site config `crm_api_key`/`crm_api_secret`; the Sales Order custom field `crm_reference`
    (Data, unique, read-only, no copy); an SST tax account and the template "Malaysia SST -
    OMW" (one row, On Net Total, 10 %, not the default). The customer group Commercial and the
    territories Malaysia and Singapore exist and are not group records. The 19 demo sales
    orders are unchanged and `check_demo` still passes 18/18.
20. The integration user can create and submit sales orders, create customers and addresses,
    read addresses (ERPNext reads an existing customer's primary address, often owned by
    another user, while filling the order), and read items and the SST template; it gets 403 for cancelling or deleting sales orders
    and for Sales Invoice, Work Order and Job Card. It reads, changes and submits only the sales
    orders it created (`if_owner`). The terminal role and its tests are
    unchanged.

### Running it
21. `CRM/docker-compose.erp.yml` joins the CRM only to a dedicated link network that the ERP
    `backend` also joins (not the ERP's internal network: no Redis or MariaDB reachable from
    the CRM), and sets
    `ERPNEXT_URL`, `ERPNEXT_SITE`, `ERPNEXT_API_KEY`, `ERPNEXT_API_SECRET` and
    `ERPNEXT_DESK_URL` from env with local-demo defaults; the ERP compose sets the matching
    `crm_api_*` site config. The README explains how to run both and the send flow.
22. Live contract tests (`CRM/scripts/test-erp.sh`) run the real CRM client against the
    `contract.localhost` site only and refuse to run against `localhost`.

### Clarifications (from testgen, 2026-10-14)
- Resend: the date entered replaces `delivery_date`; a past, missing or too-late date → 400 with the
  error by the field. Resending a sent deal → flash "This deal's order is already in
  ERPNext." (302); an open or lost deal → flash "Only won deals can be sent." (302).
- Net-total mismatch (AC8): status stays sent; the warning is kept in `erp_error` and shown
  on the panel as a warning (amber) chip and in the flash; not listed on My day.
- Address refused after the customer was created: the send fails with ERPNext's reason; a
  resend finds the customer and creates the order without an address.
- A cancelled ERPNext order holding the quote number: the lookup (docstatus < 2) misses it,
  the create is refused by the unique field, the re-lookup misses it → failed with ERPNext's
  message; no loop.
- Error text: several `errors[].message` are joined with a space; a non-JSON error body →
  "ERPNext rejected the request (<status>)."
- Customer match is by exact (stripped) name via `GET Customer/<name>`; inner whitespace
  differences are out of scope.
- Not configured: `ERPNEXT_URL` unset or empty; the send form is hidden.
- Any unexpected exception during a send marks the deal failed ("Unexpected error while
  sending; see the server log.", logged without secrets) and redirects; Won is never lost
  and the user never gets a 500 from a send.
- Desk link: `{ERPNEXT_DESK_URL}/app/sales-order/<order name>`.
- Round 1 recovery (2026-10-17): the order is created as a draft and then submitted, so ERPNext
  computes its status; a draft found by the lookup is submitted, not adopted as is. Recording
  the outcome never raises (any error → failed). A refusal flash also says the deal stays won
  and to send again after fixing the cause; the panel shows the requested delivery date.
- Round 2 recovery (2026-10-18): the requested delivery date may be at most 365 days after
  today (KL, inclusive; across 29 February that is a day short of a calendar year); later dates get "The delivery date can't be more than a year ahead." by the
  field (Won and resend). A database error while claiming the send never produces a 500:
  the Won/resend response flashes "Unexpected error while sending; see the server log." and
  the deal can be sent again.
- Known issue (accepted 2026-10-18): ERPNext's /printview lets the integration key read any
  sales order (website permission ignores if_owner); read-only, documented in README.
- SST applies to every Malaysian state alike (designated areas such as Labuan out of scope).
- `sending`: the claim sets `erp_attempted_at`; "stale" means `sending` with
  `erp_attempted_at` older than 2 minutes. A fresh `sending` shows a plain "sending…" chip and
  no form; a send attempt then gets the flash "This deal is being sent right now; refresh in
  a moment." (302) and the entered date is not stored. A stale `sending` is shown and listed
  (panel, My day) as failed with "The last send didn't finish; send it again." and offers the
  send form.

## Failure Modes
1. The ERPNext call runs inside the Won transaction: an ERP error undoes the Won, or the deal
   row stays locked during the HTTP call.
2. A resend after a timeout creates a second sales order because it doesn't look up the
   `crm_reference` first.
3. Two parallel sends (double click, two tabs, owner + manager) create two orders or two
   customers.
4. The order's total differs from the quote: line discounts left to ERPNext's rounding, the
   rounded total to whole ringgit, or `Product.list_price` used instead of the quote's
   snapshot.
5. SST charged to a Singapore customer, missing for a Malaysian one, or added twice
   (template rows plus explicit rows).
6. The order is saved as a draft and never reaches production planning.
7. Lines come from a draft, pending or superseded quote instead of the accepted one.
8. A customer that exists in ERPNext is created again (case or whitespace mismatch), or an
   Address is created with empty required fields.
9. A rep sends or resends another rep's deal by id, or a rep's GET triggers a send.
10. The API secret, an ERPNext traceback or raw HTML appears on a page, in `erp_error` or in
    the logs.
11. A test writes to the demo site `localhost`; a demo sales order changes; `check_demo` fails.
12. The integration user gets a broad standard role (e.g. Sales Manager) or the new custom
    permissions stop standard roles from using Sales Order or Customer.
13. With ERPNext down or not configured, Won returns a 500, hangs beyond the timeout, or
    can't be done at all.
14. A delivery date in the past or computed in UTC (yesterday at 7 a.m. KL) is accepted.
15. A zero-value order reaches ERPNext.
16. Regressions of 003: Won/Lost rules, the "Send a quote first" gate, Won twice, reports
    reading ERP state, access scoping (404/403), CSP, lockout, admin guard, errors beside
    fields with focus, any of the 155 CRM tests; ERP's 32 tests, the portal's 63 tests or the
    terminal role's 403s.

## Scope
**IN scope:** the delivery date on Won; sending (customer lookup/create + address, submitted
sales order, SST, exact total, idempotency) after Won and by resend; the deal fields and
migration 0004; the ERP panel and the My day panel; the ERP role, user, custom field and SST
template in `setup_masters`; the compose override and env; unit, contract and ERP tests;
README and CHANGELOG.

**OUT of scope:** invoices, deliveries, stock checks; syncing ERPNext changes back to the
CRM; cancelling or editing ERP orders from the CRM; SGD or other currencies; automatic
retries, background workers or schedulers; updating ERPNext customers after creation;
blocking Won on an expired quote; changing CRM money rules, reports or access scopes;
SST exemptions (Schedule C manufacturers, proof of export), per-product SST rates.

**Do not touch:** `rules.py` money/won/move rules, `reports.py`, `access.py`, the 003
security code (lockout, `GuardedUserAdmin`, CSP), CRM migrations 0001-0003, `ERP/portal/**`,
the terminal role, `demo.py`, `check_demo.py`, `hooks.py`, the ERPNext core and Dockerfile,
site-wide tax/PO settings, `.specship/completed/**`.

## Risks & Unknowns
- SST assumptions (see `artifacts/market-research.md`): 10 % is the default rate for goods
  not listed in the 2025 rate order; fabricated steel may be 5 % by tariff code, which is a
  one-field change in the template. "Singapore customer" is assumed to mean goods exported
  under K2. Both are stated in the README.
- Which link doctypes the integration role must read (Customer Group, Territory, Price List)
  is found by the first contract test; the role stays as narrow as the tests allow.
- Quote numbers repeat after a CRM database reseed; an old ERPNext order with the same
  `crm_reference` would be adopted. Accepted for a demo and documented.
- The compose override needs the ERP network to exist; documented, with a clear error.

## Non-Functional Requirements
- **Reliability:** every ERPNext call has a 10 s timeout; the Won response stays under
  timeout + 1 s even when ERPNext is down.
- **Security:** least-privilege API user; secrets only from env/site config; no secret, HTML
  or traceback reaches users or logs; CSRF and POST-only on the send route; access scopes as
  in 003.
- **Testing:** offline unit tests with a fake client for every AC; live contract tests on
  `contract.localhost`; ERP integration tests on `test.localhost`; all existing suites green.
- **Accessibility:** as 003 (44 px, focus visible, errors beside fields, works without JS).

## Execution Config
```yaml
model_routing:
  planner: opus
  worker: sonnet
  validator: sonnet
  alignment: opus
autonomy: guided
```

## Pre-Generated Test Cases
See: `artifacts/test-cases.md`

## Validation Results
| Validator | Result | Details |
|-----------|--------|---------|
| Code Review | PASS | round 3, f5389ba: CRM 331 (17 live), ERP 50, portal 63, live 17 + BRT-20 + AC21, check_demo 18/18 |
| Security | PASS | round 2, 0292249; /printview read accepted as a known issue |
| Integration | PASS | round 2, 0292249 |
| Browser | PASS | round 2, 0292249, 5/5 sequences |
| Design | PASS | round 1, 11c2a89: 14/15, states 5/5, Lighthouse 100 on the panels |
| Alignment | PASS | round 1, 11c2a89 |

**Aggregate Verdict:** MERGE (2 recovery cycles; skeptic: cycle-1 fixes hold; completeness critic gaps closed)
