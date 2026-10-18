# API contract: CRM → ERPNext (004)

The CRM is the only caller; nothing calls into the CRM. ERPNext REST **v2 only** (v1 has a
different error shape). Background and evidence:
`.specship/reverse-engineering/20261014-ombakmetal/api-contracts.md`; the 002 terminal's
pinned contract: `.specship/completed/002-shopfloor-terminal/artifacts/api-contract.md`.

## Transport
- Base `ERPNEXT_URL` (compose override: `http://backend:8000`), headers
  `Host: <ERPNEXT_SITE>`, `Accept: application/json`, `Content-Type: application/json`,
  `Authorization: token <ERPNEXT_API_KEY>:<ERPNEXT_API_SECRET>`.
- Timeout 10 s per call. Doctype and document names are URL-quoted in paths.
- Site: `localhost` at runtime, `contract.localhost` in live contract tests (never `localhost`).

## Calls (in send order)
| # | Call | Request | Success | Used for |
|---|---|---|---|---|
| 1 | Look up order | `GET /api/v2/document/Sales%20Order?fields=["name","docstatus","net_total","grand_total"]&filters=[["crm_reference","=","<quote no>"],["docstatus","<",2]]` | 200 `{"data": [ {...} ]}` (empty list = none) | AC12, AC13 |
| 2 | Customer exists? | `GET /api/v2/document/Customer/<quoted name>` | 200 `{"data": {...}}`; 404 = missing | AC4 |
| 3 | Create customer | `POST /api/v2/document/Customer` `{"customer_name", "customer_type": "Company", "customer_group": "Commercial", "territory": "Malaysia"\|"Singapore", "tax_id"?}` | 200 `{"data": {"name": ...}}` | AC5 |
| 4 | Create address (only with address + city) | `POST /api/v2/document/Address` `{"address_title", "address_type": "Billing", "address_line1", "city", "state"?, "pincode"?, "country", "phone"?, "links": [{"link_doctype": "Customer", "link_name": <customer>}]}` | 200 | AC5 |
| 4b | Read SST template (Malaysian customers only) | `GET /api/v2/document/Sales%20Taxes%20and%20Charges%20Template/Malaysia%20SST%20-%20OMW` | 200 `{"data": {"taxes": [{"charge_type", "account_head", "rate", "description"}, ...]}}` | AC9 (rate lives only in the template) |
| 5 | Create order (draft) | `POST /api/v2/document/Sales%20Order` (body below) | 200 `{"data": {"name": "SAL-ORD-2026-NNNNN", "docstatus": 0, "status": "Draft", "net_total", "grand_total", ...}}` | AC6-9 |
| 5b | Submit it (also a draft found by call 1) | `PUT /api/v2/document/Sales%20Order/<quoted name>` `{"docstatus": 1}`; the role needs `write` + `submit` (Frappe's save checks write); proven live on contract.localhost (CT-2, CT-11) | 200 `{"data": {"name", "docstatus": 1, "status": "To Deliver and Bill", "net_total", "grand_total", "taxes", ...}}` | AC6-9 |

Order body:
```json
{"customer": "<customer>", "company": "Ombak Metal Works Sdn Bhd",
 "transaction_date": "YYYY-MM-DD", "delivery_date": "YYYY-MM-DD", "currency": "MYR",
 "crm_reference": "QT-2026-00133", "disable_rounded_total": 1,
 "apply_discount_on": "Net Total", "discount_amount": 19.12,
 "items": [{"item_code": "FG-CT-300", "qty": 3, "rate": 85.00,
            "delivery_date": "YYYY-MM-DD", "warehouse": "Finished Goods - OMW"}],
 "taxes_and_charges": "Malaysia SST - OMW",
 "taxes": [{"charge_type": "On Net Total", "account_head": "<from template>",
            "description": "<from template>", "rate": 10}],
 "docstatus": 0}
```
Then 5b submits it; a draft found by call 1 is submitted, not adopted as a draft. Why two calls: an insert
with `docstatus` 1 keeps status "Draft", because ERPNext's `StatusUpdater.set_status()` returns early for a
new document; submitting a saved draft runs `validate` again, which sets "To Deliver and Bill".
`taxes` = the template's rows from call 4b (charge_type, account_head, rate, description),
sent explicitly because the site doesn't expand templates on REST inserts.
Singapore customers: no `taxes_and_charges`, no `taxes`. `discount_amount` is a JSON number
with 2 decimals, computed in `Decimal` (Σ qty × rate − deal amount); omitted when 0.

## Errors (ERPNext → CRM outcome)
Frappe returns `{"errors": [{"message": "...", "exception": "<traceback>"}]}`.
| ERPNext | CRM client raises | Deal outcome |
|---|---|---|
| timeout, connection error, 401, 5xx | `Unavailable` | failed: "ERPNext didn't answer. The order may or may not exist; sending again checks first, so it can't be duplicated." |
| 403 | `Refused` (fixed text) | failed: "ERPNext refused the integration user (permissions); ask the ERP admin." |
| other 4xx (417 validation, 409/417 duplicate, 404 on create) | `Refused(message)` | failed with the message: `errors[].message` joined, HTML stripped and unescaped, max 300 chars |
| create refused, but call 1 now finds the order | none | adopted: sent (AC13) |

Never read or store `exception`. The API secret never appears in messages or logs.
