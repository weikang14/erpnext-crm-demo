# Chunk: ERP side (ERPNext v16 + ombak_mfg + ERP/portal) for mission 004

Recon at HEAD `b90682a`, 2026-10-14. Read-only. The only writes to the demo site `localhost` were none: every
live fact below comes from `bench --site localhost execute frappe.get_all/get_value/get_singles_dict`
(pure getters) or REST GETs. The two test scripts wrote only to their own sites (`test.localhost`, `contract.localhost`).
`git status` showed no change outside `.specship/` afterwards.

## Scope

- Intent 004: when a CRM deal is marked Won, create the matching ERPNext Sales Order.
- This chunk covers `ERP/` only:
  - ERPNext site `localhost`;
  - the app `ERP/apps/ombak_mfg`;
  - the REST client in `ERP/portal`, which is the pattern to copy.
- The CRM side is a separate chunk. From `CRM/` this chunk read only:
  - `CRM/sales/management/commands/seed_demo.py` (PRODUCTS, ACCOUNTS);
  - `CRM/sales/rules.py` (money rounding);
  - `CRM/docker-compose.yml` (networking);
  - the `Quote.number` property.

## Stack & versions

| Piece | Version | Evidence |
|---|---|---|
| ERPNext image | `frappe/erpnext:v16.37.0` | `ERP/Dockerfile:1` |
| Running apps | erpnext 16.37.0, frappe 16.36.1, ombak_mfg 0.0.1 | `bench version` in erp-backend-1 |
| ombak_mfg | Python >=3.14, ruff, tabs, line 110 | `ERP/apps/ombak_mfg/pyproject.toml` |
| DB / cache | mariadb:11.8, redis:6.2-alpine | `ERP/docker-compose.yml:150,169,176` |
| Portal | Python 3.13-slim, Django 6.1.1, requests 2.34.2, gunicorn 26.2.0 | `ERP/portal/Dockerfile`, `ERP/portal/requirements.txt` |
| CRM (for reference) | Django 6.1.1, psycopg 3.3.6, **no `requests`** | `CRM/requirements.txt` |
| Docker | Docker Desktop 27.3.1, Compose v2.29.7-desktop.1 | `docker info`, `docker compose version` |

Sites on the bench are `localhost` (the demo), `test.localhost` and `contract.localhost` (`ls sites`).

## Sales Order on this site

**Fields that must be present.** These are `reqd` in DocField, checked live with `frappe.get_all("DocField", {"parent": "Sales Order", "reqd": 1})`:
- Header: `company`, `naming_series`, `customer`, `order_type` (default "Sales"), `transaction_date` (default Today), `currency`, `conversion_rate`, `selling_price_list`, `price_list_currency`, `plc_conversion_rate`, `items`, `status`.
- Item rows: `item_code`, `item_name`, `qty`, `uom`, `conversion_factor`.

Server-side `set_missing_values` fills every one of them except `customer`, `items[].item_code` and `items[].qty`. The proof is the known-good payload in `demo.py:205-215`, which sends only:
```python
{"doctype": "Sales Order", "customer": c, "company": COMPANY, "transaction_date": d, "delivery_date": d+12,
 "po_no": "DEMO-001", "items": [{"item_code": "FG-CT-300", "qty": 40, "delivery_date": d+12, "warehouse": "Finished Goods - OMW"}]}
```
and gets back, on all 19 demo orders (live GET):
- currency MYR and selling_price_list `Standard Selling`;
- the rate from the price list (SAL-ORD-2026-00001: 40 x 85 = 3400.00);
- `customer_address` and `shipping_address_name` = `<customer>-Shipping`, filled from the primary address;
- `set_warehouse` null.

Other fields:
- **delivery_date** is not reqd in the meta, but `validate_delivery_date` throws "Please enter Delivery Date" (order_type Sales). It takes the header date from the latest item date, copies the header date into items without one, and refuses a date before transaction_date (`erpnext/selling/doctype/sales_order/sales_order.py:425-445`). One date, at header or item level, is enough.
- **Warehouse** may be left out. Each finished good has an Item Default of `Finished Goods - OMW` (`masters.py:346`; live `Item Default` of FG-CT-300). `Stock Settings.default_warehouse` is `Raw Material - OMW` (`masters.py:256`), so never rely on that one for SO lines.
- **Discount fields** exist on `Sales Order Item` (`discount_percentage`, `discount_amount`, `rate`, `price_list_rate`). The UI hides them with Property Setter `Sales Order Item-discount_and_margin-hidden=1`, but the API can still set them.

