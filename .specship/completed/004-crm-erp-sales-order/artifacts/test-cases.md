# Test cases: 004 won deal → ERPNext sales order

Written before any 004 code exists, from `requirements.md` (AC1-22, FM1-16), `design.md`,
`artifacts/api-contract.md` and the brownfield recon. Each row is one behaviour, to be made RED first.

## Layers
| Code | Where | How |
|---|---|---|
| U | CRM offline unit | `bash CRM/scripts/test.sh`. Django `TestCase` on PostgreSQL; ERPNext replaced by a portal-style `FakeERPNext` (no network). Rows marked "client" test the real `CRM/sales/erpnext.py` with `urllib.request.urlopen` mocked |
| C | CRM live contract | `CRM/scripts/test-erp.sh`: the real client against `contract.localhost` with the CRM Integration keys |
| E | ERP | `bash ERP/scripts/test.sh`: `IntegrationTestCase` on `test.localhost`, `before_tests = setup_masters`, rollback in `tearDown` |
| M | command or manual check | compose config, read-only `check_demo` on `localhost`, README review |

## Fixtures (U unless stated)
- `CRMTestCase`: manager `hafiz`; reps `siti` (= "rep", South), `jason` (Central), `weiling` (Singapore);
  products `tray` FG-CT-300 at 85.00, `frame` FG-EBF-1000 at 1450.00.
- Accounts:
  - **TEC** "Tanjung Electrical Contractors Sdn Bhd", Johor; already a customer in the fake.
  - **SKS** "Seri Kembangan Steel Works Sdn Bhd", Selangor, SSM no. "202001023456", address "Lot 5, Jalan SR 8/3",
    city "Seri Kembangan", postcode "43300", phone "+60 3-8941 2200"; not in the fake.
  - **JPE** "Jurong Precision Engineering Pte Ltd", Singapore, UEN "201812345K", no address; not in the fake.
- **D1**: siti's open deal "Cable trays for plant 2" on TEC, with sent quote **Q133** (its `number`, written
  `QT-2026-00133` here): 3 × tray at 7.5 % → 235.88.
- **FakeERPNext**:
  - `orders` are keyed by `crm_reference`; `customers` match by name the way MariaDB does (case-insensitive,
    trailing spaces ignored);
  - the template "Malaysia SST - OMW" has one row `{charge_type: "On Net Total", account_head: "SST - OMW",
    rate: 10, description: "SST 10%"}`;
  - create stores a draft `SAL-ORD-2026-00020` (docstatus 0) and `submit_order` sets docstatus 1;
    `net_total` = Σ(qty × rate) − discount_amount;
  - it records `calls` and raises `fail[call]` when set.
  - Call names follow the API contract: c1 lookup, c2 customer GET, c3 customer POST, c4 address POST,
    c4b template GET, c5 order POST (draft), c5b submit (PUT `{"docstatus": 1}`).
  - In fake-client rows, `urlopen` is patched to fail the test if reached.
- Clock: now = 2026-10-15 09:00 KL (01:00 UTC) unless a row says otherwise; "today + 14" = 2026-10-29.
- Settings: `ERPNEXT_URL` http://erp.test, `ERPNEXT_SITE` localhost, key `k`, secret `s3cr3t-xyz`,
  `ERPNEXT_DESK_URL` http://localhost:8080.
- Texts:
  - **T1** = "ERPNext didn't answer. The order may or may not exist; sending again checks first, so it can't be duplicated."
  - **T403** = "ERPNext refused the integration user (permissions); ask the ERP admin."
  - **T0** = "The accepted quote is zero; ERPNext needs an order with a value."
  - **TU** = "Unexpected error while sending; see the server log."
- Claim: a send first sets erp_status `sending` with a conditional update, only from not_sent, failed, or a
  `sending` older than 2 minutes (age measured from erp_attempted_at). No row lock is held during HTTP.
- "Clar." = the Clarifications section of `requirements.md` (2026-10-14).
- EBn = "Existing Behavior To Preserve" n in `brownfield-contract-inputs.md`.

