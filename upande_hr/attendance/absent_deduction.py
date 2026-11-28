# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Weekly Absent -> Annual Leave deduction.

Every Sunday night each Attendance marked Absent in the last two weeks (never before
Deduct From) is checked against the ways an absence can be excused. An unexcused day is covered by a one-day
Annual Leave Application, created and submitted directly at Approved with
custom_auto_deducted = 1, and the employee is emailed.

Opt-in per site through HR Settings.custom_enable_absent_al_deduction.

Absences come from Attendance only (status Absent, submitted). Days with no Attendance
record at all are not looked for: marking them Absent is auto-attendance's job.

Altura additions (settings in absence_settings.py, all on the HR Settings Upande tab):

- Only employees whose grade is in custom_absence_deduction_grades (empty = everyone),
  never anyone in custom_absence_deduction_exempt_employees, only on or after
  custom_absence_deduction_start_date and the employee's date_of_joining.
- Outage guard: when more than half of the eligible employees are Absent on one date,
  nobody is deducted for that date. Each of those days is Flagged and goes to HR in the
  summary. This catches a device or sync failure that makes auto-attendance mark
  everyone Absent.
- Check-ins are looked for within the employee's shift on that day (start minus early
  allowance to end plus late allowance), so a night shift's OUT after midnight belongs
  to the right day. With no shift the calendar day is used, as on TSH.
- custom_single_scan_counts_as_absent: off, any check-in excuses the day (TSH); on, only
  a complete set does. What "complete" means follows the shift's "Determine Check-in and
  Check-out": Strictly based on Log Type needs an IN and an OUT (an IN without an OUT is
  a single scan); Alternating entries needs an even, non-zero count (an odd count leaves
  the last scan unpaired). With no shift, an IN and an OUT, or two or more untyped scans.
- Every employee-date handled is written to Absence Leave Deduction, whose name is
  employee + date: a day is deducted at most once, ever. Cancelling the Leave
  Application marks the row Reversed and the day is never deducted again.
- Balance below one day: if the Leave Type allows a negative balance the day is deducted
  anyway and the balance goes negative (TSH parity). Otherwise the insufficient-balance
  setting decides: Skip and flag (row Flagged, nothing deducted) or Leave Without Pay
  (the day is booked against the LWP Leave Type instead).
- run_absence_deduction() runs any date range, with a dry run that writes nothing.
- The scheduled run does not work out "this week" from the date it runs on: the scheduler
  starts a 23:59 Sunday job at Monday 00:00 often enough (Altura, 23 Nov 2026), and that
  skipped every week. It covers CATCH_UP_DAYS back to the day that has just ended (see
  get_catch_up_window), so a late start, a missed week or a Monday start all land on the
  right days. The log's employee + date name keeps a re-covered day from being deducted
  twice; a day already Flagged to HR is left for HR rather than re-flagged every run.
- Holidays are read exactly as auto-attendance reads them (get_holiday_list): the shift's
  own Holiday List if it has one, else the employee's assignment on that date. MOD Roster
  lists (mod_roster.py) reach this through the assignment, so a MOD's OFF duty day is
  excused and a missed WD day is deducted.

Notes on the Leave Application that gets created:

- Leave Application runs the "Leave Approval Workflow", which only allows Draft as an
  entry state. The deduction is not a request anyone approves, so the workflow check is
  skipped for these documents only, by a subclass of whatever controller the site
  resolves for Leave Application (so a later override_doctype_class is still honoured).
  The same subclass skips "Leave Approver is mandatory" when neither the employee nor
  their department has a leave approver.
- Annual Leave has allow_negative set on TSH and on Altura, so an exhausted balance only
  warns and the debt carries forward. The "Annual Leave Negative Limit" Server Script fires on
  "Awaiting..." states only and does not see these.
- On submit HRMS flips the day's Attendance from Absent to On Leave, so a re-run of the
  same week finds nothing left to deduct. The Absence Leave Deduction row keeps the link
  to that Attendance, which is how the day stays identifiable as an absence.