**Naming:** series `SAL-ORD-.YYYY.-`, the only option. Existing names are SAL-ORD-2026-00001..00019.

**Taxes.** The CRM says "ERPNext adds SST". That is false on this site.
- There is no SST template. The setup wizard created only `Malaysia GST 6% - OMW` (is_default=1), `Malaysia GST 5% - OMW` and `Malaysia GST 10% - OMW`, all "On Net Total" to account `GST - OMW`. Live: `Sales Taxes and Charges Template` and `Item Tax Template`.
- Malaysia's GST was replaced by SST in 2018, so these are stale defaults. No Tax Rule, no Tax Category, no Item Tax rows.
- `Accounts Settings.add_taxes_from_taxes_and_charges_template = 0` (live). So `set_taxes_and_charges` (`erpnext/controllers/accounts_controller.py:1354-1374`) adds **no** tax rows to a REST insert, even when `taxes_and_charges` is passed.
- Evidence: all 19 demo SOs have `taxes_and_charges = null` and `total_taxes_and_charges = 0` (grand_total = net_total).
- To get tax over REST, 004 must do one of these:
  - send the `taxes` child rows explicitly;
  - flip that setting;
  - leave tax at 0, as today.

**Submit: whether it is needed and what it triggers.**
- `POST /api/v2/document/Sales Order` with `"docstatus": 1` inserts and submits in one transaction. That is the same pattern as the portal's Defect Log: `erpnext.py:91-93`, and `frappe/api/v2.py:171-180` `create_doc` → `doc.insert()`.
- `on_submit` (`sales_order.py:519-541`) does the following on this site:
  - `update_reserved_qty`: Bin reserved qty for the item in `Finished Goods - OMW`, which changes projected qty and so MRP;
  - credit limit check: no Customer Credit Limit rows;
  - Authorization Control: no Authorization Rule rows;
  - stock reservation: off (`Stock Settings.enable_stock_reservation=0`, `auto_reserve_stock=0`).
- Nothing creates a Production Plan or a Work Order automatically:
  - `ombak_mfg/hooks.py` has no `doc_events` (line 147 is commented out; only `scheduler_events` at 269 and `before_tests` at 267);
  - there are no Server Scripts, Webhooks or Auto Repeat, and no Notification on Sales Order (live).
- In this site's flow the **planner** runs MRP: Production Plan from Sales Order → submit → `make_work_order` + `make_material_request` (`demo.py:218-250`).
- A Production Plan pulls only `docstatus == 1` sales orders that are not Stopped/Closed (`erpnext/manufacturing/doctype/production_plan/production_plan.py:1629-1630`). A **draft** SO is invisible to planning.

**Duplicate guard ERPNext already has.**
- `validate_po` (`sales_order.py:359-385`) refuses a second non-cancelled SO for the **same customer and same `po_no`**. It answers HTTP 417 with "Sales Order X already exists against Customer's Purchase Order Y", because `Selling Settings.allow_against_multiple_purchase_orders = 0` (live).
- The check is skipped when `skip_delivery_note=1`.
- It is a SELECT, not a DB constraint, so two parallel posts can both pass.

## Masters: customers / items / price list / company

From `ERP/apps/ombak_mfg/ombak_mfg/setup/masters.py`, confirmed live:
- **Company:** `Ombak Metal Works Sdn Bhd`, abbr `OMW`, MYR, country Malaysia, receivable `Debtors - OMW`, income `Sales - OMW`, cost centre `Main - OMW` (`masters.py:6-7`; live Company). Global Defaults: default_company is that company, MYR.
- **Customers** (`masters.py:67-83`, `_parties` 395-426):
  - Customer: `customer_type` Company, group `Commercial`; territory Johor, Selangor or Singapore. **No tax_id**, no default price list or currency, no contacts.
  - Address: one Shipping address per customer, `is_primary_address=1`, named `<customer>-Shipping`.
  - Naming: `Selling Settings.cust_master_name = "Customer Name"`, so the Customer **name equals customer_name** and the CRM can GET `/api/v2/document/Customer/<exact name>`.
  - Territories that exist live: Johor, Selangor, Singapore, Malaysia, Rest Of The World.
  - Groups that exist live: Commercial, Government, Individual, Non Profit.
