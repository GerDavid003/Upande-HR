# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The "Charge Sheet Recovery" deduction component Charge Sheet posts Additional Salary to.

Created if missing rather than shipped as a fixture. A fixture is re-imported on every
migrate and would reset whatever Finance has since set on it - the GL accounts per
company especially, which are site data this app cannot know.
"""

import frappe

from upande_hr.upande_hr.doctype.charge_sheet.charge_sheet import SALARY_COMPONENT

ABBR = "CSR"


def ensure_charge_sheet_component():
	if frappe.db.exists("Salary Component", SALARY_COMPONENT):
		return
	frappe.get_doc(
		{
			"doctype": "Salary Component",
			"salary_component": SALARY_COMPONENT,
			"salary_component_abbr": ABBR,
			"type": "Deduction",
			"description": "Recovery of the cost of lost, broken, misplaced or under-charged items (Charge Sheet).",
			"depends_on_payment_days": 0,
			"is_tax_applicable": 0,
		}
	).insert(ignore_permissions=True)
