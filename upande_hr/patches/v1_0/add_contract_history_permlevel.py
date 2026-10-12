# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Permlevel-2 DocPerm rows on Employee for custom_contract_history.

Level 2 rather than 1: permlevel 1 on Employee already guards the talent pool fields,
and HR User is deliberately kept out of it (see add_talent_pool_permlevel). Sharing the
level would have shown HR User the talent pool along with the contract history.

Rules are added through frappe.permissions rather than shipped as Custom DocPerm
fixtures: once a doctype has any Custom DocPerm it replaces the standard DocPerm
entirely, and add_permission copies the standard rows across first.

Grant-only and idempotent. A missing rule is added and a right that is off is switched
on; nothing is ever switched off, so rules a site has customised are left alone.
"""

import frappe
from frappe.permissions import add_permission, update_permission_property

DOCTYPE = "Employee"
PERMLEVEL = 2

GRANTS = {
	"HR Manager": ("read", "write"),
	"System Manager": ("read", "write"),
	"HR User": ("read",),
}


def execute():
	for role, ptypes in GRANTS.items():
		if not frappe.db.exists("Role", role):
			frappe.log_error(
				title="upande_hr: contract history permlevel skipped",
				message=f"Role {role!r} does not exist on this site.",
			)
			continue

		filters = {"parent": DOCTYPE, "role": role, "permlevel": PERMLEVEL, "if_owner": 0}
		if not frappe.db.exists("Custom DocPerm", filters):
			add_permission(DOCTYPE, role, PERMLEVEL)

		for ptype in ptypes:
			if not frappe.db.get_value("Custom DocPerm", filters, ptype):
				update_permission_property(DOCTYPE, role, PERMLEVEL, ptype, 1)

	frappe.clear_cache(doctype=DOCTYPE)