- **Items** (`masters.py:33-64`, `_items` 309-349):
  - Item: group `Products`, `stock_uom` Nos, stock item, sales item, not purchase; `inspection_required_before_delivery=1` (Final Inspection), which affects the Delivery Note, not the SO.
  - BOM: a default BOM is submitted for each (live `default_bom` BOM-<code>-001).
- **Price list:** `Standard Selling` (MYR, selling). The Item Price rows have `valid_from` 2025-01-01 and no customer-specific prices (`_item_price` 352-367; live). `Selling Settings.selling_price_list = Standard Selling`. There are no Pricing Rules (live).
- **Rounding:** `System Settings.rounding_method = "Banker's Rounding"`, float_precision 3; MYR shows 2 dp (live).

**CRM vs ERPNext.** Compared by script (constants); the live CRM `Product` rows were read via `manage.py shell`.

| CRM product (seed_demo.py:38-44, live CRM DB) | ERPNext item (masters.py, live) | Name | Price MYR | UOM |
|---|---|---|---|---|
| FG-CT-300 | FG-CT-300 | equal | 85 = 85 | Nos = Nos |
| FG-MG-1200 | FG-MG-1200 | equal | 520 = 520 | Nos = Nos |
| FG-WB-150 | FG-WB-150 | equal | 18 = 18 | Nos = Nos |
| FG-PR-UP3 | FG-PR-UP3 | equal | 310 = 310 | Nos = Nos |
| FG-EBF-1000 | FG-EBF-1000 | equal | 1450 = 1450 | Nos = Nos |

- **No CRM product lacks an ERPNext item.**
  - CRM `Product.list_price` is editable (`CRM/sales/models.py:109-114`), so prices can drift later.
- **Accounts:** the first five CRM `ACCOUNTS` (`seed_demo.py:52-57`) equal the five ERPNext customers exactly.
  - The other 11 seed accounts have no ERPNext customer: Prai Precision, Kedah Rice Mill, Ipoh Cold Storage, Klang Port, Bangsar Fit-Out, Nilai Pharma, Kuantan Palm, Melaka Glove, Senai Data Centre, Tuas Marine, Jurong Food Hub.
  - Their states (Penang, Kedah, Perak, KL, Negeri Sembilan, Pahang, Melaka) have no ERPNext Territory.
  - The live CRM DB holds **42** accounts, not 16.
- **Required fields to create these records:**
  - Customer: `customer_name` and `customer_type`; group and territory are optional.
  - Address: `address_line1`, `city`, `country`, `address_type`.
  - Contact: no reqd DocField.

## REST client pattern to reuse (`ERP/portal/terminal/erpnext.py`)

- **One module does all the HTTP** (`erpnext.py:1-4`). Shapes are pinned in `.specship/completed/002-shopfloor-terminal/artifacts/api-contract.md`.
- **Auth:** a `requests.Session` with these headers (`erpnext.py:37-47`):
  - `Host: <ERPNEXT_SITE>`;
  - `Accept: application/json`;
  - `Authorization: token <key>:<secret>`.
  The values come from Django settings, which read env (`ERP/portal/portal/settings.py:15-19`):
  - `ERPNEXT_URL` (default `http://backend:8000`);
  - `ERPNEXT_SITE` (`localhost`);
  - `ERPNEXT_API_KEY` and `ERPNEXT_API_SECRET`;
  - `ERPNEXT_TIMEOUT = 10` s.
  Compose injects them at `ERP/docker-compose.yml:138-141` from `SHOPFLOOR_API_KEY/SECRET`, with defaults `shopfloor-demo-key` and `shopfloor-demo-secret`. There is no `ERP/.env`.
