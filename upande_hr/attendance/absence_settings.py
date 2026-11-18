# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Altura settings for the Absent -> Annual Leave deduction.

All of them are Custom Fields on HR Settings, Upande tab, Absent Deduction section, below
TSH's custom_enable_absent_al_deduction. They are read through get_settings() so a site
that has never saved HR Settings since the fields landed still gets the documented
defaults (a Single only stores a value once the form is saved).
"""

import frappe
from frappe import _
from frappe.utils import cint, getdate

ENABLED = "custom_enable_absent_al_deduction"
GRADES = "custom_absence_deduction_grades"
EXEMPT = "custom_absence_deduction_exempt_employees"
LEAVE_TYPE = "custom_absence_deduction_leave_type"
SINGLE_SCAN = "custom_single_scan_counts_as_absent"
START_DATE = "custom_absence_deduction_start_date"
ON_INSUFFICIENT = "custom_absence_on_insufficient_balance"
LWP_LEAVE_TYPE = "custom_absence_lwp_leave_type"
NOTIFY = "custom_notify_employee_on_absence_deduction"

SKIP_AND_FLAG = "Skip and flag"
LEAVE_WITHOUT_PAY = "Leave Without Pay"

DEFAULT_GRADE = "Full time staff"
DEFAULTS = {
	LEAVE_TYPE: "Annual Leave",
	SINGLE_SCAN: 0,
	ON_INSUFFICIENT: SKIP_AND_FLAG,
	LWP_LEAVE_TYPE: "Leave Without Pay",
	NOTIFY: 1,
}


def get_stored(fieldname: str):
	"""The raw tabSingles value, None if HR Settings never stored it.

	Not get_single_value: that casts a missing Check to 0, which would turn the
	notify default of 1 into 0.
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

	return frappe._dict(
		enabled=cint(frappe.db.get_single_value("HR Settings", ENABLED)),
		grades=get_grades(),
		exempt_employees=get_exempt_employees(),
		leave_type=value(LEAVE_TYPE),
		single_scan_counts_as_absent=cint(value(SINGLE_SCAN)),
		start_date=getdate(value(START_DATE)) if value(START_DATE) else None,
		on_insufficient_balance=value(ON_INSUFFICIENT),
		lwp_leave_type=value(LWP_LEAVE_TYPE),
		notify_employee=cint(value(NOTIFY)),
	)


def get_grades() -> list[str]:
	"""Empty list means every employee (TSH behaviour)."""
	return frappe.get_all(
		"Absence Deduction Grade",
		filters={"parent": "HR Settings", "parenttype": "HR Settings", "parentfield": GRADES},
		pluck="employee_grade",
		order_by="idx",
	)


def get_exempt_employees() -> list[str]:
	return frappe.get_all(
		"Absence Deduction Exempt Employee",
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

	Runs once, from after_install and from a one-off patch. Both run before Frappe syncs
	fixtures, and set_single_value refuses a field HR Settings does not have yet, so this
	app's fixtures are synced first (idempotent; migrate repeats it straight after).
	Values are written directly rather than by saving HR Settings, so its validation does
	not fire. Values already set by HR are left alone, and the grade list is only filled
	if it is empty, so clearing it later ("all employees") is never undone.
	"""
	if not frappe.get_meta("HR Settings").has_field(NOTIFY):
		from frappe.utils.fixtures import sync_fixtures

		sync_fixtures("upande_hr")
		frappe.clear_cache(doctype="HR Settings")

	for fieldname, default in DEFAULTS.items():
		if get_stored(fieldname) in (None, ""):
			if fieldname in (LEAVE_TYPE, LWP_LEAVE_TYPE) and not frappe.db.exists("Leave Type", default):
				continue
			frappe.db.set_single_value("HR Settings", fieldname, default)

	if get_grades():
		return

	# Employee Grade names compare case-insensitively in MariaDB, so this also finds
	# "Full Time Staff" on a site that capitalised it differently.
	grade = frappe.db.get_value("Employee Grade", DEFAULT_GRADE)
	if not grade:
		return

	frappe.get_doc(
		{
			"doctype": "Absence Deduction Grade",
			"parent": "HR Settings",
			"parenttype": "HR Settings",
			"parentfield": GRADES,
			"idx": 1,
			"employee_grade": grade,
		}
	).db_insert()
