# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Separation Type seed data.

A seeder rather than a fixture, like Grievance Type: HR edits or disables these in the
Desk, and a fixture would overwrite that on every migrate. Only inserts what is missing.
"""

import frappe

SEPARATION_TYPES = [
	"Resignation",
	"Termination",
	"Dismissal",
	"Retirement",
	"End of Contract",
	"Redundancy",
	"Death",
	"Desertion",
]


def seed_separation_types():
	for name in SEPARATION_TYPES:
		if frappe.db.exists("Separation Type", name):
			continue

		frappe.get_doc({"doctype": "Separation Type", "separation_type": name}).insert(
			ignore_permissions=True
		)
