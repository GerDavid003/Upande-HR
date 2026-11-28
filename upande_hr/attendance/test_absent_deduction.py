# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Absent -> Annual Leave deduction.

Self-contained: builds its own employment types, holiday list, employees, allocations and
attendance on the site's first company, and rolls everything back after each test. It
does not use HRMSTestSuite, whose bootstrap needs a clean "_Test Company" fiscal-year
setup that sites restored from live data do not have.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate, today

from upande_hr.attendance import absent_deduction as ad
from upande_hr.attendance.absence_email_templates import TEMPLATES
from upande_hr.attendance.absence_settings import (
	EMPLOYMENT_TYPE_ROW,
	EMPLOYMENT_TYPES,
	ENABLED,
	EXEMPT,
	LEAVE_TYPE,
	LEAVE_WITHOUT_PAY,
	LWP_LEAVE_TYPE,
	ON_INSUFFICIENT,
	SINGLE_SCAN,
	SKIP_AND_FLAG,
	START_DATE,
	get_employment_types,
	get_stored,
	seed_defaults,
	validate_hr_settings,
)

ET = "_Test ALD Fixed Term"
OTHER_ET = "_Test ALD Casual"
HOLIDAY_LIST = "_Test ALD Holidays"
NIGHT_SHIFT = "_Test ALD Night 22-06"
STRICT_SHIFT = "_Test ALD Day Strict 07-16"
ALTERNATING_SHIFT = "_Test ALD Chef Alternating 06-15"
AL = "_Test ALD Annual Leave"
LWP = "_Test ALD Leave Without Pay"

# A fixed, fully past Monday-Sunday week, so dates never land in the future.
MONDAY = add_days(getdate(today()), -getdate(today()).weekday() - 28)
TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY = (add_days(MONDAY, i) for i in range(1, 7))
HOLIDAY = THURSDAY
START = add_days(MONDAY, -60)


