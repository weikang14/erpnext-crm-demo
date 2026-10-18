# Chunk: CRM (`CRM/`), recon for mission 004 (won deal → ERPNext sales order)

Recon at HEAD `b90682a`, 2026-10-14. Read-only. The only command that touched a database was the
test run (it created and dropped its own `test_crm_recon` DB). Live-DB evidence comes from
`SELECT`s only, run as `docker compose exec -T db psql -U crm -d crm` from `CRM/`.

## Scope

- **In:** the Won flow, the data that exists when a deal is won, Product/Account vs the ERPNext masters,
  integration-relevant models, settings and env, network reachability from the CRM container to ERP,
  UI patterns for an "ERP order" status, the test baseline, conventions, and behaviours 004 must keep.
- **Out:** leads, enquiry, pipeline board, My day and report internals, except where they read won deals.
  The ERP side (ERPNext Sales Order API, API user and role, naming) belongs to the ERP chunk. It's cited
  here only to check the CRM's claims.
- **Type:** integration change. The CRM gains an outbound call. Today it has none.

## Stack & versions

| What | Version | Evidence |
|---|---|---|
| Python | 3.13 (container reports 3.13.16) | `CRM/Dockerfile:1` `FROM python:3.13-slim`; `python -c sys.version` in `web` |
| Django | 6.1.1 | `CRM/requirements.txt:1`; `django.__version__` in `web` |
| gunicorn | 26.2.0, `--workers 2 --worker-class gthread --threads 4`, **no `--timeout`, so 30 s by default** | `CRM/requirements.txt:2`; `CRM/Dockerfile:12` |
| psycopg[binary] | 3.3.6 | `CRM/requirements.txt:3` |
| whitenoise | 6.12.0 | `CRM/requirements.txt:4` |
| PostgreSQL | 17-alpine | `CRM/docker-compose.yml:6` |
| HTTP client | **none installed.** `pip list` in `web` shows only asgiref, Django, gunicorn, pip, psycopg(-binary), sqlparse, whitenoise | `docker compose exec -T web pip list` |

The image runs `migrate` and `createcachetable` on every start, then gunicorn (`CRM/Dockerfile:12`).
The code is bind-mounted (`CRM/docker-compose.yml:29`). A new dependency in `requirements.txt` needs
`docker compose up -d --build`.

## Won-deal flow (step by step)

1. **Button.** `CRM/sales/templates/sales/deals/detail.html:18-21` holds a POST form to
   `{% url 'opportunity_won' deal.pk %}` with a `btn btn-success` "Mark won" button. It renders only
   when `deal.is_open` (line 10). It is `disabled` with `aria-describedby="won-hint"` when there is no
   `sent_quote`. The hint is at line 25: "To mark this deal won, send the customer a quote first."
   There is no confirm step. `app.js:14-21` disables a submit button after the first click (it only
   helps when JS runs).
2. **URL.** `path("deals/<int:pk>/won/", opportunities.deal_won, name="opportunity_won")` at
   `CRM/sales/urls.py:36`.
3. **View.** `deal_won` at `CRM/sales/views/opportunities.py:146-155` is `@login_required` and
   `@require_POST`.
   - It loads the deal through `access.get(access.opportunities, ...)`, so a rep can win only their own
     deals and the manager can win any deal; anything else answers 404 (`access.py:23-25,41-42`).
   - It calls `deal.mark_won(request.user)`.
   - On success it flashes `messages.success(f"Won: {deal.title}, MYR {deal.amount:,.2f}.")`.
   - On `RuleError` it flashes `messages.error(str(error))`.
   - It always ends with `redirect(deal)`. There is no form and no 400 re-render.