"""

from datetime import timedelta

import frappe
from frappe import _
from frappe.model.base_document import get_controller
from frappe.query_builder.functions import Count
from frappe.utils import (
	add_days,
	cint,
	flt,
	formatdate,
	get_datetime,
	getdate,
	now_datetime,
	to_timedelta,
	today,
)
from hrms.hr.doctype.leave_application.leave_application import (
	get_employee_leave_approver,
	get_leave_balance_on,
)
from hrms.hr.doctype.shift_assignment.shift_assignment import get_shift_details
from hrms.utils.holiday_list import get_holiday_list_for_employee

from upande_hr.attendance.absence_email_templates import (
	EMPLOYEE_TEMPLATE,
	HR_SUMMARY_TEMPLATE,
	render,
)
from upande_hr.attendance.absence_settings import LEAVE_WITHOUT_PAY, get_settings
from upande_hr.upande_hr.doctype.absence_leave_deduction.absence_leave_deduction import make_name

SETTINGS_FLAG = "custom_enable_absent_al_deduction"
AUTO_FLAG = "custom_auto_deducted"
LEAVE_TYPE = "Annual Leave"
APPROVED = "Approved"
LOG = "Absence Leave Deduction"

# Absence Leave Deduction.status
DEDUCTED = "Deducted"
FLAGGED = "Flagged"
REVERSED = "Reversed"
ERROR = "Error"

# Actions reported per employee-date (dry run and real run alike)
ACTION_DEDUCT = "Deduct"
ACTION_LWP = "Leave Without Pay"
ACTION_FLAG = "Flag"
ACTION_EXCUSED = "Excused"
ACTION_DONE = "Already processed"

# How the day's check-ins look, within the shift window
NO_SCAN = "no clock-in or clock-out recorded"
IN_ONLY = "a clock-in but no clock-out recorded"
OUT_ONLY = "a clock-out but no clock-in recorded"
SINGLE_SCAN = "a single scan recorded"
UNPAIRED_SCANS = "{0} scans recorded (an odd number, so the last one is unpaired)"
UNTYPED_SCANS = "scans recorded without an IN or OUT log type"
FULL_SCAN = "clock-in and clock-out recorded"

# Shift Type.determine_check_in_and_check_out. HRMS treats anything but STRICT as
# alternating, including an empty value.
STRICT = "Strictly based on Log Type in Employee Checkin"

# Outage guard: more than this share of the eligible employees Absent on one date means
# the attendance itself is suspect, so nobody is deducted for that date.
OUTAGE_SHARE = 0.5

# Scheduled run: how far back each run looks, and how close to midnight a run must be for
# the day it runs on to count as finished (so the 23:59 Sunday run includes Sunday).
CATCH_UP_DAYS = 14
DAY_END_GRACE = timedelta(hours=1)


def run_weekly():
	"""Scheduler entry point - cron 59 23 * * 0."""
	if not frappe.db.get_single_value("HR Settings", SETTINGS_FLAG):
		return
	deduct_recent_absences()


def get_catch_up_window(now=None, start_date=None) -> tuple:
	"""(from_date, to_date) for a scheduled run at `now`.

	to_date is the last day that has ended: yesterday, or today when the run is within
	DAY_END_GRACE of midnight (the 23:59 Sunday run). from_date is CATCH_UP_DAYS before
	today, never before Deduct From. from_date > to_date when Deduct From is in the future.
	"""
	now = get_datetime(now or now_datetime())
	to_date = add_days(getdate(now + DAY_END_GRACE), -1)
	from_date = add_days(getdate(now), -CATCH_UP_DAYS)
	if start_date:
		from_date = max(from_date, getdate(start_date))
	return from_date, to_date


def deduct_recent_absences(now=None) -> dict | None:
	"""The scheduled run: every not-yet-handled Absent day in the catch-up window."""
	from_date, to_date = get_catch_up_window(now, get_settings().start_date)
	if from_date > to_date:
		return None
	result = _run(from_date, to_date, dry_run=False, skip_flagged=True)
	return log_summary(result)


@frappe.whitelist()
def deduct_unexcused_absences(week_of: str | None = None, employee: str | None = None) -> dict:
	"""Deduct for the Monday-Sunday week containing `week_of` (default: this week).

	Callable by HR from the console or an API call to re-run a week or smoke-test one
	employee. A manual run deliberately ignores the HR Settings toggle: the toggle gates
	the schedule, not an explicit request from HR. The start date still applies.
	"""
	frappe.only_for(("HR Manager", "System Manager"))

	week_start, week_end = get_week(week_of)
	result = _run(week_start, week_end, dry_run=False, employee=employee)
	return log_summary(result)


def log_summary(result: dict) -> dict:
	def pick(*actions):
		return [
			(r.employee, str(r.absence_date), r.leave_application or r.reason)
			for r in result["rows"]
			if r.action in actions and r.status != ERROR
		]

	summary = {
		"week": f"{result['from_date']} to {result['to_date']}",
		"deducted": pick(ACTION_DEDUCT, ACTION_LWP),
		"excused": pick(ACTION_EXCUSED, ACTION_DONE),
		"flagged": pick(ACTION_FLAG),
		"failed": [(r.employee, str(r.absence_date)) for r in result["rows"] if r.status == ERROR],
	}
	frappe.logger("upande_hr").info({"absent_al_deduction": summary})
	return summary


@frappe.whitelist()
def run_absence_deduction(
	from_date: str, to_date: str, dry_run: int = 1, employee: str | None = None
) -> dict:
	"""Run the deduction over any date range. dry_run=1 (default) writes nothing.

	Returns one row per Absent employee-date: the reason, the leave balance and the
	action taken (or that would be taken). Same logic as the weekly job.
	"""
	frappe.only_for(("HR Manager", "System Manager"))
	return _run(getdate(from_date), getdate(to_date), dry_run=cint(dry_run), employee=employee)


def _run(from_date, to_date, dry_run: bool, employee: str | None = None, skip_flagged: bool = False) -> dict:
	settings = get_settings()
	if not dry_run and not settings.start_date:
		frappe.throw(_("Set Deduct From on HR Settings > Upande before running the deduction."))
	if from_date > to_date:
		frappe.throw(_("From Date must be on or before To Date."))

	absences = get_absences(from_date, to_date, settings, employee)
	# Counted over the whole eligible population even for a one-employee run, so that
	# re-running a single employee cannot get round the guard.
	outages = get_outages({getdate(a.attendance_date) for a in absences}, settings)
	if skip_flagged:
		# Already reported to HR by an earlier run; only an explicit run re-checks them.
		absences = [a for a in absences if not is_flagged(a)]

	rows = []
	for absence in absences:
		rows.append(process_absence(absence, settings, dry_run, outages))

	if not dry_run:
		send_hr_summary([r for r in rows if r.status in (FLAGGED, ERROR)], from_date, to_date, outages)

	counts = {}
	for row in rows:
		key = row.status if row.status == ERROR else row.action
		counts[key] = counts.get(key, 0) + 1

	return {
		"from_date": str(from_date),
		"to_date": str(to_date),
		"dry_run": cint(dry_run),
		"settings": {
			"grades": settings.grades or _("All employees"),
			"exempt_employees": settings.exempt_employees,
			"leave_type": settings.leave_type,
			"start_date": str(settings.start_date or ""),
			"single_scan_counts_as_absent": settings.single_scan_counts_as_absent,
			"on_insufficient_balance": settings.on_insufficient_balance,
		},
		"counts": counts,
		"outage_dates": {
			str(date): f"{absent} of {eligible}" for date, (absent, eligible) in outages.items()
		},
		"rows": rows,
	}


def is_flagged(absence) -> bool:
	return frappe.db.get_value(LOG, make_name(absence.employee, absence.attendance_date), "status") == FLAGGED


def get_week(week_of: str | None) -> tuple:
	day = getdate(week_of or today())
	monday = add_days(day, -day.weekday())
	return monday, add_days(monday, 6)


def get_absences(from_date, to_date, settings, employee: str | None = None) -> list:
	"""Submitted Absent Attendance in range, for the configured grades, never before the
	start date or the employee's date of joining."""
	Attendance = frappe.qb.DocType("Attendance")
	Employee = frappe.qb.DocType("Employee")

	query = (
		frappe.qb.from_(Attendance)
		.join(Employee)
		.on(Employee.name == Attendance.employee)
		.select(
			Attendance.name,
			Attendance.employee,
			Attendance.employee_name,
			Attendance.attendance_date,
			Attendance.company,
			Attendance.shift,
		)
		.where(
			(Attendance.status == "Absent")
			& (Attendance.docstatus == 1)
			& (Attendance.attendance_date[from_date:to_date])
			& (Employee.date_of_joining.isnull() | (Attendance.attendance_date >= Employee.date_of_joining))
		)
		.orderby(Attendance.employee)
		.orderby(Attendance.attendance_date)
	)
	if settings.grades:
		query = query.where(Employee.grade.isin(settings.grades))
	if settings.exempt_employees:
		query = query.where(Attendance.employee.notin(settings.exempt_employees))
	if settings.start_date:
		query = query.where(Attendance.attendance_date >= settings.start_date)
	if employee:
		query = query.where(Attendance.employee == employee)

	return query.run(as_dict=True)


