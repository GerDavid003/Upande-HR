import frappe
from frappe import _
from frappe.utils import date_diff
from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee
from hrms.hr.doctype.compensatory_leave_request.compensatory_leave_request import (
	CompensatoryLeaveRequest,
)


class CustomCompensatoryLeaveRequest(CompensatoryLeaveRequest):
	def validate_attendance(self):
		if self.is_weekly_off_request():
			self.add_weekly_off_note()
			return
		super().validate_attendance()

	def is_weekly_off_request(self):
		holiday_list = get_holiday_list_for_employee(self.employee, raise_exception=False)
		if not holiday_list:
			return False

		total_days = date_diff(self.work_end_date, self.work_from_date) + 1
		weekly_off_days = frappe.get_all(
			"Holiday",
			filters={
				"parent": holiday_list,
				"holiday_date": ("between", [self.work_from_date, self.work_end_date]),
				"weekly_off": 1,
			},
			pluck="holiday_date",
		)
		return len(weekly_off_days) == total_days

	def add_weekly_off_note(self):
		note_marker = _("Attendance not required")
		note = _("Attendance not required — {0} to {1} falls on {2}'s weekly off.").format(
			self.work_from_date, self.work_end_date, self.employee_name or self.employee
		)
		if note_marker not in (self.reason or ""):
			self.reason = f"{self.reason}\n{note}".strip() if self.reason else note
