# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Weekly Absent -> Annual Leave deduction.

Every Sunday night each Attendance marked Absent in the Monday-Sunday week is checked
against the ways an absence can be excused. An unexcused day is covered by a one-day
Annual Leave Application, created and submitted directly at Approved with
custom_auto_deducted = 1, and the employee (cc their leave approver) is emailed.

Opt-in per site through HR Settings.custom_enable_absent_al_deduction.

Notes on the Leave Application that gets created:

- Leave Application runs the "Leave Approval Workflow", which only allows Draft as an
  entry state. The deduction is not a request anyone approves, so the workflow check is
  skipped for these documents only, by a subclass of whatever controller the site
  resolves for Leave Application (so a later override_doctype_class is still honoured).
- Annual Leave has allow_negative set on TSH, so an exhausted balance only warns and the
  debt carries forward. The "Annual Leave Negative Limit" Server Script fires on
  "Awaiting..." states only and does not see these.
- On submit HRMS flips the day's Attendance from Absent to On Leave, so a re-run of the
  same week finds nothing left to deduct.
"""

import frappe
from frappe import _
from frappe.model.base_document import get_controller
from frappe.utils import add_days, formatdate, get_datetime, getdate, today
from hrms.utils.holiday_list import get_holiday_list_for_employee

SETTINGS_FLAG = "custom_enable_absent_al_deduction"
AUTO_FLAG = "custom_auto_deducted"
LEAVE_TYPE = "Annual Leave"
APPROVED = "Approved"

EMAIL_SUBJECT = "Annual Leave deducted for absence on {date}"
EMAIL_BODY = (
	"A day of Annual Leave has been deducted from your balance to cover your absence on "
	"{date}. If you believe this is an error, please contact HR."
)


def run_weekly():
	"""Scheduler entry point - cron 59 23 * * 0."""
	if not frappe.db.get_single_value("HR Settings", SETTINGS_FLAG):
		return
	deduct_unexcused_absences()


@frappe.whitelist()
def deduct_unexcused_absences(week_of: str | None = None, employee: str | None = None) -> dict:
	"""Deduct for the Monday-Sunday week containing `week_of` (default: this week).

	Callable by HR from the console or an API call to re-run a week or smoke-test one
	employee. A manual run deliberately ignores the HR Settings toggle: the toggle gates
	the schedule, not an explicit request from HR.
	"""
	frappe.only_for(("HR Manager", "System Manager"))

	week_start, week_end = get_week(week_of)
	filters = {
		"status": "Absent",
		"docstatus": 1,
		"attendance_date": ["between", [week_start, week_end]],
	}
	if employee:
		filters["employee"] = employee

	absences = frappe.get_all(
		"Attendance",
		filters=filters,
		fields=["name", "employee", "employee_name", "attendance_date", "company"],
		order_by="employee, attendance_date",
	)

	summary = {"week": f"{week_start} to {week_end}", "deducted": [], "excused": [], "failed": []}
	for absence in absences:
		reason = get_excuse(absence.employee, absence.attendance_date)
		if reason:
			summary["excused"].append((absence.employee, str(absence.attendance_date), reason))
			continue

		savepoint = "absent_al_deduction"
		frappe.db.savepoint(savepoint)
		try:
			leave = create_deduction(absence)
			notify_employee(absence, leave)
			summary["deducted"].append((absence.employee, str(absence.attendance_date), leave.name))
		except Exception:
			frappe.db.rollback(save_point=savepoint)
			frappe.log_error(
				title=f"Absent AL deduction failed: {absence.employee} {absence.attendance_date}",
				reference_doctype="Attendance",
				reference_name=absence.name,
			)
			summary["failed"].append((absence.employee, str(absence.attendance_date)))

	frappe.logger("upande_hr").info({"absent_al_deduction": summary})
	return summary


def get_week(week_of: str | None) -> tuple:
	day = getdate(week_of or today())
	monday = add_days(day, -day.weekday())
	return monday, add_days(monday, 6)


def get_excuse(employee: str, date) -> str | None:
	"""The first thing that excuses the absence, or None.

	A pending (not yet approved) Leave Application also excuses the day: deducting would
	collide with it on overlap validation, and it is about to be decided either way.
	Weekly offs are Holiday rows with weekly_off set, so the holiday check covers both.
	"""
	date = getdate(date)
	day_start = get_datetime(f"{date} 00:00:00")
	day_end = get_datetime(f"{date} 23:59:59")

	if frappe.db.exists(
		"Employee Checkin", {"employee": employee, "time": ["between", [day_start, day_end]]}
	):
		return "Employee Checkin"

	if frappe.db.exists(
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

	if is_holiday_on(employee, date):
		return "Holiday / Weekly Off"

	return None


def is_holiday_on(employee: str, date) -> bool:
	"""Holiday or weekly off on `date`, from the Holiday List Assignment in force *then*.

	Not erpnext's is_holiday: that resolves the employee's list as of today, which is
	wrong for a past day if their weekly-off pattern changed since.
	"""
	holiday_list = get_holiday_list_for_employee(employee, raise_exception=False, as_on=date)
	return bool(holiday_list) and bool(
		frappe.db.exists("Holiday", {"parent": holiday_list, "holiday_date": date})
	)


def get_auto_deduction_class():
	base = get_controller("Leave Application")

	class AutoDeductedLeaveApplication(base):
		def validate_workflow(self):
			# Created directly at Approved; see module docstring.
			pass

	return AutoDeductedLeaveApplication


def create_deduction(absence):
	leave_approver = frappe.db.get_value("Employee", absence.employee, "leave_approver")
	doc = get_auto_deduction_class()(
		{
			"doctype": "Leave Application",
			"employee": absence.employee,
			"company": absence.company,
			"leave_type": LEAVE_TYPE,
			"from_date": absence.attendance_date,
			"to_date": absence.attendance_date,
			"posting_date": today(),
			"status": APPROVED,
			"workflow_state": APPROVED,
			"leave_approver": leave_approver,
			"follow_via_email": 0,
			AUTO_FLAG: 1,
			"description": _("Auto-deducted for unexcused absence on {0} (Attendance {1}).").format(
				formatdate(absence.attendance_date), absence.name
			),
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	return doc


def notify_employee(absence, leave):
	from hrms.utils import get_employee_email

	recipient = get_employee_email(absence.employee)
	if not recipient:
		leave.add_comment("Info", _("Deduction email not sent: employee has no email address."))
		return

	date = formatdate(absence.attendance_date)
	cc = [leave.leave_approver] if leave.leave_approver else []
	frappe.sendmail(
		recipients=[recipient],
		cc=cc,
		subject=EMAIL_SUBJECT.format(date=date),
		message=EMAIL_BODY.format(date=date),
		reference_doctype="Leave Application",
		reference_name=leave.name,
	)
	leave.add_comment("Info", _("Deduction email sent to {0}.").format(", ".join([recipient, *cc])))