def get_outages(dates, settings) -> dict:
	"""{date: (absent, eligible)} for each date where more than OUTAGE_SHARE of the
	eligible employees are Absent.

	Eligible on a date: in a configured grade (or any, if none are set), not exempt,
	joined on or before the date and not relieved before it. Absent: submitted Absent
	Attendance on that date, before any excuse is looked at, since a sync failure loses
	the check-ins too.
	"""
	outages = {}
	for date in sorted(dates):
		Employee = frappe.qb.DocType("Employee")
		Attendance = frappe.qb.DocType("Attendance")

		def scoped(query):
			query = query.where(
				(Employee.date_of_joining.isnull() | (Employee.date_of_joining <= date))
				& (Employee.relieving_date.isnull() | (Employee.relieving_date >= date))
				& ((Employee.status != "Left") | (Employee.relieving_date >= date))
			)
			if settings.grades:
				query = query.where(Employee.grade.isin(settings.grades))
			if settings.exempt_employees:
				query = query.where(Employee.name.notin(settings.exempt_employees))
			return query

		eligible = scoped(frappe.qb.from_(Employee).select(Count(Employee.name))).run()[0][0]
		absent = scoped(
			frappe.qb.from_(Attendance)
			.join(Employee)
			.on(Employee.name == Attendance.employee)
			.select(Count(Attendance.employee).distinct())
			.where(
				(Attendance.status == "Absent")
				& (Attendance.docstatus == 1)
				& (Attendance.attendance_date == date)
			)
		).run()[0][0]

		if eligible and absent > eligible * OUTAGE_SHARE:
			outages[date] = (absent, eligible)
	return outages


