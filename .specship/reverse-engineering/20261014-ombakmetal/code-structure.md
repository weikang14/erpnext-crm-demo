# Code Structure (relevant parts)

## CRM (`CRM/`)
- `crm/settings.py`: env-driven settings (`:10-12`), CSP (`:37-42`), DB (`:64-74`), `LockoutBackend` (`:76`), TZ (`:91-93`), LOGGING with the `django` logger only (`:103-108`).
- `sales/models.py` holds all models. Workflow methods sit on the models: `Opportunity.mark_won` (`:284-292`), `_locked` (`:266-267`), `_set_stage` (`:269-274`), `Quote._lock` (`:460`).
- `sales/rules.py` holds pure functions with no DB or HTTP: money, gates and `RuleError` (`:1-57`). The module docstring makes this a rule.
- `sales/access.py`: per-user querysets (`:18-38`), `get` → 404 (`:41-42`), `manager_required` (`:45-53`). `is_manager`/`MANAGER_GROUP` live in `models.py:15-23`.
- `sales/views/*.py` hold thin views, one module per area. The Won view is `views/opportunities.py:146-155`; `detail_context` is `:103-119`.
- `sales/urls.py`: the route `deals/<int:pk>/won/` → `opportunity_won` (`:36`).
- `sales/templates/sales/**` holds the templates. Shared partials are `_stage.html`, `_field.html` and `quotes/_status.html`.
- `sales/static/sales/app.css` and `app.js` are small progressive enhancements: "every page works without this file" (`app.js:1`).
- `sales/migrations/0001_initial`, `0002_quote_revision` and `0003_ratelimit` are auto-generated. The next one is `0004_*`.
- `sales/management/commands/seed_demo.py` is the only management command.
- `sales/tests/`: one file per area plus `base.py` (`CRMTestCase`). The runner is `scripts/test.sh`.

## ERP (`ERP/`)
- `apps/ombak_mfg/ombak_mfg/setup/masters.py`: a constant-driven `setup_masters()` with the idempotent `_ensure` (`:167-175`). It also holds the role and user helpers `_terminal_role` (`:491-499`) and `_integration_user` (`:502-527`).
- `setup/demo.py` builds the demo transactions. `create_order` (`:202-216`) is the known-good Sales Order shape.
- `setup/check_demo.py` holds the demo invariants (`:12-62`).
- `setup/contract.py` holds the site-guarded contract fixtures (`:18`).
- `hooks.py`: `before_tests = setup_masters` (`:267`) and `scheduler_events` (`:269`). There is **no `doc_events`** (`:147` is commented out) and no `fixtures`.
- `tests/`: `IntegrationTestCase` with `factory.py` helpers.
- `portal/terminal/erpnext.py` is the **one module that does HTTP** (`:1-4`). There is also `fakes.py` (`FakeERPNext`), `tests/test_erpnext_client.py` (a mocked session) and `tests/test_contract.py` (live, skipped unless `CONTRACT_FIXTURE` is set, `:23`).

## Naming
- Test IDs go in trailing comments: `# WON-2` (`CRM/sales/tests/test_deals.py:102`), `# CT-7` (`ERP/portal/terminal/tests/test_contract.py:67`), `# DEMO-1`.
- `# fmt: skip` marks hand-aligned literals in the CRM, and `# ponytail:` marks deliberate shortcuts (`CRM/crm/settings.py:96`).
- The ERPNext integration user follows `<name>@ombakmetal.example` (`masters.py:124`). Roles are Title Case (`masters.py:127`).
