# Test Baseline (HEAD `b90682a`, 2026-10-14)

| Command | Result | Notes |
|---|---|---|
| `cd CRM && docker compose exec -T -e POSTGRES_TEST_DB=test_crm_recon web python manage.py test --noinput sales` | **Ran 155 tests in 57.8 s, OK, exit 0** | crm chunk run. The test DB was created and destroyed. Expected 4xx log lines appear. `bash CRM/scripts/test.sh` is the same thing on the default `test_crm` DB |
| `cd ERP && bash scripts/test.sh` | **Ran 32 tests in 22.781 s, OK, exit 0** (58 s wall) | Runs on `test.localhost` only. Counts: alert 4, defect_log 7, reports 12, setup_masters 5, smoke 1, workspace 3 |
| `cd ERP && bash scripts/test-portal.sh` | **Ran 63 tests in 11.286 s, OK, exit 0**, 0 skipped (the 6 live contract tests ran) | Runs on `contract.localhost`; `contract.py:18` refuses any other site |
| `cd ERP && docker compose exec -T backend bench --site localhost execute ombak_mfg.setup.check_demo.check` | **18/18 PASS, "All demo checks passed.", exit 0** | Run in this recon (read-only counts). This is the demo-site invariant 004 must keep |

Cross-check: counting `def test_` gives CRM 155, ombak_mfg 32 and portal 63, which agrees with the runs. The prior logs `.specship/artifacts/test-run-erp.log` and `test-run.log` agree too (erp chunk). There are no failing baselines.

## Frameworks and fixtures
- **CRM:** Django `TestCase` on PostgreSQL. `CRMTestCase` (`CRM/sales/tests/base.py:25-73`) provides the manager `hafiz` and reps (`self.rep = siti`), the products `self.tray` (FG-CT-300, 85) and `self.frame` (FG-EBF-1000, 1450), and the helpers `account()` (default: the ERPNext customer "Tanjung Electrical Contractors Sdn Bhd"), `deal()` and `quote(deal, lines, status)`.
  - Concurrency tests use `TransactionTestCase` with threads (`test_auth.py:79-119`, `test_quotes.py:259-292`).
  - No CRM test fakes an external system.
- **Portal (pattern for 004):**
  - `FakeERPNext` (`ERP/portal/terminal/tests/fakes.py`) is patched in with `mock.patch("terminal.views.erpnext_client")` (`tests/base.py:18-20`);
  - the client tests mock `session.request` and assert the exact URL, headers and body (`test_erpnext_client.py:20-25`);
  - the live contract tests are skipped unless `CONTRACT_FIXTURE` is set (`test_contract.py:23`) and override `ERPNEXT_SITE` to the contract site (`:24`).
- **ombak_mfg:** `IntegrationTestCase` with `before_tests = setup_masters` (`hooks.py:267`) and `tearDown: frappe.db.rollback()`. The least-privilege proof is `test_terminal_role_is_least_privilege` (`tests/test_setup_masters.py:89-108`); idempotency is `test_second_run_adds_nothing` (`:46-55`).

## Coverage gaps that matter for 004
- No test covers **concurrent Won**: `test_deals.py:94-108` and `test_rules.py:114-120` are single-request.
- Nothing asserts the reports and My day stay unchanged when a deal is won. They are covered only by `test_home_reports.py` with seeded states.
- There is no CRM-side harness for live ERPNext tests. The Host-routed site choice works only via `backend:8000` (see open question 8).
