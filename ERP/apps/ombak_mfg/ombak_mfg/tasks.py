import json
from urllib.parse import urlencode

import frappe
from frappe.desk.doctype.notification_log.notification_log import make_notification_logs
from frappe.utils import escape_html, format_datetime, today

SUBJECT = "Overdue work orders"
FINISHED = ("Completed", "Stopped", "Closed", "Cancelled")


def notify_overdue_work_orders():
	"""Daily: one summary bell notification per Manufacturing Manager listing late work orders."""
	overdue = frappe.get_all(
		"Work Order",
		filters={"docstatus": 1, "status": ["not in", FINISHED], "planned_end_date": ["<", today()]},
		fields=["name", "production_item", "planned_end_date"],
		order_by="planned_end_date",
	)
	if not overdue:
		return

	has_role = frappe.qb.DocType("Has Role")
	user = frappe.qb.DocType("User")
	managers = (
		frappe.qb.from_(has_role)
		.join(user)
		.on(has_role.parent == user.name)
		.select(user.name, user.email)
		.distinct()
		.where(
			(has_role.parenttype == "User")
			& (has_role.role == "Manufacturing Manager")
			& (user.enabled == 1)
		)
	).run(as_dict=True)
	already_notified = set(
		frappe.get_all(
			"Notification Log",
			filters={"subject": ["like", f"{SUBJECT}%"], "creation": [">=", today()]},
			pluck="for_user",
		)
	)
	# make_notification_logs looks users up by email, which differs from the name for Administrator
	emails = [m.email for m in managers if m.name not in already_notified]
	if not emails:
		return

	lines = "".join(
		f"<li>{escape_html(wo.name)}: {escape_html(wo.production_item)}, "
		f"planned end {format_datetime(wo.planned_end_date)}</li>"
		for wo in overdue[:20]
	)
	more = f"<p>and {len(overdue) - 20} more</p>" if len(overdue) > 20 else ""
	make_notification_logs(
		{
			"type": "Alert",
			"subject": f"{SUBJECT}: {len(overdue)}",
			"email_content": f"<ul>{lines}</ul>{more}",
			"document_type": "Work Order",
			"document_name": overdue[0].name,
			"link": overdue_list_url(),
		},
		emails,
	)


def overdue_list_url():
	"""Work order list filtered to the same orders the alert counts (list view parses JSON filters)."""
	filters = {
		"docstatus": 1,
		"status": json.dumps(["not in", list(FINISHED)]),
		"planned_end_date": json.dumps(["<", today()]),
	}
	return f"/desk/work-order?{urlencode(filters)}"
