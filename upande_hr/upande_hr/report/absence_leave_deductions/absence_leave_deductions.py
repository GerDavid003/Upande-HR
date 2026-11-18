# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe import _


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
			"width": 140,
		},
		{"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 170},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 90},
		{
			"label": _("Leave Type"),
			"fieldname": "leave_type",
			"fieldtype": "Link",
			"options": "Leave Type",
			"width": 130,
		},
		{"label": _("Balance Before"), "fieldname": "balance_before", "fieldtype": "Float", "width": 110},
		{"label": _("Balance After"), "fieldname": "balance_after", "fieldtype": "Float", "width": 110},
		{
			"label": _("Leave Application"),
			"fieldname": "leave_application",
			"fieldtype": "Link",
			"options": "Leave Application",
			"width": 150,
		},
		{
			"label": _("Attendance"),
			"fieldname": "attendance",
			"fieldtype": "Link",
			"options": "Attendance",
			"width": 150,
		},
		{"label": _("Reason"), "fieldname": "reason", "fieldtype": "Small Text", "width": 300},
		{"label": _("Notification"), "fieldname": "notification", "fieldtype": "Small Text", "width": 220},
		{
			"label": _("Log"),
			"fieldname": "name",
			"fieldtype": "Link",
			"options": "Absence Leave Deduction",
			"width": 180,
		},
	]


def get_data(filters):
	conditions = {}
	if filters.from_date and filters.to_date:
		conditions["absence_date"] = ["between", [filters.from_date, filters.to_date]]
	elif filters.from_date:
		conditions["absence_date"] = [">=", filters.from_date]
	elif filters.to_date:
		conditions["absence_date"] = ["<=", filters.to_date]
	for field in ("employee", "status", "company"):
		if filters.get(field):
			conditions[field] = filters.get(field)

	return frappe.get_list(
		"Absence Leave Deduction",
		filters=conditions,
		fields=[c["fieldname"] for c in get_columns()],
		order_by="absence_date desc, employee",
	)
