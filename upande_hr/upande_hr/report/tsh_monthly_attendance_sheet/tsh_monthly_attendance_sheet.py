# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""HRMS Monthly Attendance Sheet with Attendance.custom_attendance_label shown in place of P.

A wrapper rather than a patch of the HRMS report: HRMS owns that report's files, and
replacing its functions at import time breaks silently on the next HRMS upgrade. This
calls the stock execute() and only rewrites cells afterwards, so it depends on nothing
but the detailed-view row shape (one row per employee and shift, keyed "dd-mm-YYYY").

The summarized view is passed through untouched - a labelled day is still Present, and
is counted as one there.
"""

import frappe
from frappe.utils import getdate
from hrms.hr.report.monthly_attendance_sheet import monthly_attendance_sheet as hrms_sheet

LABEL_FIELD = "custom_attendance_label"
PRESENT = hrms_sheet.status_map["Present"]


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns, data, message, chart = hrms_sheet.execute(filters)

	if filters.summarized_view or not data:
		return columns, data, message, chart

	labels = get_labels(filters)
	used = set()
	for row in data:
		for date_key, label in labels.get(row.get("employee"), {}).items():
			if row.get(date_key) == PRESENT:
				row[date_key] = label
				used.add(label)

	if used:
		message = (message or "") + get_label_legend(used)
	return columns, data, message, chart


def get_labels(filters) -> dict[str, dict[str, str]]:
	start, end = hrms_sheet.get_date_range_from_filters(filters)
	conditions = {
		"docstatus": 1,
		"attendance_date": ["between", [start, end]],
		LABEL_FIELD: ["is", "set"],
	}
	if filters.employee:
		conditions["employee"] = filters.employee

	labels: dict[str, dict[str, str]] = {}
	for att in frappe.get_all(
		"Attendance", filters=conditions, fields=["employee", "attendance_date", LABEL_FIELD]
	):
		key = getdate(att.attendance_date).strftime("%d-%m-%Y")
		labels.setdefault(att.employee, {})[key] = att.get(LABEL_FIELD)
	return labels


def get_label_legend(used: set) -> str:
	mapping = {
		row.attendance_label: row.reason_keyword
		for row in frappe.get_all(
			"Attendance Label Map",
			filters={"parenttype": "HR Settings", "parent": "HR Settings"},
			fields=["reason_keyword", "attendance_label"],
		)
	}
	return "".join(
		f"""
			<span style='border-left: 2px solid green; padding-right: 12px; padding-left: 5px; margin-right: 3px;'>
				{frappe.utils.escape_html(mapping.get(label) or label)} - {frappe.utils.escape_html(label)}
			</span>
		"""
		for label in sorted(used)
	)