class TestAbsentDeduction(IntegrationTestCase):
	def setUp(self):
		frappe.db.savepoint("ald_test")
		frappe.set_user("Administrator")
		frappe.local.flags.pop("has_gate_pass", None)
		self.company = frappe.db.get_value("Company", {}, "name", order_by="creation")
		make_masters(self.company)
		configure(
			{
				ENABLED: 1,
				START_DATE: START,
				LEAVE_TYPE: AL,
				SINGLE_SCAN: 0,
				ON_INSUFFICIENT: SKIP_AND_FLAG,
				LWP_LEAVE_TYPE: LWP,
			},
			employment_types=[ET],
		)
		self.hr_manager = make_hr_manager()
		self.hr_manager_doc = frappe.get_doc("User", self.hr_manager)
		self.employee = make_employee(self.company, ET, "Full")
		allocate(self.employee, AL, 5)
		# Present colleagues, so the outage guard (more than half of those in scope Absent on
		# a date) stays out of the way of tests that are not about it.
		self.bystanders = [make_employee(self.company, ET, f"Bystander {i}", hla=False) for i in range(4)]

		# Render the shipped wording, not whatever HR has edited on this site.
		frappe.db.delete("Email Template", {"name": ("in", list(TEMPLATES))})

		self.sent = []
		mailer = patch("frappe.sendmail", side_effect=lambda **kw: self.sent.append(kw))
		mailer.start()
		self.addCleanup(mailer.stop)

	def tearDown(self):
		frappe.db.rollback(save_point="ald_test")
		frappe.local.flags.pop("has_gate_pass", None)

	def run_week(self, dry_run=0, **kw):
		return ad._run(MONDAY, SUNDAY, dry_run=dry_run, **kw)

	def rows_for(self, result, employee, date=None):
		return [
			r
			for r in result["rows"]
			if r.employee == employee and (date is None or r.absence_date == getdate(date))
		]

	# --- gating -------------------------------------------------------------------

	def test_checkbox_off_is_a_noop(self):
		mark_absent(self.employee, TUESDAY)
		frappe.db.set_single_value("HR Settings", ENABLED, 0)
		with patch.object(ad, "deduct_unexcused_absences") as deduct:
			ad.run_weekly()
		deduct.assert_not_called()

		frappe.db.set_single_value("HR Settings", ENABLED, 1)
		with patch.object(ad, "deduct_unexcused_absences") as deduct:
			ad.run_weekly()
		deduct.assert_called_once()

	def test_enabled_without_start_date_deducts_nothing(self):
		"""Live state before this change: switched on, no Deduct From."""
		frappe.db.set_single_value("HR Settings", START_DATE, None)
		with (
			patch.object(ad, "deduct_unexcused_absences") as deduct,
			patch.object(frappe, "log_error") as log,
		):
			ad.run_weekly()
		deduct.assert_not_called()
		self.assertIn("Deduct From is not set", log.call_args.kwargs["title"])

	def test_manual_week_run_requires_start_date(self):
		frappe.db.set_single_value("HR Settings", START_DATE, None)
		mark_absent(self.employee, TUESDAY)
		with self.assertRaises(frappe.ValidationError):
			ad.deduct_unexcused_absences(week_of=str(TUESDAY))
		self.assertFalse(frappe.db.exists("Leave Application", {"employee": self.employee}))

	# --- which week ---------------------------------------------------------------

	def test_previous_week_whenever_the_job_starts(self):
		"""The bug: cron Sunday 23:59 started Monday 00:00:01 and took the new week."""
		expected = (MONDAY, SUNDAY)
		next_monday = add_days(SUNDAY, 1)
		for run_day in (next_monday, add_days(next_monday, 1), add_days(next_monday, 6)):
			self.assertEqual(ad.get_previous_week(run_day), expected, run_day)

	def test_scheduled_run_processes_the_week_that_ended(self):
		mark_absent(self.employee, TUESDAY)
		with patch.object(ad, "today", return_value=str(add_days(SUNDAY, 1))):
			summary = ad.deduct_unexcused_absences()
		self.assertEqual(summary["week"], f"{MONDAY} to {SUNDAY}")
		[(employee, date, _leave)] = summary["deducted"]
		self.assertEqual((employee, date), (self.employee, str(TUESDAY)))

	def test_manual_week_of_still_picks_that_week(self):
		self.assertEqual(ad.get_week(str(THURSDAY)), (MONDAY, SUNDAY))

	def test_enabling_requires_start_date(self):
		settings = frappe.get_doc("HR Settings")
		settings.set(ENABLED, 1)
		settings.set(START_DATE, None)
		with self.assertRaises(frappe.ValidationError):
			validate_hr_settings(settings)
		settings.set(START_DATE, START)
		validate_hr_settings(settings)

	def test_real_run_requires_start_date(self):
		frappe.db.set_single_value("HR Settings", START_DATE, None)
		with self.assertRaises(frappe.ValidationError):
			self.run_week(dry_run=0)
		self.run_week(dry_run=1)  # a dry run works without one

	# --- who and when -------------------------------------------------------------

	def test_employment_type_not_in_list_is_ignored(self):
		casual = make_employee(self.company, OTHER_ET, "Casual")
		mark_absent(casual, TUESDAY)
		self.assertEqual(self.rows_for(self.run_week(), casual), [])
		self.assertFalse(frappe.db.exists(ad.LOG, {"employee": casual}))

	def test_empty_employment_type_list_means_all_employees(self):
		casual = make_employee(self.company, OTHER_ET, "Casual")
		blank = make_employee(self.company, None, "No Type")
		for employee in (casual, blank):
			allocate(employee, AL, 2)
			mark_absent(employee, TUESDAY)
		configure({}, employment_types=[])
		result = self.run_week()
		for employee in (casual, blank):
			[row] = self.rows_for(result, employee)
			self.assertEqual(row.action, ad.ACTION_DEDUCT)

	def test_no_employment_type_is_flagged_not_dropped(self):
		blank = make_employee(self.company, None, "No Type")
		allocate(blank, AL, 5)
		mark_absent(blank, TUESDAY)
		[row] = self.rows_for(self.run_week(), blank)
		self.assertEqual((row.action, row.status), (ad.ACTION_FLAG, ad.FLAGGED))
		self.assertIn(ad.NO_EMPLOYMENT_TYPE, row.reason)
		self.assertFalse(frappe.db.exists("Leave Application", {"employee": blank}))
		[summary] = [m for m in self.sent if "need attention" in m["subject"]]
		self.assertIn(blank, summary["message"])

		# Fixing the Employee record and re-running the week deducts the day.
		frappe.db.set_value("Employee", blank, "employment_type", ET)
		[row] = self.rows_for(self.run_week(), blank)
		self.assertEqual(row.status, ad.DEDUCTED)

	def test_no_employment_type_excused_day_is_not_flagged(self):
		blank = make_employee(self.company, None, "No Type")
		mark_absent(blank, TUESDAY)
		checkin(blank, f"{TUESDAY} 07:02:00", "IN")
		[row] = self.rows_for(self.run_week(), blank)
		self.assertEqual(row.action, ad.ACTION_EXCUSED)
		self.assertFalse(frappe.db.exists(ad.LOG, {"employee": blank}))

	def test_exempt_employee_is_never_processed(self):
		mark_absent(self.employee, TUESDAY)
		configure({}, exempt=[self.employee])
		for dry_run in (1, 0):
			result = self.run_week(dry_run=dry_run)
			self.assertEqual(self.rows_for(result, self.employee), [])
			self.assertEqual(result["settings"]["exempt_employees"], [self.employee])
		self.assertFalse(frappe.db.exists(ad.LOG, {"employee": self.employee}))
		self.assertFalse(frappe.db.exists("Leave Application", {"employee": self.employee}))
		self.assertEqual(self.sent, [])

		# Exemption also applies with an empty list ("all employees").
		configure({}, employment_types=[])
		self.assertEqual(self.rows_for(self.run_week(dry_run=1), self.employee), [])

	def test_dates_before_start_date_untouched(self):
		mark_absent(self.employee, MONDAY)
		mark_absent(self.employee, WEDNESDAY)
		frappe.db.set_single_value("HR Settings", START_DATE, TUESDAY)
		result = self.run_week()
		self.assertEqual([r.absence_date for r in self.rows_for(result, self.employee)], [WEDNESDAY])
		self.assertEqual(
			frappe.db.get_value(
				"Attendance", {"employee": self.employee, "attendance_date": MONDAY}, "status"
			),
			"Absent",
		)

	def test_dates_before_joining_untouched(self):
		mark_absent(self.employee, MONDAY)
		mark_absent(self.employee, WEDNESDAY)
		frappe.db.set_value("Employee", self.employee, "date_of_joining", TUESDAY)
		result = self.run_week()
		self.assertEqual([r.absence_date for r in self.rows_for(result, self.employee)], [WEDNESDAY])

	# --- exclusions ---------------------------------------------------------------

	def assert_excused(self, date, reason):
		[row] = self.rows_for(self.run_week(), self.employee, date)
		self.assertEqual((row.action, row.reason), (ad.ACTION_EXCUSED, reason))
		self.assertFalse(frappe.db.exists(ad.LOG, {"employee": self.employee, "absence_date": date}))

	def test_holiday_excluded(self):
		mark_absent(self.employee, HOLIDAY)
		self.assert_excused(HOLIDAY, "Holiday / Weekly Off")

	def test_shift_holiday_list_wins_like_auto_attendance(self):
		"""HRMS auto-attendance uses Shift Type.holiday_list before the employee's list."""
		shift_list = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": "_Test ALD Shift Holidays",
				"from_date": add_days(START, -30),
				"to_date": add_days(today(), 30),
				"holidays": [{"holiday_date": WEDNESDAY, "description": "Shift holiday", "weekly_off": 0}],
			}
		).insert()
		shift = frappe.get_doc(
			{
				"doctype": "Shift Type",
				"__newname": "_Test ALD Shift With List",
				"start_time": "07:00:00",
				"end_time": "16:00:00",
				"holiday_list": shift_list.name,
			}
		).insert()
		assign_shift(self.employee, shift.name, START)
		mark_absent(self.employee, WEDNESDAY)
		mark_absent(self.employee, HOLIDAY)  # a holiday in the employee's list only
		result = self.run_week(dry_run=1)
		[wed] = self.rows_for(result, self.employee, WEDNESDAY)
		[thu] = self.rows_for(result, self.employee, HOLIDAY)
		self.assertEqual((wed.action, wed.reason), (ad.ACTION_EXCUSED, "Holiday / Weekly Off"))
		self.assertEqual(thu.action, ad.ACTION_DEDUCT)  # auto-attendance would mark it Absent too

		# With the shift's own list, no Holiday List Assignment is needed.
		frappe.db.delete("Holiday List Assignment", {"assigned_to": self.employee})
		mark_absent(self.employee, FRIDAY)
		[fri] = self.rows_for(self.run_week(dry_run=1), self.employee, FRIDAY)
		self.assertEqual(fri.action, ad.ACTION_DEDUCT)

	def test_gate_pass_excluded(self):
		if not frappe.db.exists("DocType", "Gate Pass"):
			self.skipTest("No Gate Pass doctype on this site")
		mark_absent(self.employee, TUESDAY)
		raw_insert("Gate Pass", employee=self.employee, date=TUESDAY, docstatus=1, workflow_state="Approved")
		self.assert_excused(TUESDAY, "Gate Pass")

	def test_unapproved_gate_pass_does_not_excuse(self):
		if not frappe.db.exists("DocType", "Gate Pass"):
			self.skipTest("No Gate Pass doctype on this site")
		mark_absent(self.employee, TUESDAY)
		raw_insert("Gate Pass", employee=self.employee, date=TUESDAY, docstatus=1, workflow_state="Rejected")
		[row] = self.rows_for(self.run_week(dry_run=1), self.employee, TUESDAY)
		self.assertEqual(row.action, ad.ACTION_DEDUCT)

	def test_missing_gate_pass_doctype_degrades(self):
		mark_absent(self.employee, TUESDAY)
		frappe.local.flags.has_gate_pass = False
		[row] = self.rows_for(self.run_week(dry_run=1), self.employee, TUESDAY)
		self.assertEqual(row.action, ad.ACTION_DEDUCT)

	def test_attendance_request_excluded(self):
		mark_absent(self.employee, TUESDAY)
		raw_insert(
			"Attendance Request",
			employee=self.employee,
			company=self.company,
			from_date=MONDAY,
			to_date=WEDNESDAY,
			reason="On Duty",
			docstatus=1,
		)
		self.assert_excused(TUESDAY, "Attendance Request")

	def test_approved_leave_excluded(self):
		mark_absent(self.employee, TUESDAY)
		raw_insert(
			"Leave Application",
			employee=self.employee,
			company=self.company,
			leave_type=AL,
			from_date=TUESDAY,
			to_date=TUESDAY,
			status="Approved",
			docstatus=1,
		)
		self.assert_excused(TUESDAY, "Leave Application")

	# --- detection ----------------------------------------------------------------

	def test_no_scan_deducts(self):
		attendance = mark_absent(self.employee, TUESDAY)
		[row] = self.rows_for(self.run_week(), self.employee)

		self.assertEqual((row.action, row.status), (ad.ACTION_DEDUCT, ad.DEDUCTED))
		self.assertEqual((row.balance_before, row.balance_after), (5, 4))
		leave = frappe.get_doc("Leave Application", row.leave_application)
		self.assertEqual((leave.docstatus, leave.status, leave.leave_type), (1, "Approved", AL))
		self.assertEqual(leave.custom_auto_deducted, 1)
		self.assertEqual(leave.total_leave_days, 1)
		self.assertIn("Auto-deducted: absent on", leave.description)
		self.assertIn(ad.NO_SCAN, leave.description)

		log = frappe.get_doc(ad.LOG, {"employee": self.employee, "absence_date": TUESDAY})
		self.assertEqual(
			(log.status, log.leave_application, log.attendance), (ad.DEDUCTED, leave.name, attendance)
		)
		# HRMS flips the Attendance; the log keeps it identifiable as an absence.
		self.assertEqual(frappe.db.get_value("Attendance", attendance, "status"), "On Leave")

		[mail] = self.sent
		self.assertIn("1 full day", mail["message"])
		self.assertIn("<b>4.0</b>", mail["message"])
		self.assertIn("contact HR", mail["message"])
		self.assertIn("Deduction email sent", log.notification)
		self.assertEqual(log.notified, 1)
		self.assertEqual(log.employment_type, ET)

		# The email states the date and every check that was made.
		self.assertIn(frappe.utils.formatdate(TUESDAY), mail["subject"])
		for check in ad.get_checks(ad.NO_SCAN):
			self.assertIn(check, mail["message"])
		self.assertIn("No leave application", mail["message"])
		self.assertIn("Not a public holiday or weekly off", mail["message"])

	def test_single_scan_excuses_when_setting_off(self):
		mark_absent(self.employee, TUESDAY)
		checkin(self.employee, f"{TUESDAY} 07:02:00", "IN")
		self.assert_excused(TUESDAY, "Employee Checkin")

	def test_single_scan_deducts_when_setting_on(self):
		frappe.db.set_single_value("HR Settings", SINGLE_SCAN, 1)
		mark_absent(self.employee, TUESDAY)
		mark_absent(self.employee, WEDNESDAY)
		checkin(self.employee, f"{TUESDAY} 07:02:00", "IN")
		checkin(self.employee, f"{WEDNESDAY} 07:02:00", "IN")
		checkin(self.employee, f"{WEDNESDAY} 16:01:00", "OUT")
		result = self.run_week()
		[tue] = self.rows_for(result, self.employee, TUESDAY)
		[wed] = self.rows_for(result, self.employee, WEDNESDAY)
		self.assertEqual(tue.action, ad.ACTION_DEDUCT)
		self.assertIn(ad.IN_ONLY, tue.reason)
		self.assertEqual((wed.action, wed.reason), (ad.ACTION_EXCUSED, "Employee Checkin"))

	def test_night_shift_across_midnight_not_a_false_positive(self):
		frappe.db.set_single_value("HR Settings", SINGLE_SCAN, 1)
		assign_shift(self.employee, NIGHT_SHIFT, START)
		mark_absent(self.employee, TUESDAY, shift=NIGHT_SHIFT)
		mark_absent(self.employee, WEDNESDAY, shift=NIGHT_SHIFT)
		checkin(self.employee, f"{TUESDAY} 21:55:00", "IN")
		checkin(self.employee, f"{WEDNESDAY} 06:04:00", "OUT")  # Tuesday's shift, after midnight

		result = self.run_week(dry_run=1)
		[tue] = self.rows_for(result, self.employee, TUESDAY)
		[wed] = self.rows_for(result, self.employee, WEDNESDAY)
		self.assertEqual((tue.action, tue.reason), (ad.ACTION_EXCUSED, "Employee Checkin"))
		# The 06:04 OUT belongs to Tuesday's shift, so Wednesday's has no scan at all.
		self.assertEqual(wed.action, ad.ACTION_DEDUCT)
		self.assertIn(ad.NO_SCAN, wed.reason)

		# Without the shift (calendar day) Tuesday would be a lone IN, i.e. deducted.
		self.assertEqual(ad.get_scan(self.employee, TUESDAY, shift=None)[0], ad.FULL_SCAN)
		frappe.db.delete("Shift Assignment", {"employee": self.employee})
		self.assertEqual(ad.get_scan(self.employee, TUESDAY)[0], ad.IN_ONLY)

	def test_strict_log_type_shift_in_without_out_is_a_single_scan(self):
		"""Strictly based on Log Type."""
		frappe.db.set_single_value("HR Settings", SINGLE_SCAN, 1)
		assign_shift(self.employee, STRICT_SHIFT, START)
		for day in (MONDAY, TUESDAY, WEDNESDAY, FRIDAY):
			mark_absent(self.employee, day)
		checkin(self.employee, f"{MONDAY} 06:55:00", "IN")  # IN, no OUT
		checkin(self.employee, f"{TUESDAY} 06:55:00", "IN")
		checkin(self.employee, f"{TUESDAY} 16:05:00", "OUT")
		checkin(self.employee, f"{WEDNESDAY} 16:05:00", "OUT")  # OUT, no IN
		checkin(self.employee, f"{FRIDAY} 06:55:00", None)  # untyped: ignored under strict
		checkin(self.employee, f"{FRIDAY} 16:05:00", None)

		result = self.run_week(dry_run=1)
		row = {r.absence_date: r for r in self.rows_for(result, self.employee)}
		self.assertEqual(row[MONDAY].action, ad.ACTION_DEDUCT)
		self.assertIn(ad.IN_ONLY, row[MONDAY].reason)
		self.assertEqual((row[TUESDAY].action, row[TUESDAY].reason), (ad.ACTION_EXCUSED, "Employee Checkin"))
		self.assertEqual(row[WEDNESDAY].action, ad.ACTION_DEDUCT)
		self.assertIn(ad.OUT_ONLY, row[WEDNESDAY].reason)
		self.assertEqual(row[FRIDAY].action, ad.ACTION_DEDUCT)
		self.assertIn(ad.UNTYPED_SCANS, row[FRIDAY].reason)

		# Setting off (the default): any scan excuses the day.
		frappe.db.set_single_value("HR Settings", SINGLE_SCAN, 0)
		result = self.run_week(dry_run=1)
		self.assertEqual({r.action for r in self.rows_for(result, self.employee)}, {ad.ACTION_EXCUSED})

	def test_alternating_shift_odd_count_is_a_single_scan(self):
		"""Alternating entries; log types are ignored."""
		frappe.db.set_single_value("HR Settings", SINGLE_SCAN, 1)
		assign_shift(self.employee, ALTERNATING_SHIFT, START)
		for day in (MONDAY, TUESDAY, WEDNESDAY):
			mark_absent(self.employee, day)
		checkin(self.employee, f"{MONDAY} 05:58:00", "IN")  # 1 scan
		checkin(self.employee, f"{TUESDAY} 05:58:00", "IN")  # 2 scans, both typed IN
		checkin(self.employee, f"{TUESDAY} 15:03:00", "IN")
		for time in ("05:58:00", "10:00:00", "11:00:00"):  # 3 scans
			checkin(self.employee, f"{WEDNESDAY} {time}", None)

		result = self.run_week(dry_run=1)
		row = {r.absence_date: r for r in self.rows_for(result, self.employee)}
		self.assertEqual(row[MONDAY].action, ad.ACTION_DEDUCT)
		self.assertIn(ad.SINGLE_SCAN, row[MONDAY].reason)
		self.assertEqual((row[TUESDAY].action, row[TUESDAY].reason), (ad.ACTION_EXCUSED, "Employee Checkin"))
		self.assertEqual(row[WEDNESDAY].action, ad.ACTION_DEDUCT)
		self.assertIn(ad.UNPAIRED_SCANS.format(3), row[WEDNESDAY].reason)

	# --- balance ------------------------------------------------------------------

	def test_insufficient_balance_flags(self):
		poor = make_employee(self.company, ET, "Poor")
		poor_attendance = mark_absent(poor, TUESDAY)
		[row] = self.rows_for(self.run_week(), poor)
		self.assertEqual((row.action, row.status), (ad.ACTION_FLAG, ad.FLAGGED))
		self.assertIsNone(row.leave_application)
		self.assertEqual(frappe.db.get_value("Attendance", poor_attendance, "status"), "Absent")
		self.assertEqual(frappe.db.get_value(ad.LOG, {"employee": poor}, "status"), ad.FLAGGED)
		# Flagged days go to HR in one summary, never to the employee.
		self.assertEqual(len(self.sent), 1)
		self.assertIn("need attention", self.sent[0]["subject"])
		self.assertIn(self.hr_manager, self.sent[0]["recipients"])

	def test_allow_negative_does_not_bypass_the_setting(self):
		"""TSH's Annual Leave allows a negative balance, and HRMS then skips its
		allocation check. The insufficient-balance setting still decides."""
		frappe.db.set_value("Leave Type", AL, "allow_negative", 1)
		for setting, action, leave_type in (
			(SKIP_AND_FLAG, ad.ACTION_FLAG, AL),
			(LEAVE_WITHOUT_PAY, ad.ACTION_LWP, LWP),
		):
			with self.subTest(setting=setting):
				frappe.db.savepoint("ald_negative")
				frappe.db.set_single_value("HR Settings", ON_INSUFFICIENT, setting)
				short = make_employee(self.company, ET, "Short")
				allocate(short, AL, 0.5)
				unallocated = make_employee(self.company, ET, "Unallocated")
				mark_absent(short, TUESDAY)
				mark_absent(unallocated, TUESDAY)

				result = self.run_week()
				for employee in (short, unallocated):
					[row] = self.rows_for(result, employee)
					self.assertEqual((row.action, row.leave_type), (action, leave_type))
				self.assertFalse(
					frappe.db.exists(
						"Leave Application", {"leave_type": AL, "employee": ["in", [short, unallocated]]}
					)
				)
				frappe.db.rollback(save_point="ald_negative")

	def test_insufficient_balance_books_lwp(self):
		frappe.db.set_single_value("HR Settings", ON_INSUFFICIENT, LEAVE_WITHOUT_PAY)
		poor = make_employee(self.company, ET, "Poor")
		mark_absent(poor, TUESDAY)
		[row] = self.rows_for(self.run_week(), poor)
		self.assertEqual((row.action, row.status), (ad.ACTION_LWP, ad.DEDUCTED))
		self.assertEqual(frappe.db.get_value("Leave Application", row.leave_application, "leave_type"), LWP)
		self.assertIn("Leave Without Pay", self.sent[0]["message"])

	# --- idempotency and reversal ---------------------------------------------------

	def test_rerun_does_not_double_deduct(self):
		mark_absent(self.employee, TUESDAY)
		self.run_week()
		self.run_week()
		self.assertEqual(
			frappe.db.count(
				"Leave Application", {"employee": self.employee, "custom_auto_deducted": 1, "docstatus": 1}
			),
			1,
		)

		# Even if the day is somehow Absent again, the log stops a second deduction.
		frappe.db.set_value(
			"Attendance", {"employee": self.employee, "attendance_date": TUESDAY}, "status", "Absent"
		)
		[row] = self.rows_for(self.run_week(), self.employee)
		self.assertEqual(row.action, ad.ACTION_DONE)
		self.assertEqual(frappe.db.count("Leave Application", {"employee": self.employee, "docstatus": 1}), 1)

	def test_cancel_reverses_and_is_never_rededucted(self):
		mark_absent(self.employee, TUESDAY)
		[row] = self.rows_for(self.run_week(), self.employee)
		frappe.get_doc("Leave Application", row.leave_application).cancel()

		log = frappe.get_doc(ad.LOG, {"employee": self.employee, "absence_date": TUESDAY})
		self.assertEqual(log.status, ad.REVERSED)
		self.assertIn("Reversed", log.reason)

		# HRMS cancels the day's Attendance on leave cancel; mark it Absent again.
		mark_absent(self.employee, TUESDAY)
		[again] = self.rows_for(self.run_week(), self.employee)
		self.assertEqual((again.action, again.status), (ad.ACTION_DONE, ad.REVERSED))
		self.assertEqual(frappe.db.count("Leave Application", {"employee": self.employee, "docstatus": 1}), 0)

	# --- outage guard -------------------------------------------------------------

	def test_outage_guard_flags_a_date_with_most_employees_absent(self):
		# 6 eligible (employee + 4 bystanders + other): 4 Absent on Tuesday > half.
		other = make_employee(self.company, ET, "Other")
		allocate(other, AL, 5)
		for employee in (self.employee, other, *self.bystanders[:2]):
			mark_absent(employee, TUESDAY)
		mark_absent(self.employee, WEDNESDAY)  # 1 of 6: a normal day

		result = self.run_week()
		self.assertEqual(result["outage_dates"], {str(TUESDAY): "4 of 6"})
		tue = [r for r in result["rows"] if r.absence_date == TUESDAY]
		self.assertEqual(len(tue), 4)
		for row in tue:
			self.assertEqual((row.action, row.status), (ad.ACTION_FLAG, ad.FLAGGED))
			self.assertIn("Outage guard: 4 of 6", row.reason)
		self.assertFalse(
			frappe.db.exists("Leave Application", {"from_date": TUESDAY, "custom_auto_deducted": 1})
		)
		[wed] = self.rows_for(result, self.employee, WEDNESDAY)
		self.assertEqual(wed.status, ad.DEDUCTED)

		[summary] = [m for m in self.sent if "need attention" in m["subject"]]
		self.assertIn("Possible clock-in device or sync failure", summary["message"])
		self.assertIn("4 of 6 eligible employees Absent", summary["message"])

		# A one-employee re-run cannot get round the guard.
		[row] = self.rows_for(self.run_week(employee=other), other, TUESDAY)
		self.assertEqual(row.action, ad.ACTION_FLAG)

	def test_outage_guard_exactly_half_still_deducts(self):
		# 6 eligible, 3 Absent: not more than half.
		other = make_employee(self.company, ET, "Other")
		for employee in (self.employee, *self.bystanders[:2]):
			mark_absent(employee, TUESDAY)
		result = self.run_week(dry_run=1)
		self.assertEqual(result["outage_dates"], {})
		[row] = self.rows_for(result, self.employee, TUESDAY)
		self.assertEqual(row.action, ad.ACTION_DEDUCT)
		self.assertTrue(other)

	def test_outage_guard_ignores_exempt_and_other_employment_types(self):
		# Exempt employees and other employment types are not eligible, so they count neither way:
		# 5 eligible, 2 Absent.
		casuals = [make_employee(self.company, OTHER_ET, f"Casual {i}", hla=False) for i in range(3)]
		for employee in (self.employee, self.bystanders[0], *casuals):
			mark_absent(employee, TUESDAY)
		exempt = make_employee(self.company, ET, "Never clocks", hla=False)
		mark_absent(exempt, TUESDAY)
		configure({}, exempt=[exempt])
		result = self.run_week(dry_run=1)
		self.assertEqual(result["outage_dates"], {})
		self.assertEqual(self.rows_for(result, self.employee)[0].action, ad.ACTION_DEDUCT)

		# Without the exemption the same day is 3 of 6, still not more than half; one more
		# Absent colleague tips it over.
		configure({}, exempt=[])
		mark_absent(self.bystanders[1], TUESDAY)
		self.assertEqual(self.run_week(dry_run=1)["outage_dates"], {str(TUESDAY): "4 of 6"})

	# --- dry run, notifications, robustness ---------------------------------------

	def test_dry_run_writes_nothing(self):
		mark_absent(self.employee, TUESDAY)
		before = {dt: frappe.db.count(dt) for dt in ("Leave Application", ad.LOG, "Email Queue")}
		result = self.run_week(dry_run=1)
		[row] = self.rows_for(result, self.employee)
		self.assertEqual((row.action, row.balance_before, row.balance_after), (ad.ACTION_DEDUCT, 5, 4))
		self.assertIsNone(row.status)
		self.assertEqual(before, {dt: frappe.db.count(dt) for dt in before})
		self.assertEqual(self.sent, [])

	def test_whitelisted_dry_run_is_restricted(self):
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				ad.run_absence_deduction(str(MONDAY), str(SUNDAY))
		finally:
			frappe.set_user("Administrator")

	def test_dry_run_callable_from_the_browser_by_hr_manager(self):
		"""What frappe.call from the desk console does: /api/method -> execute_cmd."""
		from frappe.handler import execute_cmd

		mark_absent(self.employee, TUESDAY)
		frappe.set_user(self.hr_manager)
		frappe.local.form_dict = frappe._dict(from_date=str(MONDAY), to_date=str(SUNDAY), dry_run="1")
		frappe.local.request = frappe._dict(method="POST")  # frappe.call posts
		try:
			result = execute_cmd(ad.__name__ + ".run_absence_deduction")
		finally:
			frappe.set_user("Administrator")
			frappe.local.form_dict = frappe._dict()
			del frappe.local.request
		self.assertEqual(result["dry_run"], 1)
		[row] = self.rows_for(result, self.employee)
		self.assertEqual(row.action, ad.ACTION_DEDUCT)
		self.assertFalse(frappe.db.exists(ad.LOG, {"employee": self.employee}))
		frappe.as_json(result)  # what the response serialises

	def test_no_email_on_file(self):
		frappe.db.set_value(
			"Employee",
			self.employee,
			{"prefered_email": None, "user_id": None, "company_email": None, "personal_email": None},
		)
		mark_absent(self.employee, TUESDAY)
		[row] = self.rows_for(self.run_week(), self.employee)
		self.assertEqual(row.status, ad.DEDUCTED)
		log = frappe.get_doc(ad.LOG, {"employee": self.employee})
		self.assertIn("no email address", log.notification)
		self.assertEqual(log.notified, 0)
		# Nobody to email, so HR is told instead.
		[summary] = self.sent
		self.assertIn("need attention", summary["subject"])
		self.assertIn("no email address", summary["message"])

	def test_email_failure_keeps_the_deduction_and_tells_hr(self):
		mark_absent(self.employee, TUESDAY)
		with patch.object(ad, "notify_employee", side_effect=Exception("SMTP down")):
			[row] = self.rows_for(self.run_week(), self.employee)
		self.assertEqual((row.status, row.notified), (ad.DEDUCTED, 0))
		self.assertIn("SMTP down", frappe.db.get_value(ad.LOG, {"employee": self.employee}, "notification"))
		self.assertTrue(any("need attention" in m["subject"] for m in self.sent))

	def test_leave_approver_is_copied(self):
		self.hr_manager_doc.add_roles("Leave Approver")
		frappe.db.set_value("Employee", self.employee, "leave_approver", self.hr_manager)
		mark_absent(self.employee, TUESDAY)
		[row] = self.rows_for(self.run_week(), self.employee)
		self.assertEqual(
			frappe.db.get_value("Leave Application", row.leave_application, "leave_approver"), self.hr_manager
		)
		[mail] = self.sent
		self.assertEqual(mail["cc"], [self.hr_manager])
		self.assertIn("<b>4.0</b>", mail["message"])
		self.assertIn(
			self.hr_manager, frappe.db.get_value(ad.LOG, {"employee": self.employee}, "notification")
		)

	def test_no_leave_approver_no_cc(self):
		mark_absent(self.employee, TUESDAY)
		self.run_week()
		[mail] = self.sent
		self.assertEqual(mail["cc"], [])

	def test_no_holiday_list_assignment_flags(self):
		mark_absent(self.employee, TUESDAY)
		frappe.db.delete("Holiday List Assignment", {"assigned_to": self.employee})
		if ad.get_holiday_list_for_employee(self.employee, raise_exception=False, as_on=TUESDAY):
			self.skipTest("The company itself has a Holiday List Assignment on this site")
		[row] = self.rows_for(self.run_week(), self.employee)
		self.assertEqual((row.action, row.status), (ad.ACTION_FLAG, ad.FLAGGED))
		self.assertIn("No Holiday List Assignment", row.reason)

	def test_one_bad_record_does_not_stop_the_run(self):
		other = make_employee(self.company, ET, "Other")
		allocate(other, AL, 3)
		mark_absent(self.employee, TUESDAY)
		mark_absent(other, TUESDAY)

		real = ad.create_deduction

		def flaky(absence, leave_type=ad.LEAVE_TYPE, row=None):
			if absence.employee == self.employee:
				raise frappe.ValidationError("boom")
			return real(absence, leave_type, row)

		with patch.object(ad, "create_deduction", side_effect=flaky):
			result = self.run_week()

		[bad] = self.rows_for(result, self.employee)
		[good] = self.rows_for(result, other)
		self.assertEqual((bad.status, good.status), (ad.ERROR, ad.DEDUCTED))
		self.assertIn("boom", frappe.db.get_value(ad.LOG, {"employee": self.employee}, "error"))
		self.assertFalse(
			frappe.db.exists("Leave Application", {"employee": self.employee, "custom_auto_deducted": 1})
		)

		# An Error day is retried on the next run.
		[retry] = self.rows_for(self.run_week(), self.employee)
		self.assertEqual(retry.status, ad.DEDUCTED)

	# --- settings seeding -----------------------------------------------------------

	def test_seed_defaults(self):
		for name in ad_default_employment_types():
			if not frappe.db.exists("Employment Type", name):
				frappe.get_doc({"doctype": "Employment Type", "employee_type_name": name}).insert()
		configure({ENABLED: 0}, employment_types=[])
		for fieldname in (LEAVE_TYPE, SINGLE_SCAN, ON_INSUFFICIENT):
			frappe.db.delete("Singles", {"doctype": "HR Settings", "field": fieldname})

		seed_defaults()
		self.assertEqual(get_employment_types(), list(ad_default_employment_types()))
		self.assertEqual(get_stored(ON_INSUFFICIENT), SKIP_AND_FLAG)
		self.assertEqual(frappe.db.get_single_value("HR Settings", ENABLED), 0)

		# A list HR changed is never overwritten.
		configure({}, employment_types=[OTHER_ET])
		seed_defaults()
		self.assertEqual(get_employment_types(), [OTHER_ET])

	# --- report ---------------------------------------------------------------------

	def test_report_lists_what_needs_attention_with_current_state(self):
		from upande_hr.upande_hr.report.absence_leave_deductions import absence_leave_deductions as report

		poor = make_employee(self.company, ET, "Poor")
		mark_absent(poor, TUESDAY)  # flagged: no balance
		mark_absent(self.employee, TUESDAY)  # deducted and emailed
		self.run_week()

		filters = {"from_date": str(MONDAY), "to_date": str(SUNDAY)}
		_cols, rows = report.execute(filters)
		mine = [r for r in rows if r.employee in (poor, self.employee)]
		self.assertEqual([(r.employee, r.status) for r in mine], [(poor, ad.FLAGGED)])
		[row] = mine
		self.assertEqual((row.attendance_now, row.employment_type_now, row.excused_now), ("Absent", ET, None))

		# HR approves leave for the day: the report shows it would now be excused.
		raw_insert(
			"Leave Application",
			employee=poor,
			company=self.company,
			leave_type=AL,
			from_date=TUESDAY,
			to_date=TUESDAY,
			status="Approved",
			docstatus=1,
		)
		[row] = [r for r in report.execute(filters)[1] if r.employee == poor]
		self.assertEqual(row.excused_now, "Leave Application")

		_cols, everything = report.execute({**filters, "view": "All"})
		self.assertEqual(
			{r.status for r in everything if r.employee in (poor, self.employee)}, {ad.FLAGGED, ad.DEDUCTED}
		)


