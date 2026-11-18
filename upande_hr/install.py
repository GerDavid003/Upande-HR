import json

import frappe

MODULE = "Upande Hr"
DEFAULT_REMINDER_DAYS = (30, 14, 7, 0)


def after_install():
	set_default_reminder_days()
	from upande_hr.contracts.backfill import backfill_contracts

	backfill_contracts()


def set_default_reminder_days():
	"""Seed the default reminder points, only if none are configured."""
	settings = frappe.get_single("Upande HR Settings")
	if settings.contract_reminder_days:
		return
	for days in DEFAULT_REMINDER_DAYS:
		settings.append("contract_reminder_days", {"days_before": days})
	settings.save(ignore_permissions=True)


def before_uninstall():
	"""Record what after_uninstall must clean up. Performs NO writes and NO DDL.

	Frappe's remove_app runs this hook even for --dry-run (and before taking any
	backup), so anything destructive here would really happen. Frappe itself deletes
	the module's Custom Field / Property Setter records (only when not a dry run);
	their DB columns are left behind, so remember them for after_uninstall.
	"""
	frappe.flags.upande_hr_uninstall_columns = [
		(cf.dt, cf.fieldname)
		for cf in frappe.get_all("Custom Field", filters={"module": MODULE}, fields=["dt", "fieldname"])
	]


def _app_installed():
	# read fresh from the DB, not from a cache
	return "upande_hr" in json.loads(frappe.db.get_global("installed_apps") or "[]")


def after_uninstall():
	"""Drop leftovers once the app is really removed (no-op for a dry run)."""
	if _app_installed():
		return  # dry run: remove_app did not remove us from installed apps

	for dt, fieldname in frappe.flags.pop("upande_hr_uninstall_columns", None) or []:
		_drop_column(dt, fieldname)
		frappe.clear_cache(doctype=dt)

	frappe.db.delete("Notification Log", {"document_type": "Employee Contract"})
	frappe.db.delete("Scheduled Job Type", {"method": ["like", "upande_hr.%"]})
	frappe.db.delete("Email Queue", {"reference_doctype": "Employee Contract", "status": "Not Sent"})
	frappe.clear_cache()


def _drop_column(doctype, fieldname):
	meta = frappe.get_meta(doctype)
	if meta.issingle or meta.is_virtual:
		return
	# Skip if a standard (non-custom) field still owns this column
	if frappe.db.exists("DocField", {"parent": doctype, "fieldname": fieldname}):
		return
	if frappe.db.has_column(doctype, fieldname):
		frappe.db.sql_ddl(f"ALTER TABLE `tab{doctype}` DROP COLUMN `{fieldname}`")
