import frappe
from frappe.utils import add_days, getdate, today
from hrms.hr.doctype.attendance_request.test_attendance_request import get_employee
from hrms.tests.utils import HRMSTestSuite

from upande_hr.upande_hr.doctype.employee_contract.employee_contract import (
	confirm_as_permanent,
	make_renewal,
)


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
		for name in ("Contract", "Probation", "Full-time"):
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

	def _emp(self, field):
		return frappe.db.get_value("Employee", self.employee.name, field)

	def _status(self, c):
		return frappe.db.get_value("Employee Contract", c.name, "status")

	def test_left_employee_allows_update_after_submit(self):
		c = make_contract(self.employee.name, "2026-01-01", "2026-03-31")
		frappe.db.set_value("Employee", self.employee.name, "status", "Left")
		c = frappe.get_doc("Employee Contract", c.name)
		c.signed_contract = "/files/signed.pdf"
		c.save()
		self.assertEqual(frappe.db.get_value("Employee Contract", c.name, "signed_contract"), "/files/signed.pdf")

	def test_missing_dates_show_mandatory(self):
		with self.assertRaises(frappe.MandatoryError):
			frappe.get_doc(
				{"doctype": "Employee Contract", "employee": self.employee.name, "employment_type": "Contract"}
			).insert()

	def test_submit_syncs_employee(self):
		make_contract(self.employee.name, "2026-01-01", "2026-03-31")
		self.assertEqual(getdate(self._emp("contract_end_date")), getdate("2026-03-31"))
		self.assertEqual(self._emp("employment_type"), "Contract")

	def test_renewal_marks_previous_renewed(self):
		e = self.employee.name
		c1 = make_contract(e, "2026-01-01", "2026-03-31")
		d = make_renewal(c1.name)
		self.assertEqual(getdate(d["start_date"]), getdate("2026-04-01"))
		self.assertEqual(d["previous_contract"], c1.name)
		d.update({"end_date": "2026-06-30"})
		c2 = frappe.get_doc(d).insert()
		c2.submit()
		self.assertEqual(self._status(c1), "Renewed")
		self.assertEqual(getdate(self._emp("contract_end_date")), getdate("2026-06-30"))

	def _two(self):
		e = self.employee.name
		c1 = make_contract(e, "2026-01-01", "2026-03-31", employment_type="Probation")
		d = make_renewal(c1.name)
		d.update({"end_date": "2026-06-30", "employment_type": "Contract"})
		c2 = frappe.get_doc(d).insert()
		c2.submit()
		return c1, c2

	def test_confirm_sets_employee(self):
		c1, c2 = self._two()
		confirm_as_permanent(c2.name, "2026-07-01", "Full-time")
		self.assertEqual(self._status(c2), "Confirmed")
		self.assertEqual(frappe.db.get_value("Employee Contract", c2.name, "confirmed_employment_type"), "Full-time")
		self.assertEqual(getdate(self._emp("final_confirmation_date")), getdate("2026-07-01"))
		self.assertEqual(self._emp("employment_type"), "Full-time")
		self.assertIsNone(self._emp("contract_end_date"))

	def test_confirm_requires_employment_type(self):
		c1, c2 = self._two()
		with self.assertRaises(frappe.ValidationError):
			confirm_as_permanent(c2.name, "2026-07-01", "")
		with self.assertRaises(frappe.ValidationError):
			confirm_as_permanent(c2.name, "", "Full-time")

	def test_confirm_requires_latest(self):
		c1, c2 = self._two()
		with self.assertRaises(frappe.ValidationError):
			confirm_as_permanent(c1.name, "2026-07-01", "Full-time")

	def test_no_contract_after_confirmed(self):
		c1, c2 = self._two()
		confirm_as_permanent(c2.name, "2026-07-01", "Full-time")
		with self.assertRaises(frappe.ValidationError):
			make_contract(self.employee.name, "2026-07-01", "2026-09-30", submit=False)
		with self.assertRaises(frappe.ValidationError):
			make_renewal(c2.name)

	def test_renewal_requires_active(self):
		c1, c2 = self._two()
		with self.assertRaises(frappe.ValidationError):
			make_renewal(c1.name)

	def test_cancel_latest_restores_previous(self):
		c1, c2 = self._two()
		c2.cancel()
		self.assertEqual(self._status(c2), "Cancelled")
		self.assertEqual(self._status(c1), "Active" if getdate("2026-03-31") >= getdate(today()) else "Expired")
		self.assertEqual(getdate(self._emp("contract_end_date")), getdate("2026-03-31"))

	def test_cancel_confirmed_restores_previous(self):
		c1, c2 = self._two()
		confirm_as_permanent(c2.name, "2026-07-01", "Full-time")
		c2 = frappe.get_doc("Employee Contract", c2.name)
		c2.cancel()
		self.assertEqual(self._status(c1), "Active" if getdate("2026-03-31") >= getdate(today()) else "Expired")
		self.assertEqual(getdate(self._emp("contract_end_date")), getdate("2026-03-31"))
		self.assertEqual(self._emp("employment_type"), "Probation")
		self.assertIsNone(self._emp("final_confirmation_date"))

	def test_manual_final_confirmation_survives_submit(self):
		frappe.db.set_value("Employee", self.employee.name, "final_confirmation_date", "2025-05-05")
		make_contract(self.employee.name, "2026-01-01", "2026-03-31")
		self.assertEqual(getdate(self._emp("final_confirmation_date")), getdate("2025-05-05"))

	def test_amended_old_contract_does_not_become_latest(self):
		e = self.employee.name
		c1 = make_contract(e, "2026-01-01", "2026-03-31", employment_type="Probation")
		c2 = make_contract(e, "2026-04-01", "2026-06-30")
		c1.cancel()
		amended = make_contract(
			e, "2026-01-01", "2026-03-31", employment_type="Probation", amended_from=c1.name
		)
		self.assertEqual(getdate(self._emp("contract_end_date")), getdate("2026-06-30"))
		self.assertEqual(self._emp("employment_type"), "Contract")
		confirm_as_permanent(c2.name, "2026-07-01", "Full-time")
		self.assertEqual(self._status(c2), "Confirmed")

	def test_renew_from_expired(self):
		c1 = make_contract(self.employee.name, "2026-01-01", "2026-03-31")
		frappe.db.set_value("Employee Contract", c1.name, "status", "Expired")
		d = make_renewal(c1.name)
		d.update({"end_date": "2026-06-30"})
		c2 = frappe.get_doc(d).insert()
		c2.submit()
		self.assertEqual(self._status(c1), "Renewed")

	def test_renew_non_latest_refused(self):
		c1, c2 = self._two()
		frappe.db.set_value("Employee Contract", c1.name, "status", "Active")
		with self.assertRaises(frappe.ValidationError):
			make_renewal(c1.name)

	def test_confirm_before_start_rejected(self):
		c1, c2 = self._two()
		with self.assertRaises(frappe.ValidationError):
			confirm_as_permanent(c2.name, "2026-03-31", "Full-time")

	def test_confirm_left_employee_rejected(self):
		c1, c2 = self._two()
		frappe.db.set_value("Employee", self.employee.name, "status", "Left")
		with self.assertRaises(frappe.ValidationError):
			confirm_as_permanent(c2.name, "2026-07-01", "Full-time")

	def test_confirm_adds_comment(self):
		c1, c2 = self._two()
		confirm_as_permanent(c2.name, "2026-07-01", "Full-time")
		self.assertTrue(
			frappe.db.exists(
				"Comment",
				{"reference_doctype": "Employee Contract", "reference_name": c2.name, "comment_type": "Info"},
			)
		)

	def test_cancel_only_contract_leaves_employee(self):
		c1 = make_contract(self.employee.name, "2026-01-01", "2026-03-31")
		before = (self._emp("contract_end_date"), self._emp("employment_type"))
		c1.cancel()
		self.assertEqual((self._emp("contract_end_date"), self._emp("employment_type")), before)

	def test_submit_draft_after_confirmed_rejected(self):
		c1, c2 = self._two()
		d = make_renewal(c2.name)
		d.update({"end_date": "2026-09-30"})
		c3 = frappe.get_doc(d).insert()
		confirm_as_permanent(c2.name, "2026-07-01", "Full-time")
		with self.assertRaises(frappe.ValidationError):
			c3.submit()

	def test_submit_draft_for_left_employee_rejected(self):
		c = make_contract(self.employee.name, "2026-01-01", "2026-03-31", submit=False)
		frappe.db.set_value("Employee", self.employee.name, "status", "Left")
		with self.assertRaises(frappe.ValidationError):
			c.submit()

	def test_previous_contract_must_match_employee(self):
		c1 = make_contract(self.employee.name, "2026-01-01", "2026-03-31")
		other = frappe.get_all("Employee", filters={"name": ["!=", self.employee.name]}, limit=1, pluck="name")
		if not other:
			self.skipTest("no second employee")
		with self.assertRaises(frappe.ValidationError):
			make_contract(other[0], "2026-04-01", "2026-06-30", submit=False, previous_contract=c1.name)

	def test_dashboard_includes_contracts(self):
		data = frappe.get_meta("Employee").get_dashboard_data()
		items = [i for group in data.transactions for i in group.get("items", [])]
		self.assertIn("Employee Contract", items)
