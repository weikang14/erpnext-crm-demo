# Brownfield Contract Inputs

**Mode: Full.** The change spans two packages and stacks (`CRM/` Django + PostgreSQL, and `ERP/` ERPNext + ombak_mfg). It also crosses four boundaries:
- persistence: CRM migration `0004`, and maybe an ERPNext Custom Field;
- auth: a new least-privilege ERPNext API user, with token secrets in site config and CRM env;
- an external API: the first outbound HTTP from the CRM, to ERPNext REST v2;
- networking: two Compose projects that share no network today.

Sources: `chunks/crm.md`, `chunks/erp.md`, spot-checked against HEAD `b90682a` in this recon. Details are in the sibling files `preserved-behaviors.md`, `change-impact-map.md` and `open-questions.md`.

## Scope Classification
- Type: integration-change
- Repo(s): one git repo, two areas: `CRM/` (sales CRM, mission 003) and `ERP/` (ERPNext v16.37.0 + `ombak_mfg`; `ERP/portal` is reference only)
- Affected components:
  - CRM: the Won workflow (`Opportunity.mark_won`, `deal_won`, the deal page), a new ERPNext REST client, CRM settings, compose and requirements, and migration `0004`;
  - ERP: `ombak_mfg` `setup_masters` (CRM role, CRM user, maybe a Custom Field), the compose `create-site` config, and the contract-test script.

## Existing Behavior To Preserve
1. When a rep or manager marks an in-scope open deal Won with a sent quote, the current system does all of this in one transaction under the deal row lock: the quote becomes `accepted`, `deal.amount` = the quote total, `closed_at` = now, one `StageChange(→won)` is written, the flash says `Won: {title}, MYR {amount:,.2f}.`, and the response redirects to the deal (`CRM/sales/models.py:284-292`, `CRM/sales/views/opportunities.py:146-155`; `WON-2`).
2. When there is no sent quote, or the deal is closed, the current system refuses with "Send a quote before marking the deal won." or "This deal is closed." and changes nothing (`CRM/sales/rules.py:53-57`; `WON-1`).
3. When Won is clicked twice, the second POST waits on the row lock, gets "This deal is closed.", and nothing is applied twice (`models.py:266-267`).
4. When a deal is won, the current system makes it and its quotes read-only, hides every action, and shows "Won on {date}". It can't be reopened (`detail.html:10-27`; `CLOSED-1`, `EDIT-4`).
5. Win rate, forecast "won in quarter" and My day "won this month" are computed only from `stage`, `closed_at` and `amount` in the CRM DB (`CRM/sales/reports.py:37-61`, `CRM/sales/views/home.py:34-35`).
6. Won and Lost are reachable only through their own POSTs, never through Move (`rules.py:47-48`; `MOVE-3`).
7. Won ignores leftover draft or pending quotes and `valid_until` (crm chunk, live data).
8. Another rep's deal answers 404 on every deal route, and the manager sees all (`CRM/sales/access.py:23-25,41-42`; AC19).
9. CSRF and POST-only state changes; the sign-in lockout; `GuardedUserAdmin`; CSP with no inline script or style and no `on*=`; the friendly 500 with no traceback; errors beside fields with focus moved to them; every page works without JS (`CRM/crm/settings.py:37-42,76`; `test_security.py:102,117-124`; `app.js:1-11`).
10. Money is `Decimal`, half-up per line, then summed; MYR only; quotes say "excluding SST" (`rules.py:21-32`).
11. On ERPNext `localhost`, `check_demo.check` passes 18/18. Every submitted SO has grand_total > 0, and every Work Order comes from a Production Plan (`ERP/apps/ombak_mfg/ombak_mfg/setup/check_demo.py:12-62`).
12. `demo.run` stays idempotent via `po_no LIKE 'DEMO-%'` (`demo.py:25,83-85`). The 19 demo SOs (SAL-ORD-2026-00001..00019) are untouched.
13. Nothing auto-creates Production Plans or Work Orders from an SO (no `doc_events`, `hooks.py:147`). The planner does it.
14. The `Shop Floor Terminal` role and user are unchanged. CT-7 still gets 403 on Sales Invoice GET and Work Order POST (`ERP/portal/terminal/tests/test_contract.py:67-72`).
15. `setup_masters` stays idempotent (`test_setup_masters.py:46-55`), and tests never write to `localhost` (`test.localhost` / `contract.localhost`; guard `contract.py:18`).

