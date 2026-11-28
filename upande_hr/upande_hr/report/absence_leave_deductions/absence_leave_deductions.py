# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Absence Leave Deductions: HR's backlog of days the weekly deduction left for them.

"Needs Attention" (the default) lists Flagged and Error days, and Deducted days whose
employee was never emailed. Each row shows what the job recorded at the time and the
day's state now - the Attendance status, the employee's Employment Type, and whether
the day would be excused if the week were re-run - so HR can tell which flags have been
dealt with and which still need doing.
"""

import frappe
from frappe import _

NEEDS_ATTENTION = "Needs Attention"
ALL = "All"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Absence Date"), "fieldname": "absence_date", "fieldtype": "Date", "width": 110},
		{
			"label": _("Employee"),
			"fieldname": "employee",
			"fieldtype": "Link",
			"options": "Employee",
			"width": 130,
		},
		{"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 170},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 90},
		{"label": _("Reason"), "fieldname": "reason", "fieldtype": "Small Text", "width": 320},
		{
			"label": _("Employment Type Now"),
			"fieldname": "employment_type_now",
			"fieldtype": "Link",
			"options": "Employment Type",
			"width": 150,
		},
		{"label": _("Attendance Now"), "fieldname": "attendance_now", "fieldtype": "Data", "width": 120},
		{"label": _("Excused Now By"), "fieldname": "excused_now", "fieldtype": "Data", "width": 150},
		{
			"label": _("Leave Type"),
			"fieldname": "leave_type",
			"fieldtype": "Link",
			"options": "Leave Type",
			"width": 120,
		},
		{"label": _("Balance Before"), "fieldname": "balance_before", "fieldtype": "Float", "width": 100},
		{"label": _("Balance After"), "fieldname": "balance_after", "fieldtype": "Float", "width": 100},
		{
			"label": _("Leave Application"),
			"fieldname": "leave_application",
			"fieldtype": "Link",
			"options": "Leave Application",
			"width": 150,
		},
		{"label": _("Notified"), "fieldname": "notified", "fieldtype": "Check", "width": 80},
		{"label": _("Notification"), "fieldname": "notification", "fieldtype": "Small Text", "width": 220},
		{
			"label": _("Attendance"),
			"fieldname": "attendance",
			"fieldtype": "Link",
			"options": "Attendance",
			"width": 150,
		},
		{
			"label": _("Log"),
			"fieldname": "name",
			"fieldtype": "Link",
			"options": "Absence Leave Deduction",
			"width": 180,
		},
	]


STORED = (
	"name",
	"absence_date",
	"employee",
	"employee_name",
	"status",
	"reason",
	"leave_type",
	"balance_before",
	"balance_after",
	"leave_application",
	"notified",
	"notification",
	"attendance",
)


def get_data(filters):
	conditions = {}
	if filters.from_date and filters.to_date:
		conditions["absence_date"] = ["between", [filters.from_date, filters.to_date]]
	elif filters.from_date:
		conditions["absence_date"] = [">=", filters.from_date]
	elif filters.to_date:
		conditions["absence_date"] = ["<=", filters.to_date]
	for field in ("employee", "status", "company", "employment_type"):
		if filters.get(field):
			conditions[field] = filters.get(field)

	rows = frappe.get_list(
		"Absence Leave Deduction",
		filters=conditions,
		fields=list(STORED),
		order_by="absence_date desc, employee",
	)
	# An explicit Status filter overrides the view.
	if (filters.view or NEEDS_ATTENTION) == NEEDS_ATTENTION and not filters.status:
		rows = [r for r in rows if needs_attention(r)]

	add_current_state(rows)
	return rows


def needs_attention(row) -> bool:
	return row.status in ("Flagged", "Error") or (row.status == "Deducted" and not row.notified)


def add_current_state(rows):
	if not rows:
		return

	from upande_hr.attendance.absence_settings import get_settings
	from upande_hr.attendance.absent_deduction import get_excuse

	employment_types = dict(
		frappe.get_all(
			"Employee",
			filters={"name": ["in", list({r.employee for r in rows})]},
			fields=["name", "employment_type"],
			as_list=True,
		)
	)
	attendance = {
		a.name: a
		for a in frappe.get_all(
			"Attendance",
			filters={"name": ["in", [r.attendance for r in rows if r.attendance]]},
			fields=["name", "status", "docstatus", "shift"],
		)
	}
	settings = get_settings()

	for row in rows:
		row.employment_type_now = employment_types.get(row.employee)
		record = attendance.get(row.attendance)
		if not record:
			row.attendance_now = _("Deleted")
		elif record.docstatus == 2:
			row.attendance_now = _("Cancelled")
		else:
			row.attendance_now = record.status

		if row.status in ("Flagged", "Error"):
			try:
				row.excused_now = get_excuse(
					row.employee, row.absence_date, settings, record.shift if record else None
				)
			except Exception:
				row.excused_now = _("Could not check")