- **v2 only.** Every call goes to `/api/v2/...` (`erpnext.py:109`). The contract explains why: v1 has a different error shape (api-contract.md:10).
  - Lists: `GET /api/v2/document/<DocType>?fields=<json>&filters=<json>&limit=&order_by=` (`erpnext.py:101-105`).
  - Create: `POST /api/v2/document/<DocType>`, json body; add `"docstatus": 1` to submit in the same call (`erpnext.py:91-93`).
  - Methods: `POST /api/v2/document/<DocType>/<name>/method/<m>` (`erpnext.py:97-99`).
  - Frappe routes: `frappe/api/v2.py:288-301`.
- **Error mapping** (`erpnext.py:107-118`):
  - `requests.RequestException` (connection failure, timeout) → `ERPNextUnavailable`;
  - 401 or >=500 → `ERPNextUnavailable`;
  - 403 → `ERPNextError` with a fixed "setup problem" text;
  - any other non-2xx → `ERPNextError(_message)`.
  Frappe codes: ValidationError 417, PermissionError 403, DoesNotExist 404, DuplicateEntry/NameError 409, AuthenticationError 401 (`frappe/exceptions.py`).
- **Stripping ERPNext HTML** (`erpnext.py:120-128`): join `errors[].message`, then `html.unescape(strip_tags(...))`; a non-JSON body (e.g. nginx 502 HTML) falls back to "ERPNext rejected the request (N)". The `exception` field is never shown. It holds a full traceback: a live 403 body seen in this recon contained one.
- **Inputs are checked before they reach a URL:** `check_job_card` fullmatch allowlist (`erpnext.py:15,30-33`), tested in `test_erpnext_client.py:94-98`.
- **"The write may or may not have landed":** `views.unavailable(saving=True)` (`ERP/portal/terminal/views.py:24-28`) is used when a write raises `ERPNextUnavailable` (`views.py:97-98,138-139`). The UI then says to check ERPNext (`test_recovery.py:53`, `test_lost_connection_while_saving_says_check`).
  - A completed write is never hidden by a later failure (`views.py:141-150`).
- **No retries or backoff anywhere** in `ERP/portal` (grep). Recovery is left to the human.
- **For 004:** a server-side insert+submit is one DB transaction, so a timed-out POST either fully landed or did not. Recover by looking the SO up by the CRM reference before any re-POST.

## Least-privilege role/user pattern (002)

- **Role:** `TERMINAL_ROLE = "Shop Floor Terminal"` with `TERMINAL_PERMISSIONS` (`masters.py:125-135`).
  - `_terminal_role` (`masters.py:491-499`) creates it with `_ensure` and then calls `frappe.permissions.add_permission` and `update_permission_property` once per doctype and ptype.
  - Doctypes owned by the app grant the role in their own JSON (Defect Log, Defect Reason; `masters.py:126`).
  - Side effect (live `Custom DocPerm`): the first custom perm on a doctype copies **all** of its standard DocPerms into `Custom DocPerm` (see Employee, Job Card, Work Order, Workstation). From then on the custom set overrides the standard one. A CRM role on Sales Order or Customer would freeze those doctypes' perms the same way.
- **User:** `INTEGRATION_USER = shopfloor.terminal@ombakmetal.example` (`masters.py:124`). `_integration_user` (`masters.py:502-527`) works like this:
  - it creates the user with only the narrow role and removes the legacy `Manufacturing User`;
  - it copies `frappe.conf.shopfloor_api_key/secret` into `api_key/api_secret`;
  - the site config gets those values from compose `create-site`: `bench --site localhost set-config shopfloor_api_key "$$SHOPFLOOR_API_KEY"` (`docker-compose.yml:54-58`). `test-portal.sh` does the same for contract.localhost.
  - Live: the user has exactly one role, `Shop Floor Terminal`, with api_key `shopfloor-demo-key`.
- **How the refusals were proven:**
  - in-site: `test_terminal_role_is_least_privilege` (`ombak_mfg/tests/test_setup_masters.py:89-108`) checks `frappe.has_permission` for allowed and denied ptypes;
  - key handling: `test_integration_user_gets_keys_from_site_config` (73-87);
  - over HTTP: contract test CT-7 (`ERP/portal/terminal/tests/test_contract.py:67-72`) expects 403 on GET Sales Invoice and on POST Work Order. CT-6 (74-77) expects a bad secret to give `ERPNextUnavailable`.
  - Re-checked live in this recon: the terminal key gets **403 on GET Sales Order**.