def process_absence(absence, settings, dry_run: bool, outages: dict | None = None) -> frappe._dict:
	"""Decide (and unless dry_run, act on) one Absent employee-date. Never raises."""
	row = frappe._dict(
		employee=absence.employee,
		employee_name=absence.employee_name,
		absence_date=getdate(absence.attendance_date),
		attendance=absence.name,
		scan=None,
		action=None,
		status=None,
		reason=None,
		leave_type=None,
		balance_before=None,
		balance_after=None,
		leave_application=None,
		notification=None,
	)

	try:
		plan(row, absence, settings, outages)
	except Exception as e:
		row.status, row.reason = ERROR, _("Could not evaluate: {0}").format(e)
		if not dry_run:
			write_log(absence, ERROR, reason=row.reason, error=frappe.get_traceback())
		return row

	if dry_run or row.action in (ACTION_EXCUSED, ACTION_DONE):
		return row

	if row.action == ACTION_FLAG:
		row.status = FLAGGED
		write_log(
			absence,
			FLAGGED,
			reason=row.reason,
			leave_type=row.leave_type,
			balance_before=row.balance_before,
			balance_after=row.balance_before,
		)
		return row

	savepoint = "absent_al_deduction"
	frappe.db.savepoint(savepoint)
	try:
		leave = create_deduction(absence, row.leave_type)
		row.leave_application = leave.name
		row.status = DEDUCTED
		log = write_log(
			absence,
			DEDUCTED,
			reason=row.reason,
			leave_type=row.leave_type,
			leave_application=leave.name,
			balance_before=row.balance_before,
			balance_after=row.balance_after,
			error=None,
		)
	except Exception:
		frappe.db.rollback(save_point=savepoint)
		frappe.log_error(
			title=f"Absent AL deduction failed: {absence.employee} {absence.attendance_date}",
			reference_doctype="Attendance",
			reference_name=absence.name,
		)
		row.status = ERROR
		write_log(absence, ERROR, reason=row.reason, leave_type=row.leave_type, error=frappe.get_traceback())
		return row

	# The deduction stands even if the email cannot be sent.
	if settings.notify_employee:
		try:
			row.notification = notify_employee(absence, leave, row, settings)
		except Exception as e:
			frappe.log_error(title=f"Absent AL deduction email failed: {absence.employee}")
			row.notification = _("Email failed: {0}").format(e)
	else:
		row.notification = _("Not sent: employee notification is switched off.")
	log.db_set("notification", row.notification)
	return row


