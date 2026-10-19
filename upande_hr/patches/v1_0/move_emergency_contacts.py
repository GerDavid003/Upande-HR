# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Move Employee's standard single emergency contact into custom_emergency_contacts.

The standard fields are hidden by Property Setter fixtures, so anything left in them
would drop out of sight. Fixtures sync after post_model_sync patches, so on the first
migrate the Custom Field does not exist yet; rows are written straight to the child
table, which sync_all has already created. Employees that already have a row are left
alone, which keeps this safe to re-run.
"""

import frappe

PARENTFIELD = "custom_emergency_contacts"
CHILD = "Employee Emergency Contact"


def execute():
	options = frappe.get_meta(CHILD).get_field("relationship").options.split("\n")
	by_lower = {o.lower(): o for o in options if o}

	have_rows = set(frappe.get_all(CHILD, filters={"parenttype": "Employee"}, pluck="parent", distinct=True))
	employees = frappe.get_all(
		"Employee",
		or_filters={"person_to_be_contacted": ["is", "set"], "emergency_phone_number": ["is", "set"]},
		fields=["name", "person_to_be_contacted", "emergency_phone_number", "relation"],
	)
	for emp in employees:
		if emp.name in have_rows:
			continue
		row = frappe.new_doc(CHILD)
		row.update(
			{
				"parent": emp.name,
				"parenttype": "Employee",
				"parentfield": PARENTFIELD,
				"idx": 1,
				"contact_name": emp.person_to_be_contacted,
				"phone": emp.emergency_phone_number,
				# Relation was free text; anything that is not an option becomes Other.
				"relationship": by_lower.get((emp.relation or "").strip().lower(), "Other"),
			}
		)
		row.db_insert()