4. **Model.** `Opportunity.mark_won` at `CRM/sales/models.py:284-292`, decorated `@transaction.atomic`
   (one DB transaction):
   - `deal = self._locked()` runs `select_for_update().get(pk)` on the **deal row** (`models.py:266-267`).
     Every quote workflow method takes this same lock first (`Quote._lock`, `models.py:460`), so Won,
     Send, Revise, Lost, Edit and Reassign are serialised per deal.
   - `quote = deal.sent_quote()` returns the first quote with `status="sent"` (`models.py:263-264`). The
     quote row itself is not row-locked, and Won does not bump `revision` (it saves the status directly).
   - `rules.check_won(deal.stage, quote is not None)` (`rules.py:53-57`):
     - if the stage is not open: "This deal is closed.";
     - if there is no sent quote: "Send a quote before marking the deal won.".
   - `quote.status = ACCEPTED`, then `save(update_fields=["status"])`.
   - `deal._set_stage(Stage.WON, by, amount=quote.total, closed_at=timezone.now())` (`models.py:269-274`):
     - creates a `StageChange(from, to="won", by, at=now)`;
     - sets `stage="won"` and `last_activity_at=now`;
     - sets `amount` to the **sum of rounded line totals** and `closed_at` to now (UTC-aware, `USE_TZ=True`).
   - `self.refresh_from_db()`.
5. **Not touched by Won:**
   - other quotes in `draft` or `pending` (a revision in progress) stay as they are. The live DB has
     3 won deals with a leftover draft or pending quote: deals 140, 142, 146, quotes 90, 93, 103.
   - activities.
   - `valid_until`. Won does not check it: 14 of 21 live won deals closed after the accepted quote's
     `valid_until` (a seed artefact, but it shows there is no guard).
6. **Double click.** The second POST waits on the deal row lock. It then sees `stage="won"`, and
   `check_won` raises "This deal is closed." as an error flash. The Won is not applied twice. No test
   covers concurrent Won: `test_deals.py:94-108` and `test_rules.py:114-120` are single-request.
7. **After Won, the deal is read-only:**
   - The `is_open` checks refuse Edit, Reassign, Lost, Move and New quote: `models.py:297,307,320,448`,
     `rules.py:45`, and the views at `opportunities.py:176,194`.
   - `Quote.editable` and `_require` need `opportunity.is_open` (`models.py:442,484`).
   - The page hides Move, Won, Edit, Reassign, Lost and New quote, and shows the banner
     `msg msg-success` "Won on {closed_at}" (`detail.html:27`).
   - Covered by tests `CLOSED-1` (`test_deals.py:125`) and `EDIT-4` (`test_deals.py:218`).
   - Closed deals can't be reopened (README "Limits").

## Data available at Won (exact fields)

**Opportunity** (`models.py:221-233`): `id` BigAutoField · `title` varchar 200 · `account` FK PROTECT ·
`contact` FK **nullable** (SET_NULL; 1 live won deal has none) · `owner` FK User PROTECT · `stage` ·
`amount` Decimal(12,2), set to the quote total at Won · `expected_close` date · `closed_at` timestamptz ·
`created_at`, `last_activity_at` · `lost_reason`/`lost_note` (unused when won) · `get_absolute_url()` → `/deals/<id>/`.

**Account** (`models.py:52-81`): `name` varchar 200, unique case-insensitive (`account_name_unique_ci`,
`Lower("name")`) · `registration_no` varchar 30, blank · `industry` · `address` varchar 200, blank ·
`city` 100, blank · `state`: required, one of 16 Malaysian states or federal territories, or "Singapore"
(`regions.py:14-31`) · `postcode` varchar 10, blank · `phone` 30, blank · `website` · `owner` FK, nullable.
`country` is a **property, not a field**: "Singapore" when the state is Singapore, otherwise "Malaysia"
(`models.py:79-81`). `region` is a property too. Seed accounts never set `registration_no`, `address` or
`postcode` (`seed_demo.py:161-165`). In the live DB only 2 of 42 accounts have a registration no., 1 has
an address and 3 have a postcode.

**Contact** (`models.py:84-95`): `name`, `job_title`, `email`, `phone`. **Owner**: `auth.User`; use
`display_name(user)` for full name or username (`models.py:26-27`).

**The accepted quote** (`models.py:397-455`): `status="accepted"` · `number`, a **property**:
`QT-{local year of created_at}-{pk:05d}`, e.g. `QT-2026-00133`, with no counter table (`models.py:428-430`) ·
`valid_until` date, `created_at` + 30 days at `start()`, not updated on send · `created_by` ·
`approved_by`/`approved_at`/`decision_note` · `sent_at` · `revision` · `total`, a property: `rules.quote_total(lines)`.