# --- helpers ---------------------------------------------------------------------


def ad_default_employment_types():
	from upande_hr.attendance.absence_settings import DEFAULT_EMPLOYMENT_TYPES

	return DEFAULT_EMPLOYMENT_TYPES


def configure(values: dict, employment_types: list[str] | None = None, exempt: list[str] | None = None):
	for fieldname, value in values.items():
		frappe.db.set_single_value("HR Settings", fieldname, value)
	if exempt is not None:
		frappe.db.delete(
			"Absence Deduction Exempt Employee", {"parent": "HR Settings", "parentfield": EXEMPT}
		)
		for idx, employee in enumerate(exempt, 1):
			frappe.get_doc(
				{
					"doctype": "Absence Deduction Exempt Employee",
					"parent": "HR Settings",
					"parenttype": "HR Settings",
					"parentfield": EXEMPT,
					"idx": idx,
					"employee": employee,
				}
			).db_insert()
	if employment_types is not None:
		frappe.db.delete(EMPLOYMENT_TYPE_ROW, {"parent": "HR Settings", "parentfield": EMPLOYMENT_TYPES})
		for idx, employment_type in enumerate(employment_types, 1):
			frappe.get_doc(
				{
					"doctype": EMPLOYMENT_TYPE_ROW,
					"parent": "HR Settings",
					"parenttype": "HR Settings",
					"parentfield": EMPLOYMENT_TYPES,
					"idx": idx,
					"employment_type": employment_type,
				}
			).db_insert()