## Brownfield regressions (run first)
| ID | Layer | AC/FM | Given | Expect | Failure signal |
|---|---|---|---|---|---|
| BRT-1 | U | EB1, FM1 (models.py) | D1; c1 raises Unavailable; POST won, delivery 2026-10-29 | 302 to deal; stage won, amount 235.88, closed_at set, Q133 accepted, exactly 1 StageChange(→won) | deal open, 0 or 2 StageChanges, or 500 |
| BRT-2 | U | EB1, FM1 | as BRT-1 but c5 raises Refused("Item FG-CT-300 is disabled") | same Won effects as BRT-1 | Won rolled back by the refusal |
| BRT-3 | U | EB1 (views/opportunities.py) | D1 Won, fake OK | flashes include "Won: Cable trays for plant 2, MYR 235.88." | 003 Won flash missing or reworded |
| BRT-4 | U | EB2 | deal with only a draft quote; POST won with 2026-10-29 | "Send a quote before marking the deal won."; still open; delivery_date null; `fake.calls == []` | ERP called or date stored |
| BRT-5 | U | EB3 | D1 already won; POST won again | "This deal is closed."; amount and erp fields unchanged; no call | a second send |
| BRT-6 | U (TransactionTestCase, 2 threads) | EB3, FM3 | D1; two Won POSTs at once; fake c5 sleeps 0.5 s | one Won, one "This deal is closed.", 1 StageChange, ≤ 1 c5 call | 2 c5 calls, IntegrityError or 500 |
| BRT-7 | U | EB4 (detail.html) | D1 won (sent, failed, not_sent each) | "Won on 15 Oct 2026."; no Move, Mark won, Edit, Reassign, Lost or New quote control; POST edit refused | an action shows next to the ERP panel |
| BRT-8 | U | EB5, AC2, AC11 | siti: 3 won deals this quarter (sent / failed / not_sent) + 1 lost | win rate 75 %, won-in-quarter value, My day "won this month": same as with all three not_sent | a figure moves with erp_status |
| BRT-9 | U | EB6 (urls.py) | D1 open, ERP configured; POST move to stage=won | refused as MOVE-3; no call | Move reaches Won or sends |
| BRT-10 | U | EB7 | D1's sent quote valid_until = yesterday; a leftover pending quote | Won succeeds; order lines from Q133 only | Won blocked or pending lines sent |
| BRT-11 | U | EB8 | jason POSTs won on D1 | 404; deal open; no call | 403, 302 or a send |
| BRT-12 | U | EB9 (settings.py) | GET won D1 page in each ERP state | CSP header as SEC-4; HTML has no `style=`, no inline `<script>`, no ` on[a-z]+=` | panel adds inline style or script |
| BRT-13 | U | EB9 | 003 `test_security.py`, `test_auth.py` (lockout, GuardedUserAdmin, UI-2 500 page) | pass unmodified | any failure |
| BRT-14 | U | EB10 (rules.py) | 003 Q-1 and Q-2; quote detail page | 235.88 and 0.30; page still says "excluding SST" | money functions changed |
| BRT-15 | U | FM16 (tests/base.py) | `bash CRM/scripts/test.sh` | the 155 tests from 003 pass unmodified, plus the 004 tests | any of the 155 fails or was edited |
| BRT-16 | U | AC11 (migration 0004) | migrate to 0003; a won deal (1000.00) and an open deal; migrate to 0004 | won deal: erp_status not_sent, erp_order null, delivery_date null; stage, amount, closed_at unchanged | migration fails or backfills sent/failed |
| BRT-17 | M | EB11, FM11 | after the ERP, contract and CRM runs: `bench --site localhost execute ombak_mfg.setup.check_demo.check` | 18/18 PASS | any check fails |
| BRT-18 | M | EB12, AC19 | snapshot `name, modified, grand_total` of SOs with `po_no LIKE 'DEMO-%'`, rerun `setup_masters` on localhost, snapshot again | same 19 rows, identical | count ≠ 19 or a row changed |
| BRT-19 | U | EB12 | every order body the CRM builds | no `po_no` key; `crm_reference` never starts with "DEMO-" | demo.run's marker confused |
| BRT-20 | C | EB13 | after CT-2 submits an order | no Work Order and no Production Plan references it | something auto-plans |
| BRT-21 | E | EB14 (masters.py) | `test_terminal_role_is_least_privilege`, `test_integration_user_gets_keys_from_site_config` | pass unmodified | terminal role widened |
| BRT-22 | M | EB14 (ERP/docker-compose.yml) | `bash ERP/scripts/test-portal.sh` | 63 OK, 0 skipped (CT-7 403s intact) | < 63 or CT-7 fails |
| BRT-23 | E | EB15 (test_setup_masters.py) | `test_second_run_adds_nothing` and the other 31 ERP tests | 32 pass unmodified | idempotency broken |
| BRT-24 | M | EB15 (test-erp.sh) | read the site args of `test.sh`, `test-portal.sh`, `test-erp.sh` | each targets `test.localhost` or `contract.localhost`, never `localhost` | a suite writes to the demo |
| BRT-25 | M | EB9 (CRM/docker-compose.yml, requirements.txt) | `cd CRM && docker compose up -d --build` without the override | CRM starts, sign-in works, `web` has no ERPNEXT_URL | standalone CRM broken |