## New Or Changed Behavior
These are written as the open design space. The bracketed tags point to `open-questions.md`, which has the options and the recommended defaults.
1. When a deal is marked Won, the changed system should bring about **exactly one** ERPNext Sales Order for the deal's accepted quote. *When* it is created is open: inside the Won transaction, right after commit, or in the background. Whether an ERP failure blocks Won is also open. **[Q1]**
2. The SO is built from CRM data: company `Ombak Metal Works Sdn Bhd`, `transaction_date` = the local date of `closed_at`, one item per quote line (`item_code`, `qty`). These are open:
   - the customer resolution: create, refuse or map **[Q2]**;
   - draft or submitted **[Q3]**;
   - the delivery date source **[Q4]**;
   - the tax treatment **[Q5]**;
   - the price, discount and rounding mapping, and whether `grand_total` must equal `deal.amount` **[Q6]**.
3. The SO carries a CRM reference that makes create and retry idempotent. A retry looks the reference up before any POST. Which field holds it (`po_no` or a unique Custom Field), and its value, is open. **[Q7]**
4. The CRM records the outcome on the deal (status, SO name, safe error text) and shows it on the deal page using the existing chips, panels and messages. Who may retry and how (a button, a command, or automatic) is open. **[Q1]**
5. When ERPNext refuses or is unreachable, users see a plain-text reason with HTML stripped and never a traceback. When the write may have landed, the text says to check ERPNext (the `ERP/portal/terminal/erpnext.py:107-128` pattern). Whether Won is kept is open. **[Q1]**
6. ERPNext gains a dedicated least-privilege CRM API user and role, with keys from site config. The exact perms are open. **[Q11]**
7. The CRM reaches ERPNext by a route that lets the contract tests target `contract.localhost`, never the demo site. **[Q8]**
8. Behavior for existing won deals **[Q9]** and for quotes past `valid_until` at Won **[Q10]** is open.
9. A won deal whose total is 0 (every line discounted 100 %, allowed by `quote_line_discount_range`) must not produce a zero-value submitted SO, because that would break `check_demo.py:28`. Skip it with a status, or refuse; this is a detail for the contract.
10. The docs' false claims are corrected: "ERPNext adds tax on the order" (`README.md:290`) and "without mapping" (`README.md:165-166`).

## Regression Tests To Generate
1. Existing behavior regression:
   - `WON-1`, `WON-2`, `CLOSED-1`, `EDIT-4` and `MOVE-3` pass unchanged with the ERP client faked as **down** and as **refusing**. Won still commits `amount`, `closed_at`, `StageChange` and the accepted quote (unless Q1 = A).
   - **Two concurrent Won POSTs** (`TransactionTestCase` + threads, like `test_quotes.py:259-292`) give exactly one Won, one "This deal is closed.", and at most **one** ERP create call.
   - The reports and My day won counts and values are identical whether the ERP push succeeded or failed.
   - Another rep gets 404 on Won and on any new retry route. GET on the new routes gives 405. A POST without CSRF is refused.
   - The deal page has no `on*=` and no inline script or style, and works without JS. An ERP error never produces the 500 page.
   - ERP: `test_second_run_adds_nothing` still passes with the new role, user and field. `test_terminal_role_is_least_privilege` and CT-7 are unchanged. `check_demo.check` on `localhost` still passes 18/18 after the full test run.
2. New behavior test (the expected values depend on the Q answers):
   - Won → one create call with the expected payload (customer, company, dates, items, reference, discount fields, `disable_rounded_total`, docstatus).
   - ERPNext refusal (417) → the chosen Q1 outcome, with the stored and flashed message HTML-stripped and no `exception` text.
   - Timeout or connection error → status pending/failed; Retry looks up by reference, finds the landed SO, and stores its name **without a second POST**.
   - Retry when the lookup finds nothing → exactly one POST. Retry is allowed for the owner and the manager, and refused for others (404).
   - Customer missing → the Q2 behavior. Account names with HTML or quotes travel only as JSON data and are URL-quoted in paths.
   - Leftover draft or pending quotes are ignored. A null contact is OK. Multi-line quotes map line for line.
   - The pure payload builder (`rules.py`) covers FG-CT-300 × 3 at 7.5 % (CRM 235.88) and at 12.5 % (CRM 223.13), × 40 at 7.5 %, a 0 % line, and the zero-total deal.
   - The delivery date follows the Q4 rule and is never before `transaction_date`.
   - Past won deals behave per Q9.
3. Integration/API shape test:
   - **Client unit tests** with a mocked `session.request`, in the `ERP/portal/terminal/tests/test_erpnext_client.py:20-25` style. They assert the exact URL (`/api/v2/document/Sales%20Order`), the headers (`Host`, `Authorization: token k:s`, `Accept`), the JSON body, the error mapping (401/5xx/RequestException → unavailable; 403 → setup text; 417/409 → refusal text) and the non-JSON fallback.
   - **Live contract tests on `contract.localhost` only**, skipped unless a fixture env var is set (the `test_contract.py:23-24` pattern):
     - create + submit an SO as the CRM user, then read it back by reference;
     - `grand_total` equals the CRM total for the rounding cases (Q6);
     - a duplicate reference is refused (409 for a unique Custom Field, 417 for `po_no`);
     - the CRM role is **denied** SO cancel/delete, Sales Invoice, Work Order and Job Card;
     - a bad secret → unavailable.

