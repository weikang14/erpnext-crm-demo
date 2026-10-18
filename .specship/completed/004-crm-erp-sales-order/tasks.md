# Won deal → ERPNext sales order: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (SpecShip
> `specship-build` dispatches one fresh worker per task). Each task: turn its test IDs from
> `artifacts/test-cases.md` into runnable tests → RED → implement → GREEN → commit.

**Goal:** a Won deal in the CRM produces a submitted ERPNext sales order equal to the accepted
quote (customer created if missing, SST for Malaysia, exact net total), without ever losing
the Won or creating a duplicate.

**Architecture:** the CRM pushes after the Won commits (same request, 10 s timeout) through a
small stdlib REST v2 client; outcome stored on the deal; resend form for failures. ERP side:
idempotent `setup_masters` additions (role + user, unique `crm_reference` field, SST
template). Network: optional compose override joining the ERP network.

**Tech stack:** Django 6.1 / Python 3.13 / PostgreSQL 17 (CRM); ERPNext v16 / Frappe app
`ombak_mfg` (ERP); Docker Compose.

**Spec:** `requirements.md` (AC1-22, FM1-16, Clarifications), `design.md`,
`artifacts/api-contract.md`, `artifacts/test-cases.md` (+ `edge-cases.md`,
`api-contract-tests.md`, `browser-flows.md`, `ui-state-sequences.md`), brownfield recon
`.specship/reverse-engineering/20261014-ombakmetal/brownfield-contract-inputs.md`.

## Global Constraints
- No new CRM dependency: the HTTP client uses `urllib.request` (stdlib). ERPNext REST **v2
  only**. Timeout 10 s per call.
- Money stays `Decimal`; CRM money/won/move rules in `rules.py`, `reports.py`, `access.py`
  are not changed (only read).
- Won keeps every 003 rule; the ERP call is never inside the Won transaction and no row lock
  is held during HTTP (claim via `erp_status = sending`).
- Secrets only from env (CRM) / site config (ERP); never in messages, `erp_error`, logs or
  commits. Never read Frappe's `exception` field.
- CRM UI: existing classes only, no inline style/script/`on*=`, 44 px controls, works
  without JS, form errors by the field with 400 re-render (`detail_context`) and focus.
- ERP app: tabs, ruff, line 110; idempotent `_ensure`-style setup; tests never write to
  `localhost` (`test.localhost` / `contract.localhost` only).
- CRM tests: `docker compose exec -T -e POSTGRES_TEST_DB=test_crm_<task> web python manage.py
  test --noinput sales` from `CRM/` (unique DB name per worker). Existing 155 CRM, 32 ERP and
  63 portal tests stay green.
- Commits: `[specship] M<n> task <n.m>: <summary>` + `Co-Authored-By: Claude Opus 5.5
  <noreply@anthropic.com>`; only the task's files (`git add <paths>`).
- Test IDs as trailing comments on test methods (`# SEND-2`), house style.