- **Standard perms a "CRM Integration" role would replace** (live DocPerm):
  - `Sales User` has: Sales Order read/write/create/submit/cancel/delete; Customer, Address and Contact read/write/create; Item read; Price List read.
  - **Item Price** is readable only by Sales/Purchase Master Manager.
  - So a narrow role needs Custom DocPerms for:
    - Sales Order: read, create, submit (and write, if Frappe needs it to submit);
    - Customer: read, create;
    - Address and Contact: create, read;
    - Item: read;
    - Price List and Item Price: read, only if the CRM checks prices;
    - Customer Group and Territory: read, as link validation needs.
  - Denied list to assert: Sales Order cancel and delete, Sales Invoice, Work Order, Job Card.

## Networking options

Facts, checked read-only:
- **ERP network.** `erp_frappe_network` is 172.18.0.0/16 (compose project `erp`, network `frappe_network`, `docker-compose.yml:188`). The portal reaches ERPNext at `http://backend:8000` with `Host: localhost` (`docker-compose.yml:134-139`).
- **CRM network.** `ombak-crm-web-1` is only on `ombak-crm_default` (172.19.0.0/16, `CRM/docker-compose.yml` declares no networks). From inside it:
  - `backend` and `erp-backend-1` do not resolve;
  - `host.docker.internal` = 192.168.65.254;
  - `GET http://host.docker.internal:8080/api/method/ping` → 200 `{"message":"pong"}`;
  - with the terminal token, `GET /api/v2/document/Workstation` → 200 and `GET /api/v2/document/Sales Order` → 403.
- **Site routing.**
  - Frappe picks the site from `X-Frappe-Site-Name`, then Host (`frappe/app.py:215`).
  - The frontend nginx **forces** `proxy_set_header X-Frappe-Site-Name localhost` (erp-frontend-1 `/etc/nginx/conf.d/*.conf:46,71`; `FRAPPE_SITE_NAME_HEADER: localhost`, `docker-compose.yml:88`). So **anything that comes in on :8080 lands on the demo site, whatever its Host header.** Only `backend:8000` honours Host, and that is how the contract tests reach `contract.localhost`.

| Option | How | For | Against |
|---|---|---|---|
| A. Shared external network | CRM `web` joins `erp_frappe_network` as `external: true`; `ERPNEXT_URL=http://backend:8000`, `ERPNEXT_SITE=localhost` | Same path as the portal; Host selects the site, so CRM contract tests can target `contract.localhost` | CRM `up` fails if the ERP stack never created the network; the name depends on the ERP dir/project name (no `name:` pin) |
| B. `host.docker.internal:8080` | CRM env `ERPNEXT_URL=http://host.docker.internal:8080`; Linux needs `extra_hosts: host-gateway` | Already works (verified); no coupling between the compose files | Always the demo site: a contract test over B would **write to the demo data**; extra nginx hop; Docker Desktop specific |
| C. Publish backend :8000 on 127.0.0.1 | ERP compose change | Simple | Bypasses nginx; changes the ERP stack; no real gain over A |

## Idempotency / reference field options

1. **`po_no`** ("Customer's Purchase Order", Data). It is `allow_on_submit=1`, not unique, not indexed (live DocField).
   - For: a built-in per-customer duplicate refusal (417, see above), and v2 can look it up with `filters=[["po_no","=",ref],["docstatus","<",2]]` (the same `_list` shape as `erpnext.py:101-105`).
   - Against: users can edit it after submit; it is not race-safe; it takes the field away from the customer's real PO number.
   - It must **not** start with `DEMO-`: `demo.run` treats any `po_no like 'DEMO-%'` as "demo already exists" (`demo.py:25,83-85`). CRM quote numbers are `QT-<year>-<pk:05d>` (`CRM/sales/models.py:429-430`), which is safe. They come from the pk, so a reseeded CRM DB can reuse an old number.
2. **Custom Field** (e.g. `crm_reference`, Data, `unique=1`, `no_copy=1`, `read_only=1`). A DB unique index makes it race-safe, and it can be filtered over v2 like any field.
   - ombak_mfg has **no** custom fields and **no `fixtures`** today: live Custom Field rows all have `module=null`, and there is no `fixtures` in `hooks.py`.
   - The house style would be an idempotent creator inside `setup_masters()`, like `_terminal_role`. It reaches `localhost` only when someone runs `setup_masters`/`demo.run` there.
