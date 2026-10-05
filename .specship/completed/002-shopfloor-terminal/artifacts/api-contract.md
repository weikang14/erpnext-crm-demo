# API contract: portal -> ERPNext (REST v2)

Verified against ERPNext v16.37.0 on 2026-10-04 (contract.localhost). `terminal/erpnext.py`
is the only code that calls these; it must match this file exactly.

**Base:** `ERPNEXT_URL` (in Docker: `http://backend:8000`). **Every request** sends
`Host: <ERPNEXT_SITE>` (site `localhost`), `Accept: application/json`, and
`Authorization: token <ERPNEXT_API_KEY>:<ERPNEXT_API_SECRET>`.
**Times** are naive strings `YYYY-MM-DD HH:MM:SS` in Asia/Kuala_Lumpur.
**v2 only.** v1 (`/api/resource`, `/api/method`) returns a different error shape.

| Purpose | Method + path | Request | Success response (exact shape) | Status |
|---|---|---|---|---|
| Workstations | GET `/api/v2/document/Workstation` | `fields=["name"]`, `filters=[["disabled","=",0]]`, `order_by=name asc`, `limit=100` | `{"data": [{"name": str}], "has_next_page": bool}` | 200 |
| Defect reasons | GET `/api/v2/document/Defect Reason` | `fields=["name","category"]`, `filters=[["disabled","=",0]]`, `order_by=name asc`, `limit=100` | `{"data": [{"name": str, "category": str}], ...}` | 200 |
| Queue | GET `/api/v2/document/Job Card` | `fields=["name","status","is_paused","work_order","operation","production_item","item_name","for_quantity","total_completed_qty","expected_start_date","expected_end_date","sequence_id"]`, `filters=[["workstation","=",ws],["docstatus","=",0]]`, `order_by=expected_start_date asc`, `limit=50` | `{"data": [ {...those fields...} ], "has_next_page": bool}` | 200 |
| Siblings (readiness) | GET `/api/v2/document/Job Card` | `fields=["name","work_order","operation","sequence_id","docstatus"]`, `filters=[["work_order","in",[wo,...]],["docstatus","<",2]]`, `limit=500` | `{"data": [...]}` | 200 |
| One job card (timer) | GET `/api/v2/document/Job Card/{name}` | - | `{"data": {..., "time_logs": [{"from_time": str, "to_time": str or null, "employee": str, "completed_qty": float}], "total_time_in_mins": float}}` | 200 |
| Start | POST `/api/v2/document/Job Card/{name}/method/start_timer` | `{"start_time": t, "employees": "<Employee ID>"}` | `{"docs": [ {job card} ]}` | 200 |
| Pause | POST `.../method/pause_job` | `{"end_time": t}` | `{"docs": [...]}` | 200 |
| Resume | POST `.../method/resume_job` | `{"start_time": t}` | `{"docs": [...]}` | 200 |
| Complete + submit | POST `.../method/complete_job_card` | `{"qty": remaining, "end_time": t, "auto_submit": 1}` | `{"docs": [ {..., "docstatus": 1, "status": "Completed"} ]}` | 200 |
| Defect | POST `/api/v2/document/Defect Log` | `{"job_card": name, "defect_reason": r, "qty": q, "docstatus": 1}` | `{"data": {"name": "DL-...", "docstatus": 1, ...}}` | 200 |
| Employee lookup (seed) | GET `/api/v2/document/Employee` | `fields=["name","employee_name"]`, `filters=[["status","=","Active"]]`, `limit=100` | `{"data": [...]}` | 200 |

**Errors (all v2 endpoints):**
- Business rule rejected (sequence, cap, submitted card): **417**
  `{"errors": [{"type": str, "message": str (may contain HTML), "title": str, "indicator": str, "exception": str}]}`.
  Show `strip_tags(message)` only; never `exception`.
- Bad or missing token: **401** -> treat as ERP unavailable.
- Missing permission: **403** -> show "ERPNext doesn't allow the terminal to do this. Tell the
  supervisor." (ERPNext is reachable; the integration user's role is the problem).
- Not found: **404** -> show its message.
- 5xx or connection failure: treat as ERP unavailable.

**Known messages** (useful in tests): sequence -> "complete the operation X before the
operation Y"; submitted card -> "Submitted Job Card cannot be processed."; defect cap ->
"Only N more defective units can be logged against Job Card ...".
