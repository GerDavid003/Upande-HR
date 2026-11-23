from unittest.mock import patch

import frappe
from frappe.utils import add_days, getdate, nowdate
from hrms.tests.utils import HRMSTestSuite
from hrms.tests.test_utils import create_company
from erpnext.setup.doctype.employee.test_employee import make_employee
from hrms.hr.doctype.leave_type.test_leave_type import create_leave_type
from hrms.hr.doctype.leave_policy.test_leave_policy import create_leave_policy

from upande_hr.overrides.leave_application import CustomLeaveApplication

COMPANY = "_Test Karen Roses"


def setup_karen_roses_employee(annual_days=25, compassionate_days=12):
	"""Creates a fresh Company + Employee + Leave Policy Assignment granting
	both Annual Leave and Compassionate Leave, mirroring the real Karen Roses
	setup (Leave Policy with both leave types, Leave Policy Assignment)."""
	create_company(name=COMPANY)

	annual = create_leave_type(leave_type_name="Annual Leave", allow_negative=1)
	compassionate = create_leave_type(leave_type_name="Compassionate Leave", allow_negative=0)

	leave_policy = frappe.get_doc(
		{
			"doctype": "Leave Policy",
			"title": "_Test Karen Roses Leave Policy",
			"leave_policy_details": [
				{"leave_type": annual.name, "annual_allocation": annual_days},
				{"leave_type": compassionate.name, "annual_allocation": compassionate_days},
			],
		}
	).submit()

	employee_name = make_employee(
		"test_karen_roses_employee@example.com", company=COMPANY, date_of_joining=add_days(nowdate(), -365)
	)

	assignment = frappe.new_doc("Leave Policy Assignment")
	assignment.employee = employee_name
	assignment.leave_policy = leave_policy.name
	assignment.effective_from = add_days(nowdate(), -30)
	assignment.effective_to = add_days(nowdate(), 335)
	assignment.submit()

	return employee_name


def make_leave_application(employee, from_date, to_date, is_compassionate=0, company=COMPANY):
	doc = frappe.get_doc(
		{
			"doctype": "Leave Application",
			"employee": employee,
			"leave_type": "Annual Leave",
			"company": company,
			"from_date": from_date,
			"to_date": to_date,
			"status": "Approved",
			"custom_is_compassionate": is_compassionate,
		}
	)
	doc.insert()
	return doc


