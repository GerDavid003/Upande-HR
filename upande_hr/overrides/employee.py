# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Years of service on Employee.

Stored rather than virtual, deliberately. A virtual field is always exact but is not
written to the table, so it cannot be filtered, sorted or reported on - and "everyone
past five years" is the whole reason HR asked for it. The cost is a nightly refresh and
a figure that can be up to 24 hours stale, which does not matter for a number measured
in years.
"""

import frappe
from frappe.utils import date_diff, flt, getdate, today

DAYS_IN_YEAR = 365.25
PRECISION = 2


def set_years_of_service(doc, method=None):
	"""Employee.validate - keeps the figure right the moment a date is entered or fixed."""
	doc.custom_years_of_service = calculate_years_of_service(
		doc.get("date_of_joining"), doc.get("relieving_date")
	)


def calculate_years_of_service(date_of_joining, relieving_date=None):
	"""Years between joining and the end of service.

	Returns None, not 0, when there is no joining date - zero reads as "joined today".

	Note what happens downstream: Frappe lists Float in NOT_NULL_TYPES
	(frappe/database/schema.py), so the column is decimal NOT NULL DEFAULT 0.00 and the
	None is coerced to 0.00 on save. There is no opt-out - `not_nullable` only forces
	NOT NULL, and it is not a Custom Field property either. So a stored numeric cannot
	represent "unknown" at all, which is the price of making this filterable and
	reportable instead of virtual.

	Consequence for reports: filter on `date_of_joining is set`, never on
	`custom_years_of_service > 0`. In practice date_of_joining is mandatory on Employee,
	so only an import passing ignore_mandatory can produce the zero.
	"""
	if not date_of_joining:
		return None

	# Service length stops the day someone leaves. Measuring to today would let an
	# ex-employee's tenure keep climbing for as long as the record exists.
	end = getdate(relieving_date) if relieving_date else getdate(today())
	start = getdate(date_of_joining)

	if end < start:
		return 0.0

	return flt(date_diff(end, start) / DAYS_IN_YEAR, PRECISION)


def refresh_years_of_service():
	"""Daily. Only Active employees move - anyone else has a relieving date, so their
	figure is already fixed and rewriting it every night would be churn for nothing."""
	employees = frappe.get_all(
		"Employee",
		filters={"status": "Active", "date_of_joining": ["is", "set"]},
		fields=["name", "date_of_joining", "relieving_date", "custom_years_of_service"],
	)

	for employee in employees:
		years = calculate_years_of_service(employee.date_of_joining, employee.relieving_date)
		if years == flt(employee.custom_years_of_service, PRECISION):
			continue

		# update_modified=False: a nightly pass must not bump every Employee's timestamp,
		# which would make `modified` useless for spotting real HR edits.
		frappe.db.set_value(
			"Employee", employee.name, "custom_years_of_service", years, update_modified=False
		)
