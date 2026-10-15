# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Short attendance labels (ALBA, MUT...) for approved Attendance Requests.

The label goes into Attendance.custom_attendance_label and Attendance.status is left as
HRMS set it. Overwriting status was considered and rejected: status is a fixed Select
that HRMS compares by string all over - the Monthly Attendance Sheet abbreviates via
status_map.get(status, "") and counts only Present / Work From Home as present days - so
a status of "ALBA" renders blank and drops out of every present-day total. The label is
surfaced instead by the TSH Monthly Attendance Sheet report.

Records are found by employee and date rather than by Attendance.attendance_request.
HRMS only stamps attendance_request when it creates a record or changes its status, so an
employee already marked Present for the day keeps a record that never links back here.
"""

import frappe

LABELLED_STATUSES = ("Present", "Work From Home", "Half Day")
LABEL_FIELD = "custom_attendance_label"


def get_label_map() -> list[dict]:
	return frappe.get_all(
		"Attendance Label Map",
		filters={"parenttype": "HR Settings", "parent": "HR Settings"},
		fields=["reason_keyword", "attendance_label"],
		order_by="idx",
	)


def match_label(reason: str | None) -> str | None:
	"""First mapping row whose keyword appears in the reason, case-insensitively."""
	if not reason:
		return None
	reason = reason.casefold()
	for row in get_label_map():
		if row.reason_keyword and row.reason_keyword.strip().casefold() in reason:
			return row.attendance_label
	return None


def get_request_attendance(doc) -> list[str]:
	return frappe.get_all(
		"Attendance",
		filters={
			"employee": doc.employee,
			"attendance_date": ["between", [doc.from_date, doc.to_date]],
			"docstatus": 1,
		},
		or_filters={"attendance_request": doc.name, "status": ["in", LABELLED_STATUSES]},
		pluck="name",
	)


def apply_attendance_label(doc, method=None):
	"""Attendance Request.on_submit - runs after HRMS has created the Attendance rows.

	Approval is the transition to docstatus 1 in the Attendance Request Approval
	Workflow, so on_submit fires exactly once per approval.
	"""
	label = match_label(doc.reason)
	if not label:
		return
	for name in get_request_attendance(doc):
		frappe.db.set_value("Attendance", name, LABEL_FIELD, label, update_modified=False)


def clear_attendance_label(doc, method=None):
	"""Attendance Request.on_cancel - HRMS cancels the records it linked, but not the
	ones it found already Present, so those still need their label taken off."""
	label = match_label(doc.reason)
	if not label:
		return
	names = frappe.get_all(
		"Attendance",
		filters={
			"employee": doc.employee,
			"attendance_date": ["between", [doc.from_date, doc.to_date]],
			LABEL_FIELD: label,
		},
		pluck="name",
	)
	for name in names:
		frappe.db.set_value("Attendance", name, LABEL_FIELD, None, update_modified=False)