3. **Explicit document name.** v2 `create_doc` honours `name` (`frappe/api/v2.py:177-178`), and a repeat POST gives 409 DuplicateEntry: race-safe with no schema change. But it breaks the `SAL-ORD-.YYYY.-` series. Not recommended.

## Test baselines

Both scripts were run once in this recon. Neither touches `localhost`: `test.sh` uses `test.localhost`; `test-portal.sh` uses `contract.localhost`, and `contract.py:18` throws on any other site.

| Command (from `ERP/`) | Result | Duration | Notes |
|---|---|---|---|
| `bash scripts/test.sh` | **exit 0**, `Ran 32 tests in 22.781s`, `OK` | 58 s wall | Migrates `test.localhost`, then runs `run-tests --app ombak_mfg`; tests: alert 4, defect_log 7, reports 12, setup_masters 5, smoke 1, workspace 3 |
| `bash scripts/test-portal.sh` | **exit 0**, `Found 63 test(s)`, `Ran 63 tests in 11.286s`, `OK` (0 skipped, so the 6 live contract tests ran) | 45 s wall | Setup steps listed below |

`test-portal.sh` does this:
- on `contract.localhost`: sets the key config, migrates, runs `setup_masters`, then `contract.fresh_job_cards` (prints a JSON fixture with a new WO);
- then runs `manage.py test terminal` in erp-portal-1 with `CONTRACT_SITE` and `CONTRACT_FIXTURE`.

How the 002 contract tests are built:
- `test_contract.py` is skipped unless `CONTRACT_FIXTURE` is set (line 23), and overrides `ERPNEXT_SITE` to the contract site (24).
- It calls the real client against `backend:8000`.
- The fixtures come from an ERP-side, site-guarded function (`ombak_mfg/setup/contract.py:18`).
- Unit tests swap in `FakeERPNext` (`terminal/tests/fakes.py`) via `mock.patch("terminal.views.erpnext_client")` (`tests/base.py:18-20`).
- Client tests mock `session.request` and assert the exact URL, headers and body (`test_erpnext_client.py`).

The previous logs agree: `.specship/artifacts/test-run-erp.log` (32 OK) and `test-run.log` (63 OK).

## Conventions

- **Frappe app layout:** `ombak_mfg/ombak_mfg/{doctype,report,number_card,workspace}` and `setup/{masters,demo,check_demo,contract}.py`; `tasks.py` for scheduler jobs; tests in `ombak_mfg/tests/` with `factory.py` helpers.
- **Setup:** a constant-driven `setup_masters()` with an idempotent `_ensure(doctype, name, values)` (`masters.py:167-175`) and an "exists?" guard everywhere. A second run adds nothing, and `test_second_run_adds_nothing` (`test_setup_masters.py:46-55`) enforces it. Secrets are read from site config, never committed.
- **Tests:** `frappe.tests.IntegrationTestCase`; `before_tests = setup_masters` (`hooks.py:267`), so tests use the demo masters; `tearDown: frappe.db.rollback()` for tests that write. Each test carries an ID comment (`# DEMO-1`, `# OP-2`, `# CT-7`, `# CL-3`).
- **Portal:** one HTTP module, a fake and a live contract test; error texts are written for end users; `# ponytail:` comments mark deliberate simplifications.
- **Commits:** `[specship] 00N milestone K: ...` / `[specship] M8 task 8.2: ...` / `[specship-fix] <symptom> | root-cause: ... | contract: 00N`, plus a `Co-Authored-By:` trailer (`git log`).

## Preserved behaviours (004 must not break)

1. **Demo data and `check_demo`** (`setup/check_demo.py:12-62`) on `localhost`:
   - >=12 submitted SOs, **every SO grand_total > 0**, >=4 customers;
   - **every Work Order comes from a Production Plan**;
   - the WO on-time, late and overdue counts, MRP MRs, QIs, DNs, trips, invoices and defect logs.
   - So a zero-value CRM SO breaks it, and so does creating WOs outside a Production Plan.
   - `demo.run` must stay idempotent (the `DEMO-` po_no marker).
