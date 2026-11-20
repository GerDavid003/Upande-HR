import json

import frappe

MODULE = "Upande Hr"
DEFAULT_REMINDER_DAYS = (30, 14, 7, 0)
CONTRACT = "Employee Contract"
DEFAULT_EMAIL_TEMPLATE = "Contract Expiry Reminder"
APP_DOCTYPES = (CONTRACT, "Upande HR Settings", "Contract Reminder Day", "Contract Reminder Recipient")


def after_install():
	set_default_reminder_days()
	set_default_email_template()
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


def set_default_email_template():
	"""Seed an editable reminder Email Template and select it, without touching client edits."""
	from upande_hr.contracts.reminders import DEFAULT_SUBJECT, EMAIL_TEMPLATE

	if not frappe.db.exists("Email Template", DEFAULT_EMAIL_TEMPLATE):
		frappe.get_doc(
			{
				"doctype": "Email Template",
				"name": DEFAULT_EMAIL_TEMPLATE,
				"subject": DEFAULT_SUBJECT,
				"use_html": 1,
				"response_html": EMAIL_TEMPLATE.strip(),
			}
		).insert(ignore_permissions=True)
	if not frappe.db.get_single_value("Upande HR Settings", "contract_reminder_email_template"):
		frappe.db.set_single_value("Upande HR Settings", "contract_reminder_email_template", DEFAULT_EMAIL_TEMPLATE)


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
	# get_global goes through the defaults cache, which remove_from_installed_apps clears
	# during a real uninstall, so this reflects the post-removal state.
	return "upande_hr" in json.loads(frappe.db.get_global("installed_apps") or "[]")


def after_uninstall():
	"""Drop leftovers once the app is really removed (no-op for a dry run)."""
	if _app_installed():
		return  # dry run: remove_app did not remove us from installed apps

	for dt, fieldname in frappe.flags.pop("upande_hr_uninstall_columns", None) or []:
		_drop_column(dt, fieldname)
		frappe.clear_cache(doctype=dt)

	_delete_app_records()
	frappe.db.commit()  # nosemgrep
	# remove_app commits before running after_uninstall and bench ends with frappe.destroy()
	# (no commit), so without this the deletes above would be rolled back.
	frappe.clear_cache()


def _delete_app_records():
	doctypes = list(APP_DOCTYPES)

	frappe.db.delete("Custom DocPerm", {"parent": ["in", doctypes]})
	frappe.db.delete("Property Setter", {"doc_type": ["in", doctypes]})

	_delete_contract_files()

	frappe.db.delete("Version", {"ref_doctype": CONTRACT})
	frappe.db.delete("Comment", {"reference_doctype": CONTRACT})
	frappe.db.delete("ToDo", {"reference_type": CONTRACT})
	frappe.db.delete("DocShare", {"share_doctype": CONTRACT})
	frappe.db.delete("Notification Log", {"document_type": CONTRACT})

	queue = frappe.get_all("Email Queue", {"reference_doctype": CONTRACT}, pluck="name")
	if queue:
		frappe.db.delete("Email Queue Recipient", {"parent": ["in", queue]})
		frappe.db.delete("Email Queue", {"name": ["in", queue]})

	job_types = frappe.get_all("Scheduled Job Type", {"method": ["like", "upande_hr.%"]}, pluck="name")
	if job_types:
		frappe.db.delete("Scheduled Job Log", {"scheduled_job_type": ["in", job_types]})
		frappe.db.delete("Scheduled Job Type", {"name": ["in", job_types]})

	frappe.db.delete("Series", {"name": ["like", "HR-CON-%"]})
	frappe.db.delete("Email Template", {"name": DEFAULT_EMAIL_TEMPLATE})
	frappe.db.delete("Error Log", {"method": ["like", "Contract reminder failed%"]})


def _delete_contract_files():
	"""Remove contract attachments: the File records and their files on disk.

	frappe.delete_doc("File") cannot be used here: its on_trash comments on the attached
	Employee Contract, whose DocType is already gone, so it fails and the file stays on disk.
	A file on disk is kept when another File record (e.g. on an Employee) shares its content.
	"""
	for name in frappe.get_all("File", {"attached_to_doctype": CONTRACT, "is_folder": 0}, pluck="name"):
		file = frappe.get_doc("File", name)
		frappe.db.delete("File", {"name": name})
		if file.is_remote_file:
			continue
		try:
			file._delete_file_on_disk()  # only unlinks if no other File shares the content
		except Exception:
			frappe.log_error(title=f"Upande HR uninstall: could not delete file {file.file_url}")


def _drop_column(doctype, fieldname):
	meta = frappe.get_meta(doctype)
	if meta.issingle or meta.is_virtual:
		return
	# Skip if a standard (non-custom) field still owns this column
	if frappe.db.exists("DocField", {"parent": doctype, "fieldname": fieldname}):
		return
	if frappe.db.has_column(doctype, fieldname):
		frappe.db.sql_ddl(f"ALTER TABLE `tab{doctype}` DROP COLUMN `{fieldname}`")
