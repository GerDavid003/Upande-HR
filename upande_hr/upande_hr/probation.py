"""Probation period tracking on the Employee record.

The review reminder itself is a Notification record created in the UI:
    Document Type : Employee
    Send Alert On : Days Before
    Reference Date: custom_probation_end_date
    Days Before   : 14
    Condition     : doc.custom_probation_status in ("Ongoing", "Extended")
                    and doc.status == "Active"
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_months, getdate, nowdate

DEFAULT_MONTHS = 3
DEFAULT_LEAD_DAYS = 14


def set_probation_dates(doc, method=None):
	"""Compute probation end and review dates from the start date and period."""
	status = doc.get("custom_probation_status")

	if not status or status == "Not Applicable":
		doc.custom_probation_start_date = None
		doc.custom_probation_end_date = None
		doc.custom_probation_review_date = None
		return

	if not doc.custom_probation_start_date:
		doc.custom_probation_start_date = doc.date_of_joining

	if not doc.custom_probation_period_months:
		doc.custom_probation_period_months = (
			frappe.db.get_single_value("HR Settings", "custom_default_probation_months")
			or DEFAULT_MONTHS
		)

	recompute = (
		doc.has_value_changed("custom_probation_start_date")
		or doc.has_value_changed("custom_probation_period_months")
		or not doc.custom_probation_end_date
	)

	# "Extended" keeps whatever end date HR entered by hand.
	if recompute and status != "Extended" and doc.custom_probation_start_date:
		doc.custom_probation_end_date = add_days(
			add_months(
				getdate(doc.custom_probation_start_date),
				doc.custom_probation_period_months,
			),
			-1,
		)

	if doc.custom_probation_end_date:
		if doc.custom_probation_start_date and getdate(doc.custom_probation_end_date) < getdate(
			doc.custom_probation_start_date
		):
			frappe.throw(_("Probation End Date cannot be before Probation Start Date"))

		lead = (
			frappe.db.get_single_value("HR Settings", "custom_probation_review_lead_days")
			or DEFAULT_LEAD_DAYS
		)
		doc.custom_probation_review_date = add_days(getdate(doc.custom_probation_end_date), -lead)

	if status == "Confirmed" and not doc.final_confirmation_date:
		doc.final_confirmation_date = nowdate()