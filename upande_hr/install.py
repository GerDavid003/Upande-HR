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
	"""Remove everything this app added to other apps' doctypes.

	Doctypes owned by the Upande Hr module (e.g. Employee Separation Type) are
	dropped by Frappe's own remove_app. Custom Field / Property Setter records are
	also deleted there, but their DB columns are left behind, so drop them here.
	"""
	for cf in frappe.get_all(
		"Custom Field", filters={"module": MODULE}, fields=["name", "dt", "fieldname", "fieldtype"]
	):
		frappe.delete_doc("Custom Field", cf.name, ignore_permissions=True, force=True)
		_drop_column(cf.dt, cf.fieldname)
		frappe.clear_cache(doctype=cf.dt)

	for name in frappe.get_all("Property Setter", filters={"module": MODULE}, pluck="name"):
		frappe.delete_doc("Property Setter", name, ignore_permissions=True, force=True)

	_remove_contract_artifacts()


def _remove_contract_artifacts():
	"""Remove records in other apps' tables that reference this app's contracts/jobs."""
	frappe.db.delete("Notification Log", {"document_type": "Employee Contract"})
	frappe.db.delete("Scheduled Job Type", {"method": ["like", "upande_hr.%"]})
	frappe.db.delete("Email Queue", {"reference_doctype": "Employee Contract", "status": "Not Sent"})


def _drop_column(doctype, fieldname):
	meta = frappe.get_meta(doctype)
	if meta.issingle or meta.is_virtual:
		return
	# Skip if a standard (non-custom) field still owns this column
	if frappe.db.exists("DocField", {"parent": doctype, "fieldname": fieldname}):
		return
	if frappe.db.has_column(doctype, fieldname):
		frappe.db.sql_ddl(f"ALTER TABLE `tab{doctype}` DROP COLUMN `{fieldname}`")