## Won, delivery date and send
| ID | Layer | AC/FM | Given | Expect | Failure signal |
|---|---|---|---|---|---|
| WON-D-1 | U | 1 | GET open D1 page | Won form has `<input type="date" name="delivery_date" required min="2026-10-15" value="2026-10-29">` labelled "Requested delivery date" | field missing or default wrong |
| WON-D-2 | U | 1, FM14 | now = 2026-10-14 23:00 UTC (= 2026-10-15 07:00 KL) | min 2026-10-15, value 2026-10-29 | 2026-10-14 / 2026-10-28 (UTC date) |
| WON-D-3 | U | 1, FM14 | same instant; POST delivery_date 2026-10-14 | 400; error beside the field; deal open; Q133 still sent; `fake.calls == []` | accepted because it is "today" in UTC |
| WON-D-4 | U | 1 | same instant; POST 2026-10-15 | 302; Won; delivery_date 2026-10-15 | today refused |
| WON-D-5 | U | 1, FM16 | POST without delivery_date | 400; input has `aria-invalid="true"` and `aria-describedby` = the error's id; error beside the field | 302 with a flash, or error at page top |
| WON-D-6 | U | 1 | POST delivery_date "2026-02-30" | 400 as WON-D-5; deal open | 500 |
| WON-D-7 | U | 1 | POST 2026-11-30 | delivery_date 2026-11-30 stored with all 003 Won effects (BRT-1) | date not stored |
| WON-D-8 | U | 1, Clar. | KL today T; POST T + 365 days, then T + 366 days (Won and resend) | T + 365 accepted; T + 366 → 400 "The delivery date can't be more than a year ahead." by the field; input `max` = T + 365 (round 2) | any future date accepted |
| WON-D-9 | U | 3, Clar. | `claim_send` raises DatabaseError on Won and on resend | 302, Won kept, flash "Unexpected error while sending; see the server log."; the deal can be sent again (round 2, fix 92a7644) | 500 |
| SEND-1 | U | 3 | D1 Won, fake OK | calls in order c1, c2, c4b, c5; `msg-success` "Sales order SAL-ORD-2026-00020 created in ERPNext." | no send, or wrong order |
| SEND-2 | U | 3, 11 | same, read the deal as the Won response returns | erp_status sent, erp_order SAL-ORD-2026-00020, erp_error "", erp_attempted_at 2026-10-15 01:00 UTC | not stored, left `sending`, or left to a background job |
| SEND-3 | U (TransactionTestCase) | 2, FM1 | fake c1 reads D1 through a second DB connection | it sees stage won, amount 235.88, Q133 accepted | still open: the call ran inside the Won transaction |
| SEND-4 | U | 2, FM13 | c1 raises Unavailable | 302 to the deal; Won kept; `msg-warning` T1; erp_status failed | 500 or Won undone |
| SEND-5 | U | 14, NFR | c1 raises Unavailable | `fake.calls == [c1]`: nothing after the first Unavailable | more calls (up to 5 × 10 s) |
| SEND-6 | U (client) | 14, NFR | any request | `urlopen(..., timeout=10)` | no timeout or a longer one |
| SEND-7 | U (client) | 14, NFR | local socket that accepts and never answers; timeout patched to 0.5 s | Unavailable within 1.5 s | hangs |

## Customer and order content
| ID | Layer | AC/FM | Given | Expect | Failure signal |
|---|---|---|---|---|---|
| CUST-1 | U | 4 | D1 (TEC in the fake) | c2 only; no c3, no c4; order customer "Tanjung Electrical Contractors Sdn Bhd" | customer created again |
| CUST-2 | U | 4, FM8 | CRM account "TANJUNG ELECTRICAL CONTRACTORS SDN BHD"; fake has the mixed-case name | no c3; order customer = the name c2 returned | duplicate customer, or the CRM's spelling sent |
| CUST-3 | U | 5 | deal on SKS | c3 body == `{"customer_name": "Seri Kembangan Steel Works Sdn Bhd", "customer_type": "Company", "customer_group": "Commercial", "territory": "Malaysia", "tax_id": "202001023456"}` | any key differs |
| CUST-4 | U | 5 | deal on JPE | territory "Singapore", tax_id "201812345K" | Malaysia |
| CUST-5 | U | 5 | account in Sabah; account in Labuan | territory "Malaysia" | Singapore or an error |
| CUST-6 | U | 5 | SKS with registration_no "" | c3 body has no `tax_id` | `"tax_id": ""` |
| CUST-7 | U | 5 | SKS | one c4: address_type "Billing", address_line1 "Lot 5, Jalan SR 8/3", city "Seri Kembangan", state "Selangor", pincode "43300", country "Malaysia", phone "+60 3-8941 2200", non-empty address_title, links `[{"link_doctype": "Customer", "link_name": <c3 name>}]` | link or field missing |
| CUST-8 | U | 5, FM8 | SKS with city "" | no c4; customer created; order sent | Address with an empty city |
| CUST-9 | U | 5, FM8 | SKS with address "" | no c4 | Address with an empty line 1 |
| CUST-10 | U | 5, FM8 | SKS with postcode "" and phone "" | c4 has no `pincode` or `phone` with "" | empty strings sent |
| CUST-11 | U | 5 | second won deal on SKS after CUST-3 | c2 finds it; no second c3 or c4 | second customer or address |
| CUST-12 | U (client) | 4 | customer name "A&B Steel / Fab #1 Sdn Bhd" | path ends `/api/v2/document/Customer/A%26B%20Steel%20%2F%20Fab%20%231%20Sdn%20Bhd` | unquoted `/` or `#` |
| CUST-13 | U (client) | 4 | c2 answers 404 | "missing" (not Refused); c3 follows | 404 treated as a failure |
| CUST-14 | U | 4, Clar. | TEC's account name stored as " Tanjung Electrical Contractors Sdn Bhd " | c2 path uses the stripped name; no c3 | padded name → 404 → duplicate customer |
| CUST-15 | U | 5, Clar. | deal on SKS; c3 OK; c4 raises Refused("Address Line 1 is mandatory") | failed with that message; no c5 | order sent anyway, or the reason lost |
| CUST-16 | U | 5, Clar. | owner resends CUST-15's deal | c2 finds the customer; no c3, no c4; one c5; sent | second customer, or the Address retried |
| SO-1 | U | 6 | D1 Won | c5 body: customer, company "Ombak Metal Works Sdn Bhd", transaction_date "2026-10-15", delivery_date "2026-10-29", currency "MYR", crm_reference "QT-2026-00133", disable_rounded_total 1 | a key missing or different |
| SO-2 | U | 6, FM6 | D1 Won | c5 body has `"docstatus": 0`, then one c5b submit of the name c5 returned (round 1: an insert with docstatus 1 keeps status "Draft") | inserted as submitted, or never submitted |
| SO-3 | U | 6, FM14 | Won at 2026-10-14 23:00 UTC | transaction_date "2026-10-15" | "2026-10-14" |
| SO-4 | U | 7 | Q133 = tray 3 @ 7.5 %, frame 2 @ 5 % | items == `[{FG-CT-300, qty 3, rate 85.00, delivery_date 2026-10-29, warehouse "Finished Goods - OMW"}, {FG-EBF-1000, qty 2, rate 1450.00, same date and warehouse}]`, in that order | merged, reordered or net rates |
| SO-5 | U | 7, FM4 | tray line snapshotted at 85.00; then Product.list_price = 90.00 | rate 85.00; discount 19.12 | rate 90.00 |
| SO-6 | U | 7, FM7 | D1 also has superseded Q131 (5 × tray), draft Q134 (100 × frame), pending Q135 | items only from Q133 | another quote's lines |

