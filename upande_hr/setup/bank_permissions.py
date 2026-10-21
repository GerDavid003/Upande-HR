# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Select and Read on Bank and Bank Branch for employees, so the Link fields on
Employee Details Update work from the desk.

Role Permission rows (Custom DocPerm), not User Permissions. Re-applied on every migrate
rather than shipped as a fixture: the first Custom DocPerm on a doctype replaces its
standard DocPerms outright, so a fixture carrying only the Employee row would strip
Accounts' access to Bank. add_permission copies the standard rows over first.

Bank Branch belongs to Upande Payroll, which is not on every bench; it is skipped where
missing.
"""

import frappe
from frappe.permissions import add_permission, update_permission_property

DOCTYPES = ("Bank", "Bank Branch")
# Employees hold Employee on TSH; Employee Self Service is included where it exists.
ROLES = ("Employee", "Employee Self Service")
PTYPES = ("select", "read")


def grant_bank_permissions():
	for doctype in DOCTYPES:
		if not frappe.db.exists("DocType", doctype):
			continue
		for role in ROLES:
			if not frappe.db.exists("Role", role):
				continue
			if not frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0}):
				add_permission(doctype, role, 0)
			# Both calls are idempotent, so this is safe on every migrate.
			for ptype in PTYPES:
				update_permission_property(doctype, role, 0, ptype, 1)
		frappe.clear_cache(doctype=doctype)
