import frappe
from frappe.utils import getdate
from hrms.hr.doctype.attendance_request.test_attendance_request import get_employee
from hrms.tests.utils import HRMSTestSuite


def make_contract(employee, start_date, end_date, employment_type="Contract", submit=True, **kw):
	doc = frappe.get_doc(
		{
			"doctype": "Employee Contract",
			"employee": employee,
			"employment_type": employment_type,
			"start_date": start_date,
			"end_date": end_date,
			**kw,
		}
	)
	doc.insert()
	if submit:
		doc.submit()
	return doc


class TestEmployeeContract(HRMSTestSuite):
	def setUp(self):
		super().setUp()
		for name in ("Contract", "Probation"):
			if not frappe.db.exists("Employment Type", name):
				frappe.get_doc({"doctype": "Employment Type", "employee_type_name": name}).insert()
		self.employee = get_employee()
		frappe.db.set_value("Employee", self.employee.name, {"date_of_joining": "2020-01-01", "status": "Active"})
		for c in frappe.get_all("Employee Contract", {"employee": self.employee.name}, pluck="name"):
			frappe.db.delete("Employee Contract", {"name": c})

	def test_contract_numbers_sequence(self):
		e = self.employee.name
		c1 = make_contract(e, "2026-01-01", "2026-03-31")
		c2 = make_contract(e, "2026-04-01", "2026-06-30")
		c3 = make_contract(e, "2026-07-01", "2026-09-30")
		self.assertEqual([c1.contract_number, c2.contract_number, c3.contract_number], [1, 2, 3])
		c3.cancel()
		c4 = make_contract(e, "2026-07-01", "2026-09-30")
		self.assertEqual(c4.contract_number, 3)

	def test_end_before_start_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			make_contract(self.employee.name, "2026-03-01", "2026-02-01", submit=False)

	def test_start_before_joining_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			make_contract(self.employee.name, "2019-01-01", "2019-12-31", submit=False)

	def test_overlap_rejected(self):
		e = self.employee.name
		make_contract(e, "2026-01-01", "2026-03-31")
		with self.assertRaises(frappe.ValidationError):
			make_contract(e, "2026-03-15", "2026-06-30")
		ok = make_contract(e, "2026-04-01", "2026-06-30")
		self.assertEqual(ok.docstatus, 1)

	def test_left_employee_rejected(self):
		frappe.db.set_value("Employee", self.employee.name, "status", "Left")
		with self.assertRaises(frappe.ValidationError):
			make_contract(self.employee.name, "2026-01-01", "2026-03-31", submit=False)

	def test_submit_sets_active(self):
		c = make_contract(self.employee.name, "2026-01-01", "2026-03-31")
		self.assertEqual(c.status, "Active")

	def test_duration_months_sets_end_date(self):
		c = frappe.get_doc(
			{
				"doctype": "Employee Contract",
				"employee": self.employee.name,
				"employment_type": "Contract",
				"start_date": "2026-01-01",
				"duration_months": 3,
			}
		).insert()
		self.assertEqual(getdate(c.end_date), getdate("2026-03-31"))
