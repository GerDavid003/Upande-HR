# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Monthly MOD Off allocation.

On the 1st of every month each active Employee with custom_is_mod ticked gets a
one-day Leave Allocation of the HR Settings.custom_mod_off_leave_type, running to the
last day of the month with no carry forward, so an unused day lapses at month end.

Opt-in per site through HR Settings.custom_enable_mod_off_allocation. Covers every
company on the site.

Notes on the Leave Allocation that gets created:

- HRMS rejects a from_date before the employee's joining date or a to_date after their
  relieving date, so the allocation is clamped to both. A MOD who joins mid-month gets
  that month's day from their joining date.
- A re-run finds the month's allocation and skips the employee, so the job is safe to
  run again after a scheduler outage.
- Leave Type.max_leaves_allowed is checked against everything allocated in the
  surrounding Leave Period, not per allocation. With a yearly Leave Period, a MOD Off
  Leave Type capped at 1 fails from the second month; leave it at 0 (or 12).
"""

import frappe
from frappe.utils import get_first_day, get_last_day, getdate, today

SETTINGS_FLAG = "custom_enable_mod_off_allocation"
SETTINGS_LEAVE_TYPE = "custom_mod_off_leave_type"
DAYS_PER_MONTH = 1


def run_monthly():
	"""Scheduler entry point - cron 1 0 1 * *."""
	if not frappe.db.get_single_value("HR Settings", SETTINGS_FLAG):
		return
	allocate_mod_off()


@frappe.whitelist()
def allocate_mod_off(month_of: str | None = None, employee: str | None = None) -> dict:
	"""Allocate MOD Off for the month containing `month_of` (default: this month).

	Callable by HR from the console or an API call to re-run a month or smoke-test one
	employee. A manual run deliberately ignores the HR Settings toggle: the toggle gates
	the schedule, not an explicit request from HR.
	"""
	frappe.only_for(("HR Manager", "System Manager"))

	leave_type = frappe.db.get_single_value("HR Settings", SETTINGS_LEAVE_TYPE)
	if not leave_type:
		frappe.log_error(
			title="MOD Off allocation skipped",
			message="HR Settings > MOD Off Leave Type is not set.",
		)
		return {}

	month_start = get_first_day(month_of or today())
	month_end = get_last_day(month_start)

	filters = {"custom_is_mod": 1, "status": "Active"}
	if employee:
		filters["name"] = employee
	mods = frappe.get_all(
		"Employee",
		filters=filters,
		fields=["name", "company", "date_of_joining", "relieving_date"],
	)

	summary = {"month": f"{month_start} to {month_end}", "allocated": [], "skipped": [], "failed": []}
	for mod in mods:
		from_date = max(month_start, getdate(mod.date_of_joining or month_start))
		to_date = min(month_end, getdate(mod.relieving_date or month_end))
		if from_date > to_date:
			summary["skipped"].append((mod.name, "not employed this month"))
			continue
		if has_allocation(mod.name, leave_type, month_start, month_end):
			summary["skipped"].append((mod.name, "already allocated"))
			continue

		savepoint = "mod_off_allocation"
		frappe.db.savepoint(savepoint)
		try:
			allocation = frappe.get_doc(
				{
					"doctype": "Leave Allocation",
					"employee": mod.name,
					"company": mod.company,
					"leave_type": leave_type,
					"from_date": from_date,
					"to_date": to_date,
					"new_leaves_allocated": DAYS_PER_MONTH,
					"carry_forward": 0,
				}
			)
			allocation.insert(ignore_permissions=True)
			allocation.submit()
			summary["allocated"].append((mod.name, allocation.name))
		except Exception:
			frappe.db.rollback(save_point=savepoint)
			frappe.log_error(
				title=f"MOD Off allocation failed: {mod.name} {month_start}",
				reference_doctype="Employee",
				reference_name=mod.name,
			)
			summary["failed"].append(mod.name)

	frappe.logger("upande_hr").info({"mod_off_allocation": summary})
	return summary


def has_allocation(employee: str, leave_type: str, month_start, month_end) -> bool:
	"""A submitted allocation of this type overlapping the month - HRMS would refuse a
	second one as overlapping anyway."""
	return bool(
		frappe.db.exists(
			"Leave Allocation",
			{
				"employee": employee,
				"leave_type": leave_type,
				"docstatus": 1,
				"from_date": ["<=", month_end],
				"to_date": [">=", month_start],
			},
		)
	)