## Exact total, zero total and SST
| ID | Layer | AC/FM | Given | Expect | Failure signal |
|---|---|---|---|---|---|
| TOT-1 | U | 8, FM4 | D1: 3 × 85.00 @ 7.5 % = 235.88 | `"apply_discount_on": "Net Total"`, `"discount_amount": 19.12` (number, 2 dp) | 19.13, "19.12", or 7.5 % sent |
| TOT-2 | U | 8, FM4 | D1 | no item has discount_percentage or discount_amount | line discounts left to ERPNext |
| TOT-3 | U | 8 | 3 × 85.00 @ 12.5 % = 223.13 | discount_amount 31.87 | 31.88 |
| TOT-4 | U | 8 | 40 × 85.00 @ 7.5 % = 3,145.00 | discount_amount 255.00 | |
| TOT-5 | U | 8 | tray 3 @ 7.5 % + frame 2 @ 5 % = 2,990.88 | discount_amount 164.12 | float drift |
| TOT-6 | U | 8 | 10 × 85.00 @ 0 % = 850.00 | no `discount_amount` key | `"discount_amount": 0` |
| TOT-7 | U | 8, Clar. | fake c5 returns net_total 235.89 | erp_status sent; erp_order SAL-ORD-2026-00020; erp_error and the warning flash = "ERPNext order SAL-ORD-2026-00020 totals MYR 235.89, the quote MYR 235.88; check it in ERPNext." | mismatch swallowed, order name dropped, or marked failed |
| TOT-8 | U | 8, 12, Clar. | c1 finds an order with net_total 200.00 | adopted; status sent; erp_error is the same warning with MYR 200.00 | adoption skips the check |
| TOT-9 | U | 8 | c5 returns net_total 235.88 (JSON float) | no warning | float vs Decimal compare warns |
| ZERO-1 | U | 10, FM15 | Q133 = 3 × tray @ 100 % (0.00) | Won kept (amount 0.00); failed with T0; `fake.calls == []` | zero order sent, or Won blocked |
| ZERO-2 | U | 10 | owner resends ZERO-1's deal | still failed with T0; no call | zero order on resend |
| TAX-1 | U | 9 | D1 (Johor) | c4b made; body `taxes_and_charges` "Malaysia SST - OMW"; `taxes` == the template row exactly | no rows (ERPNext saves 0 tax) |
| TAX-2 | U | 9 | fake template rate 5 | body taxes[0].rate 5 | 10 hard-coded |
| TAX-3 | U | 9, FM5 | template with 2 rows | body taxes == those 2 rows, nothing added | 3 rows (added twice) |
| TAX-4 | U | 9, FM5 | deal on JPE (Singapore) | no c4b; no `taxes_and_charges`; no tax rows | SST on an export |
| TAX-5 | U | 9, FM5 | c4b raises Refused("Sales Taxes and Charges Template Malaysia SST - OMW not found") | no c5; failed with that message | order sent without SST |
| TAX-6 | U | 9, Clar. | accounts in Kuala Lumpur, Sabah and Labuan | c4b made; SST rows present for each | East Malaysia or Labuan treated as export |

