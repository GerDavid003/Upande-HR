import frappe

from upande_hr.setup.grievance_types import seed_grievance_types
from upande_hr.setup.separation_types import seed_separation_types
from upande_hr.setup.workspace import add_case_management_card
from upande_hr.upande_hr.employee_details import refresh_ages


def after_install():
	seed_grievance_types()
	seed_separation_types()
	add_case_management_card()


def after_migrate():
	add_case_management_card()
	# Fills custom_age the first time the field lands, rather than leaving every
	# existing employee at 0 until the nightly job. One UPDATE, so cheap to repeat.
	refresh_ages()


def before_uninstall():
	for name in frappe.get_all("Custom Field", filters={"module": "Upande Hr"}, pluck="name"):
		frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