def plan(row, absence, settings, outages: dict | None = None):
	"""Fill row.action, reason, leave_type and balances. Reads only."""
	existing = frappe.db.get_value(LOG, make_name(absence.employee, absence.attendance_date), "status")
	if existing in (DEDUCTED, REVERSED):
		row.action, row.status = ACTION_DONE, existing
		row.reason = _("Already {0} - never deducted twice.").format(_(existing).lower())
		return

	excuse = get_excuse(absence.employee, absence.attendance_date, settings, absence.shift)
	if excuse:
		row.action, row.reason = ACTION_EXCUSED, excuse
		return

	row.scan = get_scan(absence.employee, absence.attendance_date, absence.shift)[0]
	row.reason = _("Absent, {0}.").format(row.scan)

	leave_type = settings.leave_type or LEAVE_TYPE
	outage = (outages or {}).get(getdate(absence.attendance_date))
	if outage:
		row.action, row.leave_type = ACTION_FLAG, leave_type
		row.reason = f"{row.reason} " + _(
			"Outage guard: {0} of {1} eligible employees are Absent on this date, which looks like "
			"a clock-in device or sync failure. Nobody is deducted for this date."
		).format(*outage)
		return

	if not get_holiday_list(absence.employee, absence.attendance_date, absence.shift):
		# HRMS v16 reads holidays only from Holiday List Assignment (or the shift's own
		# list). Without one the day cannot be told apart from a weekly off.
		row.action, row.leave_type = ACTION_FLAG, leave_type
		row.reason = f"{row.reason} " + _(
			"No Holiday List Assignment for the employee or company on this date; nothing deducted."
		)
		return

	balance = flt(
		get_leave_balance_on(
			absence.employee,
			leave_type,
			absence.attendance_date,
			absence.attendance_date,
			consider_all_leaves_in_the_allocation_period=True,
			for_consumption=True,
		).get("leave_balance_for_consumption")
	)
	row.balance_before = balance

	if balance >= 1:
		row.action, row.leave_type, row.balance_after = ACTION_DEDUCT, leave_type, balance - 1
		return

	if cint(frappe.db.get_value("Leave Type", leave_type, "allow_negative")):
		# TSH parity: the Leave Type allows it, so the balance goes negative.
		row.action, row.leave_type, row.balance_after = ACTION_DEDUCT, leave_type, balance - 1
		row.reason = f"{row.reason} " + _("{0} allows a negative balance; it goes to {1}.").format(
			leave_type, flt(balance - 1, 2)
		)
		return

	short = _("Insufficient {0} balance ({1}).").format(leave_type, balance)
	if settings.on_insufficient_balance == LEAVE_WITHOUT_PAY and settings.lwp_leave_type:
		row.action, row.leave_type, row.balance_after = ACTION_LWP, settings.lwp_leave_type, balance
		row.reason = f"{row.reason} {short} " + _("Booked as {0}.").format(settings.lwp_leave_type)
	else:
		row.action, row.leave_type = ACTION_FLAG, leave_type
		row.reason = f"{row.reason} {short} " + _("Nothing deducted; flagged for HR.")