## Idempotency, sending claim and errors
| ID | Layer | AC/FM | Given | Expect | Failure signal |
|---|---|---|---|---|---|
| IDEM-1 | U (client) | 12 | c1 for QT-2026-00133 | GET `/api/v2/document/Sales%20Order`; decoded fields `["name","docstatus","net_total","grand_total"]`, filters `[["crm_reference","=","QT-2026-00133"],["docstatus","<",2]]` | filter missing |
| IDEM-2 | U | 12 | fake holds SAL-ORD-2026-00020 for QT-2026-00133 (net 235.88) | sent with that name; `fake.calls == [c1]` | any c2-c5 call |
| IDEM-3 | U | 12, FM2 | c5 times out after the fake stored the order → failed; owner resends | resend calls `[c1]` only; sent with SAL-ORD-2026-00020; fake holds 1 order | second order |
| IDEM-4 | U | 12 | resend; c1 empty | exactly one c5 | none or two |
| IDEM-5 | U | 13, FM3 | c5 raises Refused("Duplicate entry 'QT-2026-00133'…") and the order now exists | calls end c5, c1; sent with that order's name | failed |
| IDEM-6 | U | 13, Clar. | a cancelled order holds QT-2026-00133: c1 empty, c5 refused as duplicate, second c1 empty | failed with ERPNext's message; exactly 2 c1 and 1 c5 | retry loop or crash |
| IDEM-7 | U (TransactionTestCase, 2 threads) | 15, FM3 | deal on SKS failed; siti and hafiz POST send at once; c5 sleeps 0.5 s | the conditional claim updates 1 row for one request and 0 for the other; one c3 and one c5 in total; one order | two orders or two customers (read-then-write check) |
| IDEM-8 | U | 11 | erp_order "SAL-ORD-2026-00020" on two deals | both saved, no IntegrityError (round 1: order names are unique per ERPNext site only; `crm_reference` guards duplicates) | IntegrityError, so a send to another site gives a 500 |
| CLAIM-1 | U (TransactionTestCase) | 15, 11 | D1 Won; fake c1 reads D1 through a second connection | it sees erp_status `sending`, erp_attempted_at = now (claimed and committed before any call) | `not_sent`: no claim, or the claim is still uncommitted |
| CLAIM-2 | U | 15 | D1 failed; owner POSTs send | claim succeeds (failed → sending), then sent | failed deals can't be resent |
| CLAIM-3 | U | 15, FM3 | D1 `sending`, erp_attempted_at 1 minute ago; owner POSTs send | refused; no call; still `sending` with the same erp_attempted_at | a second send while the first is in flight |
| CLAIM-4 | U | 15 | D1 `sending`, erp_attempted_at 3 minutes ago; fake holds no order | claimed again; c1, then one c5; sent | a stuck `sending` can never be resent |
| CLAIM-5 | U | 15, FM2 | as CLAIM-4, but the fake already holds the order | adopted via c1; no c5 | second order |
| CLAIM-6 | U (TransactionTestCase) | 15, FM1 | while fake c5 sleeps 2 s, in a Won send and in a resend, a second connection runs `select_for_update(nowait=True)` on D1 | succeeds: no row lock is held during HTTP | "could not obtain lock" |
| CLAIM-7 | U (TransactionTestCase) | 15 | while c5 sleeps 3 s: hafiz GETs D1's page; siti logs a call on D1 | both answer within 1 s; the activity is saved | requests wait for the send |
| CLAIM-8 | U | 11, 15 | c5 raises Refused, then Unavailable, then RuntimeError (3 runs) | erp_status ends failed each time, never `sending` | stuck `sending` blocks resends for 2 minutes |
| ERR-1 | U | 14 | c5 raises Unavailable (timeout) | failed; erp_error == T1; warning flash T1 | other text |
| ERR-2 | U (client) | 14 | urlopen raises URLError(ConnectionRefusedError) / socket.timeout | Unavailable | uncaught → 500 |
| ERR-3 | U (client) | 14 | HTTP 401, 500, 502, 503 | Unavailable | Refused with HTML text |
| ERR-4 | U (client) | 14 | HTTP 403 | Refused with T403 | raw ERPNext text |
| ERR-5 | U (client) | 14, FM10 | 417 `{"errors": [{"message": "Could not find Item: <strong>FG-XX-999</strong>", "exception": "Traceback (most recent call last): … LinkValidationError"}]}` | message "Could not find Item: FG-XX-999"; no "Traceback", no "LinkValidationError" | tags or exception kept |
| ERR-6 | U (client) | 14 | message `Customer &quot;A&amp;B&quot; is disabled` | `Customer "A&B" is disabled` | entities shown |
| ERR-7 | U (client) | 14, Clar. | two errors "Value missing for: Delivery Date", "Row 1: Rate is mandatory" | "Value missing for: Delivery Date Row 1: Rate is mandatory" (one space) | only the first, or another separator |
| ERR-8 | U | 14 | a 1,000-char message | erp_error ≤ 300 chars, starts with the message's first 100 chars | full text stored |
| ERR-9 | U (client) | 14, Clar. | 417 with body `<html><body>Bad request</body></html>` | Refused "ERPNext rejected the request (417)." | JSONDecodeError → 500, or HTML shown |
| ERR-10 | U (client + view) | 14, FM10 | urlopen raises HTTPError 401, then URLError; Won; render page; capture all logs | "s3cr3t-xyz" and "token k:" absent from erp_error, flashes, page and log output | secret in a log line |
| ERR-11 | U | 14, FM10 | Refused, then Unavailable, during Won | deal page 200; no "Traceback", no exception class name | 500 or class name shown |
| ERR-12 | U (client) | 14 | 404 and 409 on c5 | Refused(message) | Unavailable |
| ERR-13 | U | Clar., FM13 | D1 Won; fake c4b returns `{}` (no `taxes`), so the mapping raises | 302 to the deal; Won kept; failed with TU; flash TU | 500 page, Won lost, or `KeyError` shown |
| ERR-14 | U | Clar. | owner resends; fake c5 raises RuntimeError("boom") | 302; failed with TU | 500 page |
| ERR-15 | U | Clar., FM10 | ERR-13 with all logs captured | an ERROR record for the send; no "s3cr3t-xyz" and no "token k:" in any record | secret logged |