**QuoteLine** (`models.py:535-557`): `product` FK PROTECT · `qty` Decimal(10,2) > 0 · `unit_price`
Decimal(12,2), a **snapshot of `product.list_price` taken at add_line** (`models.py:473`) · `discount_pct`
Decimal(5,2), 0-100 · `total`, a property: `rules.line_total`. Product `item_code`, `name` and `uom` are
**not** snapshotted on the line. They are read live through the FK, which is editable in `/admin/`.

Live DB check: every won deal has exactly 1 accepted quote, and `amount` equals Σ round(line) for all 21
(SQL over `sales_opportunity`/`sales_quote`/`sales_quoteline`).

## Products, prices and customers vs the ERPNext claims

**Product** (`models.py:109-120`): `item_code` (verbose name "ERPNext item code", varchar 40, unique) ·
`name` varchar 140 · `uom`, default "Nos" · `list_price` Decimal(12,2), "list price (MYR)" · `active`.
Managers can add and change products in `/admin/` (`apps.py:5-8`, `admin.py:9-13`). Nothing keeps them
in sync with ERPNext.

**Item codes and prices match ERPNext (verified in source and the live DB):**
- `seed_demo.py:37-44` PRODUCTS: `FG-CT-300` 85, `FG-MG-1200` 520, `FG-WB-150` 18, `FG-PR-UP3` 310,
  `FG-EBF-1000` 1450.
- `ERP/apps/ombak_mfg/ombak_mfg/setup/masters.py:33-64` FINISHED_GOODS has the same codes and names with
  rates 85/520/18/310/1450 as "Standard Selling" Item Prices (`masters.py:349`) and `stock_uom: "Nos"`
  (`masters.py:340`).
- Live `sales_product` has the same 5 rows, all `uom=Nos`, all active.
- The claim is in the README ("product codes and prices are the ERPNext items ... without mapping",
  `README.md:165-166`) and in 003 `design.md:9-10,60`.
- The seed only `get_or_create`s products (`seed_demo.py:129-130`), so a price edited later in either
  system drifts silently.

**Customers: only partly true:**
- `seed_demo.py:51` says "the first five are ERPNext's customers". Tanjung Electrical Contractors Sdn
  Bhd, Kulai Food Processing Sdn Bhd, Seri Alam Logistics Sdn Bhd, Mutiara Automation Sdn Bhd and
  Harbourline Packaging Pte Ltd exactly equal the `CUSTOMERS` keys in `masters.py:66-83`. ERPNext gives
  them full shipping addresses with postcodes; the CRM has only city, state and phone.
- The other **11 seeded accounts are not ERPNext customers**, and neither is any account a rep or a lead
  conversion creates.
- In the live DB, **only 3 of 21 won deals belong to an ERPNext customer** (Harbourline, Mutiara, Seri
  Alam). The others include validator data, such as an account named
  `VAL-security 8300 <img src=x onerror=alert(1)>…`.
- There is no external customer id in the CRM. The only join key is the exact account name. ERPNext's
  `customer_name` is the CRM name, and the ERP chunk must confirm whether the docname equals it.

## Money and tax

- Money rules live in `rules.py:3-32`:
  - `Decimal` throughout, `CENT=0.01`, `ROUND_HALF_UP`;
  - `line_total = money(qty × unit_price × (100 − disc) / 100)`, rounded once per line;
  - `quote_total` is the sum of the rounded lines.
- The README example is "85.00 × 3 less 7.5 % = 235.88" (`README.md:245-246`).
- MYR only, and totals exclude SST ("ERPNext adds tax on the order", `README.md:290`, 003 `design.md:88-89`,
  `requirements.md:150`). There is no currency or tax field anywhere. Singapore accounts are also quoted
  in MYR.
- **Rounding risk for 004 (verify on the ERP side):** if ERPNext computes `rate` = price_list_rate ×
  (1 − disc), rounded to 2 dp, and then amount = rate × qty, then 85 × 0.925 = 78.625 → 78.63, and
  × 3 = 235.89. That is one sen off the CRM's 235.88. The order total may not equal `deal.amount` for
  fractional discounts (`DISCOUNTS` include 7.5 and 12.5, `seed_demo.py:81`).

## Integration-relevant models & gaps

