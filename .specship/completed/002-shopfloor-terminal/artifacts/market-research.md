# Market research: shop-floor operator terminal

## Research Sources
1. Odoo 19 Shop Floor time tracking: https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/manufacturing/shop_floor/shop_floor_tracking.html
2. Odoo Shop Floor tablet interface overview: https://www.infintor.com/odoo-shop-floor-tablet-interface-improve-operator-efficiency-and-manufacturing-productivity/
3. Katana Shop Floor App quick start: https://support.katanamrp.com/en/articles/12586926-shop-floor-operator-quick-start-guide
4. Katana partial completion: https://katanamrp.com/blog/partial-complete-sfa/
5. MRPeasy production reporting for workers / Internet-Kiosk: https://www.mrpeasy.com/resources/user-manual/reporting/
6. MRPeasy review (touch complaints): https://ciroapp.com/software/mrpeasy
7. HMI design best practices: https://www.aufaitux.com/blog/hmi-design-best-practices/
8. Industrial touch display guidance: https://www.aptusdisplay.com/info-detail/how-to-design-an-industrial-touch-display-interface
9. Shop-floor data collection compared (operator complaints): https://totalcontrolpro.com/blog/shop-floor-data-collection-software-barcodes-tablets-clocking-stations/
10. Business Central shop-floor time tracking challenges: https://dmsiworks.com/blog/shop-floor-time-tracking-business-central

## Reference Products
Odoo Shop Floor, Katana Shop Floor App, MRPeasy Internet-Kiosk / My Production Plan,
ERPNext's own Job Card form (the thing operators find too complex).

## What's Good / What's Bad
- **Odoo**: one page per work center; Start shows a running timer; tapping the card again
  pauses; "Mark as Done" removes the card (src 1). Bad: pause by re-tapping a card is
  easy to trigger by accident.
- **Katana**: tasks filtered by resource (station) and by material availability; explicit
  Start / Pause / Resume / Quit / Finish; finished tasks disappear; status syncs to the
  main app in real time (src 3); partial completion asks for qty (src 4).
- **MRPeasy**: separate simplified kiosk view for phones/tablets listing the worker's
  operations; reports good qty and scrap/rejected qty (src 5). Bad: reviewers say the
  layout is not touch-friendly and start/stop buttons "need to be much larger" (src 6).

## Table Stakes Features
1. Task list filtered to one workstation (Odoo, Katana, MRPeasy).
2. Start / Pause / Resume / Finish with a visible running timer (Odoo, Katana, MRPeasy).
3. Report completed quantity on finish (Odoo, Katana, MRPeasy).
4. Report rejected / scrap quantity (MRPeasy; Odoo via quality checks).
5. Tasks not ready yet are visibly not startable (Katana availability filter).
6. Finished tasks leave the list (Odoo, Katana).
7. Time is booked to a named operator (Odoo employee, Katana operator, MRPeasy worker).
8. Changes reach the ERP immediately (Katana real-time sync).

## Professional UX Patterns
- Touch targets >= 15-20 mm (about 56-76 CSS px) with 2-3 mm (8-12 px) between them (src 7, 8).
- Large sans-serif type, readable from a distance; colour-coded status (src 7).
- Minimal typing: numbers prefilled with the expected quantity; numeric keypad (src 9).
- No hover-only controls; clear pressed/disabled feedback (src 8).
- Station stays selected between actions; no repeated log-ins (src 9).

## Design Reference
- Density: one task card per row, 2-4 visible at once on a 10" tablet; primary button
  64 px tall, full card width on narrow screens.
- Type: body 18 px, card title 22 px, timer 40 px tabular numerals.
- Colour: running = green, paused = amber, waiting = grey, error = red, on a light
  neutral background (high contrast for bright factory lighting).
- Layout: header (station picker, operator, sign out) + queue; running job pinned at top.

## Keyboard Shortcuts
Not applicable: touch kiosk. All actions reachable by Tab/Enter for accessibility.

## Common Complaints
- Buttons too small for touch (src 6).
- Walking to a terminal, typing job numbers, logging in and out repeatedly (src 9).
- Manual entry errors: wrong job, missed clock-outs (src 9, 10).
- Data hours old by the time managers see it (src 9).

## Our Target
- **Must-have:** sign in once per shift as an operator mapped to an ERPNext Employee;
  station picker remembered; queue of that station's open job cards in planned order with
  Ready / Waiting / Running / Paused status; Start, Pause, Resume, Complete (full quantity)
  with defect lines (reason + qty) written as Defect Logs; live timer; clear errors when
  ERPNext rejects an action or is unreachable; empty state; tablet + phone layouts.
- **Nice-to-have (not now):** barcode scanning, partial completion, multiple concurrent
  jobs per operator, PIN quick-switch, offline queueing.
- **Explicitly skip:** quality-check steps, material transfer, "quit task".
- **Quality bar:** 64 px primary buttons, no typing needed for the normal path, every
  action visible in ERPNext's Job Card within one refresh.