## Resend, permissions and not configured
| ID | Layer | AC/FM | Given | Expect | Failure signal |
|---|---|---|---|---|---|
| RES-1 | U | 15 | D1 failed (T1); siti POSTs `/deals/<pk>/erp/send/` with 2026-10-29 | 302 to deal; sent; success flash | |
| RES-2 | U | 15 | hafiz POSTs the same | sent | manager refused |
| RES-3 | U | 15, FM9 | jason POSTs | 404; no call; still failed | 403 or a send |
| RES-4 | U | 15, Clar. | D1 sent; owner POSTs | 302; flash "This deal's order is already in ERPNext."; no call; erp_order unchanged | second order or a 500 |
| RES-5 | U | 15, FM9 | GET the send URL | 405; no call | GET sends |
| RES-6 | U | 15, FM9 | GET the deal page of a not_sent and a failed deal | `fake.calls == []` | page view triggers a send |
| RES-7 | U | 15 | POST without CSRF (`enforce_csrf_checks`) | 403; no call | |
| RES-8 | U | 15, Clar. | owner POSTs send on an open deal; on a lost deal | 302; flash "Only won deals can be sent."; no call | order for a non-won deal |
| RES-9 | U | 15 | pre-004 won deal (not_sent, delivery_date null) | form prefilled 2026-10-29; owner send → sent | old deals can't be sent |
| RES-10 | U | 15 | failed deal, stored delivery_date 2026-10-20 | prefilled 2026-10-20 | |
| RES-11 | U | 15 | failed deal, stored 2026-10-01 | prefilled 2026-10-29 | past date prefilled |
| RES-12 | U | 15, Clar., FM14 | failed deal, stored 2026-10-20; POST send with 2026-10-14 | 400; error beside the date field; delivery_date still 2026-10-20; still failed (no claim); no call | past date accepted or claimed |
| RES-13 | U | 15, 6 | failed deal; resend on 2026-10-20 with 2026-11-05 | body transaction_date 2026-10-20; delivery_date and every item delivery_date 2026-11-05 | Won-day or stored date used |
| RES-14 | U | 15, Clar. | POST send with no date | 400; error beside the field; no claim; no call | 302, or a send with no date |
| RES-15 | U | 15, Clar. | failed deal, stored 2026-10-20; resend with 2026-11-05 succeeds | delivery_date 2026-11-05 | stored date kept |
| CFG-1 | U | 16, FM13 | `ERPNEXT_URL` unset; D1 Won | 302; 003 Won flash; no request; no "Sales order" flash | network attempted |
| CFG-2 | U | 16, 17 | same; GET the deal | panel "ERP link not configured" in a neutral `chip` (no colour modifier) | red chip or failed |
| CFG-3 | U | 16 | not configured; POST send directly (the form is hidden) | no request; erp_status unchanged | network attempted |
| CFG-4 | U | 16 | settings import with no `ERPNEXT_*` env | CRM starts; ERP not configured | ImproperlyConfigured |
| CFG-5 | U | 16, Clar. | `ERPNEXT_URL=""`; D1 Won | as CFG-1 and CFG-2: no request; "ERP link not configured" | empty string used as a URL → ValueError or 500 |
| CFG-6 | U | 16, 17, Clar. | not configured; siti and hafiz view a won not_sent deal | no send form in the panel | a form that can never work |

