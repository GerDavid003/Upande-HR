# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import add_days, add_months, flt, getdate, today
from hrms.hr.doctype.attendance_request.test_attendance_request import get_employee
from hrms.hr.doctype.holiday_list_assignment.test_holiday_list_assignment import (
	create_holiday_list_assignment,
)
from hrms.hr.doctype.leave_period.test_leave_period import create_leave_period
from hrms.tests.utils import HRMSTestSuite

from upande_hr.upande_hr.doctype.extra_shift_compensation.extra_shift_compensation import (
	DOUBLE_SHIFT,
	LEAVE_DAY,
	OFF_DAY,
)

LEAVE_TYPE = "_Test Upande Comp Off"
HOLIDAY_LIST = "_Test Upande ESC Holidays"


def make_leave_type():
	if not frappe.db.exists("Leave Type", LEAVE_TYPE):
		frappe.get_doc(
			{
				"doctype": "Leave Type",
				"leave_type_name": LEAVE_TYPE,
				# Deliberately NOT is_compensatory: mirrors the prod config change that
				# drops this leave type out of the Compensatory Leave Request picker.
				"is_compensatory": 0,
				"is_carry_forward": 0,
				"max_leaves_allowed": 0,
			}
		).insert()
	return LEAVE_TYPE


def make_holiday_list(weekly_off_date, public_holiday_date):
	if frappe.db.exists("Holiday List", HOLIDAY_LIST):
		frappe.db.delete("Holiday", {"parent": HOLIDAY_LIST})
		frappe.db.delete("Holiday List", HOLIDAY_LIST)

	frappe.get_doc(
		{
			"doctype": "Holiday List",
			"holiday_list_name": HOLIDAY_LIST,
			"from_date": add_months(today(), -6),
			"to_date": add_months(today(), 6),
			"holidays": [
				{"description": "Weekly Off", "holiday_date": weekly_off_date, "weekly_off": 1},
				{"description": "Jamhuri Day", "holiday_date": public_holiday_date, "weekly_off": 0},
			],
		}
	).insert()
	return HOLIDAY_LIST


def set_settings(**kwargs):
	settings = frappe.get_doc("Extra Shift Compensation Settings")
	settings.update(
		{
			"leave_type": kwargs.get("leave_type", LEAVE_TYPE),
			"max_backdate_days": kwargs.get("max_backdate_days", 30),
			"overtime_overlap_action": kwargs.get("overtime_overlap_action", "Block"),
		}
	)
	settings.save()
	frappe.clear_cache(doctype="Extra Shift Compensation Settings")


