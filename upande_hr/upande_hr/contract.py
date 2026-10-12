# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Employment contracts on the Employee record.

The current contract is Contract Type + Contract Start Date + the standard
contract_end_date. Every contract the employee has held is kept in the
Contract History table, keyed on its start date:

- same start date  -> the same contract. An extension or a correction updates that row.
- new start date   -> a new contract. A row is appended and the old one stays as it was.

So correcting a mistyped start date leaves the mistyped row behind for an HR Manager
to delete. The table is at permlevel 2: HR Manager can add, correct or delete rows by
hand, HR User only reads it.

The upsert below still works when an HR User saves. Document.save() and insert() call
validate_higher_perm_levels() - which restores fields the user cannot write from the
database - before run_before_save_methods(), which is where this validate hook runs.
So the reset happens first and the row appended here is not wiped by it.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, escape_html, formatdate, get_url_to_form, getdate, nowdate

DEFAULT_LEAD_DAYS = 21
HR_MANAGER_ROLE = "HR Manager"


def employee_validate(doc, method=None):
	"""Employee.validate - keeps Contract History in step with the current contract."""
	if not doc.get("custom_contract_start_date"):
		return

	start = getdate(doc.custom_contract_start_date)
	end = getdate(doc.contract_end_date) if doc.contract_end_date else None

	if end and end < start:
		frappe.throw(_("Contract End Date cannot be before Contract Start Date"))

	row = next(
		(
			row
			for row in doc.get("custom_contract_history") or []
			if row.from_date and getdate(row.from_date) == start
		),
		None,
	)

	if row:
		row.contract_type = doc.custom_contract_type
		row.to_date = end
	else:
		doc.append(
			"custom_contract_history",
			{"contract_type": doc.custom_contract_type, "from_date": start, "to_date": end},
		)

	rows = sorted(doc.custom_contract_history, key=lambda row: getdate(row.from_date or "1900-01-01"))
	for idx, row in enumerate(rows, start=1):
		row.idx = idx
	doc.custom_contract_history = rows


def notify_expiring_contracts():
	"""Daily. Tells every HR Manager about contracts ending exactly lead-days from today.

	Idempotent per employee per end date: a Notification Log with the same subject for
	the same user and employee means that user has already been told, so a second run
	the same day sends nothing. The end date is in the subject, so an extended contract
	gets a fresh notification when its new end date comes round.

	The log is type "Alert", which Frappe never emails on its own
	(notification_skip_email_types), so the one sendmail below is the only email.
	"""
	lead_days = (
		cint(frappe.db.get_single_value("HR Settings", "custom_contract_expiry_lead_days"))
		or DEFAULT_LEAD_DAYS
	)
	end_date = add_days(nowdate(), lead_days)

	employees = frappe.get_all(
		"Employee",
		filters={"status": "Active", "contract_end_date": end_date},
		fields=[
			"name",
			"employee_name",
			"company",
			"department",
			"custom_contract_type",
			"contract_end_date",
		],
	)
	if not employees:
		return

	recipients = get_hr_managers()
	if not recipients:
		frappe.log_error(
			title="upande_hr: contract expiry notification skipped",
			message=f"No enabled users with role {HR_MANAGER_ROLE!r} to notify.",
		)
		return

	for employee in employees:
		notify_hr_managers(employee, recipients)


def notify_hr_managers(employee, recipients):
	subject = _("Contract ending {0}: {1} ({2})").format(
		formatdate(employee.contract_end_date), employee.employee_name, employee.name
	)

	pending = [
		user
		for user in recipients
		if not frappe.db.exists(
			"Notification Log",
			{
				"for_user": user.name,
				"document_type": "Employee",
				"document_name": employee.name,
				"subject": subject,
			},
		)
	]
	if not pending:
		return

	message = get_expiry_message(employee)

	for user in pending:
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"type": "Alert",
				"for_user": user.name,
				"subject": subject,
				"email_content": message,
				"document_type": "Employee",
				"document_name": employee.name,
			}
		).insert(ignore_permissions=True)

	frappe.sendmail(
		recipients=[user.email for user in pending if user.email],
		subject=subject,
		message=message,
		reference_doctype="Employee",
		reference_name=employee.name,
	)


def get_expiry_message(employee):
	rows = [
		(_("Employee"), f"{employee.employee_name} ({employee.name})"),
		(_("Company"), employee.company),
		(_("Department"), employee.department),
		(_("Contract Type"), employee.custom_contract_type),
		(_("Contract End Date"), formatdate(employee.contract_end_date)),
	]
	table = "".join(
		f"<tr><td style='padding-right: 16px'><b>{label}</b></td><td>{escape_html(value or '-')}</td></tr>"
		for label, value in rows
	)
	link = get_url_to_form("Employee", employee.name)

	return (
		f"<p>{_('The following employment contract is due to end.')}</p>"
		f"<table>{table}</table>"
		f"<p><a href='{link}'>{_('Open Employee record')}</a></p>"
	)


def get_hr_managers():
	"""Enabled users holding HR Manager, minus the system accounts."""
	users = frappe.get_all(
		"Has Role",
		filters={
			"role": HR_MANAGER_ROLE,
			"parenttype": "User",
			"parent": ["not in", ["Administrator", "Guest"]],
		},
		pluck="parent",
		distinct=True,
	)
	if not users:
		return []

	return frappe.get_all(
		"User",
		filters={"name": ["in", users], "enabled": 1},
		fields=["name", "email"],
		order_by="name",
	)
