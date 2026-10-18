# Data Models (what 004 maps)

## CRM side (PostgreSQL, `CRM/sales/models.py`)
| Entity | Fields 004 reads | Notes |
|---|---|---|
| `Opportunity` (`:221-239`) | `id`, `title`, `account`, `contact` (nullable, SET_NULL), `owner`, `stage`, `amount` Decimal(12,2), `expected_close` date, `closed_at` timestamptz | `amount` = the accepted quote total at Won. Constraint `opportunity_amount_not_negative` (`:239`) |
| `Account` (`:52-81`) | `name` (≤200, unique case-insensitive, `account_name_unique_ci` `:67`), `registration_no`, `address`, `city`, `state` (required), `postcode`, `phone` | `country` is a property: Singapore if the state is Singapore, else Malaysia (`:79-81`). Live: 42 accounts; only 2 have a reg. no., 1 an address, 3 a postcode |
| `Quote` (`:397-455`) | `status = accepted`, `number`, `valid_until`, `sent_at`, `revision` | `number` is a **property**: `QT-{local year}-{pk:05d}` (`:428-430`). It comes from the pk, so a reseeded DB reuses numbers |
| `QuoteLine` (`:535-557`) | `product` FK, `qty` Decimal(10,2) > 0, `unit_price` Decimal(12,2), `discount_pct` 0-100 | `unit_price` is a snapshot of `list_price` at add_line (`:473`). `item_code`/`name`/`uom` are read **live** through the FK |
| `Product` (`:109-120`) | `item_code` ("ERPNext item code", unique), `name`, `uom` (default `Nos`), `list_price`, `active` | Editable in `/admin/`. Nothing syncs it with ERPNext |
| `StageChange` | from, to, by, at | The only record of Won. There is no event or outbox table |
| `RateLimit` (`:560-565`) | `key`, `count`, `expires` | A precedent for a small lock-protected table; not reusable as a sync record |

Money: `line_total = money(qty × unit_price × (100 − disc)/100)`, rounded half-up **per line**. `quote_total` is the sum of the rounded lines (`CRM/sales/rules.py:21-32`). MYR only. There is no currency, tax or SST field anywhere.

**Integration fields: none exist.** There is no ERP order name, sync status, error, attempt count or synced-at. Migrations `0001`-`0003` are applied live, so 004 adds `0004_*`.

## ERP side (ERPNext site `localhost`, live-verified in the erp chunk)
- **Sales Order:** naming `SAL-ORD-.YYYY.-`; existing orders are SAL-ORD-2026-00001..00019 with `po_no` `DEMO-001..019`.
  - Reqd fields are filled server-side except `customer`, `items[].item_code` and `items[].qty`.
  - `po_no` is Data, `allow_on_submit = 1`, not unique, not indexed (live DocField).
- **Customer:** `name == customer_name`. The 5 customers carry type Company, group `Commercial`, territory Johor/Selangor/Singapore, and a `<customer>-Shipping` primary address. None has a tax_id, a default currency or a contact (`ERP/apps/ombak_mfg/ombak_mfg/setup/masters.py:66-83,395-426`).
- **Item:** the 5 FGs have `stock_uom` Nos, a default warehouse `Finished Goods - OMW` and a default BOM (`masters.py:33-64,309-349`).
- **Price list:** `Standard Selling` (MYR). Item Prices are valid from 2025-01-01. There are no Pricing Rules (live).
- **Rounding:** `System Settings.rounding_method = Banker's Rounding`. MYR `smallest_currency_fraction_value = 0` (live), so `rounded_total` = grand_total **rounded to whole ringgit** unless the SO sets `disable_rounded_total` (`frappe/utils/data.py:1365-1379`, `erpnext/controllers/taxes_and_totals.py:837-853`, read in the container this recon).
- **Tax:** the only templates are `Malaysia GST 6/5/10% - OMW` (stale; GST 6 % is default). `add_taxes_from_taxes_and_charges_template = 0`, so REST inserts get **no tax rows**. All 19 demo SOs have `total_taxes_and_charges = 0`.
- **Custom Fields:** ombak_mfg defines none, and `hooks.py` has no `fixtures`.

## CRM ↔ ERPNext join keys
| CRM | ERPNext | Match today |
|---|---|---|
| `Product.item_code` | `Item.name` | 5/5 codes, names, prices (85/520/18/310/1450) and UOM equal (`seed_demo.py:37-44` vs `masters.py:33-64`, live) |
| `Account.name` (exact) | `Customer.name` | Only the first 5 seed accounts (`seed_demo.py:51-57` vs `masters.py:67-83`). Only **3 of 21** live won deals have an ERPNext customer |
| none | SO reference | To be chosen (open question 7) |
