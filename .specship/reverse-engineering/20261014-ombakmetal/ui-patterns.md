# UI Patterns (CRM deal page, where the ERP order status will show)

- **Server-rendered Django templates with no SPA.** Every page works without JS (`CRM/sales/static/sales/app.js:1`). Controls are 44 px, and there is no inline script or style (CSP; `test_security.py:117-124`).
- **Deal page** (`CRM/sales/templates/sales/deals/detail.html`):
  - the page head has crumbs, the `_stage.html` chip, the amount and the owner (`:4-9`); the actions (Move, Mark won) show only when `deal.is_open` (`:10-23`);
  - status banners sit under the head as `<p class="msg msg-success|msg-error">` (`:26-27`). This is the natural slot for "ERPNext sales order SAL-ORD-… created" or "not sent";
  - the right column uses `.panel` + `.panelhead` + `<dl class="details">` (`:75-89`). An "ERP order" row or panel fits here;
  - POST action panels are `{% csrf_token %}` + `.btn`, e.g. the reassign panel (`:90-100`). A "Retry" button would follow that pattern.
- **Chips** (`app.css:159-163`): `chip`, `chip-blue`, `chip-green`, `chip-amber`, `chip-red`. Quote status mapping is in `quotes/_status.html` (pending amber, accepted green, declined red). A sync status can mirror it: sent green, pending amber, failed red.
- **Flash messages** (`base.html:30-36`): `msg msg-{{ tags }}` with `role="alert"` for errors and `role="status"` otherwise. `msg-warning` exists (`app.css:146`), so `messages.warning` works for "Won, but ERPNext didn't take the order".
- **Invalid form → 400 re-render:** `detail_context(...)` is re-rendered with status 400 (`opportunities.py:103-119,164,199`), and `app.js:7-11` focuses the first `[aria-invalid='true']`. Won has no form today. Adding one (e.g. a delivery date) would switch Won to this pattern.
- **Double-submit guard:** `app.js:14-21` handles it in the browser; the server-side guard is the row lock.
- **ERPNext Desk link** (if wanted): `http://localhost:8080/app/sales-order/<name>`, as a plain `<a>`, which CSP allows.