- **No external-reference fields exist today.** The models have no ERPNext sales-order name, no sync
  status, no last error, no attempt count and no synced-at (`models.py`, full read).
- **Migrations:** `0001_initial` (11 models, 6 constraints), `0002_quote_revision` (AddField `Quote.revision`),
  `0003_ratelimit` (CreateModel `RateLimit`). All three are applied live (`django_migrations`). They are
  auto-generated style, so 004 would add `0004_*`.
- **Constraints:**
  - `account_name_unique_ci` (`models.py:67`)
  - `opportunity_amount_not_negative` (`:239`)
  - `activity_has_one_parent` and `planned_activity_has_due_date` (`:364-374`)
  - `quote_line_qty_positive` and `quote_line_discount_range` (`:546-549`)
  - `Product.item_code` unique
- **`RateLimit`** (`models.py:560-565`): `key` PK varchar 64, `count`, `expires` (indexed). It is used by
  `ratelimit.hit/count/clear` with a row lock (`ratelimit.py:21-35`). It's a precedent for a small
  lock-protected state table, but it isn't reusable as a sync record.
- `StageChange` records the Won transition (who and when). There is no event or outbox table.

## Cross-cutting

- **Settings** (`CRM/crm/settings.py`):
  - `SECRET_KEY` comes from `DJANGO_SECRET_KEY` (:10).
  - `DEBUG` is on only when `DJANGO_DEBUG=="1"` (:11).
  - `ALLOWED_HOSTS` comes from `DJANGO_ALLOWED_HOSTS`, default `localhost,127.0.0.1` (:12). A callback
    from ERP via `host.docker.internal` or a service name would be rejected.
  - CSP: `default-src`/`base-uri`/`form-action` `'self'`, `frame-ancestors 'none'` (:37-42). This governs
    the browser only. A plain `<a href>` to ERPNext Desk is fine, but a form posting to ERPNext or an
    iframe is not.
  - The DB comes from `POSTGRES_*` with `CONN_MAX_AGE=60`, and `TEST.NAME` from `POSTGRES_TEST_DB` (:64-74).
  - `AUTHENTICATION_BACKENDS=[LockoutBackend]` (:76).
  - `TIME_ZONE="Asia/Kuala_Lumpur"`, `USE_TZ=True` (:91-93).
- **Compose env** (`CRM/docker-compose.yml:19-26`): `DJANGO_SECRET_KEY`, `POSTGRES_HOST/DB/USER/PASSWORD`
  and `DEMO_PASSWORD`, with host-side overrides `CRM_SECRET_KEY`, `CRM_DB_PASSWORD` and `CRM_DEMO_PASSWORD`.
  There are no ERPNext variables yet.
- **Precedent for config and client:** `ERP/portal/portal/settings.py:15-19` (`ERPNEXT_URL`, `ERPNEXT_SITE`,
  `ERPNEXT_API_KEY`, `ERPNEXT_API_SECRET`, `ERPNEXT_TIMEOUT=10`) and `ERP/portal/terminal/erpnext.py`, a REST v2
  client on `requests` 2.34.2 with `Authorization: token key:secret`, `ERPNextError` (refusal, safe message) vs
  `ERPNextUnavailable` (unreachable, 401, 5xx), and HTML stripped from ERPNext messages (`:96-128`). Its tests
  fake the session with `mock.patch.object(session, "request")` (`terminal/tests/test_erpnext_client.py:20-25`).
- **Outbound HTTP:** none. A grep for `urllib|requests|httpx|http.client|socket|celery` in `CRM/**/*.py`
  hits only `threading` in tests.
- **Network** (`docker network ls`, `docker ps`): the CRM is on `ombak-crm_default` only (its compose declares
  no networks); ERP containers are on `erp_frappe_network` (`ERP/docker-compose.yml:13,187-189`).
  `erp-frontend-1` publishes `127.0.0.1:8080`, `erp-portal-1` `127.0.0.1:8081`, `erp-backend-1` nothing.
  Probed from inside `ombak-crm-web-1`: `backend`, `erp-backend-1` and `erp-frontend-1` do **not resolve**;
  `host.docker.internal` → 192.168.65.254 and `GET http://host.docker.internal:8080/api/method/ping` →
  **200 `{"message":"pong"}`** (nginx fixes the site via `FRAPPE_SITE_NAME_HEADER: localhost`,
  `ERP/docker-compose.yml:88`). So today the CRM reaches ERPNext only through Docker Desktop's
  `host.docker.internal`. The alternative is joining `erp_frappe_network` as an `external` network and using
  `http://backend:8000` like the portal, which couples the two compose projects that 003 kept separate on
  purpose (`design.md:18-19`).
