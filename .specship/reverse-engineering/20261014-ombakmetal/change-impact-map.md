# Change Impact Map (mission 004)

Exact files depend on the open questions. The **[Qn]** tags mark where a decision changes the list.

## Files likely to change: CRM
| File | Change | Downstream effect |
|---|---|---|
| `CRM/sales/models.py` | Sync state on `Opportunity` (e.g. `erp_order` unique-when-set, `erp_status`, `erp_error`, `erp_synced_at`) or a one-to-one `ErpOrder`. A push or retry method that takes the deal lock and re-checks state. `mark_won` itself stays as is | Every deal query sees the new columns. Reports are unaffected if they keep filtering on `stage`/`closed_at`/`amount` |
| `CRM/sales/migrations/0004_*.py` (new) | AddField(s) or CreateModel | Runs on container start (`CRM/Dockerfile:12`). Existing rows get the default status (open question 9) |
| `CRM/sales/erpnext.py` (new) | A REST v2 client copied from `ERP/portal/terminal/erpnext.py`: SO create, lookup by reference, customer GET/create **[Q2]**, error mapping, HTML strip, 10 s timeout | The only HTTP module in the CRM |
| `CRM/sales/rules.py` | Add pure functions: deal → SO payload, delivery date **[Q4]**, rate/discount mapping **[Q6]**. **Do not change** `money`/`line_total`/`quote_total`/`check_won` | Pure, so unit-testable with no DB |
| `CRM/sales/views/opportunities.py` | `deal_won`: push after the Won commits **[Q1]** and flash success or warning. A new `deal_erp_retry` POST view, scoped through `access` | Won's response time now includes the ERP call (≤ timeout) if it is synchronous after commit |
| `CRM/sales/urls.py` | `deals/<int:pk>/erp/retry/` (name TBD) | n/a |
| `CRM/sales/templates/sales/deals/detail.html` | An "ERP order" row or panel with the status chip, the SO name/link and a Retry `.btn` form | Must keep CSP-clean markup with no `on*=` |
| `CRM/crm/settings.py` | `ERPNEXT_URL/SITE/API_KEY/API_SECRET` from env and `ERPNEXT_TIMEOUT`; a `sales` logger in `LOGGING` | n/a |
| `CRM/docker-compose.yml` | `ERPNEXT_*` env with demo defaults; maybe `networks: erp_frappe_network (external)` or `extra_hosts` **[Q8]** | Option A makes CRM `up` depend on the ERP stack existing |
| `CRM/requirements.txt` | `requests==2.34.2`, unless stdlib `urllib` is chosen | Needs `docker compose up -d --build` |
| `CRM/sales/tests/test_erp_*.py`, `CRM/sales/tests/base.py` | Fake client and fixtures; client, view and concurrency tests | n/a |
| `CRM/sales/admin.py` (optional) | Show the sync fields read-only | n/a |
| `CRM/sales/management/commands/<backfill>.py` (only if open question 9 = yes) | Batch push of past wins | n/a |
| `README.md` | Correct the SST claim (`:290`) and the "without mapping" claim (`:165-166`); document 004 and its env | Docs only |

## Files likely to change: ERP
| File | Change | Downstream effect |
|---|---|---|
| `ERP/apps/ombak_mfg/ombak_mfg/setup/masters.py` | A `CRM_ROLE` + `CRM_PERMISSIONS` constant, `_crm_role()`, `_crm_integration_user()` (keys from `crm_api_key/secret` in site config) **[Q11]**. Maybe a Custom Field such as `crm_reference` (unique) via `_ensure` **[Q7]**, and maybe Territories **[Q2]** | `setup_masters` must stay idempotent. Custom DocPerm freezes the Sales Order and Customer standard perms. The demo site gets them only after `setup_masters` is rerun there |
| `ERP/apps/ombak_mfg/ombak_mfg/tests/test_setup_masters.py` | CRM role least-privilege and key-from-config tests, mirroring `:73-108` | n/a |
| `ERP/docker-compose.yml` | `create-site`: `set-config crm_api_key/crm_api_secret` (like `:54-58`); maybe a `name:` pin on `frappe_network` **[Q8]** | Recreating `create-site` only sets config; it is idempotent |
| `ERP/scripts/test-portal.sh` or a new `ERP/scripts/test-crm-contract.sh` | Set the `crm_*` keys on `contract.localhost` and run the CRM live contract tests there | Must never target `localhost` |
| `ERP/apps/ombak_mfg/ombak_mfg/setup/contract.py` (maybe) | A site-guarded fixture (e.g. reset/cancel test SOs) | Guard stays at `:18` |

## Files that must not change
| File/Area | Reason |
|---|---|
| `CRM/sales/rules.py` `money`, `line_total`, `quote_total`, `check_won`, `check_move` | Quote totals, `deal.amount`, the README example 235.88, and the `WON-*`/`MOVE-*` tests |
| `CRM/sales/reports.py`, `CRM/sales/views/home.py` | They read won deals; they must stay unaffected by ERP state |
| `CRM/sales/access.py` | Reuse the scopes; don't widen them |
| `CRM/sales/views/auth.py`, `CRM/sales/admin.py` `GuardedUserAdmin`, CSP in `CRM/crm/settings.py:37-42` | Security behaviour from 003 (AC22, lockout fixes) |
| `CRM/sales/migrations/0001-0003` | Already applied live |
| `ERP/portal/**` | Copy the pattern; don't import across projects, and don't change the terminal |
| `masters.py` `TERMINAL_ROLE`/`TERMINAL_PERMISSIONS`/`_integration_user` | CT-7 least-privilege contract |
| `ERP/apps/ombak_mfg/ombak_mfg/setup/demo.py`, `setup/check_demo.py` | The demo invariants and the `DEMO-` marker (`demo.py:25,83-85`) |
| `ERP/apps/ombak_mfg/ombak_mfg/hooks.py` | No `doc_events` are needed: the CRM pushes |
| `ERP/Dockerfile`, ERPNext/frappe core | Version pin `v16.37.0` |
| Site settings `add_taxes_from_taxes_and_charges_template`, `allow_against_multiple_purchase_orders` | Leave them unless open question 5 or 7 decides otherwise; they are site-wide |
| `.specship/completed/**` | Archived missions |

## Migration and back-compat risks
- The 21 existing won deals get the new columns: what status do they show (open question 9)?
- There are 19 demo SOs (`DEMO-001..019`) on `localhost`. 004 must not edit them, and must not add zero-value SOs, because `check_demo` requires "every sales order has a value" (`check_demo.py:28`).
- The new ERPNext role and user reach `localhost` only after `setup_masters` is rerun (e.g. via `demo.run`, which is idempotent).
- The CRM image must be rebuilt if `requests` is added.
