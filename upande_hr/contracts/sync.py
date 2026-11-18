# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe


LATEST_ORDER = "end_date desc, contract_number desc, creation desc"


def get_latest_contract(employee: str) -> dict | None:
	"""The employee's current contract: the submitted one with the latest end date.

	contract_number can repeat (amend after cancel, abandoned drafts), so it is only a
	tie-breaker after end_date.
	"""
	rows = frappe.get_all(
		"Employee Contract",
		filters={"employee": employee, "docstatus": 1},
		fields=[
			"name", "status", "end_date", "employment_type", "confirmation_date",
			"confirmed_employment_type",
		],
		order_by=LATEST_ORDER,
		limit=1,
	)
	return rows[0] if rows else None


def sync_employee(employee: str, clear_confirmation: bool = False) -> None:
	"""Mirror the employee's latest live contract onto the Employee record.

	final_confirmation_date is only cleared when clear_confirmation is True (a Confirmed
	contract was just cancelled); otherwise a manually entered value is left alone.
	"""
	if clear_confirmation:
		frappe.db.set_value("Employee", employee, "final_confirmation_date", None)

	latest = get_latest_contract(employee)
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
		}
	frappe.db.set_value("Employee", employee, values)
