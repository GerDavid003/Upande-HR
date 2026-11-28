# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Probation tab on Employee.

The end date is always derived, never entered: Employee.validate recalculates it on every
save (form, import or API), so a value sent for it is overwritten. public/js/employee.js
mirrors calculate_end_date() for the live preview on the form; keep the two in step.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate

START_DATE = "custom_probation_start_date"
PERIOD_DAYS = "custom_probation_period_days"
END_DATE = "custom_probation_end_date"


def calculate_end_date(start_date, period_days):
	"""Last day of probation, counting the start day as day 1.

	A 90-day probation starting 1 Jan ends 31 Mar. This is the single place the counting
	rule lives; drop the "- 1" if HR counts the period as ending the day after.
	"""
	period_days = cint(period_days)
	if not start_date or period_days <= 0:
		return None
	return add_days(getdate(start_date), period_days - 1)


def set_probation_end_date(doc, method=None):
	"""Employee.validate: reject a negative period, then recalculate the end date.

	Int fields are stored NOT NULL DEFAULT 0, so 0 is what every employee without a period
	carries; it means "not set" and leaves the end date blank rather than raising.
	"""
	period_days = cint(doc.get(PERIOD_DAYS))
	if period_days < 0:
		frappe.throw(
			_("{0} must be greater than 0.").format(_(doc.meta.get_label(PERIOD_DAYS))),
			title=_("Invalid Probation Period"),
		)

	start_date = doc.get(START_DATE) or doc.get("date_of_joining")
	doc.set(END_DATE, calculate_end_date(start_date, period_days))
