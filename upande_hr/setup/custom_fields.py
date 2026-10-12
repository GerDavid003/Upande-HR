# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Create this app's fixture Custom Fields ahead of the fixture sync.

bench migrate runs post_model_sync patches *before* sync_fixtures, so on the first
migrate after a Custom Field is added, a patch that reads or writes it finds no column.
A patch calls ensure_custom_fields with the names it needs; the later fixture sync then
finds them already there and updates them in place.
"""

import json

import frappe


def ensure_custom_fields(names):
	path = frappe.get_app_path("upande_hr", "fixtures", "custom_field.json")
	with open(path) as f:
		records = {record["name"]: record for record in json.load(f)}

	for name in names:
		if frappe.db.exists("Custom Field", name):
			continue

		record = dict(records[name])
		record.pop("modified", None)
		frappe.get_doc(record).insert(ignore_permissions=True)
