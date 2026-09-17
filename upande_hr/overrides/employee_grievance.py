# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Confidentiality on Employee Grievance.

On Kentrout this was a Permission Query Server Script, which only runs when
`server_script_enabled` is on and only filters list and report views — a direct link
to the document still opened. Shipping it as app hooks removes both problems: the
query condition scopes the list, `has_permission` closes the direct-link route.
"""

import frappe

# Grievance Types whose records are restricted. These must match the Grievance Type
# names seeded by upande_hr.patches.v1_0.seed_grievance_types.
CONFIDENTIAL_TYPES = ("Sexual Harassment",)

PRIVILEGED_ROLES = {"HR Manager", "Group HR Manager", "System Manager"}


def is_privileged(user: str) -> bool:
	if user == "Administrator":
		return True
	return bool(PRIVILEGED_ROLES.intersection(frappe.get_roles(user)))


def get_permission_query_conditions(user: str | None = None) -> str:
	user = user or frappe.session.user
	if is_privileged(user):
		return ""

	# `!= 'Sexual Harassment'` would also drop rows where grievance_type is NULL,
	# because NULL never compares equal in SQL. The IS NULL arm keeps untyped
	# grievances visible.
	values = ", ".join(frappe.db.escape(t) for t in CONFIDENTIAL_TYPES)
	return (
		"(`tabEmployee Grievance`.grievance_type IS NULL"
		f" OR `tabEmployee Grievance`.grievance_type NOT IN ({values}))"
	)


def has_permission(doc, ptype=None, user=None) -> bool:
	user = user or frappe.session.user
	if doc.get("grievance_type") not in CONFIDENTIAL_TYPES:
		return True
	return is_privileged(user)