## Files Likely To Change
| File | Why | Risk | Required tests |
|---|---|---|---|
| `CRM/sales/models.py` | ERP sync state on `Opportunity` (or an `ErpOrder` one-to-one); a push/retry method that takes the deal lock and re-checks state. `mark_won` stays as is | High: the Won path and locks | WON-1/2, CLOSED-1, EDIT-4, concurrent Won, sync-state transitions |
| `CRM/sales/migrations/0004_*.py` (new) | New fields or a new model | Medium: runs on container start; 21 live won deals get defaults | Suite migrates the test DB; the backfill status per Q9 |
| `CRM/sales/erpnext.py` (new) | The only CRM HTTP module, copied from `ERP/portal/terminal/erpnext.py` | Medium-High: error mapping, secrets, untrusted names | Client unit tests (URL, headers, body, errors, HTML strip) and live contract tests |
| `CRM/sales/rules.py` | Add the pure SO-payload, delivery-date and discount mapping. **Don't touch** the existing money functions | Medium: money | Pure unit tests for the rounding cases and the zero total |
| `CRM/sales/views/opportunities.py` | `deal_won` triggers the push per Q1 and flashes success or warning; a new retry POST view | High: user-facing Won | Won OK, refused or unavailable; retry scope, 404, 405, CSRF |
| `CRM/sales/urls.py` | The retry route | Low | Route resolves; POST only |
| `CRM/sales/templates/sales/deals/detail.html` | ERP order row or panel, chip, SO name or Desk link, Retry form | Medium: CSP and accessibility | Content per status; no `on*=`; button only for allowed users |
| `CRM/crm/settings.py` | `ERPNEXT_*` from env, the timeout, a `sales` logger | Low | A settings smoke test; a failure is logged |
| `CRM/docker-compose.yml` | `ERPNEXT_*` env with demo defaults; network per Q8 | Medium: couples the stacks under Q8 = A | The container reaches `/api/method/ping` |
| `CRM/requirements.txt` | `requests==2.34.2` (or stdlib) | Low; needs a rebuild | Suite passes in the rebuilt image |
| `CRM/sales/tests/test_erp_*.py`, `CRM/sales/tests/base.py` | Fake client and fixtures | Low | n/a |
| `ERP/apps/ombak_mfg/ombak_mfg/setup/masters.py` | CRM role, perms and user (keys from `crm_api_key/secret`); a Custom Field per Q7 | Medium-High: Custom DocPerm freeze; idempotency | `test_second_run_adds_nothing`; new CRM least-privilege and key-from-config tests |
| `ERP/apps/ombak_mfg/ombak_mfg/tests/test_setup_masters.py` | New role, user and field tests | Low | n/a |
| `ERP/docker-compose.yml` | `create-site` sets `crm_api_key/secret`; maybe pin the network name (Q8) | Medium | `test.sh` 32 OK, `test-portal.sh` 63 OK, `check_demo` 18/18 |
| `ERP/scripts/test-portal.sh` or a new `ERP/scripts/test-crm-contract.sh` | Set the CRM keys on `contract.localhost`; run the CRM live contract tests | Medium: must never hit `localhost` | The contract suite itself |
| `README.md` | Fix the SST and "without mapping" claims; document 004 and its env | Low | n/a |

## Files To Avoid Touching
| File/Area | Reason |
|---|---|
| `CRM/sales/rules.py` `money`/`line_total`/`quote_total`/`check_won`/`check_move` | Quote totals, `deal.amount`, the README example 235.88, and the WON/MOVE tests |
| `CRM/sales/reports.py`, `CRM/sales/views/home.py` | Reports must not depend on ERP state |
| `CRM/sales/access.py` | Reuse the scopes as they are |
| `CRM/sales/views/auth.py`, `GuardedUserAdmin` in `CRM/sales/admin.py`, CSP in `CRM/crm/settings.py:37-42` | 003 security fixes (lockout, admin, AC22) |
| `CRM/sales/migrations/0001`-`0003` | Already applied live |
| `ERP/portal/**` | Pattern source only: copy it, don't import it or change it |
| `TERMINAL_ROLE`/`TERMINAL_PERMISSIONS`/`_integration_user` in `masters.py` | The CT-7 least-privilege contract |
| `ERP/apps/ombak_mfg/ombak_mfg/setup/demo.py`, `check_demo.py` | The demo invariants and the `DEMO-` marker |
| `ERP/apps/ombak_mfg/ombak_mfg/hooks.py` | No `doc_events` are needed: the CRM pushes |
| `ERP/Dockerfile`, ERPNext/frappe core | Pinned v16.37.0 |
| Site settings `add_taxes_from_taxes_and_charges_template`, `allow_against_multiple_purchase_orders` | Site-wide; change them only if Q5 or Q7 decides to |
| The 19 demo SOs on `localhost`; any test write to `localhost` | Demo data |
| `.specship/completed/**` | Archived missions |

