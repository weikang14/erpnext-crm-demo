# Cross-Cutting Concerns

## Transactions and locking (CRM)
- Workflow methods are `@transaction.atomic` and lock the **deal row** first (`CRM/sales/models.py:266-267`). `Quote._lock` (`:460`) takes the same lock, so Won, Lost, Send, Revise, Edit and Reassign are serialised per deal. The state is re-checked under the lock.
- **An HTTP call inside `mark_won` would hold the deal lock for the whole call (up to gunicorn's 30 s).** An exception would roll the Won back. If ERPNext committed but the response was lost, the CRM rolls back while the SO exists: a ghost order.
- ERPNext insert+submit is one DB transaction on its side, so a timed-out POST either fully landed or didn't. Before any re-POST, look up by the reference (erp chunk).

## Auth and authorization
- CRM: `@login_required`, then `access.*` scopes (rep sees own, manager sees all, else 404; `CRM/sales/access.py:18-42`), then `manager_required` (`:45-53`). `is_manager` lives in `models.py:18-23`.
- CRM: `LockoutBackend`, 10 tries per 15 min, on every sign-in path (`CRM/crm/settings.py:76`, `views/auth.py:17-31`). `GuardedUserAdmin` (`admin.py:30-44`).
- ERPNext: token auth per API user. Least privilege comes through a dedicated Role with Custom DocPerms (`masters.py:491-499`).
  - **Side effect:** the first Custom DocPerm on a doctype copies all of its standard DocPerms into Custom DocPerm, which then override the standard ones (live: Employee, Job Card, Work Order, Workstation). A CRM role on Sales Order or Customer would freeze those doctypes the same way.

## Validation and errors
- CRM rule failures are a `RuleError` with a plain sentence, shown verbatim (`CRM/sales/rules.py:18-19`).
- CRM unhandled exceptions give a friendly 500 with no traceback (`sales/templates/500.html`, test `UI-2` `test_security.py:102`).
- ERPNext errors: map them like `ERP/portal/terminal/erpnext.py:107-128`. Strip HTML, never show `exception`, and say "check ERPNext" when a write may have landed (`ERP/portal/terminal/views.py:24-28`, `test_recovery.py:53`).
- Account names are **untrusted** (live names include `<img src=x onerror=…>`). Send them only as JSON values and URL-quote them in paths (`erpnext.py:71` pattern). Escape ERPNext text on the way back; Django autoescape does this in templates.

## Security headers
CSP is `'self'` with `frame-ancestors 'none'` (`CRM/crm/settings.py:37-42`). A plain `<a href>` to ERPNext Desk is fine; an iframe or a form posting to ERPNext is not. Inline script and style are forbidden (`test_security.py:117-124`).

## Logging and observability
Only the `django` logger, on the console at INFO (`CRM/crm/settings.py:103-108`). The app code has no `logging.getLogger`, and the root logger has no handler. **An integration failure would vanish** unless 004 adds a `sales` logger.

## Config and secrets
Everything comes from env with demo defaults (`CRM/docker-compose.yml:22-28`, AC22 style). ERPNext keys live in site config, never in git (`masters.py:502-504`).

## Time
`TIME_ZONE = Asia/Kuala_Lumpur`, `USE_TZ = True` (`CRM/crm/settings.py:91-93`). `closed_at` is UTC-aware, so the SO `transaction_date` should be `timezone.localdate(closed_at)`.

## Rate limiting, caching, feature flags
Only sign-in and enquiry rate limits (`RateLimit`, `CRM/sales/ratelimit.py:21-35`). No feature flags.
