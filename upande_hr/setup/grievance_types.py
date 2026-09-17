# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Grievance Type seed data.

Deliberately a seeder rather than a fixture: fixtures re-sync on every migrate, so
HR editing a description in the Desk would silently lose it on the next deploy. This
only ever inserts what is missing.
"""

import frappe

GRIEVANCE_TYPES = [
	(
		"Sexual Harassment",
		"Complaints of a sexual nature, including unwelcome advances, requests for favours,"
		" or other verbal/physical conduct. Handled confidentially.",
	),
	("Harassment", "Bullying, intimidation, or other harassment not of a sexual nature."),
	(
		"Discrimination",
		"Unfair treatment based on gender, ethnicity, religion, disability, or other protected grounds.",
	),
	("Remuneration and Benefits", "Concerns about pay, benefits, allowances, or deductions."),
	(
		"Working Conditions",
		"Concerns about the working environment, facilities, hours, or health and safety.",
	),
	("Interpersonal Conflict", "Disputes between colleagues or with a supervisor."),
	("Other", "Any grievance not covered by the other categories."),
]


def seed_grievance_types():
	for name, description in GRIEVANCE_TYPES:
		if frappe.db.exists("Grievance Type", name):
			continue

		frappe.get_doc(
			{
				"doctype": "Grievance Type",
				"name": name,
				"description": description,
			}
		).insert(ignore_permissions=True)
