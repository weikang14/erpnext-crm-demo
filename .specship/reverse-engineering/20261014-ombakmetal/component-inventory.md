# Component Inventory (004-relevant)

| Component | Purpose | Owner files | Public interface |
|---|---|---|---|
| CRM Won workflow | Close a deal as won from its sent quote | `CRM/sales/models.py:284-292`, `CRM/sales/rules.py:53-57` | `Opportunity.mark_won(by)`; raises `RuleError` |
| CRM Won endpoint | Thin POST view | `CRM/sales/views/opportunities.py:146-155`, `CRM/sales/urls.py:36` | `POST /deals/<id>/won/` → 302 to the deal, with a flash |
| CRM deal page | Shows stage, banners, facts and the actions | `CRM/sales/templates/sales/deals/detail.html` | `detail_context(request, deal, **forms)` (`opportunities.py:103-119`) |
| CRM money rules | Line and quote totals | `CRM/sales/rules.py:21-32` | `money`, `line_total`, `quote_total` |
| CRM access scopes | Rep sees their own records, manager sees all | `CRM/sales/access.py:18-53`, `CRM/sales/models.py:15-23` | `access.opportunities(user)`, `access.get(...)` → 404, `manager_required` |
| CRM reports and My day | Read won deals | `CRM/sales/reports.py:37-61`, `CRM/sales/views/home.py:34-35` | win rate, forecast "won in quarter", "won this month" |
| CRM seed | Demo products and accounts (the first 5 are ERPNext customers) | `CRM/sales/management/commands/seed_demo.py:37-57` | `manage.py seed_demo` |
| ERPNext Sales Order | Target document | ERPNext core `erpnext/selling/doctype/sales_order/sales_order.py` (in image) | REST v2 `POST /api/v2/document/Sales Order` |
| ombak_mfg setup | Masters, roles, integration users, demo | `ERP/apps/ombak_mfg/ombak_mfg/setup/masters.py`, `demo.py`, `check_demo.py`, `contract.py` | `setup_masters()`, `demo.run`, `check_demo.check`, `contract.fresh_job_cards` |
| Portal ERPNext client (pattern) | One-module REST v2 client with error mapping | `ERP/portal/terminal/erpnext.py:22-128` | `ERPNext()._call/_list`; `ERPNextError` (refusal, safe text) vs `ERPNextUnavailable` (unreachable, 401 or 5xx) |
| Terminal role and user (pattern) | Least-privilege API user | `masters.py:124-135,491-527` | Role `Shop Floor Terminal`, user `shopfloor.terminal@ombakmetal.example`, keys from site config |

**Does not exist yet:** a CRM outbound client, CRM ERP-sync state, a CRM integration role or user in ERPNext, ERPNext Custom Fields, and any job runner.
