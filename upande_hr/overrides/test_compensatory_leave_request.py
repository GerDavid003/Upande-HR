import frappe
from frappe.utils import add_days, add_months, today
from hrms.tests.utils import HRMSTestSuite

from hrms.hr.doctype.attendance_request.test_attendance_request import get_employee
from hrms.hr.doctype.holiday_list_assignment.test_holiday_list_assignment import (
	create_holiday_list_assignment,
)
from hrms.hr.doctype.leave_period.test_leave_period import create_leave_period

from upande_hr.overrides.compensatory_leave_request import CustomCompensatoryLeaveRequest


def create_holiday_list_with_weekly_off(weekly_off_date, holiday_list_name="_Test Upande HR Weekly Off"):
	if frappe.db.exists("Holiday List", holiday_list_name):
		frappe.db.delete("Holiday List", holiday_list_name)
		frappe.db.delete("Holiday", {"parent": holiday_list_name})

	holiday_list = frappe.get_doc(
		{
			"doctype": "Holiday List",
			"holiday_list_name": holiday_list_name,
			"from_date": add_months(today(), -3),
			"to_date": add_months(today(), 3),
			"holidays": [
				{
					"description": "Weekly Off",
					"holiday_date": weekly_off_date,
					"weekly_off": 1,
				},
				{
					"description": "Regular Holiday",
					"holiday_date": add_days(weekly_off_date, -1),
					"weekly_off": 0,
				},
			],
		}
	)
	holiday_list.save()
	return holiday_list


class TestCustomCompensatoryLeaveRequest(HRMSTestSuite):
	def test_controller_override_is_active(self):
		doc = frappe.new_doc("Compensatory Leave Request")
		self.assertIsInstance(doc, CustomCompensatoryLeaveRequest)

	def test_is_weekly_off_request_true_when_range_is_all_weekly_off(self):
		create_leave_period(add_months(today(), -3), add_months(today(), 3), "_Test Company")
		weekly_off_date = today()
		holiday_list = create_holiday_list_with_weekly_off(weekly_off_date)
		employee = get_employee()
		create_holiday_list_assignment("Employee", employee.name, holiday_list.name)

		doc = frappe.new_doc("Compensatory Leave Request")
		doc.update(
			{
				"employee": employee.name,
				"leave_type": "Compensatory Off",
				"work_from_date": weekly_off_date,
				"work_end_date": weekly_off_date,
				"reason": "test",
			}
		)
		self.assertTrue(doc.is_weekly_off_request())

	def test_is_weekly_off_request_false_for_regular_holiday(self):
		create_leave_period(add_months(today(), -3), add_months(today(), 3), "_Test Company")
		weekly_off_date = today()
		regular_holiday_date = add_days(weekly_off_date, -1)
		holiday_list = create_holiday_list_with_weekly_off(weekly_off_date)
		employee = get_employee()
		create_holiday_list_assignment("Employee", employee.name, holiday_list.name)

		doc = frappe.new_doc("Compensatory Leave Request")
		doc.update(
			{
				"employee": employee.name,
				"leave_type": "Compensatory Off",
				"work_from_date": regular_holiday_date,
				"work_end_date": regular_holiday_date,
				"reason": "test",
			}
		)
		self.assertFalse(doc.is_weekly_off_request())