def make_hr_manager():
	email = "_test_ald_hr@example.com"
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "_Test ALD HR", "send_welcome_email": 0}
		).insert()
	user = frappe.get_doc("User", email)
	user.add_roles("HR Manager")
	return email


def make_masters(company):
	for employment_type in (ET, OTHER_ET):
		if not frappe.db.exists("Employment Type", employment_type):
			frappe.get_doc({"doctype": "Employment Type", "employee_type_name": employment_type}).insert()

	for name, extra in ((AL, {}), (LWP, {"is_lwp": 1})):
		if not frappe.db.exists("Leave Type", name):
			frappe.get_doc({"doctype": "Leave Type", "leave_type_name": name, **extra}).insert()

	if not frappe.db.exists("Holiday List", HOLIDAY_LIST):
		frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": HOLIDAY_LIST,
				"from_date": add_days(START, -30),
				"to_date": add_days(today(), 30),
				"holidays": [{"holiday_date": HOLIDAY, "description": "Test holiday", "weekly_off": 0}],
			}
		).insert()

	if not frappe.db.exists("Shift Type", NIGHT_SHIFT):
		frappe.get_doc(
			{
				"doctype": "Shift Type",
				"__newname": NIGHT_SHIFT,
				"start_time": "22:00:00",
				"end_time": "06:00:00",
				"begin_check_in_before_shift_start_time": 60,
				"allow_check_out_after_shift_end_time": 60,
				"holiday_list": HOLIDAY_LIST,
			}
		).insert()

	for name, start, end, mode in (
		(STRICT_SHIFT, "07:00:00", "16:00:00", "Strictly based on Log Type in Employee Checkin"),
		(
			ALTERNATING_SHIFT,
			"06:00:00",
			"15:00:00",
			"Alternating entries as IN and OUT during the same shift",
		),
	):
		if not frappe.db.exists("Shift Type", name):
			frappe.get_doc(
				{
					"doctype": "Shift Type",
					"__newname": name,
					"start_time": start,
					"end_time": end,
					"begin_check_in_before_shift_start_time": 60,
					"allow_check_out_after_shift_end_time": 60,
					"determine_check_in_and_check_out": mode,
					"holiday_list": HOLIDAY_LIST,
				}
			).insert()