def get_excuse(employee: str, date, settings=None, shift: str | None = None) -> str | None:
	"""The first thing that excuses the absence, or None.

	A pending (not yet approved) Leave Application also excuses the day: deducting would
	collide with it on overlap validation, and it is about to be decided either way.
	Weekly offs are Holiday rows with weekly_off set, so the holiday check covers both.
	"""
	settings = settings or get_settings()
	date = getdate(date)

	scan, _logs = get_scan(employee, date, shift)
	if scan == FULL_SCAN or (scan != NO_SCAN and not settings.single_scan_counts_as_absent):
		return "Employee Checkin"

	if has_gate_pass_workflow() and frappe.db.exists(
		"Gate Pass", {"employee": employee, "date": date, "docstatus": 1, "workflow_state": APPROVED}
	):
		return "Gate Pass"

	if frappe.db.exists(
		"Attendance Request",
		{"employee": employee, "docstatus": 1, "from_date": ["<=", date], "to_date": [">=", date]},
	):
		return "Attendance Request"

	if frappe.db.exists(
		"Leave Application",
		{
			"employee": employee,
			"docstatus": ["<", 2],
			"status": ["!=", "Rejected"],
			"from_date": ["<=", date],
			"to_date": [">=", date],
		},
	):
		return "Leave Application"

	if is_holiday_on(employee, date, shift):
		return "Holiday / Weekly Off"

	return None


def has_gate_pass_workflow() -> bool:
	"""Gate Pass is not part of this app (on Altura it comes from upande_ta), so the check
	is skipped on a site without it instead of failing every day."""
	if "has_gate_pass" not in frappe.local.flags:
		frappe.local.flags.has_gate_pass = bool(
			frappe.db.exists("DocType", "Gate Pass")
			and frappe.get_meta("Gate Pass").has_field("workflow_state")
		)
	return frappe.local.flags.has_gate_pass


def get_scan(employee: str, date, shift: str | None = None) -> tuple[str, list]:
	"""How the day's check-ins look, within the shift window, read the way the shift's
	"Determine Check-in and Check-out" setting reads them."""
	date = getdate(date)
	shift = resolve_shift(employee, date, shift)
	start, end = get_checkin_window(employee, date, shift)
	logs = frappe.get_all(
		"Employee Checkin",
		filters={"employee": employee, "time": ["between", [start, end]]},
		pluck="log_type",
		order_by="time",
	)
	if not logs:
		return NO_SCAN, logs

	types = {t for t in logs if t}
	mode = shift and frappe.db.get_value("Shift Type", shift, "determine_check_in_and_check_out")

	if shift and mode != STRICT:
		# Alternating entries: log types are ignored, scans pair up IN, OUT, IN, OUT...
		if len(logs) % 2 == 0:
			return FULL_SCAN, logs
		return (SINGLE_SCAN if len(logs) == 1 else UNPAIRED_SCANS.format(len(logs))), logs

	if {"IN", "OUT"} <= types:
		return FULL_SCAN, logs
	if types == {"IN"}:
		return IN_ONLY, logs
	if types == {"OUT"}:
		return OUT_ONLY, logs
	if mode == STRICT:
		# HRMS ignores untyped scans under Strictly based on Log Type.
		return UNTYPED_SCANS, logs
	# No shift: two or more untyped scans are taken as a pair, as TSH did.
	return (FULL_SCAN if len(logs) > 1 else SINGLE_SCAN), logs


