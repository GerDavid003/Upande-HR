import frappe
from frappe.utils import add_days, getdate, today
from hrms.hr.doctype.attendance_request.test_attendance_request import get_employee
from hrms.tests.utils import HRMSTestSuite

from upande_hr.contracts.backfill import backfill_contracts


class TestBackfill(HRMSTestSuite):
	def setUp(self):
		super().setUp()
		for name in ("Contract", "Probation"):
			if not frappe.db.exists("Employment Type", name):
				frappe.get_doc({"doctype": "Employment Type", "employee_type_name": name}).insert()
		self.employee = get_employee()
		self.name = self.employee.name
		frappe.db.delete("Employee Contract", {"employee": self.name})
		self._set(date_of_joining="2020-01-01", status="Active", employment_type="Contract",
			contract_end_date=add_days(today(), 100))

	def _set(self, **kw):
		frappe.db.set_value("Employee", self.name, kw)

	def _contracts(self):
		return frappe.get_all("Employee Contract", filters={"employee": self.name},
			fields=["name", "contract_number", "start_date", "status", "docstatus", "remarks"])

	def test_backfill_creates_contract(self):
		result = backfill_contracts()
		self.assertIn(self._contracts()[0].name, result["created"])
		rows = self._contracts()
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0].contract_number, 1)
		self.assertEqual(rows[0].docstatus, 1)
		self.assertEqual(rows[0].status, "Active")
		self.assertEqual(getdate(rows[0].start_date), getdate("2020-01-01"))
		self.assertEqual(rows[0].remarks, "Auto-created from Employee Contract End Date")

	def test_backfill_past_end_is_expired(self):
		self._set(contract_end_date=add_days(today(), -10))
		backfill_contracts()
		rows = self._contracts()
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0].status, "Expired")

	def test_backfill_idempotent(self):
		backfill_contracts()
		backfill_contracts()
		self.assertEqual(len(self._contracts()), 1)

	def test_backfill_skips_without_type(self):
		self._set(employment_type=None)
		frappe.rename_doc("Employment Type", "Contract", "Contract-tmp-bf", force=True)
		result = backfill_contracts()
		self.assertEqual(self._contracts(), [])
		self.assertIn(self.name, [e for e, _ in result["skipped"]])

	def test_backfill_skips_end_before_joining(self):
		self._set(contract_end_date="2019-06-01")
		result = backfill_contracts()
		self.assertEqual(self._contracts(), [])
		self.assertIn(self.name, [e for e, _ in result["skipped"]])