class TestExtraShiftCompensation(HRMSTestSuite):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		create_leave_period(add_months(today(), -6), add_months(today(), 6), "_Test Company")

	def setUp(self):
		self.employee = get_employee()
		self.weekly_off = add_days(today(), -3)
		self.public_holiday = add_days(today(), -4)
		self.leave_type = make_leave_type()
		self.holiday_list = make_holiday_list(self.weekly_off, self.public_holiday)
		create_holiday_list_assignment(
			"Employee",
			self.employee.name,
			self.holiday_list,
			from_date=add_months(today(), -6),
		)
		set_settings()

	def tearDown(self):
		frappe.db.rollback()

	# --------------------------------------------------------------------- helpers

	def make_request(self, rows, submit=False, do_not_save=False):
		doc = frappe.get_doc(
			{
				"doctype": "Extra Shift Compensation",
				"naming_series": "HR-ESC-.YYYY.-",
				"company": "_Test Company",
				"department": self.employee.department,
				"posting_date": today(),
				"entries": [
					{
						"employee": row.get("employee", self.employee.name),
						"work_date": row["work_date"],
						"reason": row["reason"],
						"days_awarded": row.get("days_awarded", 1),
						"row_status": row.get("row_status", "Approved"),
					}
					for row in rows
				],
			}
		)
		if do_not_save:
			return doc
		doc.insert()
		if submit:
			doc.submit()
		return doc

	def make_leave_application(self, from_date, to_date, status="Approved", submit=True):
		leave_type = "_Test Leave Type"
		if not frappe.db.exists("Leave Type", leave_type):
			frappe.get_doc({"doctype": "Leave Type", "leave_type_name": leave_type}).insert()

		frappe.get_doc(
			{
				"doctype": "Leave Allocation",
				"employee": self.employee.name,
				"leave_type": leave_type,
				"from_date": add_months(today(), -6),
				"to_date": add_months(today(), 6),
				"new_leaves_allocated": 30,
			}
		).insert().submit()

		application = frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": self.employee.name,
				"leave_type": leave_type,
				"from_date": from_date,
				"to_date": to_date,
				"company": "_Test Company",
				"status": status,
				"leave_approver": "test@example.com",
			}
		)
		application.insert(ignore_permissions=True)
		if submit:
			application.submit()
		return application

	def get_allocation(self, valid_from=None):
		valid_from = valid_from or add_days(self.weekly_off, 1)
		name = frappe.db.get_value(
			"Leave Allocation",
			{
				"employee": self.employee.name,
				"leave_type": self.leave_type,
				"from_date": ("<=", valid_from),
				"to_date": (">=", valid_from),
				"docstatus": 1,
			},
			"name",
		)
		return frappe.get_doc("Leave Allocation", name) if name else None

	# ------------------------------------------------------------------ date checks

	def test_future_work_date_is_rejected(self):
		doc = self.make_request(
			[{"work_date": add_days(today(), 1), "reason": DOUBLE_SHIFT}], do_not_save=True
		)
		self.assertRaisesRegex(frappe.ValidationError, "in the future", doc.insert)

	def test_work_date_beyond_backdate_limit_is_rejected(self):
		set_settings(max_backdate_days=5)
		doc = self.make_request(
			[{"work_date": add_days(today(), -10), "reason": DOUBLE_SHIFT}], do_not_save=True
		)
		self.assertRaisesRegex(frappe.ValidationError, "backdating limit", doc.insert)

	def test_work_date_inside_backdate_limit_is_accepted(self):
		set_settings(max_backdate_days=30)
		doc = self.make_request([{"work_date": add_days(today(), -10), "reason": DOUBLE_SHIFT}])
		self.assertTrue(doc.name)

	def test_zero_days_awarded_is_rejected(self):
		doc = self.make_request(
			[{"work_date": self.weekly_off, "reason": OFF_DAY, "days_awarded": 0}], do_not_save=True
		)
		self.assertRaisesRegex(frappe.ValidationError, "greater than zero", doc.insert)

	# -------------------------------------------------------------- worked on off day

	def test_off_day_on_weekly_off_is_accepted_and_noted(self):
		doc = self.make_request([{"work_date": self.weekly_off, "reason": OFF_DAY}])
		self.assertIn("Weekly off", doc.entries[0].verification_note)
		self.assertIn(self.holiday_list, doc.entries[0].verification_note)

	def test_off_day_on_ordinary_working_day_is_rejected(self):
		doc = self.make_request([{"work_date": add_days(today(), -1), "reason": OFF_DAY}], do_not_save=True)
		self.assertRaisesRegex(frappe.ValidationError, "not an off day", doc.insert)

	def test_off_day_on_public_holiday_redirects_to_compensatory_leave_request(self):
		doc = self.make_request([{"work_date": self.public_holiday, "reason": OFF_DAY}], do_not_save=True)
		self.assertRaisesRegex(frappe.ValidationError, "Compensatory Leave Request", doc.insert)

	def test_off_day_without_holiday_list_is_rejected(self):
		frappe.db.delete("Holiday List Assignment", {"assigned_to": self.employee.name})
		frappe.db.delete("Holiday List Assignment", {"assigned_to": "_Test Company"})
		doc = self.make_request([{"work_date": self.weekly_off, "reason": OFF_DAY}], do_not_save=True)
		self.assertRaisesRegex(frappe.ValidationError, "no Holiday List", doc.insert)

	# ------------------------------------------------------------ reported on leave day

	def test_leave_day_requires_an_approved_leave_application(self):
		doc = self.make_request([{"work_date": add_days(today(), -1), "reason": LEAVE_DAY}], do_not_save=True)
		self.assertRaisesRegex(frappe.ValidationError, "no approved Leave Application", doc.insert)

	def test_leave_day_records_the_leave_type_in_the_note(self):
		work_date = add_days(today(), -1)
		self.make_leave_application(work_date, work_date)
		doc = self.make_request([{"work_date": work_date, "reason": LEAVE_DAY}])
		self.assertIn("_Test Leave Type", doc.entries[0].verification_note)

	# ------------------------------------------------------------------ double shift

	def test_double_shift_records_punch_count_and_span(self):
		work_date = add_days(today(), -1)
		for hour in (6, 14, 22):
			frappe.get_doc(
				{
					"doctype": "Employee Checkin",
					"employee": self.employee.name,
					"time": f"{getdate(work_date)} {hour:02d}:00:00",
					"log_type": "IN" if hour != 22 else "OUT",
					"skip_auto_attendance": 1,
				}
			).insert()

		doc = self.make_request([{"work_date": work_date, "reason": DOUBLE_SHIFT}])
		note = doc.entries[0].verification_note
		self.assertIn("3 check-in(s)", note)
		self.assertIn("06:00", note)
		self.assertIn("22:00", note)
		self.assertIn("16.0 hrs", note)

	def test_double_shift_without_punches_still_saves(self):
		doc = self.make_request([{"work_date": add_days(today(), -1), "reason": DOUBLE_SHIFT}])
		self.assertIn("No Employee Checkin records", doc.entries[0].verification_note)

	def test_verification_note_is_rebuilt_when_the_date_changes(self):
		doc = self.make_request([{"work_date": self.weekly_off, "reason": OFF_DAY}])
		self.assertIn("Weekly off", doc.entries[0].verification_note)

		doc.entries[0].reason = DOUBLE_SHIFT
		doc.entries[0].work_date = add_days(today(), -1)
		doc.save()
		self.assertNotIn("Weekly off", doc.entries[0].verification_note)
		self.assertIn("No Employee Checkin records", doc.entries[0].verification_note)

	# --------------------------------------------------------------------- duplicates

	def test_duplicate_submitted_entry_is_rejected(self):
		self.make_request([{"work_date": self.weekly_off, "reason": OFF_DAY}], submit=True)
		doc = self.make_request([{"work_date": self.weekly_off, "reason": OFF_DAY}], do_not_save=True)
		self.assertRaisesRegex(frappe.ValidationError, "already claimed", doc.insert)

	def test_duplicate_of_a_rejected_row_is_allowed(self):
		first = self.make_request(
			[
				{"work_date": self.weekly_off, "reason": OFF_DAY, "row_status": "Rejected"},
				{"work_date": add_days(today(), -1), "reason": DOUBLE_SHIFT},
			]
		)
		first.submit()

		second = self.make_request([{"work_date": self.weekly_off, "reason": OFF_DAY}])
		self.assertTrue(second.name)

	def test_draft_entries_do_not_block_a_second_request(self):
		self.make_request([{"work_date": self.weekly_off, "reason": OFF_DAY}])
		doc = self.make_request([{"work_date": self.weekly_off, "reason": OFF_DAY}])
		self.assertTrue(doc.name)

	# ---------------------------------------------------------------- overtime overlap

	def make_bulk_overtime(self, work_date):
		doc = frappe.get_doc(
			{
				"doctype": "Bulk Overtime",
				"naming_series": "HR-BOT-.YYYY.-",
				"company": "_Test Company",
				"department": self.employee.department,
				"from_date": work_date,
				"to_date": work_date,
				"reason_for_overtime": "Test",
				"bulk_overtime_entries": [
					{
						"employee": self.employee.name,
						"overtime_date": work_date,
						"verification_type": "Manual",
						"normal_hours": 4,
						"row_status": "Approved",
					}
				],
			}
		)
		doc.insert()
		# Bulk Overtime.on_submit builds Overtime Slips, which needs payroll setup this
		# test does not care about. Mirror the docstatus directly instead.
		frappe.db.set_value("Bulk Overtime", doc.name, "docstatus", 1, update_modified=False)
		frappe.db.set_value(
			"Bulk Overtime Entry", doc.bulk_overtime_entries[0].name, "docstatus", 1, update_modified=False
		)
		return doc

	def test_overtime_overlap_blocks_by_default(self):
		self.make_bulk_overtime(self.weekly_off)
		doc = self.make_request([{"work_date": self.weekly_off, "reason": OFF_DAY}], do_not_save=True)
		self.assertRaisesRegex(frappe.ValidationError, "overtime is already claimed", doc.insert)

	def test_overtime_overlap_warn_lets_it_through(self):
		set_settings(overtime_overlap_action="Warn")
		self.make_bulk_overtime(self.weekly_off)
		doc = self.make_request([{"work_date": self.weekly_off, "reason": OFF_DAY}])
		self.assertTrue(doc.name)

	def test_overtime_overlap_ignore_skips_the_check(self):
		set_settings(overtime_overlap_action="Ignore")
		self.make_bulk_overtime(self.weekly_off)
		doc = self.make_request([{"work_date": self.weekly_off, "reason": OFF_DAY}])
		self.assertTrue(doc.name)

	# ------------------------------------------------------------------- on submit

	def test_submit_requires_at_least_one_approved_row(self):
		doc = self.make_request([{"work_date": self.weekly_off, "reason": OFF_DAY, "row_status": "Pending"}])
		self.assertRaisesRegex(frappe.ValidationError, "must be marked", doc.submit)

	def test_submit_creates_an_allocation_when_none_exists(self):
		self.assertIsNone(self.get_allocation())
		doc = self.make_request([{"work_date": self.weekly_off, "reason": OFF_DAY}], submit=True)

		allocation = self.get_allocation()
		self.assertIsNotNone(allocation)
		self.assertEqual(flt(allocation.new_leaves_allocated), 1.0)
		self.assertEqual(doc.entries[0].leave_allocation, allocation.name)
		self.assertEqual(getdate(allocation.from_date), getdate(add_days(self.weekly_off, 1)))

	def test_submit_increments_an_existing_allocation_without_replacing_it(self):
		"""The five allocations on prod carry 6.0 days of pre-existing entitlement."""
		existing = frappe.get_doc(
			{
				"doctype": "Leave Allocation",
				"employee": self.employee.name,
				"leave_type": self.leave_type,
				"from_date": add_months(today(), -6),
				"to_date": add_months(today(), 6),
				"new_leaves_allocated": 2.0,
			}
		)
		existing.insert()
		existing.submit()

		self.make_request([{"work_date": self.weekly_off, "reason": OFF_DAY}], submit=True)

		existing.reload()
		self.assertEqual(existing.name, self.get_allocation().name)
		self.assertEqual(flt(existing.new_leaves_allocated), 3.0)
		self.assertEqual(flt(existing.total_leaves_allocated), 3.0)

	def test_submit_writes_a_ledger_entry_for_the_delta_only(self):
		doc = self.make_request(
			[{"work_date": self.weekly_off, "reason": OFF_DAY, "days_awarded": 0.5}], submit=True
		)
		allocation = self.get_allocation()
		ledger = frappe.get_all(
			"Leave Ledger Entry",
			filters={
				"transaction_type": "Leave Allocation",
				"transaction_name": allocation.name,
				"docstatus": 1,
			},
			fields=["leaves", "from_date"],
		)
		self.assertEqual(sum(flt(entry.leaves) for entry in ledger), 0.5)
		self.assertEqual(flt(doc.entries[0].days_awarded), 0.5)

	def test_half_day_award_is_credited(self):
		self.make_request(
			[{"work_date": self.weekly_off, "reason": OFF_DAY, "days_awarded": 0.5}], submit=True
		)
		self.assertEqual(flt(self.get_allocation().new_leaves_allocated), 0.5)

	def test_rejected_rows_credit_nothing(self):
		doc = self.make_request(
			[
				{"work_date": self.weekly_off, "reason": OFF_DAY, "row_status": "Rejected"},
				{"work_date": add_days(today(), -1), "reason": DOUBLE_SHIFT, "row_status": "Approved"},
			],
			submit=True,
		)
		self.assertIsNone(doc.entries[0].leave_allocation)
		self.assertTrue(doc.entries[1].leave_allocation)
		self.assertEqual(flt(self.get_allocation(today()).new_leaves_allocated), 1.0)

	def test_two_approved_rows_for_the_same_employee_both_credit(self):
		self.make_request(
			[
				{"work_date": self.weekly_off, "reason": OFF_DAY},
				{"work_date": add_days(today(), -1), "reason": DOUBLE_SHIFT},
			],
			submit=True,
		)
		self.assertEqual(flt(self.get_allocation().new_leaves_allocated), 2.0)

	# ------------------------------------------------------- attendance override

	def test_leave_day_submit_flips_attendance_to_present(self):
		work_date = add_days(today(), -1)
		application = self.make_leave_application(work_date, work_date)
		attendance = frappe.db.get_value(
			"Attendance", {"employee": self.employee.name, "attendance_date": work_date}, "name"
		)
		if not attendance:
			doc = frappe.get_doc(
				{
					"doctype": "Attendance",
					"employee": self.employee.name,
					"attendance_date": work_date,
					"status": "On Leave",
					"leave_type": application.leave_type,
					"leave_application": application.name,
					"company": "_Test Company",
				}
			)
			doc.insert()
			doc.submit()
			attendance = doc.name

		esc = self.make_request([{"work_date": work_date, "reason": LEAVE_DAY}], submit=True)

		record = frappe.get_doc("Attendance", attendance)
		self.assertEqual(record.status, "Present")
		self.assertIsNone(record.leave_application)
		self.assertIsNone(record.leave_type)
		self.assertEqual(record.custom_comp_off_override, 1)
		self.assertEqual(record.custom_comp_off_request, esc.name)
		self.assertEqual(esc.entries[0].original_attendance_status, "On Leave")
		self.assertEqual(esc.entries[0].original_leave_application, application.name)

	def test_override_survives_a_plain_save_in_desk(self):
		"""check_leave_record() reassigns status to On Leave on every validate; the
		doc_events hook has to put it back."""
		work_date = add_days(today(), -1)
		self.make_leave_application(work_date, work_date)
		self.make_request([{"work_date": work_date, "reason": LEAVE_DAY}], submit=True)

		name = frappe.db.get_value(
			"Attendance",
			{"employee": self.employee.name, "attendance_date": work_date, "docstatus": 1},
			"name",
		)
		record = frappe.get_doc("Attendance", name)
		record.save()

		record.reload()
		self.assertEqual(record.status, "Present")
		self.assertIsNone(record.leave_application)

	def test_leave_day_submit_creates_attendance_when_none_exists(self):
		work_date = add_days(today(), -1)
		self.make_leave_application(work_date, work_date)
		frappe.db.delete("Attendance", {"employee": self.employee.name, "attendance_date": work_date})

		esc = self.make_request([{"work_date": work_date, "reason": LEAVE_DAY}], submit=True)

		record = frappe.get_doc(
			"Attendance",
			frappe.db.get_value(
				"Attendance",
				{"employee": self.employee.name, "attendance_date": work_date, "docstatus": 1},
				"name",
			),
		)
		self.assertEqual(record.status, "Present")
		self.assertEqual(record.custom_comp_off_request, esc.name)
		self.assertFalse(esc.entries[0].original_attendance_status)

	def test_off_day_row_leaves_attendance_alone(self):
		esc = self.make_request([{"work_date": self.weekly_off, "reason": OFF_DAY}], submit=True)
		self.assertFalse(esc.entries[0].original_attendance_status)
		self.assertFalse(
			frappe.db.exists(
				"Attendance", {"employee": self.employee.name, "attendance_date": self.weekly_off}
			)
		)

	# --------------------------------------------------------------------- on cancel

	def test_cancel_decrements_the_allocation_and_keeps_pre_existing_days(self):
		existing = frappe.get_doc(
			{
				"doctype": "Leave Allocation",
				"employee": self.employee.name,
				"leave_type": self.leave_type,
				"from_date": add_months(today(), -6),
				"to_date": add_months(today(), 6),
				"new_leaves_allocated": 2.0,
			}
		)
		existing.insert()
		existing.submit()

		doc = self.make_request([{"work_date": self.weekly_off, "reason": OFF_DAY}], submit=True)
		existing.reload()
		self.assertEqual(flt(existing.new_leaves_allocated), 3.0)

		doc.cancel()

		existing.reload()
		self.assertEqual(flt(existing.new_leaves_allocated), 2.0)
		self.assertEqual(flt(existing.total_leaves_allocated), 2.0)
		self.assertEqual(existing.docstatus, 1)

	def test_cancel_does_not_delete_the_allocation(self):
		doc = self.make_request([{"work_date": self.weekly_off, "reason": OFF_DAY}], submit=True)
		allocation_name = doc.entries[0].leave_allocation
		doc.cancel()
		self.assertTrue(frappe.db.exists("Leave Allocation", allocation_name))

	def test_cancel_to_zero_days_is_possible_on_a_non_compensatory_leave_type(self):
		"""Leave Allocation.validate() throws when the total hits zero unless the leave
		type is compensatory or earned. Cancelling must not go through validate()."""
		self.assertEqual(frappe.db.get_value("Leave Type", self.leave_type, "is_compensatory"), 0)
		doc = self.make_request([{"work_date": self.weekly_off, "reason": OFF_DAY}], submit=True)
		allocation_name = doc.entries[0].leave_allocation

		doc.cancel()

		allocation = frappe.get_doc("Leave Allocation", allocation_name)
		self.assertEqual(flt(allocation.new_leaves_allocated), 0.0)
		self.assertEqual(flt(allocation.total_leaves_allocated), 0.0)

	def test_cancel_restores_attendance(self):
		work_date = add_days(today(), -1)
		application = self.make_leave_application(work_date, work_date)
		record = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.employee.name,
				"attendance_date": work_date,
				"status": "On Leave",
				"leave_type": application.leave_type,
				"leave_application": application.name,
				"company": "_Test Company",
			}
		)
		record.insert()
		record.submit()

		esc = self.make_request([{"work_date": work_date, "reason": LEAVE_DAY}], submit=True)
		esc.cancel()

		record.reload()
		self.assertEqual(record.status, "On Leave")
		self.assertEqual(record.leave_application, application.name)
		self.assertEqual(record.leave_type, application.leave_type)
		self.assertFalse(record.custom_comp_off_override)
		self.assertFalse(record.custom_comp_off_request)

	def test_cancel_reverses_attendance_it_created_itself(self):
		work_date = add_days(today(), -1)
		self.make_leave_application(work_date, work_date)
		frappe.db.delete("Attendance", {"employee": self.employee.name, "attendance_date": work_date})

		esc = self.make_request([{"work_date": work_date, "reason": LEAVE_DAY}], submit=True)
		created = frappe.db.get_value(
			"Attendance",
			{"employee": self.employee.name, "attendance_date": work_date, "docstatus": 1},
			"name",
		)
		esc.cancel()

		self.assertEqual(frappe.db.get_value("Attendance", created, "docstatus"), 2)

	def test_ledger_nets_to_zero_after_cancel(self):
		doc = self.make_request([{"work_date": self.weekly_off, "reason": OFF_DAY}], submit=True)
		allocation_name = doc.entries[0].leave_allocation
		doc.cancel()

		total = sum(
			flt(entry.leaves)
			for entry in frappe.get_all(
				"Leave Ledger Entry",
				filters={
					"transaction_type": "Leave Allocation",
					"transaction_name": allocation_name,
					"docstatus": 1,
				},
				fields=["leaves"],
			)
		)
		self.assertEqual(total, 0.0)
