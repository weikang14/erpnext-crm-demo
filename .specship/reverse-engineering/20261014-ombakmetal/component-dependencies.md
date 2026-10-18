# Component Dependencies

## Today
```
Browser ──POST /deals/<id>/won/──> CRM deal_won (views/opportunities.py:146)
   └─ access.get(access.opportunities) ─> Opportunity.mark_won (models.py:284, @transaction.atomic)
        ├─ _locked(): SELECT … FOR UPDATE on the deal row (models.py:266)
        ├─ rules.check_won (rules.py:53)
        ├─ Quote.status = accepted
        └─ _set_stage(WON, amount=quote.total, closed_at=now) → StageChange row (models.py:269)
reports.py / views/home.py ── read stage="won", closed_at, amount

ERP/portal ──REST v2 (requests, token auth, Host header)──> erp backend:8000 (frappe_network)
CRM ──(nothing)──> ERP          # grep for urllib|requests|httpx|http.client|socket in CRM/**/*.py: no hits (crm chunk)
```

| From | To | Kind | Evidence |
|---|---|---|---|
| CRM views | `access`, `models`, `rules` | in-process | `CRM/sales/views/opportunities.py:146-155` |
| CRM `access` | `models.is_manager` | import | `CRM/sales/access.py:15` |
| CRM reports | `Opportunity` won fields | ORM read | `CRM/sales/reports.py:37-61` |
| Portal | ERPNext | HTTP REST v2, `http://backend:8000`, `Host: localhost` | `ERP/docker-compose.yml:134-141`, `ERP/portal/terminal/erpnext.py:36-47` |
| ERP frontend nginx | backend | proxy, **forces** `X-Frappe-Site-Name: localhost` | `ERP/docker-compose.yml:88`; nginx conf (erp chunk) |

## Added by 004 (shape is open; see open-questions.md)
`CRM` → ERPNext REST v2 (`Sales Order` create, `Customer` read and maybe create, and a lookup by reference). ERPNext makes **no** callback: `ombak_mfg/hooks.py` has no `doc_events`, and the CRM `ALLOWED_HOSTS` (`CRM/crm/settings.py:12`) would reject one anyway. The CRM reaches ERPNext in one of two ways, either `host.docker.internal:8080` (verified 200 on `/api/method/ping`) or the shared `erp_frappe_network` with `backend:8000`. See open question 8.
