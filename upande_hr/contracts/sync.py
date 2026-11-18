# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe


def sync_employee(employee: str) -> None:
	"""Mirror the employee's latest live contract onto the Employee record."""
	latest = frappe.db.get_value(
		"Employee Contract",
		{"employee": employee, "docstatus": 1},
		["status", "end_date", "employment_type", "confirmation_date", "confirmed_employment_type"],
		order_by="contract_number desc, creation desc",
		as_dict=True,
	)
	if not latest:
		return

	if latest.status == "Confirmed":
		values = {
			"final_confirmation_date": latest.confirmation_date,
			"employment_type": latest.confirmed_employment_type,
			"contract_end_date": None,
		}
	else:
		values = {
			"contract_end_date": latest.end_date,
			"employment_type": latest.employment_type,
			"final_confirmation_date": None,
		}
	frappe.db.set_value("Employee", employee, values)