## Review Focus
Inputs the spec implies but no generated case pins; each has its test in the owning task.
1. Account names that need URL-quoting (`&`, `/`, `'`, `#`, non-ASCII, e.g. "A&B / Ng's Sdn
   Bhd") in `GET Customer/<name>` → found and reused, not re-created (task 2.2, 2.4).
2. An ERPNext error message that echoes the request (could contain the API key) or is very
   long → stored text has no key/secret, ≤ 300 chars (task 2.2).
3. A 200 reply that isn't JSON or has no `data` → failed "ERPNext sent an unexpected reply."
   (no crash, no adoption) (task 2.2, 2.4).
4. Quote lines with fractional qty (0.5) or awkward prices (33.33 × 3 at 33.3 %) → header
   discount still makes the net total exact (task 2.3).
5. A Won at 23:59 KL on the last day of a month → default delivery date and
   `transaction_date` use the KL date, not UTC (task 3.1).

---

## Milestone 1: ERP side (setup_masters additions)

### Task 1.1: SST account and template; customer group and territories
**Files:** modify `ERP/apps/ombak_mfg/ombak_mfg/setup/masters.py` (new `_sst()`,
`_crm_masters()` called from `setup_masters()` after `_parties()`); test
`ERP/apps/ombak_mfg/ombak_mfg/tests/test_setup_masters.py`.
**Interfaces — produces:** constants `SST_ACCOUNT = f"SST Payable - {ABBR}"`,
`SST_TEMPLATE = f"Malaysia SST - {ABBR}"`, `SST_RATE = 10`; Customer Group "Commercial" and
Territories "Malaysia", "Singapore" exist with `is_group = 0`.
- [ ] RED: tests for ERP rows about the SST account (Tax, under Duties and Taxes - OMW), the
  template (one row On Net Total, rate 10, account SST Payable, `is_default` 0, company OMW),
  groups not group records, idempotency (run twice, counts unchanged), demo SOs untouched.
  Run `bash ERP/scripts/test.sh` → the new tests fail.
- [ ] GREEN: implement `_sst()` / `_crm_masters()` with `_ensure`; rerun → all pass (32 + new).
- [ ] Commit.

### Task 1.2: `crm_reference` custom field on Sales Order
**Files:** `masters.py` (new `_crm_reference_field()` via
`frappe.custom.doctype.custom_field.custom_field.create_custom_field`, idempotent); test file
as 1.1.
**Produces:** Sales Order field `crm_reference` (Data, `unique` 1, `read_only` 1, `no_copy` 1,
`insert_after` "po_no", label "CRM reference").
- [ ] RED: ERP rows for the field's properties, a second SO with the same value refused
  (unique), `po_no` untouched, idempotency. Run → fail.
- [ ] GREEN: implement; `bench --site test.localhost migrate` happens in `test.sh`; rerun → pass.
- [ ] Commit.

### Task 1.3: CRM Integration role and user; site config wiring
**Files:** `masters.py` (constants `CRM_ROLE = "CRM Integration"`, `CRM_USER =
"crm.integration@ombakmetal.example"`, `CRM_PERMISSIONS = {doctype: [ptypes]}`, functions
`_crm_role()`, `_crm_user()` copying the `_terminal_role()` / `_integration_user()` pattern,
keys from `frappe.conf` `crm_api_key` / `crm_api_secret`); `ERP/docker-compose.yml` (create-site:
`bench --site localhost set-config crm_api_key "$$CRM_API_KEY"` and secret, env defaults
`crm-demo-key` / `crm-demo-secret`); tests in `test_setup_masters.py`.
**Produces:** a user whose API key/secret equal the site config; permissions: Sales Order
read/create/submit (+ write only if submit needs it), Customer read/create, Address create,
Item read, Sales Taxes and Charges Template read, plus the link-doctype reads the contract
test proves necessary.
- [ ] RED: PERM-* and ERP-* rows (role has exactly these perms; user has only this role; 403
  for SO cancel/delete, Sales Invoice, Work Order, Job Card via `frappe.has_permission` as the
  user; terminal role and standard Sales User/Manager perms on SO and Customer unchanged).
  Run → fail.
- [ ] GREEN: implement; rerun `bash ERP/scripts/test.sh` and `bash ERP/scripts/test-portal.sh`
  → all pass.
- [ ] Commit.

## Milestone 2: CRM data, client, mapping, send

### Task 2.1: Deal fields and migration 0004
**Files:** modify `CRM/sales/models.py` (`Opportunity`); create
`CRM/sales/migrations/0004_opportunity_erp.py` (makemigrations); tests `CRM/sales/tests/test_erp.py`
(new) and the BRT rows in existing `test_deals.py`.
**Produces:** `Opportunity.delivery_date` (DateField, null), `erp_status` (choices
`not_sent`/`sending`/`sent`/`failed`, default `not_sent`), `erp_order` (CharField 140, unique,
null), `erp_error` (TextField, blank), `erp_attempted_at` (DateTimeField, null);
`Opportunity.mark_won(by, delivery_date=None)` stores the date inside the existing transaction
(rules unchanged); `Opportunity.claim_send(now) -> bool` (conditional `UPDATE … WHERE
erp_status IN (not_sent, failed) OR (erp_status = sending AND erp_attempted_at < now - 2 min)`,
sets `sending` + `erp_attempted_at`, returns whether it claimed); `Opportunity.record_send(status,
order="", error="")` (plain update, no lock).
- [ ] RED: BRT rows for Won (all 003 Won effects, twice-refused, closed read-only, reports
  unchanged), CLAIM-* (second claim refused, stale claim allowed, no lock held during HTTP),
  migration of existing won deals to `not_sent`. Run → fail.
- [ ] GREEN: implement; `makemigrations`; rerun the full CRM suite → pass (155 + new).
- [ ] Commit.

### Task 2.2: ERPNext REST client (stdlib) and fake
**Files:** create `CRM/sales/erpnext.py`, `CRM/sales/tests/fakes.py`; tests in `test_erp.py`.
**Produces:**
```python
class Unavailable(Exception): ...          # timeout, connection error, 401, 5xx
class Refused(Exception): ...              # other 4xx; str() = safe message (stripped, ≤300 chars)
class Client:
    def __init__(self, url, site, key, secret, timeout=10): ...
    def find_order(self, reference) -> dict | None        # call 1 (docstatus < 2)
    def get_customer(self, name) -> dict | None           # call 2 (404 → None), URL-quoted
    def create_customer(self, payload) -> dict            # call 3
    def create_address(self, payload) -> dict             # call 4
    def tax_rows(self, template) -> list[dict]            # call 4b: charge_type, account_head, rate, description
    def create_order(self, payload) -> dict               # call 5, docstatus 1
def client_from_settings() -> Client | None               # None when ERPNEXT_URL unset/empty
```
`FakeERPNext` in `fakes.py` has the same methods, in-memory orders keyed by `crm_reference`
(raising `Refused` on a duplicate), customers matched case-insensitively, configurable failures.
- [ ] RED: ERR client rows + Review Focus 1-3 (headers Host/token/JSON, timeout 10, quoting,
  error mapping table from `api-contract.md`, HTML stripped, join with a space, non-JSON body,
  no `exception`, no secret in text, 200 without `data` → `Refused("ERPNext sent an unexpected
  reply.")`), with `urllib.request.urlopen` mocked. Run → fail.
- [ ] GREEN: implement; rerun → pass.
- [ ] Commit.

### Task 2.3: Mapping (pure functions)
**Files:** create `CRM/sales/erp.py` (mapping part); tests in `test_erp.py`.
**Produces:**
```python
def territory(account) -> str                 # "Singapore" | "Malaysia"
def taxed(account) -> bool                    # True for Malaysian states
def customer_payload(account) -> dict
def address_payload(account, customer) -> dict | None   # None without address + city
def header_discount(lines, amount) -> Decimal            # Σ qty × unit_price − amount
def order_payload(deal, quote, customer, tax_rows, today, delivery_date) -> dict
```
- [ ] RED: CUST-* (payload rows), SO-*, TOT-* (incl. 235.88/19.12 and Review Focus 4), TAX-*
  (rows copied from the template input, none for Singapore), ZERO-* (zero total detected).
  Run → fail.
- [ ] GREEN: implement with `Decimal` and `quantize(Decimal("0.01"))`; rerun → pass.
- [ ] Commit.

### Task 2.4: `send_order` orchestration
**Files:** `CRM/sales/erp.py` (add `send_order`); tests in `test_erp.py`.
**Produces:** `send_order(deal, client, today, delivery_date=None) -> Outcome` where
`Outcome = namedtuple("Outcome", "status order message level")` (`level` in `success`,
`warning`, `error`) and the deal's `record_send` is called with the result. Order of calls:
claim → zero check → `find_order` (adopt) → `get_customer` / `create_customer` (+ address) →
`tax_rows` (taxed only) → `create_order` → on `Refused` re-`find_order` (adopt) → net-total
check (warning, status sent) → record. `client is None` → status unchanged, message "ERP link
not configured". Any other exception → failed "Unexpected error while sending; see the server
log." and `logger.exception` without secrets.
- [ ] RED: IDEM-*, SEND-* (orchestration rows), ERR-* (flow rows incl. ERR-13..15), CFG-*, address-refused and
  cancelled-order clarifications, Review Focus 1 and 3, with `FakeERPNext`. Run → fail.
- [ ] GREEN: implement; rerun full CRM suite → pass.
- [ ] Commit.

## Milestone 3: CRM screens

### Task 3.1: Won form with delivery date; send after Won
**Files:** `CRM/sales/forms.py` (new `WonForm` with `delivery_date`, default KL today + 14,
`min` today, rejects past); `CRM/sales/views/opportunities.py` (`deal_won`: validate form →
`mark_won(by, delivery_date)` → `send_order(...)` → flash → redirect; invalid → 400 via
`detail_context(won_form=form)`); `CRM/sales/templates/sales/deals/detail.html` (date field
beside "Mark won"); tests in `test_deals.py` / `test_erp.py`.
- [ ] RED: WON-D-*, SEND-* (view rows: flash texts, Won kept on every ERP failure, timing with
  a slow fake), BRT rows for the Won view and template, Review Focus 5. Run → fail.
- [ ] GREEN: implement; rerun full CRM suite → pass.
- [ ] Commit.

### Task 3.2: Resend route and permissions
**Files:** `CRM/sales/urls.py` (`deals/<int:pk>/erp/send/`, name `opportunity_erp_send`);
`views/opportunities.py` (`deal_erp_send`: POST only, `access.opportunities` scope, owner or
manager, won and not sent, `WonForm`-style date form replacing `delivery_date`, refusals per
Clarifications); tests in `test_erp.py`.
- [ ] RED: RES-* (owner, manager, other rep 404, GET 405, no CSRF 403, sent/open/lost/sending
  refusals, date replace, past or missing date 400, double click via the claim). Run → fail.
- [ ] GREEN: implement; rerun → pass.
- [ ] Commit.

### Task 3.3: ERP panel on the deal and My day panel
**Files:** `CRM/sales/templates/sales/deals/detail.html` (+ an `_erp_panel.html` include);
`views/opportunities.py` (`detail_context` adds `erp_configured`, `erp_desk_url`, send form);
`CRM/sales/views/home.py` + `templates/sales/home.html` ("ERP orders not created": failed
sends, own deals / manager's team, hidden when none); tests in `test_erp.py`,
`test_home_reports.py`.
- [ ] RED: PANEL-* (chips `chip-green` sent + link `{ERPNEXT_DESK_URL}/app/sales-order/<name>`
  + attempted time; `chip-red` failed + reason + time (stale `sending` shown as failed); amber
  warning for a mismatch; plain chip not sent / not configured / fresh `sending`; form only for owner/manager and only when configured), DAY-*
  (failed + stale `sending`, constant query count), UI-3 (no inline style/script). Run → fail.
- [ ] GREEN: implement; rerun full CRM suite → pass.
- [ ] Commit.

## Milestone 4: Wiring, live contract, deploy

### Task 4.1: Settings, compose override, live contract tests
**Files:** `CRM/crm/settings.py` (`ERPNEXT_URL`, `ERPNEXT_SITE`, `ERPNEXT_API_KEY`,
`ERPNEXT_API_SECRET`, `ERPNEXT_DESK_URL` from env, empty defaults); create
`CRM/docker-compose.erp.yml` (web joins external network `erp_frappe_network`, env with demo
defaults `crm-demo-key` / `crm-demo-secret`, `ERPNEXT_URL=http://backend:8000`,
`ERPNEXT_SITE=localhost`, `ERPNEXT_DESK_URL=http://localhost:8080`); create
`CRM/scripts/test-erp.sh` (ensures `contract.localhost` exists with `crm_api_*` config and
`setup_masters`, then runs `sales.tests.test_erp_contract` with `ERPNEXT_SITE=contract.localhost`;
refuses `localhost`); create `CRM/sales/tests/test_erp_contract.py` (skipped unless
`ERP_CONTRACT=1`).
- [ ] RED: NET-* (compose config renders; settings empty → not configured), CT-* and ACT-*
  (live: customer create, SO create+submit, net total exact, SST row for MY / none for SG,
  duplicate `crm_reference` refused, lookup finds it, integration user 403s), guard refuses
  `localhost`. Run `bash CRM/scripts/test-erp.sh` → fail.
- [ ] GREEN: implement; narrow `CRM_PERMISSIONS` to what the live tests prove (update 1.3's
  tests in the same commit if a link-doctype read is needed); rerun `test-erp.sh`,
  `bash CRM/scripts/test.sh`, `bash ERP/scripts/test.sh` → pass.
- [ ] Commit.

### Task 4.2: Deploy to the demo stack and probe
**Files:** `CRM/scripts/ui-probe/probe.mjs` (add a won deal's page with the ERP panel to the
size checks); no app code.
- [ ] Run `setup_masters` on `localhost` (set `crm_api_key/secret` config first), then
  `check_demo` → 18/18; restart the CRM with `-f docker-compose.yml -f docker-compose.erp.yml`;
  win one demo deal end to end and see the SO in ERPNext Desk (net total = quote, SST row).
- [ ] RED/GREEN for the probe addition (fails without the panel page, passes with it).
- [ ] Commit (probe + any compose fix found while deploying).

(README "Part 3" section, 中文, CHANGELOG and screenshots are written in the SHIP phase.)