def resolve_shift(employee: str, date, shift: str | None = None) -> str | None:
	"""The Attendance's own shift, else the Shift Assignment active on the day, else the
	employee's default shift."""
	return (
		shift
		or get_assigned_shift(employee, date)
		or frappe.db.get_value("Employee", employee, "default_shift")
	)


def get_checkin_window(employee: str, date, shift: str | None = None) -> tuple:
	"""Shift start minus early allowance to shift end plus late allowance.

	Without a shift (see resolve_shift), the calendar day (as on TSH).
	"""
	shift = resolve_shift(employee, date, shift)
	start_time = shift and frappe.db.get_value("Shift Type", shift, "start_time")
	if start_time is not None and start_time != "":
		# A timestamp at the shift's own start time resolves to the instance that starts
		# on `date`, including a shift that ends after midnight.
		details = get_shift_details(shift, get_datetime(date) + to_timedelta(start_time))
		if details and details.actual_start and details.actual_end:
			return details.actual_start, details.actual_end

	return get_datetime(f"{date} 00:00:00"), get_datetime(f"{date} 23:59:59")


def get_assigned_shift(employee: str, date) -> str | None:
	ShiftAssignment = frappe.qb.DocType("Shift Assignment")
	rows = (
		frappe.qb.from_(ShiftAssignment)
		.select(ShiftAssignment.shift_type)
		.where(
			(ShiftAssignment.employee == employee)
			& (ShiftAssignment.docstatus == 1)
			& (ShiftAssignment.status == "Active")
			& (ShiftAssignment.start_date <= date)
			& (ShiftAssignment.end_date.isnull() | (ShiftAssignment.end_date >= date))
		)
		.orderby(ShiftAssignment.start_date, order=frappe.qb.desc)
		.limit(1)
	).run()
	return rows[0][0] if rows else None


def get_holiday_list(employee: str, date, shift: str | None = None) -> str | None:
	"""The holiday list auto-attendance uses for this employee-date.

	Same order as HRMS's ShiftType.get_holiday_list: the shift's own Holiday List when it
	has one, else the employee's Holiday List Assignment in force on `date` (falling back
	to the company's). Kept identical so that a day auto-attendance treats as a holiday is
	never deducted, and a day it marks Absent is never wrongly excused.
	"""
	shift = resolve_shift(employee, date, shift)
	shift_list = shift and frappe.db.get_value("Shift Type", shift, "holiday_list")
	return shift_list or get_holiday_list_for_employee(employee, raise_exception=False, as_on=date)


def is_holiday_on(employee: str, date, shift: str | None = None) -> bool:
	"""Holiday or weekly off on `date`, from the list in force *then* (see get_holiday_list).

	Not erpnext's is_holiday: that resolves the employee's list as of today, which is
	wrong for a past day if their weekly-off pattern changed since.
	"""
	holiday_list = get_holiday_list(employee, date, shift)
	return bool(holiday_list) and bool(
		frappe.db.exists("Holiday", {"parent": holiday_list, "holiday_date": date})
	)


def get_auto_deduction_class():
	base = get_controller("Leave Application")

	class AutoDeductedLeaveApplication(base):
		def validate_workflow(self):
			# Created directly at Approved; see module docstring.
			pass

		def validate_leave_approver(self):
			# Nobody approves an automatic deduction. Keep an approver when the employee
			# or department has one, but do not fail the deduction when neither does.
			if self.leave_approver:
				super().validate_leave_approver()

	return AutoDeductedLeaveApplication


