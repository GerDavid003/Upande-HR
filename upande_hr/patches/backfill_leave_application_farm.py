import frappe
from frappe.modules.utils import sync_customizations


def execute():
	"""Fill Leave Application.custom_farm from each employee's current farm.

	Uses the employee's farm as of today (no history is kept), and only fills blanks.
	"""
	# Patches run before migrate syncs custom/*.json, so make sure the column exists.
	if not frappe.db.has_column("Leave Application", "custom_farm"):
		sync_customizations("upande_hr")
	if not frappe.db.has_column("Employee", "custom_farm"):
		return

	frappe.db.sql(
		"""
		UPDATE `tabLeave Application` la
		JOIN `tabEmployee` emp ON emp.name = la.employee
		SET la.custom_farm = emp.custom_farm
		WHERE IFNULL(la.custom_farm, '') = ''
			AND IFNULL(emp.custom_farm, '') != ''
		"""
	)