2. **The 4 reports** read Defect Log, Job Card, Work Order and Job Card Scheduled Time, not Sales Order (`report/*/*.py` qb sources). They change only if 004 creates WOs or plans.
3. **Shop-floor terminal and its role:**
   - `Shop Floor Terminal` perms (live Custom DocPerm) and the `shopfloor_*` config keys;
   - CT-7 still expects 403 on Sales Invoice and on POST Work Order. Do not widen that role; make a separate CRM role and user.
4. **The 19 existing SOs** (SAL-ORD-2026-00001..19, `DEMO-001..019`): no edits.
5. **Overdue alert** (`tasks.py:12-65`, daily via `hooks.py:269-271`): it counts submitted WOs past their planned end. Untouched unless 004 makes WOs.
6. **Both test scripts stay green** (32 + 63), and `masters.setup_masters` stays idempotent.

## Risks & open questions for 004

1. **Draft or submitted?**
   - Submitted: one POST with `docstatus: 1`; visible to Production Plan at once (pp.py:1629); reserves qty.
   - Draft: lets someone review tax, terms and dates in ERPNext first, but planning cannot see it until a human submits.
   - Owner decision.
2. **Tax/SST.** The site has no SST template, only stale "Malaysia GST" ones, and REST inserts get **zero tax** because `add_taxes_from_taxes_and_charges_template=0`. Fixing that means one of:
   - a new SST template (needs an SST account) set as default, plus explicit `taxes` rows or the setting flipped;
   - accepting tax-free SOs and fixing the CRM/README claim.
   The desk form probably applies the default GST 6% when a person creates an SO (client side; not verified).
3. **Price and rounding mismatch.**
   - With no Pricing Rules, ERPNext keeps an explicit `rate` and records the difference as `discount_amount` (`erpnext/controllers/taxes_and_totals.py:194-224`). So "CRM price wins" works if the CRM sends `rate`.
   - The CRM rounds each **line total** half-up (`CRM/sales/rules.py:22-27`); ERPNext rounds the **unit rate** with Banker's rounding, then multiplies.
   - Hand-computed example (check it in a test): FG-CT-300 x 3 at 12.5 % off gives CRM 223.13 and ERPNext 74.38 x 3 = 223.14.
   - Decide which total is authoritative, and whether 1 sen of drift is acceptable.
   - Also decide what happens when CRM `list_price` drifts from `Standard Selling`.
4. **Delivery date source.** The SO needs one (`sales_order.py:445`) on or after `transaction_date`. Does the CRM capture a promised date? `demo.py` uses order date + 12 days.
5. **Customers.**
   - Exact-name match works for the 5 seeded customers. The other 11 seeded accounts (42 live) have no ERPNext customer.
   - Options: create on first win (role needs Customer create; territory "Malaysia" or new territories; group `Commercial`), or refuse with a clear message.
   - Name collisions and renames in the CRM break name matching. Should the ERPNext customer name be stored back on the CRM account?
6. **Address/contact.** An ERPNext Address needs `address_line1`, `city`, `country`. CRM `Account.address`, `city` and `postcode` are optional (`CRM/sales/models.py:56-59`). Without an address the SO still saves, but Delivery Trips later need a stop address (`demo.py:402`).
7. **ERPNext down or slow.**
   - Map failures the way `erpnext.py` does. The 10 s client timeout is shorter than gunicorn and nginx's 120 s.
   - The Won transition in the CRM must not depend on ERPNext being up (an outbox or retry state on the CRM side). Every retry must look up the reference first.
   - `validate_po` (same customer + po_no) is a second line of defence, not a lock.
8. **Network choice** (above). Option B cannot reach `contract.localhost`, so live contract tests need option A, or must run from the ERP side (an ombak_mfg integration test inserting as the CRM user via `frappe.set_user` on `test.localhost`).
9. **Credentials.**
   - Mirror 002: `crm_api_key/secret` in site config, set by compose `create-site` and copied in by a new `_crm_integration_user()`.
   - On the existing demo site the new role and user appear only after someone reruns `setup_masters` there (e.g. `demo.run`, which is idempotent).
   - The CRM env needs `ERPNEXT_*`, and the CRM image has no `requests`.