- **Background jobs:** none. No celery, cron, scheduler or threads. The container runs only gunicorn
  (`Dockerfile:12`). Management commands: only `seed_demo` (`sales/management/commands/`).
- **Logging:** only the `django` logger, console, INFO (`settings.py:103-108`); no `logging.getLogger` anywhere
  in app code (grep). Integration failures need a `sales` logger added to `LOGGING` (root has no handler).
- **Errors:** friendly `sales/templates/500.html` via Django's default handler (test `UI-2`,
  `test_security.py:102-110`), 403/404 templates beside it. An unhandled exception from an outbound call
  inside `deal_won` would give this 500 and **roll back the Won** (atomic block).
- **Roles:** `MANAGER_GROUP="Sales Manager"` and `is_manager()` (superuser or group member, cached on the user)
  live in `models.py:15-23`, **not in `access.py`**; `access.py:15` imports them and adds the scopes (`:18-42`),
  `manager_required` (`:45-53`) and nav context (`:72-87`). Group admin perms sync on `post_migrate`
  (`apps.py:5-28`). `GuardedUserAdmin` (`admin.py:30-44`) makes `is_staff`/`is_superuser`/`groups`/
  `user_permissions` read-only for non-superusers and blocks editing a superuser.
- **Lockout:** `LockoutBackend` (`views/auth.py:17-31`): 10 tries per 15 min per NFKC-lowercased
  username, on every sign-in path. An API caller into the CRM (if 004 adds one) would not go through it.

## UI patterns to reuse

- **Deal page** (`deals/detail.html`):
  - page head with crumbs, `_stage.html` chip, amount and owner (:4-9);
  - status banners as `<p class="msg msg-success|msg-error">` under the head (:26-27). This is the natural
    slot for "ERP sales order SAL-ORD-… created" or "not sent yet";
  - right column `.panel` + `.panelhead` + `<dl class="details">` (:75-89); an "ERP order" row or panel fits;
  - POST action forms are `{% csrf_token %}` + `.btn` (e.g. the reassign panel, :90-100). A "Retry"
    button would follow this.
- **Chips** (`app.css:159-163`): `chip`, `chip-blue`, `chip-green`, `chip-amber`, `chip-red`. Quote status
  mapping is in `quotes/_status.html` (pending=amber, accepted=green, declined=red). A sync status can
  mirror this: sent=green, pending=amber, failed=red.
- **Flash messages** (`base.html:30-36`): `msg msg-{{ tags }}`, with `role="alert"` for errors and
  `role="status"` otherwise. `msg-warning` exists (`app.css:146`), so `messages.warning` works for "Won,
  but ERPNext didn't take the order".
- **400 re-render:** `detail_context(request, deal, **forms)` (`opportunities.py:103-119`) is re-rendered
  with `status=400` for invalid Lost and Assign forms (`:164`, `:199`). Won has no form today.
- **Focus first error:** `app.js:7-11` focuses `form [aria-invalid='true']`. Django 6 sets `aria-invalid`
  itself (no custom code in `forms.py`). Field partial: `_field.html`.
- **Double-submit guard:** `app.js:14-21`.
- **Hard rules from 003:** no inline script or style (CSP; `test_security.py:117-124` checks for no `on*=`
  handlers), 44 px controls, every page works without JS.

## Test baseline

| Command (from `CRM/`) | Result |
|---|---|
| `docker compose exec -T -e POSTGRES_TEST_DB=test_crm_recon web python manage.py test --noinput sales` | **Ran 155 tests in 57.8 s, OK, exit 0.** The test DB was created and destroyed. Expected 4xx log lines appear (Not Found, Bad Request, Too Many Requests). |

- **Layout:** `CRM/sales/tests/`, one file per area: accounts, auth, deals, home_reports, leads, pages,
  quotes, rules, security.
