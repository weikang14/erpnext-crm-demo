# Design: 004 won deal → ERPNext sales order

**Status:** approved in conversation 2026-10-14 (sections 1-3), written spec awaiting review
**Recon:** `.specship/reverse-engineering/20261014-ombakmetal/` (see `artifacts/reverse-engineering/source.txt`)

## Intent
Part 3 of the Ombak Metal Works demo. When a rep marks a deal **Won** in the Django CRM
(`CRM/`), ERPNext (`ERP/`) gets a **submitted sales order** with the right customer,
products, quantities and prices, which the production manager can plan from straight away.
A failure never loses the Won or creates a second order. The CRM and ERP stay two separate
systems that talk only through ERPNext's REST API, as the shop-floor terminal (002) does.

Success: click Won → a `SAL-ORD-…` exists in ERPNext whose net total equals the accepted
quote to the sen, with SST for Malaysian customers; when ERPNext is down the deal is still
Won and shows a "send again" form that can't create a duplicate.

## Decisions (user, 2026-10-14)
| # | Question | Decision |
|---|---|---|
| 1 | ERP failure at Won | Won commits first; the order is sent right after in the same request; failure shows the reason and a resend form. Older won deals can be sent on demand with the same form. |
| 2 | Account not in ERPNext | Create the ERPNext Customer automatically (and an Address when the CRM has address + city). |
| 3 | Draft or submitted | Submitted (`docstatus: 1`), so MRP/production planning sees it. |
| 4 | Delivery date | Entered at Won: required "requested delivery date", default today + 14 days, not before today. |
| 5 | Tax | Add SST: a "Malaysia SST - OMW" sales tax template (10 %); Malaysian customers' orders carry it, Singapore (export) doesn't. CRM quotes stay tax-exclusive. |
| 6 | Amount alignment | Exact: lines at the quote's list price, the discount as a header discount, rounding to whole ringgit off, so the order's net total equals the quote total. |
| - | Architecture | A. CRM pushes (no ERP polling, no background worker). |

## Architecture and data flow
```
Rep: Mark won (+ delivery date)
  └─ Opportunity.mark_won(...)      unchanged rules, row lock, one transaction (commit)
  └─ erp.send_order(deal)           after commit, same request, 10 s timeout
       1. GET Sales Order where crm_reference = quote number → found: adopt it, done
       2. GET Customer by exact name → missing: POST Customer (+ Address)
       3. POST Sales Order as a draft, then PUT docstatus 1 to submit it (round 1: an insert
          with docstatus 1 keeps status "Draft")
       4. duplicate crm_reference refused (race) → GET again and adopt
  └─ store result on the deal → flash success / warning → redirect to the deal
```
- Won itself (`CRM/sales/models.py` `Opportunity.mark_won`) keeps every 003 rule: needs a
  sent quote, quote becomes Accepted, deal amount = quote total, deal read-only. The new
  delivery date is stored with it. The ERP call is never inside the Won transaction.
- Sending (first time or resend) first claims the deal with a conditional update to
  `sending` (from `not_sent`, `failed`, or a `sending` older than 2 minutes), then calls
  ERPNext with no row lock held, so two clicks can't send in parallel and a slow ERPNext
  never blocks other requests. Only a Won deal whose ERP status is not `sent` can be sent.

