# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Permlevel-1 DocPerm rows on Employee for the talent pool fields.

`depends_on` hides the designations field until the box is ticked, but it enforces
nothing: any role with write access to Employee can still set both through the API or
an import, and HR User has write access to Employee here. Permlevel 1 is the part that
actually restricts it.

Note the failure mode this guards against: a permlevel with no matching DocPerm row
makes the field invisible to *everyone*, including HR Manager - it fails closed and
silently, with no error to notice. So if this patch does not run, the fields do not
appear at all rather than appearing unprotected.
"""

import frappe
from frappe.permissions import add_permission, update_permission_property

PERMLEVEL = 1

# HR User is deliberately absent: no row at this permlevel means the talent pool fields
# are invisible to them. Whether that is the right policy is a live question - see the
# note in the commit message.
ROLES = ("HR Manager", "Group HR Manager", "System Manager")

DOCTYPE = "Employee"


def execute():
	for role in ROLES:
		if not frappe.db.exists("Role", role):
			frappe.log_error(
				title="upande_hr: talent pool permlevel skipped",
				message=f"Role {role!r} does not exist on this site.",
			)
			continue

		if not frappe.db.exists(
			"Custom DocPerm", {"parent": DOCTYPE, "role": role, "permlevel": PERMLEVEL}
		):
			add_permission(DOCTYPE, role, PERMLEVEL)

		# add_permission creates the row with read only, so write is set explicitly.
		# Both calls are idempotent, which is what makes the patch safe to re-run.
		for ptype in ("read", "write"):
			update_permission_property(DOCTYPE, role, PERMLEVEL, ptype, 1)

	frappe.clear_cache(doctype=DOCTYPE)
