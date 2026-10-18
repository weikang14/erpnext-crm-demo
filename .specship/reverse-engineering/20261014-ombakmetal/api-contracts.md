# API Contracts

## CRM: existing endpoint 004 builds on
`POST /deals/<int:pk>/won/` (`CRM/sales/urls.py:36`, name `opportunity_won`):
- needs login, POST and a CSRF token;
- answers 404 when the deal is outside the user's scope (`CRM/sales/access.py:41-42`) and 405 on GET;
- otherwise always 302 to `/deals/<pk>/`, with a flash: success `Won: {title}, MYR {amount:,.2f}.` or error `str(RuleError)` (`CRM/sales/views/opportunities.py:146-155`).

The CRM has no JSON API, and 004 doesn't need one: nothing calls into the CRM.

## ERPNext REST v2: the shapes 004 will call
The pinned 002 reference is `.specship/completed/002-shopfloor-terminal/artifacts/api-contract.md`. Use **v2 only**, because v1 has a different error shape (that contract, `:10`). Routes are in `frappe/api/v2.py:288-301`. Auth uses the headers `Authorization: token <key>:<secret>`, `Host: <site>` and `Accept: application/json` (`ERP/portal/terminal/erpnext.py:41-47`).

| Call | Request | Success |
|---|---|---|
| Create + submit SO | `POST /api/v2/document/Sales%20Order`, JSON body below; `"docstatus": 1` inserts and submits in one transaction (`frappe/api/v2.py:171-180`; same as `erpnext.py:91-93`) | 200 `{"data": {"name": "SAL-ORD-2026-000NN", …full doc…}}` |
| Look up by reference | `GET /api/v2/document/Sales%20Order?fields=["name","docstatus","grand_total"]&filters=[["<ref field>","=","QT-2026-00133"],["docstatus","<",2]]` (the `_list` shape, `erpnext.py:101-105`) | 200 `{"data": [ {…} ]}` |
| Customer exists? | `GET /api/v2/document/Customer/<url-quoted exact name>`. The name equals `customer_name` because `cust_master_name = "Customer Name"` (erp chunk, live) | 200 `{"data": {…}}`, or 404 DoesNotExist |
| Create customer (if chosen) | `POST /api/v2/document/Customer` `{"customer_name", "customer_type": "Company", "customer_group": "Commercial", "territory"}` (only `customer_name` and `customer_type` are reqd) | 200 `{"data": {"name": …}}` |

Minimal known-good SO body (`ERP/apps/ombak_mfg/ombak_mfg/setup/demo.py:205-215`). Server `set_missing_values` fills every other reqd field: currency MYR, price list `Standard Selling`, naming `SAL-ORD-.YYYY.-`, the address from the primary address, and item name and UOM.
```json
{"customer": "<name>", "company": "Ombak Metal Works Sdn Bhd", "transaction_date": "YYYY-MM-DD",
 "delivery_date": "YYYY-MM-DD", "items": [{"item_code": "FG-CT-300", "qty": 3}], "docstatus": 1}
```
More about the body:
- `delivery_date` must be present (header or item) and must not fall before `transaction_date`, or ERPNext answers 417 "Please enter Delivery Date" (`sales_order.py:425-445`).
- Each item's warehouse defaults to `Finished Goods - OMW` via Item Default (`masters.py:346`).
- The optional `rate`, `price_list_rate`, `discount_percentage`, `discount_amount`, `apply_discount_on`, `additional_discount_percentage`, `disable_rounded_total` and `po_no` are all settable over the API. Their UI sections are hidden by Property Setters `Sales Order Item-discount_and_margin` and `Sales Order-additional_discount_section` (live, this recon).

## Error format and mapping
- Frappe returns `{"errors": [{"message": "<html-ish text>", "exception": "<traceback>"}]}`. Status codes: ValidationError 417, PermissionError 403, DoesNotExist 404, DuplicateEntry 409, AuthenticationError 401 (`frappe/exceptions.py`).
- The portal maps them in `erpnext.py:107-118`:
  - `RequestException`, 401 and >=500 become `ERPNextUnavailable`;
  - 403 becomes `ERPNextError` with a fixed "setup problem" text;
  - any other non-2xx becomes `ERPNextError(text)`.
- The text is `html.unescape(strip_tags(join(errors[].message)))`. A non-JSON body becomes "ERPNext rejected the request (N)." (`:120-128`).
- **Never surface `exception`.** It holds a traceback; a live 403 seen in this recon had one.
- Duplicate guard: the same customer and the same `po_no` give 417 "Sales Order X already exists against Customer's Purchase Order Y" (`sales_order.py:359-385`, `allow_against_multiple_purchase_orders = 0`). It is a SELECT, not a constraint.
