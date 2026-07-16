import frappe
from frappe.utils import date_diff
from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee
from hrms.hr.doctype.compensatory_leave_request.compensatory_leave_request import (
	CompensatoryLeaveRequest,
)


class CustomCompensatoryLeaveRequest(CompensatoryLeaveRequest):
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
