# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Keep an Extra Shift Compensation attendance override in place.

`Attendance.validate()` ends with `check_leave_record()`, which reassigns
`status = "On Leave"` whenever an approved Leave Application covers the date. When an
employee reported for duty on a leave day and was compensated with a comp off day, the
record has to read `Present` instead.

`db_set` alone is not enough: it survives until someone opens the Attendance in desk and
saves, at which point `check_leave_record()` overwrites it again. This runs as a
`doc_events` validate hook, which frappe fires *after* the controller's own `validate()`,
so it gets the last word.
"""


def reassert_comp_off_override(doc, method=None):
	if doc.get("custom_comp_off_override"):
		doc.status = "Present"
		doc.leave_type = None
		doc.leave_application = None
