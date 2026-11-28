# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Settings for the Absent -> Annual Leave deduction.

All of them are Custom Fields on HR Settings, Upande tab, Absenteeism Penalties section.
They are read through get_settings() so a site that has never saved HR Settings since
the fields landed still gets the documented defaults (a Single only stores a value once
the form is saved).

Ported from the altura branch, with two TSH differences: employees are scoped by
Employment Type rather than Employee Grade (TSH grades do not say who holds Annual
Leave), and there is no switch for the employee email - a deducted day is always
notified.
"""

import frappe
from frappe import _
from frappe.utils import cint, getdate

ENABLED = "custom_enable_absent_al_deduction"
START_DATE = "custom_absence_deduction_start_date"
EMPLOYMENT_TYPES = "custom_absence_deduction_employment_types"
EXEMPT = "custom_absence_deduction_exempt_employees"
LEAVE_TYPE = "custom_absence_deduction_leave_type"
SINGLE_SCAN = "custom_single_scan_counts_as_absent"
ON_INSUFFICIENT = "custom_absence_on_insufficient_balance"
LWP_LEAVE_TYPE = "custom_absence_lwp_leave_type"

EMPLOYMENT_TYPE_ROW = "Absence Deduction Employment Type"
EXEMPT_ROW = "Absence Deduction Exempt Employee"

SKIP_AND_FLAG = "Skip and flag"
LEAVE_WITHOUT_PAY = "Leave Without Pay"

# TSH: SN- staff are exactly these two. Casuals and interns hold no Annual Leave, so
# every one of their absences would only end up as an insufficient-balance flag.
DEFAULT_EMPLOYMENT_TYPES = ("Fixed Term Contract", "Permanent")
DEFAULTS = {
	LEAVE_TYPE: "Annual Leave",
	SINGLE_SCAN: 0,
	ON_INSUFFICIENT: SKIP_AND_FLAG,
	LWP_LEAVE_TYPE: "Leave Without Pay",
}


def get_stored(fieldname: str):
	"""The raw tabSingles value, None if HR Settings never stored it.

	Not get_single_value: that casts a missing value to the field type's empty value,
	which would hide whether a default applies.
	"""
	Singles = frappe.qb.DocType("Singles")
	rows = (
		frappe.qb.from_(Singles)
		.select(Singles.value)
		.where((Singles.doctype == "HR Settings") & (Singles.field == fieldname))
	).run()
	return rows[0][0] if rows else None


def get_settings() -> frappe._dict:
	def value(fieldname):
		stored = get_stored(fieldname)
		return DEFAULTS.get(fieldname) if stored in (None, "") else stored

	start_date = get_stored(START_DATE)
	return frappe._dict(
		enabled=cint(frappe.db.get_single_value("HR Settings", ENABLED)),
		start_date=getdate(start_date) if start_date else None,
		employment_types=get_employment_types(),
		exempt_employees=get_exempt_employees(),
		leave_type=value(LEAVE_TYPE),
		single_scan_counts_as_absent=cint(value(SINGLE_SCAN)),
		on_insufficient_balance=value(ON_INSUFFICIENT),
		lwp_leave_type=value(LWP_LEAVE_TYPE),
	)


def get_employment_types() -> list[str]:
	"""Empty list means every employee, including those with no Employment Type."""
	return frappe.get_all(
		EMPLOYMENT_TYPE_ROW,
		filters={"parent": "HR Settings", "parenttype": "HR Settings", "parentfield": EMPLOYMENT_TYPES},
		pluck="employment_type",
		order_by="idx",
	)


def get_exempt_employees() -> list[str]:
	return frappe.get_all(
		EXEMPT_ROW,
		filters={"parent": "HR Settings", "parenttype": "HR Settings", "parentfield": EXEMPT},
		pluck="employee",
		order_by="idx",
	)


def validate_hr_settings(doc, method=None):
	"""doc_events HR Settings.validate."""
	if not cint(doc.get(ENABLED)):
		return

	if not doc.get(START_DATE):
		frappe.throw(
			_("Set {0} before switching on {1}, so that enabling never deducts past absences.").format(
				frappe.bold(_("Deduct From")), frappe.bold(_("Deduct Annual Leave for Unexcused Absences"))
			)
		)

	if not doc.get(LEAVE_TYPE):
		frappe.throw(_("Set the Leave Type to Deduct before switching on the deduction."))

	if doc.get(ON_INSUFFICIENT) == LEAVE_WITHOUT_PAY:
		lwp = doc.get(LWP_LEAVE_TYPE)
		if not lwp or not frappe.db.get_value("Leave Type", lwp, "is_lwp"):
			frappe.throw(
				_("{0} must be a Leave Type with Is Leave Without Pay ticked.").format(
					frappe.bold(_("Leave Without Pay Leave Type"))
				)
			)


def seed_defaults():
	"""Write the documented defaults into HR Settings once.

	Runs from after_install and from a one-off patch. The patch runs before Frappe syncs
	fixtures, and set_single_value refuses a field HR Settings does not have yet, so this
	app's fixtures are synced first (idempotent; migrate repeats it straight after).
	Values are written directly rather than by saving HR Settings, so its validation does
	not fire - and the deduction switch is never touched. Values already set by HR are
	left alone, and the Employment Type list is only filled if it is empty, so clearing
	it later ("everyone") is never undone.
	"""
	if not frappe.get_meta("HR Settings").has_field(EMPLOYMENT_TYPES):
		from frappe.utils.fixtures import sync_fixtures

		sync_fixtures("upande_hr")
		frappe.clear_cache(doctype="HR Settings")

	for fieldname, default in DEFAULTS.items():
		if get_stored(fieldname) in (None, ""):
			if fieldname in (LEAVE_TYPE, LWP_LEAVE_TYPE) and not frappe.db.exists("Leave Type", default):
				continue
			frappe.db.set_single_value("HR Settings", fieldname, default)

	if get_employment_types():
		return

	idx = 0
	for employment_type in DEFAULT_EMPLOYMENT_TYPES:
		if not frappe.db.exists("Employment Type", employment_type):
			continue
		idx += 1
		frappe.get_doc(
			{
				"doctype": EMPLOYMENT_TYPE_ROW,
				"parent": "HR Settings",
				"parenttype": "HR Settings",
				"parentfield": EMPLOYMENT_TYPES,
				"idx": idx,
				"employment_type": employment_type,
			}
		).db_insert()