## Local Conventions Workers Must Follow
- **CRM layering:**
  - `rules.py` stays pure, with no DB or HTTP;
  - workflow methods are `@transaction.atomic`, lock the deal row first, then re-check state;
  - views stay thin: `access` scope → method → catch `RuleError` → flash → redirect, or re-render with 400 through `detail_context`;
  - user text is a plain sentence.
- **CRM UI:** server-rendered; no inline script, style or `on*=`; 44 px controls; works without JS; reuse `msg msg-*`, `chip-*`, `.panel`/`<dl class="details">` and `.btn` POST forms with `{% csrf_token %}`.
- **HTTP client:**
  - one module, REST **v2 only**, a `requests.Session` with `Host`/`Accept`/`Authorization: token`;
  - `ERPNextError` (safe refusal text) vs `ERPNextUnavailable` (401, 5xx, network); strip HTML; never surface `exception`;
  - a timeout well under 30 s (10 s precedent); URL-quote names in paths; "check ERPNext" wording when a write may have landed;
  - no automatic retries unless Q1 = C.
- **Secrets:** env with demo defaults in compose (CRM); site config read by `setup_masters`, never committed (ERP).
- **ERP app:** tabs, ruff, line 110; constants plus an idempotent `_ensure` in `setup_masters`; `IntegrationTestCase` with `before_tests = setup_masters` and a `tearDown` rollback.
- **Tests:**
  - descriptive `test_*` names with the test-case ID as a trailing comment (`# WON-2`, `# CT-7`);
  - CRM `CRMTestCase` fixtures, `TransactionTestCase` + threads for concurrency;
  - the portal-style fake client plus a mocked `session.request`;
  - live contract tests are env-gated and only on `contract.localhost`.
- **Style:** black-style at about 120 columns in the CRM, `# fmt: skip` on hand-aligned literals, `# ponytail:` comments on deliberate shortcuts with their upgrade path.
- **Commits:** `[specship] 004 …` / `[specship] M<n> task <n.m>: …` / `[specship-fix] <symptom> | root-cause: <cause> | contract: 004`, with the `Co-Authored-By:` trailer.

## Baseline Commands
| Command | Current result | Notes |
|---|---|---|
| `cd CRM && docker compose exec -T -e POSTGRES_TEST_DB=test_crm_recon web python manage.py test --noinput sales` (or `bash CRM/scripts/test.sh`) | **155 tests, OK**, exit 0, 57.8 s | crm chunk run; 155 `def test_` counted |
| `cd ERP && bash scripts/test.sh` | **32 tests, OK**, exit 0 | `test.localhost` only |
| `cd ERP && bash scripts/test-portal.sh` | **63 tests, OK**, exit 0, 0 skipped | `contract.localhost`; the 6 live contract tests ran |
| `cd ERP && docker compose exec -T backend bench --site localhost execute ombak_mfg.setup.check_demo.check` | **18/18 PASS**, exit 0 | Read-only demo invariant, run in this recon |

## Open Questions Blocking Contract
See `open-questions.md` for the options, trade-offs and recommended defaults.
- Q1: push timing (in the transaction, after commit, or background), whether an ERP failure blocks Won, and the retry UX and who may retry. Default: after commit, Won always kept, a Retry button for the owner and the manager.
- Q2: accounts that aren't ERPNext customers: create, refuse or map manually; with or without an address. Default: create the Customer, no address.
- Q3: draft or submitted SO. Default: submitted.
- Q4: delivery date source. Default: Won date + 12 days.
- Q5: tax/SST (the site has no SST template, and REST inserts get 0 tax). Default: no tax rows, fix the README claim.
- Q6: price and rounding authority (CRM per-line half-up vs ERPNext per-rate Banker's, plus the whole-ringgit `rounded_total`). Default: a header `discount_amount` so `grand_total == deal.amount`, plus `disable_rounded_total`, verified by a contract test.
- Q7: idempotency key: `po_no` = quote number, or a unique Custom Field. Default: a Custom Field `crm_reference` holding the quote number.
- Q8: networking: the shared `erp_frappe_network` or `host.docker.internal:8080`. Default: the shared network, so contract tests hit `contract.localhost`, never the demo site.
- Q9: backfill the 21 existing won deals? Default: no.
- Q10: expired quotes at Won. Default: allowed, as today.
- Q11: the least-privilege CRM role and user perms. Default: a new `CRM Integration` role and user, mirroring 002.
