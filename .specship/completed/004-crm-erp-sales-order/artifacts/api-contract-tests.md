# API contract tests: CRM → ERPNext REST v2 (004)

All of these are live tests on **`contract.localhost`** only, run by `CRM/scripts/test-erp.sh` (layer C). They
use the real `CRM/sales/erpnext.py` client with the CRM Integration keys. Each run uses its own reference
`QT-CT-<run>-<n>` and customer names ending in `<run>`. They check the **shape the client reads**, not just the
status code: `data` is a **list** for call 1 and an **object** for calls 2-5, and errors come as
`errors[].message`. The CRM never reads `exception`. Call numbers follow `api-contract.md`.

## Calls
| ID | Call | Setup | Request | Verify (shape the CRM reads) | Failure signal |
|---|---|---|---|---|---|
| ACT-1 | 1 lookup | ACT-6 has created an order with reference R | `GET /api/v2/document/Sales%20Order?fields=["name","docstatus","net_total","grand_total"]&filters=[["crm_reference","=","R"],["docstatus","<",2]]` | 200; `data` is a list of length 1 whose item has `name`, `docstatus` 1, numeric `net_total` and `grand_total`. For an unused reference, `data == []`. The client returns `data[0]["name"]`, or "none" | client indexes `data["name"]`, or treats `[]` as an error |
| ACT-2 | 2 customer exists? | ACT-3's customer "A&B Steel / Fab #1 <run> Sdn Bhd" | `GET /api/v2/document/Customer/A%26B%20Steel%20%2F%20Fab%20%231%20<run>%20Sdn%20Bhd` | 200; `data` is an object with `name` equal to the customer name. An unknown name gives 404, which the client reports as missing (not Refused) | unquoted `/` or `#` gives 404, so a second customer is created |
| ACT-3 | 3 create customer | none | `POST /api/v2/document/Customer` `{"customer_name": "A&B Steel / Fab #1 <run> Sdn Bhd", "customer_type": "Company", "customer_group": "Commercial", "territory": "Malaysia", "tax_id": "202001023456"}` | 200; `data` is an object; `data.name` is the name the client later sends as the order's `customer` and the Address's `link_name`. The same call with `territory` "Singapore" also returns 200 (leaf records) | 417 "Cannot select a Group type…"; client reads `data[0]` |
| ACT-4 | 4 create address | ACT-3's customer | `POST /api/v2/document/Address` `{"address_title", "address_type": "Billing", "address_line1": "Lot 5, Jalan SR 8/3", "city": "Seri Kembangan", "state": "Selangor", "pincode": "43300", "country": "Malaysia", "phone": "+60 3-8941 2200", "links": [{"link_doctype": "Customer", "link_name": <ACT-3 name>}]}` | 200; `data` is an object; `data.links[0].link_name` equals the customer | link dropped (Address orphaned) |
| ACT-5 | 4b SST template | none | `GET /api/v2/document/Sales%20Taxes%20and%20Charges%20Template/Malaysia%20SST%20-%20OMW` | 200; `data.taxes` is a list with exactly one row whose `charge_type` is "On Net Total", `rate` 10, and `account_head` and `description` are non-empty. The client copies only those 4 keys | 403 (role can't read it); extra keys such as `name`/`parent`/`idx` copied into the order |
| ACT-6 | 5 create order (draft) + 5b submit (`PUT …/Sales%20Order/<name>` `{"docstatus": 1}`; status must become "To Deliver and Bill", recovery cycle 1) | ACT-3's customer; ACT-5's rows | `POST /api/v2/document/Sales%20Order` with the `api-contract.md` body: 3 × FG-CT-300 at 85.00, `discount_amount` 19.12, `apply_discount_on` Net Total, `disable_rounded_total` 1, `crm_reference` R, the SST rows, `docstatus` 0; then `PUT /api/v2/document/Sales%20Order/<name>` `{"docstatus": 1}` | 200 for both; `data` is an object; `data.name` matches `^SAL-ORD-\d{4}-\d{5}$`; after the PUT `docstatus` 1 and `status` "To Deliver and Bill"; `net_total` 235.88; one `taxes` row with `tax_amount` 23.59; `grand_total` 259.47. The client returns `name` and `net_total` | `docstatus` 0 (draft), 0 tax rows, 235.87/235.89, or 259.00 |
| ACT-7 | 5 (Singapore) | an SG customer (territory Singapore) | same, without `taxes_and_charges` and `taxes`: 2 × FG-EBF-1000 at 1450.00, discount 145.00 | 200; `data.taxes == []`; `net_total` == `grand_total` == 2755.00 | ERPNext adds the template on its own |

## Error mapping
| ID | Situation | Setup | Verify | Failure signal |
|---|---|---|---|---|
| ACT-E1 | 401 → Unavailable | `ERPNEXT_API_SECRET=wrong`; call 1 | raw status 401; the client raises `Unavailable` (deal outcome T1); "wrong" appears nowhere in its text | Refused with ERPNext's text; the secret is echoed |
| ACT-E2 | 403 → Refused (fixed text) | as the CRM user: `GET /api/v2/document/Sales%20Invoice`, `POST /api/v2/document/Work%20Order`, `GET /api/v2/document/Job%20Card`, cancel and `DELETE` ACT-6's order | raw status 403 for each; the client raises `Refused` whose text is exactly "ERPNext refused the integration user (permissions); ask the ERP admin."; ACT-6 is still `docstatus` 1 | 200 for any of them (role too broad); ERPNext's raw text shown |
| ACT-E3 | other 4xx (validation) → Refused(message) | call 5 with item `FG-NOPE-999` | the raw body has `errors`, a list of objects each with `message` and `exception`; the raw `exception` contains "Traceback" (the trap is real). The client's message contains "FG-NOPE-999", no `<`, no "Traceback", no exception class name, and is at most 300 chars | traceback or HTML reaches `erp_error` |
| ACT-E4 | duplicate `crm_reference` → Refused, then adopt | call 5 again with ACT-6's reference R | raw status 409 or 417 with `errors[].message`; the client raises `Refused`. Call 1 then returns ACT-6's name, so `send_order` adopts it (AC13) | a second order created; the 409 mapped to Unavailable |
| ACT-E5 | connection error → Unavailable | `ERPNEXT_URL=http://backend:9` | `Unavailable` raised in ≤ 10 s | hangs, or `URLError` escapes |
| ACT-E6 | never reads `exception` | static check | `grep -nE "[\"']exception[\"']" CRM/sales/erpnext.py` finds nothing | the client reads or stores the traceback |

5xx and timeouts can't be provoked safely on the live site. The client unit rows ERR-2, ERR-3 and SEND-7 in
`test-cases.md` cover them with a mocked `urlopen`.
