# Market research: internal B2B sales CRM for a sheet-metal factory (003)

Searched 2026-10-05. Queries were about the product category only, not this repo.

## Research Sources
1. Method, "Best CRM for manufacturing (2026)": https://www.method.me/blog/crm-for-manufacturing-industry/
2. monday.com, "Best CRM quoting software 2026": https://monday.com/blog/crm-and-sales/crm-with-quoting/
3. Scopic, "Deal desk software: quote approval workflow": https://scopicstudios.com/blog/top-8-deal-desk-software-tools-for-b2b-in-2026/
4. Pipedrive KB, "Pipeline view": https://support.pipedrive.com/en/article/pipeline-view
5. Pipedrive KB, "How deals are ordered in the pipeline view": https://support.pipedrive.com/en/article/how-are-deals-ordered-in-the-pipeline-view
6. Pipedrive KB, "The rotting feature": https://support.pipedrive.com/en/article/the-rotting-feature
7. HubSpot, "Automated territory assignment": https://blog.hubspot.com/sales/automated-territory-assignment
8. CodeStringers, "Assignment rules in Zoho CRM": https://www.codestringers.com/articles/how-to-set-up-assignment-rules-in-zoho-crm
9. Odoo 19 docs, "Pipeline analysis (win/loss)": https://www.odoo.com/documentation/19.0/applications/sales/crm/performance/win_loss.html
10. Odoo app store, "Sales quotation discount approval": https://apps.odoo.com/apps/modules/17.0/sales_approval_enhancement
11. Rework, "Forecast categories: commit and best case": https://resources.rework.com/libraries/pipeline-management/forecast-categories
12. Rework, "Weighted pipeline": https://resources.rework.com/libraries/pipeline-management/weighted-pipeline
13. Clari, "Why sales reps hate CRM": https://clari.com/blog/why-sales-reps-hate-using-crm
14. Salesflare, "CRM challenges 2026": https://blog.salesflare.com/crm-challenges

## Reference Products
Pipedrive (visual pipeline), Odoo CRM + Sales (lead to quotation to order in one system),
Zoho CRM (assignment rules, Blueprint approvals), HubSpot Sales Hub (territory + round robin).

## What's Good / What's Bad
- **Pipedrive, good:** the board is the home screen. Cards show title, organisation,
  value, owner and an activity indicator. Cards sort by next activity: overdue (red), due
  today (green), no activity (yellow warning), future (grey) [4, 5]. "Rotting" highlights
  deals idle past N days [6]. **Bad:** quotes and approvals need add-ons; nothing stops a
  rep from dragging a deal to "Proposal" with no proposal.
- **Odoo, good:** lost reasons are a configurable list and a required pick when marking
  lost; the pipeline analysis groups by lost reason [9]. A quotation is created from the
  opportunity and carries its lines into the sales order. **Bad:** discount approval is
  not built in; it is a paid add-on module [10].
- **Zoho, good:** assignment rules route by territory, and spread a shared queue
  round-robin [8]; Blueprint gates stage moves on approvals [1]. **Bad:** setup is heavy
  and admin-only.
- **HubSpot, good:** routing by geography and rep capacity [7]. **Bad:** round robin and
  territories need higher tiers.
- **All of them, bad:** reps spend hours a week on data entry and skip fields they see as
  clutter, so the data rots [13, 14].

## Table Stakes Features
1. Leads with owner and status; disqualify with a reason [7, 8].
2. Automatic lead assignment by territory, spread evenly inside a territory [7, 8].
3. Convert a lead to account + contact + opportunity [9].
4. Accounts and contacts.
5. Pipeline board with stage columns, per-column count and value, drag to move [4].
6. Next-activity indicator and sort on each deal card [5].
7. Stale ("rotting") deal flag [6].
8. Activities: log calls/meetings/notes, schedule follow-ups with due dates [5].
9. Required lost reason from a configurable list [9].
10. Quotes from a price list, printable for the customer [2, 9].
11. Discount approval above a threshold before the quote can go out [3, 10].
12. Reports: pipeline by stage, win rate per rep, weighted forecast, loss reasons [11, 12, 9].
13. Search, filters and CSV export of lists.
14. Roles: reps see their own deals, managers see the team.

## Professional UX Patterns
- Activity indicator colours and sort order: overdue, today, none, future [5].
- Board column header: stage name, deal count, sum of values [4].
- Win rate = won / (won + lost), by count; open deals excluded from both sides [11].
- Weighted pipeline = sum(amount x stage probability) [12]; forecast categories layer
  "won", "commit"/"best case" on top [11].
- Moderate discount: sales manager approves; above that, finance (we keep one level) [10].

## Design Reference
Desk app for laptops first, still usable on a tablet. 16 px body, 14 px table text,
40 px row height in tables, 44 px minimum tap target, 8 px spacing grid. Neutral slate
background (#F8FAFC), white cards, one blue accent (#1D4ED8), status colours shared with
the shop-floor terminal (green #157F3D, amber #B45309, red #B91C1C, grey #6B7280).

## Keyboard Shortcuts
Pipedrive has many shortcuts. We keep native ones: every action is a link, button or
form control, reachable by Tab, and the board's "Move to" control works without a mouse.
Explicitly skipped: custom shortcut keys.

## Common Complaints (become requirements)
- Too much data entry: forms ask only for what a report or the ERP needs; region,
  probability, owner, quote number and totals are derived, never typed [13, 14].
- Cluttered screens: one primary action per page.
- Stale data: stale-deal flag and "no next activity" warning push the rep to update.
- Deals in "Proposal" with no proposal: stage gate, a deal enters Quotation only when a
  quote has been sent.

## Our Target
- **Must have:** table stakes 1 to 14.
- **Nice to have (in):** public enquiry form that creates an auto-assigned lead; duplicate
  warning on leads.
- **Explicitly skip:** email sync, calendar sync, multi-currency, multi-level approval,
  custom fields, custom shortcut keys, mobile app, marketing campaigns.
- **Quality bar:** every list has empty, filtered-empty and error states; every money
  figure is a Decimal rounded half-up to 2 dp; no page leaks another rep's records.
