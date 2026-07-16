import frappe
from hrms.tests.utils import HRMSTestSuite

from upande_hr.overrides.compensatory_leave_request import CustomCompensatoryLeaveRequest


class TestCustomCompensatoryLeaveRequest(HRMSTestSuite):
	def test_controller_override_is_active(self):
		doc = frappe.new_doc("Compensatory Leave Request")
		self.assertIsInstance(doc, CustomCompensatoryLeaveRequest)
