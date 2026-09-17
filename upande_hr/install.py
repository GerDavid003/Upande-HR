import frappe

from upande_hr.setup.grievance_types import seed_grievance_types
from upande_hr.setup.workspace import add_case_management_card


def after_install():
	seed_grievance_types()
	add_case_management_card()


def after_migrate():
	add_case_management_card()


def before_uninstall():
	for name in frappe.get_all("Custom Field", filters={"module": "Upande Hr"}, pluck="name"):
		frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