### New CRM code (`CRM/sales/`)
| Unit | Job |
|---|---|
| `erp.py` | pure mapping: deal + accepted quote + account → Customer, Address and Sales Order payloads; the tax decision; the header discount; `send_order(deal, client)` orchestrating lookup → customer → order and returning an outcome |
| `erpnext.py` | the only HTTP code: a small REST v2 client on the Python standard library (`urllib.request`), token auth, Host header for the site, 10 s timeout, two error kinds (`Refused` with ERPNext's message stripped of HTML, `Unavailable` for timeouts/connection errors), the same shape as `ERP/portal/terminal/erpnext.py` |
| `models.py` | `Opportunity` gains `delivery_date`, `erp_status` (`not_sent`, `sending`, `sent`, `failed`), `erp_order` (not unique since round 1: names are unique per ERPNext site only), `erp_error`, `erp_attempted_at`; migration `0004` (existing won deals become `not_sent`) |
| `views/` | Won takes the delivery date (form, 400 re-render on error); a new POST `deals/<pk>/erp/send/` for the owner or manager |
| templates | the Won form's date field; an "ERP order" panel on won deals; a My day panel listing the user's (manager: team's) deals whose send failed |

### New ERP code (`ERP/apps/ombak_mfg/`, inside the idempotent `setup_masters`)
- Role **CRM Integration** and user `crm.integration@ombakmetal.example`, API key/secret
  from site config `crm_api_key` / `crm_api_secret` (set from env `CRM_API_KEY` /
  `CRM_API_SECRET` with local-demo defaults, like the terminal's `shopfloor_api_*`).
  Permissions: Sales Order read/create/write/submit on its own orders only (`if_owner`; write
  because Frappe's submit is a save), Customer read/create, Address create and read, Item read, and whatever link validation proves necessary
  (Customer Group, Territory, Price List read), found by the contract test. Denied and
  tested: Sales Order cancel/delete, Sales Invoice, Work Order, Job Card.
- Custom field **`crm_reference`** on Sales Order: Data, unique, read-only, no-copy. The
  database unique index makes duplicate orders impossible even under a race. It is
  ombak_mfg's first custom field, created by `_ensure`-style code like the other masters.
- An **SST** tax account under Duties and Taxes and a Sales Taxes and Charges Template
  "Malaysia SST - OMW" (one row, On Net Total, 10 %). Not the default template; the 19
  demo orders are not touched.

### Network
`CRM/docker-compose.erp.yml` (optional override) joins the CRM `web` container to the ERP
stack's network as an external network and sets `ERPNEXT_URL=http://backend:8000`,
`ERPNEXT_SITE=localhost`, the API key/secret and `ERPNEXT_DESK_URL=http://localhost:8080`.
Frappe picks the site from the Host header, so live contract tests use
`contract.localhost` and never write demo data (`:8080` nginx would force `localhost`).
Without the override the CRM runs on its own as in 003, and won deals show "ERP link not
configured" with no call made.

## Mapping
**Customer** (looked up by exact name: ERPNext names customers by customer name, the CRM
keeps account names unique case-insensitively)
- `customer_name` = account name, `customer_type` Company, `customer_group` Commercial,
  `territory` = Malaysia or Singapore from the account's state, `tax_id` = SSM/UEN no.
- Address only when the account has address and city: line 1, city, state, postcode,
  country, phone, linked to the customer.

**Sales Order**
- `customer`, `company` Ombak Metal Works Sdn Bhd, `transaction_date` = send date (Kuala
  Lumpur), `delivery_date` = the deal's delivery date, `currency` MYR, `crm_reference` =
  quote number (e.g. `QT-2026-00133`), `disable_rounded_total` 1.
- `items`: one per accepted-quote line: `item_code`, `qty`, `rate` = the line's list price
  snapshot, `delivery_date`, `warehouse` Finished Goods - OMW (as `demo.py:209-213`).
- Header discount: `apply_discount_on` Net Total, `discount_amount` = Σ(qty × list price) −
  deal amount, so the order's net total equals the quote total exactly.
- Tax: Malaysian customer → `taxes_and_charges` "Malaysia SST - OMW" with the template's
  rows read from ERPNext at send time and sent explicitly (the site doesn't add template rows
  to REST inserts), so the rate (10 %, assumed; steel may be 5 % by tariff code) lives only
  in the template; Singapore → no tax (assumed exported under K2). Exemptions (Schedule C,
  proof of export) are out of scope.
- After create or adopt: compare ERPNext's net total with the deal amount; a difference keeps
  the order name but shows a warning on the deal.
- Not sent: a quote whose total is 0 (every line 100 % off). The deal shows why.

## Errors, idempotency, resend
| Situation | Result on the deal |
|---|---|
| Order created and submitted | `sent`, order name stored, flash "Sales order SAL-ORD-… created in ERPNext" |
| An order with this `crm_reference` already exists | adopted: `sent` with that name |
| Duplicate refused during create (race) | look up again and adopt |
| Timeout / connection error | `failed`: "ERPNext didn't answer. The order may or may not exist; sending again checks first, so it can't be duplicated." |
| ERPNext refuses (e.g. unknown item) | `failed` with ERPNext's message, HTML stripped, shortened |
| Link not configured | no call; panel says "ERP link not configured" |

- Resend form (owner or manager, Won deals that aren't `sent`): delivery date, prefilled
  with the stored date, or today + 14 days if none or already past.
- No automatic retries, no background jobs.

## UI
- Won form: required "Requested delivery date" next to "Mark won", default today + 14,
  min today, max today + 365 (round 2); errors follow 003's pattern (400 re-render, error by the field, focus on it).
- Deal page, won deals only: "ERP order" panel with a status chip (sent green with the order
  name and a link to it in ERPNext Desk; failed red with the reason; not sent / not
  configured grey) and the send form where allowed.
- My day: "ERP orders not created" panel with failed sends (own deals; manager: team).
- Existing classes, tokens and patterns from `app.css` and 003 templates only.

## Testing
- **CRM unit tests (offline, fake client)**: mapping (customer, address rule, lines, header
  discount, SST for Malaysia only, zero total refused); flow (Won survives every ERP failure,
  lookup-first adoption, race adoption, the `sending` claim, owner/manager only, not configured);
  delivery-date validation; panel states; My day panel. All 155 existing tests stay green.
- **CRM live contract tests** (`CRM/scripts/test-erp.sh`, with the override, against
  `contract.localhost`): create customer, create + submit order, net total == quote total,
  SST 10 % row for Malaysia and none for Singapore, duplicate `crm_reference` refused,
  lookup finds it, the integration user can't cancel orders or create invoices.
- **ERP tests** (`ERP/scripts/test.sh`, `test.localhost`): `setup_masters` creates the role,
  user, custom field, SST account and template idempotently; permissions as listed; the
  32 existing tests, the 63 portal tests and `check_demo` stay green.

## Out of scope
Invoices, delivery, stock checks; syncing ERPNext changes (cancel, amend, delivery) back
to the CRM; cancelling or editing ERP orders from the CRM; SGD (orders are MYR); automatic
retries or a worker; updating ERPNext customers after creation; blocking Won on an expired
quote.

## Design Spec
No new design system: the CRM's 003 system (`CRM/sales/static/sales/app.css` tokens,
`.panel`, `<dl class="details">`, `chip-*`, `msg msg-*`, `.btn` POST forms, `_field.html`
errors, `app.js` focus on the first invalid field; see `.specship/completed/003-django-crm/design.md`).
Status chips: sent = the success chip, failed = the danger chip, not sent / not configured =
the neutral chip. Date input is a native `<input type="date">` with `min` set to today.

## API contract
`artifacts/api-contract.md` (ERPNext REST v2 calls, bodies, error mapping).

## Market Research Reference
`artifacts/market-research.md`.

## Risks
- Quote numbers come from the CRM primary key, so they repeat after a CRM database reseed;
  an old ERPNext order with the same `crm_reference` would then be adopted. Acceptable for a
  demo; documented.
- Custom DocPerms on Sales Order and Customer freeze their standard permissions (seen with
  the terminal role); the ERP tests must prove standard roles still work.
- The CRM compose override needs the ERP stack's network to exist; `docker compose up` with
  the override fails with a clear error otherwise (README says to start ERP first).
