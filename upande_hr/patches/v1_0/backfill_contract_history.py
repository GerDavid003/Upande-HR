# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""One Contract History row for every employee who already has a contract on record.

Before this release the only contract field on Employee was the standard
contract_end_date. Where an employee has one but no Contract Start Date, the start is
taken to be date_of_joining, and the start date field is filled in too: without it the
next save would not find this row by its start date and would append a second one.

Writes go straight to the database rather than through doc.save(), so the backfill does
not re-run every Employee validation (shift rules, probation) across the whole table.
"""

import frappe

from upande_hr.setup.custom_fields import ensure_custom_fields

REMARKS_ASSUMED_START = "Backfilled. Start date assumed to be the date of joining."
REMARKS = "Backfilled from the existing contract dates."


def execute():
	ensure_custom_fields(
		[
			"Employee-custom_contract_type",
			"Employee-custom_contract_start_date",
			"Employee-custom_contract_history_section",
			"Employee-custom_contract_history",
		]
	)

	employees = frappe.db.sql(
		"""
		select e.name, e.date_of_joining, e.contract_end_date,
			e.custom_contract_type, e.custom_contract_start_date
		from `tabEmployee` e
		where (e.contract_end_date is not null or e.custom_contract_start_date is not null)
			and not exists (
				select 1 from `tabEmployee Contract History` h
				where h.parenttype = 'Employee' and h.parent = e.name
					and h.parentfield = 'custom_contract_history'
			)
		""",
		as_dict=True,
	)

	for employee in employees:
		start = employee.custom_contract_start_date or employee.date_of_joining
		if not start:
			continue

		if not employee.custom_contract_start_date:
			frappe.db.set_value(
				"Employee", employee.name, "custom_contract_start_date", start, update_modified=False
			)

		frappe.get_doc(
			{
				"doctype": "Employee Contract History",
				"parenttype": "Employee",
				"parent": employee.name,
				"parentfield": "custom_contract_history",
				"idx": 1,
				"contract_type": employee.custom_contract_type,
				"from_date": start,
				"to_date": employee.contract_end_date,
				"remarks": REMARKS if employee.custom_contract_start_date else REMARKS_ASSUMED_START,
			}
		).db_insert()