## Screens
| ID | Layer | AC/FM | Given | Expect | Failure signal |
|---|---|---|---|---|---|
| PANEL-1 | U | 17, Clar. | D1 sent, erp_attempted_at 2026-10-14 23:30 UTC | "ERP order" panel; `chip-green` "sent"; link text SAL-ORD-2026-00020, href exactly `http://localhost:8080/app/sales-order/SAL-ORD-2026-00020`; "15 Oct 2026" and "07:30" (KL) | UTC date/time, or a wrong link |
| PANEL-2 | U | 17 | D1 sent | no send form | resend offered |
| PANEL-3 | U | 17 | D1 failed (T1), erp_attempted_at 01:00 UTC; viewer siti | `chip-red` "failed"; T1; "09:00"; POST form to `/deals/<pk>/erp/send/` with csrf, date input and "Send again" | reason, time or form missing |
| PANEL-4 | U | 17 | pre-004 not_sent deal; viewer hafiz | neutral chip "not sent"; send form | |
| PANEL-5 | U | 17 | open deal; lost deal | no "ERP order" panel | |
| PANEL-6 | U | 17 | panel HTML in every state | no `style=`, no inline script, no `on*=`; `.btn` and `_field.html` markup (44 px in app.css) | |
| PANEL-7 | U | 17, FM10 | erp_error `<script>alert(1)</script>` (ERPNext text after unescape) | rendered escaped (`&lt;script&gt;`) | script injected |
| PANEL-8 | U | 8, 17, Clar. | D1 sent with TOT-7's warning in erp_error | `chip-amber` with the warning text; the order link; no send form | green chip hides the mismatch |
| DAY-1 | U | 18 | siti: D1 failed, D2 failed, D3 sent, D4 not_sent | "ERP orders not created" lists D1 and D2, linking to `/deals/<pk>/` | sent or not_sent listed |
| DAY-2 | U | 18 | jason has a failed deal | not on siti's panel | another rep's deal |
| DAY-3 | U | 18 | hafiz | lists D1, D2 and jason's failed deal | own deals only |
| DAY-4 | U | 18 | no failed deals | no "ERP orders not created" heading | empty panel shown |
| DAY-5 | U | 18 | D1 failed, then resent OK | D1 leaves the panel | stale row |
| DAY-6 | U | 18, Clar. | siti's D1 sent with TOT-7's warning | not on "ERP orders not created" | a mismatch listed as a failed send |

## ERP side
| ID | Layer | AC/FM | Given | Expect | Failure signal |
|---|---|---|---|---|---|
| ERP-1 | E | 19 | conf `crm_api_key` "test-crm-key", `crm_api_secret` "test-crm-secret"; setup_masters | role "CRM Integration"; user crm.integration@ombakmetal.example enabled with it; api_key test-crm-key; decrypted secret test-crm-secret | |
| ERP-2 | E | 19, FM12 | that user's roles | none of Sales Manager, Sales User, System Manager, Accounts User, Stock User, Manufacturing User | broad standard role |
| ERP-3 | E | 19 | Custom Field "Sales Order-crm_reference" | fieldtype Data, unique 1, read_only 1, no_copy 1 | |
| ERP-4 | E | 13, 19 | two SOs with crm_reference "QT-TEST-1" | second insert raises a duplicate error | both saved |
| ERP-5 | E | 19 | `frappe.copy_doc` of an SO with crm_reference | the copy's crm_reference is empty | copied: amend collides |
| ERP-6 | E | 19 | SST account | exists under "Duties and Taxes - OMW", account_type Tax | |
| ERP-7 | E | 19 | template "Malaysia SST - OMW" | company OMW; is_default 0; one row: On Net Total, rate 10, account_head = ERP-6's account | default 1: every new SO taxed |
| ERP-8 | E | 19 | Customer Group "Commercial"; Territories "Malaysia", "Singapore" | exist; is_group 0 each | "Cannot select a Group type" |
| ERP-9 | E | 19 | setup_masters twice | counts of Role, User, Custom Field, Account, Sales Taxes and Charges Template, Customer Group, Territory and the DEMO-2 list unchanged by the second run | |
| ERP-10 | E | 19 | the default Sales Taxes and Charges Template before and after | unchanged | site-wide default replaced |
| PERM-1 | E | 20 | `has_permission` as the CRM user | True: Sales Order read/create/submit, Customer read/create, Address create, Item read, the SST template read | |
| PERM-2 | E | 20, FM12 | `has_permission` as the CRM user | False: Sales Order cancel/delete; Sales Invoice, Work Order, Job Card read/create | |
| PERM-3 | E | 20, FM12 | test users with only Sales User / only Sales Manager | Sales Order read/create/submit and Customer read/create still True | Custom DocPerm froze standard roles |
| PERM-4 | E | 20 | the Shop Floor Terminal user | Sales Order and Customer read/create False | terminal widened by the new perms |
| PERM-5 | E | 20 | the CRM user and an Address owned by Administrator, linked to a customer | read allowed; write and delete refused; an SO for that customer can be created and submitted | 403 on the address read during SO insert (found at deploy, fix 38371ba) |
| PERM-6 | E | 20, FM12 | the CRM user; a draft and a submitted Sales Order created by Administrator; one it created itself | its Sales Order rule is `if_owner` (also where the rule predates it); it reads, writes and submits only its own order | write or submit on another user's order (round 1, fix 0292249) |

