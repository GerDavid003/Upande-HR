# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""MOD Roster: Managers on Duty and their alternating duty weekday (Altura: Saturday).

Each MOD works the duty weekday on some weeks (WD) and has it off on the others (OFF),
following the rotation of their MOD Rotation Group, with one-off MOD Duty Swaps on top.
HRMS knows only holiday lists, so the roster is written into one Holiday List per MOD
per year ("MOD - <employee> - <year>") and assigned with Holiday List Assignments:

- the list is the employee's base list (see base_list) with the roster applied: an OFF
  duty day is a holiday described "MOD Off...", a WD duty day is a working day, and a
  public holiday in the base list always stays a holiday;
- auto-attendance, leave counting, payroll and the absent -> AL deduction all read the
  list through the assignment, so an OFF day is never marked Absent or deducted and a
  missed WD day is.

Rules:
- Holiday rows dated before the regeneration date (today, or a swap's own date) are never
  rewritten, and assignments are only ever created from today forward.
- The roster owns a MOD's employee-level Holiday List Assignments (custom_mod_roster = 1)
  while they are a member; any other assignment for an active MOD is refused (see
  validate_holiday_list_assignment). The base list is changed through
  Employee.holiday_list (or the company's assignment) instead.
- Lists are filled for whole years and next year's list is created as soon as the
  horizon (today + custom_mod_generate_weeks_ahead weeks) reaches it, provided a base
  list covers that year.
- Feature off: nothing is generated or guarded; existing lists are left as they are.

Base list for an employee on a date: the first of Employee.holiday_list, the latest
non-MOD employee assignment starting on or before the date, and the company's latest
assignment, whose own From/To dates cover the date.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, formatdate, get_link_to_form, getdate, today
from frappe.utils.user import get_users_with_role
from hrms.utils.holiday_list import get_holiday_list_for_employee

from upande_hr.attendance.absence_settings import get_stored

ENABLED = "custom_enable_mod_roster"
DUTY_WEEKDAY = "custom_mod_duty_weekday"
WEEKS_AHEAD = "custom_mod_generate_weeks_ahead"
MIN_ON_DUTY = "custom_mod_min_on_duty"
DEFAULTS = {DUTY_WEEKDAY: "Saturday", WEEKS_AHEAD: 8, MIN_ON_DUTY: 1}
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

GROUP = "MOD Rotation Group"
MEMBER = "MOD Rotation Member"
SWAP = "MOD Duty Swap"
HLA = "Holiday List Assignment"
ROSTER_FLAG = "custom_mod_roster"  # Holiday List Assignment, set on the ones we create
LIST_PREFIX = "MOD - "
MOD_OFF = "MOD Off"

# Day codes, as on HR's roster sheet
DAY = "D"
DUTY = "WD"
OFF = "OFF"
WEEKLY_OFF = "WO"
PUBLIC_HOLIDAY = "PH"
LEAVE = "L"


# --- settings ------------------------------------------------------------------------


def get_settings() -> frappe._dict:
	def value(fieldname):
		stored = get_stored(fieldname)
		return DEFAULTS.get(fieldname) if stored in (None, "") else stored

	duty_weekday = value(DUTY_WEEKDAY)
	if duty_weekday not in WEEKDAYS:
		duty_weekday = DEFAULTS[DUTY_WEEKDAY]
	return frappe._dict(
		enabled=cint(get_stored(ENABLED)),
		duty_weekday=duty_weekday,
		duty_weekday_index=WEEKDAYS.index(duty_weekday),
		weeks_ahead=max(cint(value(WEEKS_AHEAD)), 1),
		min_on_duty=max(cint(value(MIN_ON_DUTY)), 0),
	)


def seed_settings():
	"""Store the documented defaults once, so the HR Settings form shows them."""
	for fieldname, default in DEFAULTS.items():
		if get_stored(fieldname) in (None, ""):
			frappe.db.set_single_value("HR Settings", fieldname, default)


def validate_hr_settings(doc, method=None):
	"""doc_events HR Settings.validate."""
	duty_weekday = doc.get(DUTY_WEEKDAY) or DEFAULTS[DUTY_WEEKDAY]
	if doc.get(WEEKS_AHEAD) not in (None, "") and cint(doc.get(WEEKS_AHEAD)) < 1:
		frappe.throw(_("MOD Roster: Generate Weeks Ahead must be at least 1."))
	if cint(doc.get(MIN_ON_DUTY)) < 0:
		frappe.throw(_("MOD Roster: Minimum MODs on Duty cannot be negative."))

	clashing = [
		g.name
		for g in frappe.get_all(GROUP, filters={"is_active": 1}, fields=["name", "anchor_date"])
		if g.anchor_date and WEEKDAYS[getdate(g.anchor_date).weekday()] != duty_weekday
	]
	if clashing:
		frappe.throw(
			_("MOD Duty Weekday cannot be {0}: the Anchor Date of {1} is not a {0}.").format(
				_(duty_weekday), ", ".join(clashing)
			)
		)


# --- helpers ---------------------------------------------------------------------------


def is_mod_list(holiday_list: str | None) -> bool:
	return bool(holiday_list) and holiday_list.startswith(LIST_PREFIX)


def list_name(employee: str, year: int) -> str:
	return f"{LIST_PREFIX}{employee} - {year}"


def date_range(start, end):
	day = getdate(start)
	end = getdate(end)
	while day <= end:
		yield day
		day = add_days(day, 1)


def horizon_end(settings) -> object:
	return add_days(getdate(today()), 7 * settings.weeks_ahead)


def hr_managers() -> list[str]:
	return [u for u in get_users_with_role("HR Manager") if u not in ("Administrator", "Guest")]


class Roster:
	"""Read-only view of the roster with per-run caches."""

	def __init__(self, settings=None):
		self.settings = settings or get_settings()
		self.duty_weekday = self.settings.duty_weekday_index
		self._list_ranges = {}
		self._rows = {}
		self._employees = {}
		self._assignments = {}
		self._memberships = None
		self._swaps = None

	# memberships and rotation

	def memberships(self, employee: str | None = None) -> list:
		if self._memberships is None:
			Group = frappe.qb.DocType(GROUP)
			Member = frappe.qb.DocType(MEMBER)
			rows = (
				frappe.qb.from_(Member)
				.join(Group)
				.on(Group.name == Member.parent)
				.select(
					Member.employee,
					Member.employee_name,
					Member.from_date,
					Member.to_date,
					Group.name.as_("group"),
					Group.cycle_weeks,
					Group.duty_week,
					Group.anchor_date,
				)
				.where((Group.is_active == 1) & (Member.parenttype == GROUP))
				.orderby(Member.employee)
				.orderby(Member.from_date)
			).run(as_dict=True)
			for row in rows:
				row.from_date = getdate(row.from_date)
				row.to_date = getdate(row.to_date) if row.to_date else None
				row.anchor_date = getdate(row.anchor_date)
			self._memberships = rows
		if employee is None:
			return self._memberships
		return [m for m in self._memberships if m.employee == employee]

	def membership_on(self, employee: str, day):
		for m in self.memberships(employee):
			if m.from_date <= day and (m.to_date is None or day <= m.to_date):
				return m
		return None

	def is_member_between(self, employee: str, start, end) -> bool:
		return any(
			m.from_date <= end and (m.to_date is None or m.to_date >= start)
			for m in self.memberships(employee)
		)

	def employees(self) -> list[str]:
		return sorted({m.employee for m in self.memberships()})

	@staticmethod
	def rostered_on_duty(membership, day) -> bool:
		cycle = max(cint(membership.cycle_weeks), 1)
		week = ((day - membership.anchor_date).days // 7) % cycle + 1
		return week == cint(membership.duty_week)

	def swaps_on(self, day, exclude: str | None = None) -> list:
		if self._swaps is None:
			self._swaps = {}
			for swap in frappe.get_all(
				SWAP,
				filters={"docstatus": 1},
				fields=["name", "date", "off_employee", "cover_employee"],
				order_by="creation",
			):
				self._swaps.setdefault(getdate(swap.date), []).append(swap)
		return [s for s in self._swaps.get(day, []) if s.name != exclude]

	# holiday lists

	def employee(self, employee: str):
		if employee not in self._employees:
			self._employees[employee] = frappe.db.get_value(
				"Employee", employee, ["name", "employee_name", "holiday_list", "company"], as_dict=True
			) or frappe._dict(name=employee)
		return self._employees[employee]

	def assignments(self, assigned_to: str | None) -> list:
		if not assigned_to:
			return []
		if assigned_to not in self._assignments:
			rows = frappe.get_all(
				HLA,
				filters={"assigned_to": assigned_to, "docstatus": 1},
				fields=["name", "holiday_list", "from_date", ROSTER_FLAG, "applicable_for"],
				order_by="from_date asc, creation asc",
			)
			for row in rows:
				row.from_date = getdate(row.from_date)
			self._assignments[assigned_to] = rows
		return self._assignments[assigned_to]

	def forget_assignments(self, assigned_to: str):
		self._assignments.pop(assigned_to, None)

	def list_range(self, holiday_list: str | None):
		if not holiday_list:
			return None
		if holiday_list not in self._list_ranges:
			dates = frappe.db.get_value("Holiday List", holiday_list, ["from_date", "to_date"])
			self._list_ranges[holiday_list] = (getdate(dates[0]), getdate(dates[1])) if dates else None
		return self._list_ranges[holiday_list]

	def covers(self, holiday_list: str | None, day) -> bool:
		dates = self.list_range(holiday_list)
		return bool(dates) and dates[0] <= day <= dates[1]

	def rows(self, holiday_list: str | None) -> dict:
		if not holiday_list:
			return {}
		if holiday_list not in self._rows:
			self._rows[holiday_list] = {
				getdate(h.holiday_date): h
				for h in frappe.get_all(
					"Holiday",
					filters={"parent": holiday_list, "parenttype": "Holiday List"},
					fields=["holiday_date", "description", "weekly_off", "is_half_day"],
				)
			}
		return self._rows[holiday_list]

	def forget_list(self, holiday_list: str):
		self._rows.pop(holiday_list, None)
		self._list_ranges.pop(holiday_list, None)

	def base_list(self, employee: str, day) -> str | None:
		"""The list the employee would have on `day` without the roster (see module docstring)."""
		emp = self.employee(employee)
		if emp.holiday_list and not is_mod_list(emp.holiday_list) and self.covers(emp.holiday_list, day):
			return emp.holiday_list
		for assigned_to in (employee, emp.company):
			for a in reversed(self.assignments(assigned_to)):
				if (
					a.from_date <= day
					and not is_mod_list(a.holiday_list)
					and self.covers(a.holiday_list, day)
				):
					return a.holiday_list
		return None

	# the roster

	def day_status(self, employee: str, day, exclude_swap: str | None = None) -> frappe._dict:
		day = getdate(day)
		base = self.base_list(employee, day)
		base_row = self.rows(base).get(day) if base else None
		membership = self.membership_on(employee, day)
		status = frappe._dict(
			code=DAY, swapped=0, swap=None, membership=membership, base_list=base, base_row=base_row
		)

		if membership and day.weekday() == self.duty_weekday:
			if base_row and not cint(base_row.weekly_off):
				status.code = PUBLIC_HOLIDAY
				return status
			on_duty = self.rostered_on_duty(membership, day)
			for swap in self.swaps_on(day, exclude_swap):
				if swap.off_employee == employee:
					on_duty, status.swapped, status.swap = False, 1, swap.name
				elif swap.cover_employee == employee:
					on_duty, status.swapped, status.swap = True, 1, swap.name
			status.code = DUTY if on_duty else OFF
		elif base_row:
			status.code = WEEKLY_OFF if cint(base_row.weekly_off) else PUBLIC_HOLIDAY
		return status

	def holiday_row(self, employee: str, day) -> dict | None:
		"""The Holiday row the employee's MOD list should have on `day`, or None."""
		status = self.day_status(employee, day)
		if status.code == OFF:
			description = MOD_OFF + (f" (swap {status.swap})" if status.swap else "")
			return {"holiday_date": day, "description": description, "weekly_off": 0, "is_half_day": 0}
		if status.code in (WEEKLY_OFF, PUBLIC_HOLIDAY) and status.base_row:
			row = status.base_row
			return {
				"holiday_date": day,
				"description": row.description,
				"weekly_off": cint(row.weekly_off),
				"is_half_day": cint(row.is_half_day),
			}
		return None


# --- generation --------------------------------------------------------------------------


def regenerate(employees: list[str] | None = None, from_date=None) -> frappe._dict:
	"""Bring the MOD lists and assignments up to date from `from_date` (default today).

	Holiday rows before `from_date` are never touched; assignments are only created or
	cancelled from today forward. Returns what was done and what needs HR's attention.
	"""
	result = frappe._dict(
		employees=[], lists=[], assignments=[], cancelled=[], late_off=[], problems=[], cover=[]
	)
	settings = get_settings()
	if not settings.enabled:
		result.skipped = _("MOD Roster is switched off in HR Settings.")
		return result

	roster = Roster(settings)
	start = getdate(from_date or today())
	end = getdate(f"{horizon_end(settings).year}-12-31")

	if employees is None:
		employees = sorted(set(roster.employees()) | set(employees_on_mod_lists()))

	frappe.flags.in_mod_roster = True
	try:
		for employee in employees:
			savepoint = "mod_roster_employee"
			frappe.db.savepoint(savepoint)
			try:
				sync_employee(roster, employee, start, end, result)
				result.employees.append(employee)
			except Exception:
				frappe.db.rollback(save_point=savepoint)
				frappe.log_error(title=f"MOD Roster: regeneration failed for {employee}")
				result.problems.append(
					_("{0}: regeneration failed, see the Error Log.").format(employee_label(roster, employee))
				)
	finally:
		frappe.flags.in_mod_roster = False

	flag_late_off_days(result.late_off)
	result.cover = cover_warnings(Roster(settings))
	return result


def employees_on_mod_lists() -> list[str]:
	"""Employees with a roster-managed list assigned, so a removed member is put back."""
	return frappe.get_all(
		HLA,
		filters={"docstatus": 1, "applicable_for": "Employee", "holiday_list": ["like", f"{LIST_PREFIX}%"]},
		pluck="assigned_to",
		distinct=True,
	)


def employee_label(roster, employee) -> str:
	name = roster.employee(employee).employee_name
	return f"{employee} ({name})" if name else employee


def sync_employee(roster, employee, start, end, result):
	for year in range(start.year, end.year + 1):
		year_start = max(start, getdate(f"{year}-01-01"))
		year_end = getdate(f"{year}-12-31")
		name = list_name(employee, year)
		if not roster.is_member_between(employee, year_start, year_end) and not frappe.db.exists(
			"Holiday List", name
		):
			continue
		if not roster.base_list(employee, year_start):
			if year > getdate(today()).year:
				continue  # reported from 1 December by next_year_problems()
			result.problems.append(
				_("{0}: no base holiday list covers {1}, so the {2} MOD list was not built.").format(
					employee_label(roster, employee), formatdate(year_start), year
				)
			)
			continue
		sync_list(roster, employee, year, year_start, result)

	sync_assignments(roster, employee, max(start, getdate(today())), end, result)


def sync_list(roster, employee, year, from_date, result):
	"""Write the roster into the employee's list for `year` from `from_date` on."""
	name = list_name(employee, year)
	if frappe.db.exists("Holiday List", name):
		doc = frappe.get_doc("Holiday List", name)
	else:
		doc = frappe.new_doc("Holiday List")
		doc.holiday_list_name = name
		doc.from_date = f"{year}-01-01"
		doc.to_date = f"{year}-12-31"
		from_date = getdate(doc.from_date)  # a new list is filled for the whole year

	is_new = doc.is_new()
	old = {getdate(h.holiday_date): h.as_dict() for h in doc.holidays}
	kept = [h for d, h in old.items() if d < from_date]
	new = [
		row
		for day in date_range(from_date, getdate(f"{year}-12-31"))
		if (row := roster.holiday_row(employee, day))
	]

	def key(row):
		row = frappe._dict(row)
		return (getdate(row.holiday_date), row.description, cint(row.weekly_off), cint(row.is_half_day))

	current = [h for d, h in old.items() if d >= from_date]
	if not is_new and sorted(map(key, current)) == sorted(map(key, new)):
		return

	doc.set("holidays", [])
	for h in kept:
		doc.append(
			"holidays",
			{
				"holiday_date": h.holiday_date,
				"description": h.description,
				"weekly_off": h.weekly_off,
				"is_half_day": h.is_half_day,
			},
		)
	for row in new:
		doc.append("holidays", row)

	# A past day newly OFF (only a late swap can do that) may already have been deducted
	# as an absence. Only days this list was actually in force for count.
	past_end = add_days(getdate(today()), -1)
	for row in [] if is_new else new:
		day = getdate(row["holiday_date"])
		if (
			day <= past_end
			and row["description"].startswith(MOD_OFF)
			and get_holiday_list_for_employee(employee, raise_exception=False, as_on=day) == name
		):
			before = old.get(day)
			if not before or not (before.description or "").startswith(MOD_OFF):
				result.late_off.append((employee, day, row["description"]))

	doc.flags.ignore_permissions = True
	doc.save()
	roster.forget_list(name)
	result.lists.append(name)


def sync_assignments(roster, employee, start, end, result):
	"""Make the assignments from `start` on point at the MOD list while the employee is a
	member, and back at the base list when they are not.

	Only roster-created assignments (custom_mod_roster = 1) starting on or after `start`
	are ever cancelled. Everything before `start` is left exactly as it is.
	"""
	existing = roster.assignments(employee)
	fixed = [a for a in existing if a.from_date < start or not cint(a.get(ROSTER_FLAG))]
	ours_ahead = {a.from_date: a for a in existing if a.from_date >= start and cint(a.get(ROSTER_FLAG))}
	fixed_dates = {a.from_date: a for a in fixed}
	planned = {}

	def effective(day):
		best = None
		for a in fixed:
			if a.from_date <= day and (best is None or a.from_date >= best[0]):
				best = (a.from_date, a.holiday_list)
		for d, holiday_list in planned.items():
			if d <= day and (best is None or d >= best[0]):
				best = (d, holiday_list)
		return best[1] if best else None

	for day in date_range(start, end):
		membership = roster.membership_on(employee, day)
		if membership:
			want = list_name(employee, day.year)
			if not frappe.db.exists("Holiday List", want):
				break  # reported by sync_employee; nothing can be assigned from here
			if effective(day) == want:
				continue
		else:
			if not is_mod_list(effective(day)):
				continue
			want = roster.base_list(employee, day)
			if not want:
				result.problems.append(
					_("{0}: no base holiday list covers {1}, so the MOD list stays assigned.").format(
						employee_label(roster, employee), formatdate(day)
					)
				)
				break

		clash = fixed_dates.get(day)
		if clash:
			result.problems.append(
				_(
					"{0}: Holiday List Assignment {1} from {2} conflicts with the roster; cancel it and set the base list on the Employee instead."
				).format(employee_label(roster, employee), clash.name, formatdate(day))
			)
			continue
		planned[day] = want

	for day, assignment in ours_ahead.items():
		if planned.get(day) == assignment.holiday_list:
			planned.pop(day)
			continue
		doc = frappe.get_doc(HLA, assignment.name)
		doc.flags.ignore_permissions = True
		doc.cancel()
		result.cancelled.append(assignment.name)

	created_mod_dates = []
	for day, holiday_list in sorted(planned.items()):
		result.assignments.append(make_assignment(employee, holiday_list, day))
		if is_mod_list(holiday_list):
			created_mod_dates.append(day)

	if created_mod_dates:
		backfill_base_assignment(roster, employee, min(created_mod_dates), result)
	roster.forget_assignments(employee)


def make_assignment(employee, holiday_list, from_date) -> str:
	doc = frappe.get_doc(
		{
			"doctype": HLA,
			"applicable_for": "Employee",
			"assigned_to": employee,
			"holiday_list": holiday_list,
			"from_date": from_date,
			ROSTER_FLAG: 1,
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	return doc.name


def backfill_base_assignment(roster, employee, first_mod_date, result):
	"""HRMS falls back to an employee's *earliest* assignment for dates before all of
	them. Without an earlier assignment, the MOD list would apply retroactively; an
	assignment of the base list from its own start keeps earlier dates on the base."""
	if any(a.from_date < first_mod_date for a in roster.assignments(employee)):
		return
	emp = roster.employee(employee)
	if any(a.from_date < first_mod_date for a in roster.assignments(emp.company)):
		return  # the company's assignment already covers earlier dates
	base = roster.base_list(employee, add_days(first_mod_date, -1))
	if not base:
		return
	base_start = roster.list_range(base)[0]
	if base_start < first_mod_date:
		result.assignments.append(make_assignment(employee, base, base_start))


# --- late OFF days over deducted absences -------------------------------------------------


def flag_late_off_days(late_off: list):
	"""A swap that turns a past day into OFF never touches a leave already deducted for
	it. The deduction row is annotated and HR is emailed so they can cancel the leave."""
	from upande_hr.upande_hr.doctype.absence_leave_deduction.absence_leave_deduction import make_name

	flagged = []
	for employee, day, description in late_off:
		name = make_name(employee, day)
		if frappe.db.get_value("Absence Leave Deduction", name, "status") != "Deducted":
			continue
		note = _(
			"{0} on {1} is now a MOD Off day ({2}). The deducted leave was left as it is; cancel {3} if the day should not be charged."
		).format(
			employee,
			formatdate(day),
			description,
			frappe.db.get_value("Absence Leave Deduction", name, "leave_application"),
		)
		doc = frappe.get_doc("Absence Leave Deduction", name)
		doc.db_set({"mod_roster_conflict": 1, "mod_roster_note": note})
		doc.add_comment("Info", note)
		flagged.append(frappe._dict(name=name, note=note))

	if not flagged:
		return
	recipients = hr_managers()
	if not recipients:
		frappe.log_error(title="MOD Roster: no HR Manager to tell about deducted MOD Off days")
		return
	frappe.sendmail(
		recipients=recipients,
		subject=_("MOD Roster: {0} deducted absence(s) now fall on a MOD Off day").format(len(flagged)),
		message="<p>{0}</p><ul>{1}</ul>".format(
			_("A late duty swap made these past days MOD Off. The leave deducted for them was not touched:"),
			"".join(
				f"<li>{get_link_to_form('Absence Leave Deduction', f.name)}: {frappe.utils.escape_html(f.note)}</li>"
				for f in flagged
			),
		),
	)


# --- cover ----------------------------------------------------------------------------


def cover_warnings(roster=None) -> list:
	"""Duty days in the coming weeks with fewer MODs on duty than the minimum."""
	roster = roster or Roster()
	settings = roster.settings
	start = getdate(today())
	end = horizon_end(settings)
	on_leave = approved_leave_days([m.employee for m in roster.memberships()], start, end)

	warnings = []
	for day in date_range(start, end):
		if day.weekday() != roster.duty_weekday:
			continue
		employees = sorted(
			{m.employee for m in roster.memberships() if roster.membership_on(m.employee, day)}
		)
		if not employees:
			continue
		statuses = {e: roster.day_status(e, day) for e in employees}
		if all(s.code == PUBLIC_HOLIDAY for s in statuses.values()):
			continue
		on_duty = [e for e, s in statuses.items() if s.code == DUTY and (e, day) not in on_leave]
		if len(on_duty) < settings.min_on_duty:
			warnings.append(
				frappe._dict(
					date=day,
					on_duty=len(on_duty),
					minimum=settings.min_on_duty,
					names=", ".join(roster.employee(e).employee_name or e for e in on_duty) or _("nobody"),
				)
			)
	return warnings


def approved_leave_days(employees: list[str], start, end) -> set:
	if not employees:
		return set()
	days = set()
	for leave in frappe.get_all(
		"Leave Application",
		filters={
			"employee": ["in", list(set(employees))],
			"docstatus": 1,
			"status": "Approved",
			"from_date": ["<=", end],
			"to_date": [">=", start],
		},
		fields=["employee", "from_date", "to_date"],
	):
		for day in date_range(
			max(getdate(leave.from_date), getdate(start)), min(getdate(leave.to_date), getdate(end))
		):
			days.add((leave.employee, day))
	return days


def cover_message(warnings: list) -> str:
	return "<br>".join(
		_("{0}: {1} on duty ({2}), minimum {3}").format(formatdate(w.date), w.on_duty, w.names, w.minimum)
		for w in warnings
	)


# --- scheduler --------------------------------------------------------------------------


def run_daily():
	"""Scheduler, daily: extend the lists, then tell HR what needs attention."""
	if not get_settings().enabled:
		return
	result = regenerate()
	problems = list(result.problems) + next_year_problems()
	send_attention_email(result.cover, problems)


def next_year_problems() -> list:
	"""From 1 December: members still on the roster on 1 January whose base list does not
	cover next year (HRMS would treat every day of it as a working day)."""
	now = getdate(today())
	if now.month != 12:
		return []
	roster = Roster()
	new_year = getdate(f"{now.year + 1}-01-01")
	return [
		_(
			"{0}: no base holiday list covers {1}. Create next year's list and set it on the Employee (or the company's assignment) before 1 January."
		).format(employee_label(roster, employee), now.year + 1)
		for employee in roster.employees()
		if roster.membership_on(employee, new_year) and not roster.base_list(employee, new_year)
	]


def send_attention_email(cover: list, problems: list):
	if not cover and not problems:
		return
	recipients = hr_managers()
	if not recipients:
		frappe.log_error(title="MOD Roster: no HR Manager to send the daily summary to")
		return
	parts = []
	if cover:
		parts.append(
			"<p><b>{0}</b></p><ul>{1}</ul>".format(
				_("Duty days below the minimum number of MODs on duty:"),
				"".join(
					"<li>{0}</li>".format(
						_("{0}: {1} on duty ({2}), minimum {3}").format(
							formatdate(w.date), w.on_duty, frappe.utils.escape_html(w.names), w.minimum
						)
					)
					for w in cover
				),
			)
		)
	if problems:
		parts.append(
			"<p><b>{0}</b></p><ul>{1}</ul>".format(
				_("Needs attention:"), "".join(f"<li>{frappe.utils.escape_html(p)}</li>" for p in problems)
			)
		)
	frappe.sendmail(
		recipients=recipients,
		subject=_("MOD Roster: {0} item(s) need attention").format(len(cover) + len(problems)),
		message="".join(parts),
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def member_query(doctype, txt, searchfield, start, page_len, filters):
	"""Employee link query on MOD Duty Swap: members of active groups only."""
	Group = frappe.qb.DocType(GROUP)
	Member = frappe.qb.DocType(MEMBER)
	return (
		frappe.qb.from_(Member)
		.join(Group)
		.on(Group.name == Member.parent)
		.select(Member.employee, Member.employee_name, Group.name)
		.distinct()
		.where(
			(Group.is_active == 1)
			& (Member.parenttype == GROUP)
			& (Member.employee.like(f"%{txt}%") | Member.employee_name.like(f"%{txt}%"))
		)
		.orderby(Member.employee_name)
		.limit(page_len)
		.offset(start)
	).run()


@frappe.whitelist()
def regenerate_now() -> dict:
	"""HR Manager: regenerate every MOD list now (what the daily job does), and return the
	result instead of emailing it."""
	frappe.only_for(("HR Manager", "System Manager"))
	result = regenerate()
	result.problems = list(result.problems) + next_year_problems()
	return result


# --- doc_events -----------------------------------------------------------------------------


def validate_holiday_list_assignment(doc, method=None):
	"""doc_events Holiday List Assignment.validate: the roster owns an active MOD's
	employee-level assignments. Bulk Week Off logs this error instead of failing."""
	if cint(doc.get(ROSTER_FLAG)) and frappe.flags.in_mod_roster:
		return
	if cint(doc.get(ROSTER_FLAG)):
		frappe.throw(_("Only the MOD Roster creates assignments marked as MOD Roster."))
	if not get_settings().enabled or doc.applicable_for != "Employee":
		return
	if is_mod_list(doc.holiday_list):
		frappe.throw(_("MOD holiday lists are assigned by the MOD Roster only."))

	from_date = getdate(doc.from_date)
	roster = Roster()
	membership = next(
		(m for m in roster.memberships(doc.assigned_to) if m.to_date is None or m.to_date >= from_date),
		None,
	)
	if membership:
		frappe.throw(
			_(
				"{0} is on the MOD roster ({1}), which manages their holiday list assignments. To change their base holiday list, set Holiday List on the Employee instead; the roster picks it up from today."
			).format(frappe.bold(doc.assigned_to), get_link_to_form(GROUP, membership.group)),
			title=_("Managed by MOD Roster"),
		)


def on_holiday_list_update(doc, method=None):
	"""doc_events Holiday List.on_update: a base list changed (e.g. a public holiday was
	added), so the MOD lists built from it are refreshed from today."""
	if frappe.flags.in_mod_roster or is_mod_list(doc.name) or not get_settings().enabled:
		return
	roster = Roster()
	affected = [
		e
		for e in roster.employees()
		if roster.employee(e).holiday_list == doc.name
		or any(a.holiday_list == doc.name for a in roster.assignments(e))
		or any(a.holiday_list == doc.name for a in roster.assignments(roster.employee(e).company))
	]
	if affected:
		frappe.enqueue(
			"upande_hr.attendance.mod_roster.regenerate",
			employees=affected,
			enqueue_after_commit=True,
			now=frappe.in_test,
		)


def on_employee_update(doc, method=None):
	"""doc_events Employee.on_update: Employee.holiday_list is a MOD's base pointer."""
	if not doc.has_value_changed("holiday_list") or not get_settings().enabled:
		return
	if frappe.get_all(MEMBER, filters={"employee": doc.name, "parenttype": GROUP}, limit=1):
		frappe.enqueue(
			"upande_hr.attendance.mod_roster.regenerate",
			employees=[doc.name],
			enqueue_after_commit=True,
			now=frappe.in_test,
		)


# --- Altura's current roster ------------------------------------------------------------------

ALTURA_GROUPS = (
	{
		"group_name": "MOD Group 1",
		"anchor_date": "2026-11-07",
		"members": ("Philip Musonye Asenabi", "Olger Nyabisi Nyakundi"),
	},
	{
		"group_name": "MOD Group 2",
		"anchor_date": "2026-10-31",
		"members": ("Yvonne Lucy Anyango Omondi",),
	},
)


@frappe.whitelist()
def seed_altura_mod_groups(dry_run: int = 1, from_date: str | None = None) -> dict:
	"""Create Altura's two MOD Rotation Groups (cycle 2, duty week 1). dry_run=1 writes
	nothing and returns what would be created. Employees are looked up by full name."""
	frappe.only_for(("HR Manager", "System Manager"))
	dry_run = cint(dry_run)
	from_date = str(getdate(from_date or today()))
	plan, problems = [], []

	for spec in ALTURA_GROUPS:
		members = []
		for full_name in spec["members"]:
			found = frappe.get_all(
				"Employee",
				filters={"employee_name": full_name, "status": "Active"},
				fields=["name", "employee_name"],
			)
			if len(found) != 1:
				problems.append(_("{0}: {1} active employees with this name.").format(full_name, len(found)))
				continue
			members.append(
				{"employee": found[0].name, "employee_name": found[0].employee_name, "from_date": from_date}
			)

		exists = frappe.db.exists(GROUP, spec["group_name"])
		plan.append(
			{
				"group_name": spec["group_name"],
				"cycle_weeks": 2,
				"duty_week": 1,
				"anchor_date": spec["anchor_date"],
				"members": members,
				"action": _("exists, left as it is") if exists else _("create"),
			}
		)

	if not dry_run:
		if problems:
			frappe.throw("<br>".join(problems), title=_("Nothing was created"))
		for group in plan:
			if frappe.db.exists(GROUP, group["group_name"]):
				continue
			doc = frappe.get_doc(
				{
					"doctype": GROUP,
					"group_name": group["group_name"],
					"is_active": 1,
					"cycle_weeks": group["cycle_weeks"],
					"duty_week": group["duty_week"],
					"anchor_date": group["anchor_date"],
					"members": [
						{"employee": m["employee"], "from_date": m["from_date"]} for m in group["members"]
					],
				}
			)
			doc.insert()
			group["action"] = _("created")

	return {"dry_run": dry_run, "groups": plan, "problems": problems}
