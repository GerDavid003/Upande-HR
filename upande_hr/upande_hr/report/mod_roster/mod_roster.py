# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""MOD Roster, laid out like HR's sheet: one block per week, a row per MOD, a column per
day, and an "On duty" count. Codes: D day, WD weekend duty, OFF MOD off, WO weekly off,
PH public holiday, L approved leave; * marks a day changed by a MOD Duty Swap; ! marks a day
no base holiday list covers (e.g. next year's list not created yet): the roster cannot be
applied there, and HRMS treats the day as a working day."""

import frappe
from frappe import _
from frappe.utils import add_days, add_months, formatdate, get_first_day, get_last_day, getdate, today

from upande_hr.attendance import mod_roster as mr

DAY_COLUMNS = [f"d{i}" for i in range(7)]
ON_DUTY_CODES = (mr.DAY, mr.DUTY)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	from_date = getdate(filters.from_date or get_first_day(today()))
	to_date = getdate(filters.to_date or get_last_day(add_months(today(), 1)))
	if from_date > to_date:
		frappe.throw(_("From Date must be on or before To Date."))
	if (to_date - from_date).days > 366:
		frappe.throw(_("Choose at most a year."))
	data, gaps = get_data(from_date, to_date, filters.group)
	return get_columns(), data, gap_message(gaps)


def get_columns():
	return [
		{"label": _("Group"), "fieldname": "group", "fieldtype": "Data", "width": 110},
		{
			"label": _("Employee"),
			"fieldname": "employee",
			"fieldtype": "Link",
			"options": "Employee",
			"width": 130,
		},
		{"label": _("Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 200},
		*[
			{"label": _(mr.WEEKDAYS[i][:3]), "fieldname": DAY_COLUMNS[i], "fieldtype": "Data", "width": 75}
			for i in range(7)
		],
	]


def get_data(from_date, to_date, group=None):
	roster = mr.Roster()
	memberships = [m for m in roster.memberships() if not group or m.group == group]
	on_leave = mr.approved_leave_days([m.employee for m in memberships], from_date, to_date)

	data = []
	gaps = {}  # (employee, name) -> [first, last] day with no base holiday list
	monday = add_days(from_date, -from_date.weekday())
	while monday <= to_date:
		days = [add_days(monday, i) for i in range(7)]
		in_range = [from_date <= d <= to_date for d in days]
		members = sorted(
			{
				(m.group, m.employee, m.employee_name)
				for m in memberships
				if any(
					ok and m.from_date <= d and (m.to_date is None or d <= m.to_date)
					for d, ok in zip(days, in_range, strict=True)
				)
			}
		)
		if members:
			header = {"employee_name": _("Week of {0}").format(formatdate(monday)), "is_header": 1}
			totals = {"employee_name": _("On duty"), "is_total": 1}
			rows = []
			for i, (d, ok) in enumerate(zip(days, in_range, strict=True)):
				header[DAY_COLUMNS[i]] = d.strftime("%d %b") if ok else ""
				totals[DAY_COLUMNS[i]] = 0 if ok else ""
			for group_name, employee, employee_name in members:
				row = {"group": group_name, "employee": employee, "employee_name": employee_name}
				for i, (d, ok) in enumerate(zip(days, in_range, strict=True)):
					text, no_base = cell(roster, employee, group_name, d, on_leave) if ok else ("", False)
					row[DAY_COLUMNS[i]] = text
					if no_base:
						span = gaps.setdefault((employee, employee_name), [d, d])
						span[0], span[1] = min(span[0], d), max(span[1], d)
					if text.rstrip("*!") in ON_DUTY_CODES:
						totals[DAY_COLUMNS[i]] += 1
				rows.append(row)
			data += [header, *rows, totals]
		monday = add_days(monday, 7)
	return data, gaps


def cell(roster, employee, group, day, on_leave) -> tuple[str, bool]:
	"""(cell text, True if no base holiday list covers the day)."""
	membership = roster.membership_on(employee, day)
	if not membership or membership.group != group:
		return "", False
	status = roster.day_status(employee, day)
	code = status.code
	if code in ON_DUTY_CODES and (employee, day) in on_leave:
		code = mr.LEAVE
	no_base = not status.base_list
	return code + ("*" if status.swapped else "") + ("!" if no_base else ""), no_base


def gap_message(gaps: dict) -> str | None:
	if not gaps:
		return None
	lines = "".join(
		"<li>{}</li>".format(
			_("{0} ({1}): {2} to {3}").format(
				frappe.bold(name or employee), employee, formatdate(first), formatdate(last)
			)
		)
		for (employee, name), (first, last) in sorted(gaps.items())
	)
	return "<p><b>{}</b> {}</p><ul>{}</ul>".format(
		_("No base holiday list covers the days marked !"),
		_(
			"The roster cannot be applied to them, so HRMS treats every one of them as a working day"
			" (OFF days included). Create the base holiday list for that period and set it on the"
			" Employee (or the company's assignment); the roster then builds the MOD list."
		),
		lines,
	)