def create_deduction(absence, leave_type: str = LEAVE_TYPE):
	leave_approver = get_employee_leave_approver(absence.employee)
	doc = get_auto_deduction_class()(
		{
			"doctype": "Leave Application",
			"employee": absence.employee,
			"company": absence.company,
			"leave_type": leave_type,
			"from_date": absence.attendance_date,
			"to_date": absence.attendance_date,
			"posting_date": today(),
			"status": APPROVED,
			"workflow_state": APPROVED,
			"leave_approver": leave_approver,
			"follow_via_email": 0,
			AUTO_FLAG: 1,
			"description": _("Auto-deducted: absent on {0} (no clock-in/out recorded).").format(
				formatdate(absence.attendance_date)
			),
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	return doc


def notify_employee(absence, leave, row, settings) -> str:
	from hrms.utils import get_employee_email

	recipient = get_employee_email(absence.employee)
	if not recipient:
		note = _("Deduction email not sent: employee has no email address.")
		leave.add_comment("Info", note)
		return note

	subject, message = render(
		EMPLOYEE_TEMPLATE,
		{
			"employee": absence.employee,
			"employee_name": absence.employee_name,
			"absence_date": formatdate(absence.attendance_date),
			"reason": row.scan,
			"leave_type": row.leave_type,
			"deduction_leave_type": settings.leave_type or LEAVE_TYPE,
			"is_lwp": row.action == ACTION_LWP,
			"balance_after": flt(row.balance_after, 2),
			"leave_application": leave.name,
		},
	)
	# TSH parity: the leave approver is copied in when there is one.
	cc = [leave.leave_approver] if leave.leave_approver and leave.leave_approver != recipient else []
	frappe.sendmail(
		recipients=[recipient],
		cc=cc,
		subject=subject,
		message=message,
		reference_doctype="Leave Application",
		reference_name=leave.name,
	)
	note = _("Deduction email sent to {0}.").format(", ".join([recipient, *cc]))
	leave.add_comment("Info", note)
	return note


def send_hr_summary(rows: list, from_date, to_date, outages: dict | None = None):
	"""One email to HR Managers listing the Flagged and Error days of a run."""
	if not rows:
		return

	from frappe.utils.user import get_users_with_role

	recipients = [u for u in get_users_with_role("HR Manager") if u not in ("Administrator", "Guest")]
	if not recipients:
		frappe.log_error(
			title="Absent AL deduction: no HR Manager to send the summary to",
			message=f"{len(rows)} flagged/failed day(s) from {from_date} to {to_date}",
		)
		return

	subject, message = render(
		HR_SUMMARY_TEMPLATE,
		{
			"from_date": formatdate(from_date),
			"to_date": formatdate(to_date),
			"outages": [
				{"date": formatdate(date), "absent": absent, "eligible": eligible}
				for date, (absent, eligible) in sorted((outages or {}).items())
			],
			"rows": [
				{**r, "absence_date": formatdate(r.absence_date), "reason": r.reason or ""} for r in rows
			],
		},
	)
	frappe.sendmail(recipients=recipients, subject=subject, message=message)


def write_log(absence, status: str, **values):
	"""Create or update the employee-date row. Its name is the uniqueness guarantee."""
	name = make_name(absence.employee, absence.attendance_date)
	if frappe.db.exists(LOG, name):
		doc = frappe.get_doc(LOG, name)
	else:
		doc = frappe.new_doc(LOG)
		doc.employee = absence.employee
		doc.absence_date = absence.attendance_date

	doc.update(
		{
			"employee_name": absence.employee_name,
			"company": absence.company,
			"attendance": absence.name,
			"status": status,
			**values,
		}
	)
	doc.flags.ignore_permissions = True
	doc.save()
	return doc


def on_leave_application_cancel(doc, method=None):
	"""doc_events Leave Application.on_cancel: HR reversing a deduction.

	The balance comes back through HRMS's own ledger reversal. The log row turns
	Reversed, and plan() never deducts a Reversed day again.
	"""
	if not doc.get(AUTO_FLAG):
		return

	for name in frappe.get_all(
		LOG, filters={"leave_application": doc.name, "status": DEDUCTED}, pluck="name"
	):
		log = frappe.get_doc(LOG, name)
		log.status = REVERSED
		log.reason = "\n".join(
			filter(
				None,
				[
					log.reason,
					_("Reversed: {0} cancelled by {1} on {2}.").format(
						doc.name, frappe.session.user, formatdate(today())
					),
				],
			)
		)
		log.flags.ignore_permissions = True
		log.save()
