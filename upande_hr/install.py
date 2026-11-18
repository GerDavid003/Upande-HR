import frappe


def before_uninstall():
	for name in frappe.get_all("Custom Field", filters={"module": "Upande Hr"}, pluck="name"):
		frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)


def after_install():
	set_comp_off_leave_type()

	from upande_hr.attendance.absence_settings import seed_defaults

	seed_defaults()

	from upande_hr.attendance.absence_email_templates import ensure_email_templates

	ensure_email_templates()

	from upande_hr.attendance.mod_roster import seed_settings

	seed_settings()


def set_comp_off_leave_type():
	"""Conditional default for Extra Shift Compensation Settings.leave_type: stored only if a
	matching Leave Type exists on the site. Never a JSON default (see get_default_leave_type)."""
	from upande_hr.upande_hr.doctype.extra_shift_compensation.extra_shift_compensation import (
		SETTINGS,
		get_default_leave_type,
	)

	if frappe.db.get_single_value(SETTINGS, "leave_type"):
		return
	leave_type = get_default_leave_type()
	if leave_type:
		frappe.db.set_single_value(SETTINGS, "leave_type", leave_type)