- **Base fixtures** (`tests/base.py:25-73`): `CRMTestCase(TestCase)` with manager `hafiz`, reps `aisyah`,
  `kumar`, `jason`, `siti`, `weiling` (`self.rep = siti`, force-logged-in), products `self.tray` (FG-CT-300, 85)
  and `self.frame` (FG-EBF-1000, 1450), two lost reasons, and helpers `account()` (default "Tanjung Electrical
  Contractors Sdn Bhd", an ERPNext customer), `deal()` and `quote(deal, lines, status)` (status forced by a
  queryset `update`).
- **Runner:** `CRM/scripts/test.sh` brings up `db`/`web` and runs `manage.py test --noinput ${@:-sales}`.
  `POSTGRES_TEST_DB` (`settings.py:72`) lets parallel runs use separate DBs.
- **Concurrency tests** use `TransactionTestCase` with real threads (`test_auth.py:79-119`,
  `test_quotes.py:259-292`). That's the pattern for a two-clicks-on-Won test.
- **Fakes:** no test fakes an external system. `mock` is used only for time, a slow auth or form check,
  stale reads and a DatabaseError. The portal's `test_erpnext_client.py` is the in-repo precedent for
  faking ERPNext.

## Conventions

- **Code style:** black-style at ~120 columns (no formatter config in the repo); `# fmt: skip` on hand-aligned
  tuples, dicts and calls (49 occurrences); short docstrings naming the rule and AC/FM number (e.g.
  `models.py:305,318,458-459`); user-facing text is a plain sentence raised as `RuleError` and shown verbatim
  (`rules.py:18-19`).
- **Layering:**
  - `rules.py` holds pure functions with no DB or HTTP (the module docstring says so).
  - Workflow methods on the models are `@transaction.atomic` and lock the deal row first, then re-check
    the state under the lock.
  - Views stay thin: scope through `access`, validate the form, call the method, catch `RuleError`, flash,
    then redirect or re-render with 400.
  - Records are reached only through `access.py` scopes (404 for other reps' records).
- **Ponytail comments** mark deliberate shortcuts and their upgrade path: `settings.py:96`,
  `regions.py:60`, `views/auth.py:26`, `views/enquiry.py:15`.
- **Commits** (`git log --oneline -15`): `[specship] M8 task 8.1: …`, `[specship] 003: …`,
  `[specship-fix] <symptom> | root-cause: <cause> | contract: 003`, `[specship] ship 003 …`.
- **Test names:** a descriptive `test_*` method with the test-case ID as a trailing comment, e.g.
  `def test_won(self):  # WON-2` (`test_deals.py:102`), `# CLOSED-1`, `# AC20`. The IDs come from
  003 `artifacts/test-cases.md` (Won/Lost at lines 61-68).

## Preserved behaviours (004 must not break)

1. Won needs a sent quote. The quote becomes Accepted, `amount` becomes its total, `closed_at` is set,
   and a `StageChange` is written (AC13, FM6). Tests: `WON-1`/`WON-2` (`test_deals.py:94-108`,
   `test_rules.py:114-120`).
2. Won and Lost go only through their own POSTs, never through Move (`rules.py:47-48`, `MOVE-3`).
3. A closed deal and its quotes are read-only, and closed deals can't be reopened (AC23, `CLOSED-1`,
   `EDIT-4`).
4. One deal row lock serialises Won, Lost, Send, Revise and Edit. A double Won gives "This deal is
   closed." and changes nothing.
5. Reports read won deals by `stage="won"`, `closed_at` and `amount`:
   - win rate by count (`reports.py:37-57`);
   - forecast "won in quarter" (`reports.py:61`);
   - "won this month" on My day (`views/home.py:34`).
   If a sync failure undid Won, or Won waited on ERPNext, all three would change.
6. Access scoping: a rep wins only their own deals, the manager any deal, and another rep's deal answers
   404 (AC19).
7. Sign-in lockout on all sign-in paths. GuardedUserAdmin. CSP with no inline script or style. CSRF and
   POST-only state changes (AC22).
8. The friendly 500 page with no traceback (AC20 / `UI-2`). Field errors next to the field with focus
   moved to them (AC20).
9. All of AC1-26: the suite of 155 tests must stay green.

## Risks & open questions for 004

