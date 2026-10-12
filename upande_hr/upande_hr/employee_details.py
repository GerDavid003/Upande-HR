# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Personal details on Employee: age and beneficiaries.

Age is stored rather than virtual for the same reason as years of service - HR filters
and reports on it. It goes stale on every birthday, so a nightly job refreshes it.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

ALLOCATION_TOTAL = 100
ALLOCATION_TOLERANCE = 0.01


def employee_validate(doc, method=None):
	"""Employee.validate."""
	set_age(doc)
	validate_beneficiaries(doc)


def set_age(doc):
	doc.custom_age = calculate_age(doc.get("date_of_birth"))


def calculate_age(date_of_birth, on_date=None):
	"""Whole years completed on `on_date`. 0 with no date of birth - Int is NOT NULL, so
	None would be coerced to 0 on save anyway."""
	if not date_of_birth:
		return 0

	dob = getdate(date_of_birth)
	today = getdate(on_date or nowdate())
	if today < dob:
		return 0

	# Subtract a year if this year's birthday has not happened yet. Tuple comparison
	# handles 29 February: a leap-day birthday ticks over on 1 March in other years.
	return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def refresh_ages():
	"""Daily, and after migrate. One UPDATE rather than a doc.save() per employee:
	nothing else on Employee depends on age, so the controller has no work to do, and
	bumping `modified` would make every record look edited overnight.

	The date is passed in rather than using CURDATE() so it follows the site's time zone,
	not the database server's.
	"""
	# Absent until the fixture sync has run, e.g. after `bench migrate --skip-fixtures`.
	if not frappe.db.has_column("Employee", "custom_age"):
		return

	frappe.db.sql(
		"""
		update `tabEmployee`
		set custom_age = if(
			date_of_birth is null or date_of_birth > %(today)s,
			0,
			timestampdiff(year, date_of_birth, %(today)s)
		)
		where custom_age != if(
			date_of_birth is null or date_of_birth > %(today)s,
			0,
			timestampdiff(year, date_of_birth, %(today)s)
		)
		""",
		{"today": nowdate()},
	)


def validate_beneficiaries(doc):
	"""Allocations must cover exactly 100%. An empty table is allowed - not every
	employee has nominated anyone yet."""
	rows = doc.get("custom_beneficiaries") or []
	if not rows:
		return

	for row in rows:
		if flt(row.allocation_percentage) <= 0:
			frappe.throw(
				_("Beneficiaries row {0} ({1}): Allocation must be greater than 0%.").format(
					row.idx, row.beneficiary_name or _("unnamed")
				),
				title=_("Invalid Beneficiary Allocation"),
			)

	total = sum(flt(row.allocation_percentage) for row in rows)
	if abs(total - ALLOCATION_TOTAL) > ALLOCATION_TOLERANCE:
		if total > ALLOCATION_TOTAL:
			message = _("Beneficiary allocations total {0}%, which is {1}% over 100%.")
		else:
			message = _("Beneficiary allocations total {0}%, which is {1}% short of 100%.")

		frappe.throw(
			message.format(f"{flt(total, 2):g}", f"{flt(abs(total - ALLOCATION_TOTAL), 2):g}"),
			title=_("Invalid Beneficiary Allocation"),
		)