class TestCustomLeaveApplication(HRMSTestSuite):
	def test_controller_override_is_active(self):
		doc = frappe.new_doc("Leave Application")
		self.assertIsInstance(doc, CustomLeaveApplication)

	def test_checkbox_gate_matches_annual_leave_and_karen_roses_only(self):
		employee = setup_karen_roses_employee()
		doc = make_leave_application(employee, nowdate(), nowdate(), is_compassionate=1)
		self.assertTrue(doc._is_compassionate())

		doc.company = "_Test Company"
		self.assertFalse(doc._is_compassionate())

		doc.company = COMPANY
		doc.leave_type = "Compassionate Leave"
		self.assertFalse(doc._is_compassionate())

	def test_compassionate_application_deducts_both_ledgers(self):
		employee = setup_karen_roses_employee()
		doc = make_leave_application(
			employee, nowdate(), add_days(nowdate(), 4), is_compassionate=1
		)
		doc.submit()

		annual_entry = frappe.db.exists(
			"Leave Ledger Entry",
			{"transaction_name": doc.name, "leave_type": "Annual Leave", "docstatus": 1},
		)
		compassionate_entry = frappe.db.exists(
			"Leave Ledger Entry",
			{"transaction_name": doc.name, "leave_type": "Compassionate Leave", "docstatus": 1},
		)
		self.assertTrue(annual_entry)
		self.assertTrue(compassionate_entry)

		compassionate_leaves = frappe.db.get_value("Leave Ledger Entry", compassionate_entry, "leaves")
		self.assertEqual(compassionate_leaves, -5)

		doc.reload()
		self.assertIn("Compassionate Leave applied: 5", doc.custom_compassionate_balance_note)

	def test_compassionate_application_over_balance_is_blocked(self):
		employee = setup_karen_roses_employee(compassionate_days=3)
		doc = make_leave_application(
			employee, nowdate(), add_days(nowdate(), 4), is_compassionate=1
		)
		with self.assertRaises(frappe.ValidationError):
			doc.submit()

	def test_non_compassionate_annual_leave_untouched(self):
		employee = setup_karen_roses_employee()
		doc = make_leave_application(
			employee, nowdate(), add_days(nowdate(), 1), is_compassionate=0
		)
		doc.submit()

		compassionate_entry = frappe.db.exists(
			"Leave Ledger Entry",
			{"transaction_name": doc.name, "leave_type": "Compassionate Leave"},
		)
		self.assertFalse(compassionate_entry)

	def test_cancelling_compassionate_application_removes_both_ledger_entries(self):
		employee = setup_karen_roses_employee()
		doc = make_leave_application(
			employee, nowdate(), add_days(nowdate(), 2), is_compassionate=1
		)
		doc.submit()
		doc.cancel()

		annual_entry = frappe.db.exists(
			"Leave Ledger Entry",
			{"transaction_name": doc.name, "leave_type": "Annual Leave", "docstatus": 1},
		)
		compassionate_entry = frappe.db.exists(
			"Leave Ledger Entry",
			{"transaction_name": doc.name, "leave_type": "Compassionate Leave", "docstatus": 1},
		)
		self.assertFalse(annual_entry)
		self.assertFalse(compassionate_entry)


class TestLeaveApplicationFarmAndLeaveTypeGate(HRMSTestSuite):
	def setUp(self):
		# Gate the test company instead of the real "Karen Roses".
		patcher = patch("upande_hr.overrides.leave_application.COMPASSIONATE_GATED_COMPANY", COMPANY)
		patcher.start()
		self.addCleanup(patcher.stop)

	def _new_application(self, employee, leave_type):
		return frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": employee,
				"leave_type": leave_type,
				"from_date": nowdate(),
				"to_date": nowdate(),
				"status": "Open",
			}
		)

	def test_farm_is_fetched_from_employee(self):
		employee = setup_karen_roses_employee()
		farm = frappe.get_all("Farm", pluck="name", limit=1)
		if not farm:
			self.skipTest("No Farm records on this site")
		frappe.db.set_value("Employee", employee, "custom_farm", farm[0])

		doc = make_leave_application(employee, nowdate(), nowdate())
		self.assertEqual(doc.custom_farm, farm[0])

	def test_new_compassionate_leave_type_blocked_for_gated_company(self):
		employee = setup_karen_roses_employee()
		with self.assertRaisesRegex(frappe.ValidationError, "cannot apply for Compassionate Leave directly"):
			self._new_application(employee, "Compassionate Leave").insert()

	def test_changing_to_compassionate_leave_type_blocked_for_gated_company(self):
		employee = setup_karen_roses_employee()
		doc = make_leave_application(employee, nowdate(), nowdate())
		doc.leave_type = "Compassionate Leave"
		with self.assertRaisesRegex(frappe.ValidationError, "cannot apply for Compassionate Leave directly"):
			doc.save()

	def test_existing_compassionate_draft_can_still_be_saved(self):
		employee = setup_karen_roses_employee()
		with patch("upande_hr.overrides.leave_application.COMPASSIONATE_GATED_COMPANY", "_No Such Company"):
			doc = self._new_application(employee, "Compassionate Leave").insert()
		doc.description = "edited after the gate went live"
		doc.save()  # must not raise

	def test_compassionate_leave_type_allowed_for_other_companies(self):
		employee = setup_karen_roses_employee()
		with patch("upande_hr.overrides.leave_application.COMPASSIONATE_GATED_COMPANY", "_No Such Company"):
			self._new_application(employee, "Compassionate Leave").insert()  # must not raise