1. **Won is one DB transaction today.**
   - An HTTP call inside `mark_won` would hold the deal row lock for up to gunicorn's 30 s. A timeout or
     exception would roll the Won back, and if ERPNext succeeded but the response was lost, the CRM rolls
     back while the order exists: a ghost order.
   - Recommended shape (decision for the contract): commit the Won first, push after commit
     (`transaction.on_commit` or an explicit second step), and keep the outcome on the deal, so "Won
     always succeeds and the ERP order is pending or failed with a retry".
   - Needs a user decision: should an ERP failure block Won?
2. **Idempotency.**
   - Two Won clicks are already safe in the CRM.
   - The risk is a duplicate ERPNext order after a retry or a lost response. The CRM needs a stable key
     sent to ERPNext and checked before creating, e.g. the quote number `QT-2026-00133`, the deal id, or
     ERPNext's `po_no`. The ERP chunk must say which field and whether it is unique.
   - The CRM side should store the returned SO name with a unique constraint.
3. **Retries.**
   - There is no job runner. The options are a "Retry" POST on the deal page (`.btn`, manager or owner,
     row-locked like the other methods), and/or a management command for a batch retry.
   - Adding celery or redis would be a big step for this app (YAGNI unless the user asks).
4. **Where the reference lives.** The candidates are new fields on `Opportunity`, e.g. `erp_order` (blank
   varchar, unique when set), `erp_status` (none/pending/sent/failed), `erp_error`, `erp_synced_at`, or a
   one-to-one `ErpOrder` table. Either needs migration `0004`. Fields on the deal are the lazy option.
5. **Can a deal be won without a quote?** No (`rules.py:56-57`), so the order lines always come from
   exactly one Accepted quote.
   - Leftover draft or pending quotes on won deals must be ignored; a pending one even stays in the
     manager's approvals list (`views/quotes.py:129`).
   - Seeded won deals have single-line quotes; real ones have up to N lines.
6. **Customer mismatch:**
   - only the 5 ERPNext customers exist on both sides (3 of 21 live won deals);
   - for any other account, 004 must create the ERPNext Customer, refuse with a clear message, or fall
     back. That's a user decision.
   - The CRM has no address or postcode for seeded accounts, `registration_no` is mostly blank, and
     `country` is derived from `state`.
   - Account names are untrusted text (live XSS-style names exist). Send them as JSON data only, and strip
     or escape ERPNext's HTML error text on the way back, as the portal does.
7. **Prices.**
   - Send the CRM's `unit_price` and `discount_pct` (or the final `rate`) explicitly. Don't let ERPNext
     re-price from its own list: prices can drift via `/admin/` vs ERPNext Item Price, and the quote's
     `unit_price` is a snapshot.
   - Check the rounding (one-sen difference above).
   - The ERP chunk should confirm the SO currency for the Singapore customer, Harbourline (the CRM is
     MYR only).
8. **Dates.**
   - The SO `transaction_date` could be the local date of `closed_at`.
   - `delivery_date` (required by ERPNext) has no CRM source. Options are `expected_close` (often in the
     past at Won), the Won date plus N days, or a field the rep fills in. That's a user decision.
   - `valid_until` is not checked at Won (14 of 21 live won deals closed after it). Decide whether an
     expired quote may still become an order.
9. **Network and secrets.**
   - Pick `host.docker.internal:8080`, which works today on Docker Desktop only, or attach the CRM to the
     external `erp_frappe_network` and use `backend:8000`.
   - Add the env vars `ERPNEXT_URL`/`ERPNEXT_SITE`/`ERPNEXT_API_KEY`/`ERPNEXT_API_SECRET` to
     `CRM/docker-compose.yml` with demo defaults (AC22 style).
   - Add `requests` to `requirements.txt` (matching the portal's 2.34.2), or use stdlib `urllib`.
   - Use a timeout well under gunicorn's 30 s, like the portal's 10 s.
10. **Backfill.** There are 21 existing won deals. Should 004 push past wins, or only Wins made after it
    ships? (Many are VAL- validator data.)
11. **Who sees the ERP status and who may retry:** the owner, the manager, or both? Is there an ERP link
    (ERPNext Desk URL `http://localhost:8080/app/sales-order/<name>`) on the deal page?