## Running it
| ID | Layer | AC/FM | Given | Expect | Failure signal |
|---|---|---|---|---|---|
| NET-1 | M | 21 | `cd CRM && docker compose -f docker-compose.yml -f docker-compose.erp.yml config` | `web` env: ERPNEXT_URL http://backend:8000, ERPNEXT_SITE localhost, ERPNEXT_DESK_URL http://localhost:8080, non-empty API key/secret; `web` on the ERP network, marked external | |
| NET-2 | M | 21 | same with `ERPNEXT_SITE=contract.localhost ERPNEXT_API_KEY=k2` exported | config shows those values | hard-coded values |
| NET-3 | M | 21 | ERP compose, then `bench --site localhost show-config` | crm_api_key/secret set, equal to the override's default key/secret | out-of-the-box 401 |
| NET-4 | M | 21 | in `web` with the override: GET http://backend:8000/api/method/ping, Host localhost | 200 `{"message": "pong"}` | network not joined |
| NET-5 | M | 21 | ERP stack not created; CRM `up` with the override | fails with an error naming the missing network | starts, every send fails |
| NET-6 | M | 21 | README | how to run both, the env, the send flow, "10 % assumed; confirm per HS code", Singapore = export under K2, the reseed risk; the old "ERPNext adds tax" and "without mapping" claims gone | |

## Live contract (`CRM/scripts/test-erp.sh`, references `QT-CT-<run>-<n>`, run-unique customer names)
| ID | Layer | AC/FM | Given | Expect | Failure signal |
|---|---|---|---|---|---|
| CT-1 | C | 22, FM11 | `ERPNEXT_SITE=localhost CRM/scripts/test-erp.sh` | exits non-zero before any request, naming contract.localhost | runs on the demo |
| CT-2 | C | 6, 8, 9 | new MY customer; 3 × FG-CT-300 at 85.00, discount 19.12, SST row | docstatus 1; net_total 235.88; one tax row 23.59; grand_total 259.47 | 235.87/235.89, 0 tax, or 259.00 |
| CT-3 | C | 9 | SG customer; 2 × FG-EBF-1000 at 1450.00, discount 145.00, no tax | no tax rows; net_total = grand_total = 2755.00 | SST on export |
| CT-4 | C | 8, 9 | MY; 3 × FG-CT-300 at 12.5 % (discount 31.87) | net 223.13; tax 22.31; grand 245.44 | |
| CT-5 | C | 8, 9 | MY; tray 3 @ 7.5 % + frame 2 @ 5 % (discount 164.12) | net 2990.88; tax 299.09; grand 3289.97 | per-item rounding drift |
| CT-6 | C | 12 | lookup by CT-2's reference | one row, CT-2's name | |
| CT-7 | C | 13 | create again with CT-2's reference | Refused; lookup still returns one row | second order |
| CT-8 | C | 4, FM8 | GET Customer by CT-2's customer name lower-cased | 200 with the original-case name | 404: FM8's protection fails, escalate |
| CT-9 | C | 20 | as the CRM user: cancel CT-2's order; DELETE it; GET Sales Invoice; POST Work Order; GET Job Card | Refused with T403 each; CT-2 still docstatus 1 | any allowed |
| CT-10 | C | 14 | `ERPNEXT_API_SECRET=wrong` | Unavailable | Refused with raw text |
| CT-11 | C | 2, 3, 5, 9 | `send_order` for a won fixture deal on a new MY account with an address | deal sent; ERPNext order net_total == deal amount 235.88; crm_reference = the quote number; Address linked | |
| CT-12 | C | 4, 20 | an existing customer whose primary Address is owned by Administrator (fixture `existing_customer()` on contract.localhost) | create + submit an SO as the CRM user succeeds | `Refused` "ERPNext refused the integration user (permissions)" |
| CT-13 | C | 12, 20, FM12 | a draft and a submitted SO created by Administrator (fixture `others_orders()`), each with a `crm_reference` | as the CRM user: the lookup doesn't find them; GET, PUT and submit are refused; both unchanged | the CRM key reads, edits or submits orders it didn't create |

## Contract gaps (still open after the 2026-10-14 clarifications)
1. **A `sending` deal on screen.** AC17 gives chips for sent (green, or amber on a mismatch), failed, not sent
   and not configured, but none for `sending`. It doesn't say whether a stale `sending` (over 2 minutes) shows
   the send form.
2. **Send refused by a fresh `sending`.** No flash text or status is given, and it isn't said whether the date
   entered is still stored. CLAIM-3 asserts only "refused, no call".
3. **A send whose process dies after the claim.** The deal stays `sending`. It is never failed, so it never
   reaches My day (AC18 lists failed sends only), until someone resends after 2 minutes.
4. **The 2-minute age.** The cases assume it is measured from `erp_attempted_at`, set at the claim. The
   contract doesn't name the field.