def make_employee(company, employment_type, first_name, hla=True):
	employee = (
		frappe.get_doc(
			{
				"doctype": "Employee",
				# Own series: a site restored from live data can have its real series
				# counter behind the employees that already exist.
				"naming_series": "_TALD-.#####",
				"first_name": f"_Test ALD {first_name}",
				"gender": frappe.db.get_value("Gender", {}, "name"),
				"date_of_birth": "1990-01-01",
				"date_of_joining": add_days(START, -365),
				"company": company,
				"status": "Active",
				"employment_type": employment_type,
				"personal_email": f"ald.{frappe.generate_hash(length=6)}@example.com",
				"prefered_contact_email": "Personal Email",
			}
		)
		.insert()
		.name
	)
	if not hla:
		return employee
	frappe.get_doc(
		{
			"doctype": "Holiday List Assignment",
			"applicable_for": "Employee",
			"assigned_to": employee,
			"holiday_list": HOLIDAY_LIST,
			"from_date": add_days(START, -30),
		}
	).submit()
	return employee


def allocate(employee, leave_type, days):
	frappe.get_doc(
		{
			"doctype": "Leave Allocation",
			"employee": employee,
			"leave_type": leave_type,
			"from_date": START,
			"to_date": add_days(today(), 30),
			"new_leaves_allocated": days,
		}
	).submit()


def mark_absent(employee, date, shift=None):
	attendance = frappe.get_doc(
		{
			"doctype": "Attendance",
			"employee": employee,
			"attendance_date": date,
			"status": "Absent",
			"shift": shift,
		}
	)
	attendance.submit()
	return attendance.name


def assign_shift(employee, shift, start):
	raw_insert(
		"Shift Assignment",
		employee=employee,
		shift_type=shift,
		start_date=start,
		status="Active",
		docstatus=1,
		company=frappe.db.get_value("Employee", employee, "company"),
	)


def checkin(employee, time, log_type):
	raw_insert("Employee Checkin", employee=employee, time=time, log_type=log_type)


def raw_insert(doctype, **values):
	"""Insert without controllers, to set up a state (e.g. an approved Gate Pass)
	without walking its whole workflow."""
	doc = frappe.new_doc(doctype)
	doc.update(values)
	doc.name = f"_Test ALD {frappe.generate_hash(length=10)}"
	doc.db_insert()
	return doc.name
