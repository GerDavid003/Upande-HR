import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today


class IntegrationTestEmployeeReasonForExit(IntegrationTestCase):
	def setUp(self):
		# Excludes Frappe's own synthetic "_T-Employee-*" test fixtures: they
		# are intentionally minimal (missing designation, custom_business_unit,
		# custom_farm, etc.) and were never meant to satisfy this site's
		# custom mandatory fields, so picking one here would fail on those
		# unrelated to reason_for_exit. Real seeded Employee records are used
		# instead, per the instruction to use an existing Employee record.
		employees = frappe.get_all(
			"Employee",
			filters={"status": "Active", "name": ["not like", "_T-%"]},
			limit=1,
			pluck="name",
		)
		if not employees:
			self.skipTest("Need at least 1 Active Employee record on this site.")
		self.employee = frappe.get_doc("Employee", employees[0])
		# Unrelated pre-existing data gap on this site: employee_category is a
		# mandatory Employee field (added in an earlier task) but no Active
		# Employee has it set and no Employee Category records exist yet.
		# Backfill it in-memory (never persisted; IntegrationTestCase rolls
		# back) so these tests exercise reason_for_exit specifically instead
		# of failing on an unrelated MandatoryError.
		if not self.employee.employee_category:
			category = frappe.db.get_value("Employee Category", {}, "name")
			if not category:
				category = frappe.get_doc(
					{"doctype": "Employee Category", "category_name": "Test Category"}
				).insert(ignore_permissions=True).name
			self.employee.employee_category = category
		# Another unrelated pre-existing data gap: some Active Employees have
		# custom_ppe_history rows whose ppe_assignment link points at Employee
		# PPE Assignment records that no longer exist, which trips Frappe's
		# link validation on any save(). Drop dangling rows in-memory only
		# (never persisted) so these tests aren't blocked by that.
		valid_rows = [
			row
			for row in (self.employee.get("custom_ppe_history") or [])
			if not row.ppe_assignment or frappe.db.exists("Employee PPE Assignment", row.ppe_assignment)
		]
		self.employee.set("custom_ppe_history", valid_rows)

	def test_reason_for_exit_required_when_status_is_left(self):
		# relieving_date is set so the ValidationError we assert on below is
		# specifically the reason_for_exit check, not ERPNext core's
		# pre-existing "Please enter relieving date." requirement for Left.
		self.employee.status = "Left"
		self.employee.relieving_date = today()
		self.employee.reason_for_exit = None
		with self.assertRaisesRegex(frappe.ValidationError, "Reason for Exit"):
			self.employee.save()

	def test_reason_for_exit_not_required_when_status_is_not_left(self):
		self.employee.status = "Active"
		self.employee.reason_for_exit = None
		self.employee.save()  # must not raise

	def test_status_left_with_reason_for_exit_succeeds(self):
		separation_type = frappe.get_doc(
			{
				"doctype": "Employee Separation Type",
				"separation_type_name": "Test Resignation",
			}
		).insert(ignore_permissions=True)
		self.employee.status = "Left"
		self.employee.relieving_date = today()
		self.employee.reason_for_exit = separation_type.name
		self.employee.save()  # must not raise
