# Market research: won deal → ERP sales order (004)

Researched 2026-10-14. 25 web searches plus ~20 page fetches; queries named product categories only.
Some vendor pages (Celigo docs, PwC, vatcalc, Malay Mail) returned 403, so those points come
from search snippets and are marked *(snippet)*.

## Research Sources
1. Odoo 19 docs, Create and send quotations: https://www.odoo.com/documentation/19.0/applications/sales/crm/acquire_leads/send_quotes.html
2. Odoo forum, Sales and CRM relation (confirming an order doesn't mark the opportunity Won): https://www.odoo.com/forum/help-1/sales-and-crm-relation-213518
3. Frappe CRM ↔ ERPNext integration docs: https://docs.frappe.io/crm/erpnext
4. Frappe CRM issue #2143 (pipeline gaps, customer creation fails at Won): https://github.com/frappe/crm/issues/2143
5. Frappe forum, Sales Order from a CRM quotation fails (`customer = None`): https://discuss.frappe.io/t/issues-with-sales-order-creation-from-quotations/134427
6. ERPNext issue #49874, taxes not calculated on a Sales Order created over REST: https://github.com/frappe/erpnext/issues/49874
7. ERPNext docs, Apply discounts to sales transactions: https://docs.frappe.io/erpnext/user/manual/en/applying-discount
8. HubSpot KB, View the NetSuite sync card: https://knowledge.hubspot.com/integrations/view-the-netsuite-sync-card
9. HubSpot Community, NetSuite "Create Sales Order" workflow action retries: https://community.hubspot.com/t/netsuite-app-integration-creating-sales-order-workflow/97676 *(snippet)*
10. Oracle NetSuite, Troubleshooting Salesforce Connector data sync: https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_0604054741.html
11. Celigo, Salesforce–NetSuite errors (Failed to save record; retry from the dashboard): https://docs.celigo.com/hc/en-us/articles/20702505313691 *(snippet)*
12. Breadwinner, NetSuite Salesforce integration: https://breadwinner.com/netsuite-salesforce-integration/ and https://docs.breadwinner.com/netsuite/creating-netsuite-records-from-within-salesforce
13. Houseblend, Salesforce–NetSuite order integration guide (external ID, empty order-ID guard): https://www.houseblend.io/articles/salesforce-netsuite-order-integration-guide *(snippet)*
14. Stacksync, NetSuite integration duplicate data (timeout + blind retry = duplicate): https://www.stacksync.com/blog/netsuite-integration-failing-fix-duplicate-data-fast *(snippet)*
15. Microsoft Learn, Dynamics 365 Sales, Close a quote (creating an order closes the quote as won): https://learn.microsoft.com/en-us/dynamics365/sales/close-quote
16. Codestringers, Quote to cash: where the quote stops matching the invoice: https://www.codestringers.com/articles/quote-to-cash-where-the-quote-stops-matching-the-invoice *(snippet)*
17. Pipedrive, CRM-ERP integration guide (duplicate customers on both sides): https://www.pipedrive.com/en/crm/integrations/crm-erp-integration *(snippet)*
18. MOF Malaysia press release, targeted revision of sales tax, 1 July 2025: https://www.mof.gov.my/portal/en/news/press-release/targeted-revision-of-sales-tax-rate-and-expansion-of-service-tax-scope-effective-1-july-2025
19. MySST (Royal Malaysian Customs), FAQ on the 2025 sales tax rate change: https://mysst.customs.gov.my/faq-transition-of-sales-tax-rate-changes-2025/
20. Customs Sales Tax 2018 Guide on Manufacturing & Import/Export (official PDF now 404; mirror): https://mysst.customs.gov.my/assets/document/Guide%20Manufacturing%20&%20Import%20Export.pdf, https://taxation88.blogspot.com/2019/01/sst-guide-manufacturing-import-export.html
21. Mondaq, Expansion of SST scope (iron, steel, industrial machinery at 5 % or 10 %): https://www.mondaq.com/sales-taxes-vat-gst/1662338/expansion-of-sales-and-service-tax-sst-scope
22. Ecovis, SST revised and expanded (industrial machinery moved 0 % → 5 %): https://global.ecovis.com/expanded-scope-of-sales-and-service-tax-in-malaysia/
23. Acclime, SST guide (RM500k threshold, Schedule C): https://malaysia.acclime.com/guides/sales-service-tax/ and ClearTax: https://www.cleartax.com/my/en/sst-in-malaysia

## Reference Products
| Product | Won → order flow | Where the order shows on the deal |
|---|---|---|
| **Odoo CRM + Sales** | "New Quotation" on the opportunity; "Confirm" turns the quotation into a sales order; marking Won is a **separate manual step** that adds a green Won banner [1][2] | "Quotations" smart button (count) and "Orders" smart button (amount of confirmed orders) on the opportunity [1] |
| **ERPNext (built-in CRM)** | Opportunity → Make Quotation → submit → Create > Sales Order; one database, nothing to sync | Linked documents on the form |
| **Frappe CRM + ERPNext** | Deal Won (configurable status) **auto-creates the ERPNext Customer**, carrying contacts and the org address; "Create Quotation" opens a prefilled ERPNext Quotation; the Sales Order is made by hand in ERPNext [3] | "View Customer" button in the deal header opens ERPNext in a new tab. **No sync status and no documented error handling** [3] |
| **HubSpot → NetSuite** (native app, workflow action) | Workflow "Create Sales Order" on Closed Won; the platform retries automatically ("Action wasn't able to execute, but will retry soon") [9] | NetSuite sync card in the right sidebar of deal/company records: record link, sync status, "Last updated" [8] |
| **Salesforce → NetSuite** (Oracle connector, Celigo, Breadwinner) | Opportunity Closed Won → Sales Order flow; Breadwinner uses a rep-clicked button on the opportunity [10][11][12] | NetSuite Order ID stored back on the opportunity; failure status written to the opportunity ("Update Opportunity Sync Failure Status") [10][13] |
| **Dynamics 365 Sales** (reference only) | "Create Order" from an active quote closes the quote **as won** automatically and offers to close the opportunity [15] | Quotes/Orders tabs on the opportunity |

## What's Good / What's Bad
- **Odoo.** Good: the order is a first-class link with its amount right on the opportunity [1]. Bad: Won and order confirmation aren't connected, so the pipeline and the orders drift unless someone does both [2].
- **Frappe CRM.** Good: customer auto-create at Won, address carried over, a one-click link to the ERP record [3]. Bad: Won fails outright on a bad master ("Cannot select a Group type Customer Group") with no fallback [4]; quotations stay invisible in the CRM deal view [4]; a CRM-made quotation broke Sales Order creation (`customer = None`) [5]; no status and no retry [3].
- **HubSpot NetSuite app.** Good: precise status wording, a record link and a last-synced time in one card [8]. Bad: the card has no retry button; the user has to go to a separate Sync Health page [8]. Silent background retries happen out of the rep's sight [9].
- **Salesforce connectors.** Good: the "only create when NetSuite Order ID is empty" guard and the stored external ID stop duplicates [13]; Celigo has an errors dashboard with a Retry button [11]. Bad: errors are raw ERP codes ("Invalid item reference key … for subsidiary …", `ORCL-BRT-OPPORTUNITY2SALESORDER_FAULT`) [10]; most failures are missing dependencies (customer not synced, item not mapped) [12][13].
- **ERPNext as the target.** Good: Additional Discount on **Net Total** spreads across item net amounts before tax, so tax lands on the discounted value [7]. Bad: a REST insert **doesn't expand a tax template into rows**, so the order lands with `"taxes": []` unless the rows (or item tax templates) are sent [6].

## Table Stakes Features
(Done by 3 or more of the products above.)
| Feature | Seen in | Our design |
|---|---|---|
| A link from the deal to the ERP order/customer | Odoo [1], Frappe CRM [3], HubSpot [8], Salesforce connectors [12][13] | Yes: order name plus a Desk link |
| Visible sync status on the deal | HubSpot [8], Oracle connector [10], Salesforce custom fields [13] | Yes: status chip |
| The ERP's error message shown on failure | HubSpot (hover) [8], Oracle [10], Celigo [11] | Yes: ERPNext message, HTML stripped |
| Manual retry | Celigo [11], Oracle "retry the failed sync" [10], HubSpot workflow retries [9] | Yes: resend form |
| No duplicate on retry (external ID / empty-ID guard) | Houseblend [13], Stacksync [14], Pipedrive guide [17] | Yes: `crm_reference` unique plus lookup-first |
| Customer auto-create or match | Frappe CRM [3], Salesforce/Celigo account → customer [11][12], Odoo customer pop-up [1] | Yes: exact name |
| Lines and prices carried from the quote, not retyped | Odoo [1], Frappe CRM [3], Breadwinner [12], Codestringers [16] | Yes: list price plus header discount |
| Tax computed or applied by the ERP | ERPNext template [6], NetSuite [16], Dynamics | Yes: SST template row sent explicitly |
| Last-synced time | HubSpot "Last updated" [8] | Stored (`erp_sent_at`) but **not shown**. See Our Target. |

## Professional UX Patterns
- **Placement:** a card or panel on the deal record (HubSpot: right sidebar of deal/company [8]; Odoo: smart buttons in the header [1]; Frappe: a header button [3]). Ours: an "ERP order" panel on won deals.
- **Status wording (HubSpot, verbatim) [8]:** "Up to date", "Sync not found", "Sync off", "Record not syncing" (error), "Unknown sync", "Record excluded". Ours: sent / failed / not sent / ERP link not configured. Plain, and it maps cleanly.
- **Link:** the ERP record's name/number shown as a link that opens the ERP in a new tab ("Click the record link to open the record in NetSuite" [8]; Frappe "View Customer" [3]).
- **Error detail:** behind the status (hover or click in HubSpot [8]). Ours shows it inline, which is better because the rep doesn't have to leave the page.
- **Colours:** HubSpot documents no colours; Odoo uses a green "Won" ribbon [2]. Green = sent, red = failed, grey = idle is the convention. No contrary evidence.
- **Retry:** a button in the error list (Celigo [11]). Ours puts the resend form in the panel itself plus a "failed sends" list on My day, which covers both the record and the queue.

## Design Reference
- HubSpot NetSuite sync card [8]: title row "NetSuite", then the linked NetSuite record, the status label, and "Last updated: <time>". Errors link to Sync Health.
- Odoo opportunity [1]: header smart buttons "Quotations (n)" and "Orders (amount)"; a green Won ribbon on the form.
- Frappe CRM deal [3]: a "View Customer" button in the deal header once the ERPNext customer exists.
- Suggested panel (ours): heading "ERP order"; chip; on sent: "SAL-ORD-… (link) · sent <date time>"; on failed: the reason, then the delivery-date field and a "Send again" button.

## Keyboard Shortcuts
N/A for a server-side integration.

## Common Complaints → Quality Requirements
| Complaint | Source | Requirement |
|---|---|---|
| A timed-out create succeeded and the retry made a second order | [14] | Look up by `crm_reference` before every create; a unique DB index; adopt on conflict |
| Duplicate customers on both sides | [17] | Look up before create; never create a second customer for the same account |
| Won blocked or crashed by the ERP (bad Customer Group) | [4] | Won commits first; ERP masters (customer group, territory) are leaf nodes and tested live |
| Quote total ≠ order total (rounding, discount order) | [16] | Order net total == quote total to the sen; rounded total off; discount on Net Total |
| Tax missing on API-created orders | [6] | Send the tax row explicitly; a contract test asserts the SST row and amount |
| Tax added twice / tax before discount | [7][16] | One tax row, On Net Total, after the header discount; CRM quotes stay tax-exclusive |
| Silent failures / background retries the rep never sees | [9][3] | Failure visible on the deal and on My day; no hidden auto-retry |
| Raw ERP error codes | [10] | Strip HTML, shorten, and keep ERPNext's sentence |

## SST notes
- **Rates:** sales tax is 5 % or 10 % on taxable goods; since **1 July 2025** the MOF has kept essentials unchanged and applied "5% or 10%" to discretionary and non-essential goods [18]. Goods **not listed** in the Rate of Tax Order 2025 or the Exemption Order 2025 **default to 10 %** [19]. Iron, steel and industrial machinery are named among the goods now charged 5 % or 10 % [21]; industrial machinery specifically moved 0 % → 5 % [22]. The rate goes **by HS tariff code**, so a fabricated steel product may sit at 5 % or 10 %; we couldn't confirm the code-level rate from a readable source.
- **Who charges:** a **registered manufacturer** (taxable sales > RM500,000 in 12 months), once, on sale [23].
- **Exports:** "Taxable goods which are exported are not subject to sales tax", provided "the exportation is declared in the Customs Form No. 2 (K2)" [20]. The exemption follows **the goods leaving Malaysia**, not the customer's country.
- **Schedule C:** a Malaysian customer that is itself a registered manufacturer can buy raw materials and components **tax-free** under Schedule C [23].

## Our Target
**Must-have (all in the design; research confirms each)**
- Won commits first, then the order is pushed in the same request. Never lose the Won (Frappe's failure mode [4] is what we avoid).
- Idempotency: quote number in a unique `crm_reference`, lookup-first, adoption on race [13][14].
- A submitted ERPNext order whose net total equals the quote total; header discount on **Net Total** so SST lands on the discounted value [7].
- The SST row sent explicitly in the payload (confirmed necessary by [6]).
- Customer auto-create by exact name (+ Address), as Frappe CRM does [3].
- An "ERP order" panel: chip, order link to Desk, ERPNext's reason on failure, a resend form; a "failed sends" list on My day.

**Gaps the research shows (add, they're cheap)**
1. **Show "sent <date time>"** in the panel. `erp_sent_at` is already stored; HubSpot shows "Last updated" [8].
2. **Check totals after create:** compare the returned `net_total` with the quote total and fail loudly on a mismatch (≥ 0.01). A runtime guard for complaint [16], beyond the contract test.
3. **Customer Group / Territory must be leaf (non-group) records**, or customer creation fails as in [4]. Assert this in the ERP tests.

**Nice-to-have**
- Store the ERPNext customer name on the account after the first create, so a later account rename can't create a second customer (name matching is the weakest matcher [17]).
- Match an existing customer by `tax_id` (SSM/UEN) before falling back to the name.

**Explicitly skip (document in README)**
- Schedule C exemptions for Malaysian customers that are registered manufacturers [23]: every Malaysian order gets SST.
- Per-item SST rates (Item Tax Templates) for products whose HS code is 5 %: one 10 % template.
- K2 / proof-of-export handling: "Singapore = export, no SST" is assumed.
- Automatic retries and background workers (HubSpot's hidden retries are a complaint, not a target).

**Challenges to the design (SST)**
- **The 10 % rate is a defensible default (goods not listed = 10 % [19]), but not proven for steel fabrications:** iron and steel are reported in the 5 %-or-10 % group [21] and the rate goes by tariff code. Keep the rate in the template (data, not code). The README should say "10 % assumed; confirm per HS code". Consider naming the template "Malaysia SST - OMW" with the rate in the row, so a 5 % correction doesn't need a rename.
- **The export rule is keyed to the wrong thing:** the design picks tax by the account's state/territory (Singapore → no tax), but the exemption applies to goods **exported with a K2 declaration** [20]. A Singapore customer collecting in Johor would be taxable. Acceptable for the demo if "Singapore customer ⇒ shipped to Singapore" is written down as an assumption.

**Quality bar**
- Zero duplicate orders under double-click, timeout-then-resend and concurrent sends (unique index + lookup-first, tested live).
- Order net total == quote total to the sen in every contract test; Malaysian orders carry exactly one SST row of 10 % of the net total; Singapore orders carry none.
- Every failure shows a human sentence on the deal and on My day within the same request; a failure never undoes the Won.
- Panel copy says what happened, what to do next and that resending is safe ("…sending again checks first, so it can't be duplicated").
