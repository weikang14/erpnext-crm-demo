# Code Quality Assessment (only what affects 004)

| Risk | Where | Why it matters for 004 |
|---|---|---|
| Won is one atomic block holding the deal row lock | `CRM/sales/models.py:284-292` | Putting the HTTP call inside means lock contention up to 30 s, a rolled-back Won on any error, and ghost orders when the response is lost. The call must come after commit (open question 1) |
| No outbound client and no app logger | `CRM/requirements.txt`; `CRM/crm/settings.py:103-108` | Both are new for the CRM. Without a `sales` logger, failures leave no trace |
| False claims in the docs | `README.md:165-166` ("…turn a won deal into an ERPNext sales order without mapping"), `README.md:290` ("ERPNext adds tax on the order"), 003 `design.md:88-89` | Customers aren't mapped for 37 of 42 accounts. The site has no SST template, and REST inserts get zero tax (open question 5). The CRM's "excluding SST" text on quotes (`quotes/detail.html:51`, `print.html:58`) stays true |
| Quote number comes from the pk | `CRM/sales/models.py:428-430` | Not stable across a CRM DB reseed, so an idempotency key based on it can collide with orders left from an earlier DB (open question 7) |
| Line product data is not snapshotted | `QuoteLine.product` FK (`models.py:537`); `Product` editable in `/admin/` | A retry after a product edit sends the edited `item_code`. `unit_price` *is* a snapshot (`:473`) |
| CRM and ERPNext prices drift silently | `Product.list_price` (admin) vs `Standard Selling` Item Price; seed only `get_or_create`s (`seed_demo.py:129-130`) | Decide whose price wins (open question 6) |
| The rounding models differ | CRM rounds each line half-up (`rules.py:21-27`); ERPNext rounds the unit rate with Banker's rounding, then multiplies, then rounds `rounded_total` to whole MYR | Sen-level drift between `deal.amount` and the SO total (open question 6) |
| ERPNext's duplicate guard is not race-safe | `validate_po` (`sales_order.py:359-385`) is a SELECT | It works only as a second line of defence |
| Custom DocPerm freeze | first Custom DocPerm per doctype (live) | A new CRM role on Sales Order or Customer pins those doctypes' perms to today's standard set |
| Stale tax defaults | `Malaysia GST 6% - OMW` is default (live) | A desk-created SO probably gets GST 6 % (client side, not verified), while REST SOs get none: an inconsistency |
| ERP network name not pinned | `ERP/docker-compose.yml:187-189` | A CRM `external` network must hard-code `erp_frappe_network` |
| Stale doc pointer | `ERP/portal/terminal/erpnext.py:3` cites `.specship/specs/002-shopfloor-terminal/...`; the file is now in `.specship/completed/002-shopfloor-terminal/artifacts/api-contract.md` | Cosmetic. Use the `completed/` path |

No large or god files sit in the path: `models.py` is about 565 lines and `erpnext.py` 128. There is no duplication problem; the risk is only in *copying* the portal client.
