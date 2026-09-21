import frappe
from frappe.tests import IntegrationTestCase

from upande_hr.api import hr_dashboard


class IntegrationTestHRDashboardPermissions(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_non_hr_manager_is_denied(self):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": "no-hr-role@example.com",
				"first_name": "No HR Role",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
		frappe.set_user(user.name)
		self.assertRaises(frappe.PermissionError, hr_dashboard.get_filter_options)

	def test_hr_manager_is_allowed(self):
		frappe.set_user("teddy@upande.com")
		result = hr_dashboard.get_filter_options()
		self.assertIn("companies", result)
		self.assertEqual(result["statuses"], ["Active", "Inactive", "Suspended", "Left"])


class IntegrationTestHRDashboardFilterOptionsCompanyScoping(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_unrestricted_hr_manager_sees_all_companies(self):
		frappe.set_user("teddy@upande.com")
		result = hr_dashboard.get_filter_options()
		self.assertGreater(len(result["companies"]), 1)
		self.assertIn("Karen Roses", result["companies"])

	def test_company_restricted_hr_manager_sees_only_their_company(self):
		frappe.set_user("pkiarie@karenroses.com")
		result = hr_dashboard.get_filter_options()
		self.assertEqual(result["companies"], ["Karen Roses"])


class IntegrationTestHRDashboardData(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_pagination_and_total_are_consistent(self):
		frappe.set_user("teddy@upande.com")
		expected_total = frappe.db.count("Employee")
		result = hr_dashboard.get_dashboard_data(page_length=10)
		self.assertEqual(result["total"], expected_total)
		self.assertEqual(len(result["employees"]), 10)
		self.assertEqual(result["kpis"]["total"], expected_total)

	def test_status_filter_narrows_results_and_kpis(self):
		frappe.set_user("teddy@upande.com")
		expected_active = frappe.db.count("Employee", {"status": "Active"})
		result = hr_dashboard.get_dashboard_data(status="Active", page_length=5)
		self.assertEqual(result["total"], expected_active)
		self.assertEqual(result["kpis"]["active"], expected_active)
		for employee in result["employees"]:
			self.assertEqual(employee["status"], "Active")

	def test_search_matches_employee_name(self):
		frappe.set_user("teddy@upande.com")
		sample = frappe.db.get_value("Employee", {"employee_name": ["!=", ""]}, "employee_name")
		term = sample[:4]
		result = hr_dashboard.get_dashboard_data(search=term, page_length=1)
		self.assertGreaterEqual(result["total"], 1)

	def test_gender_breakdown_sums_to_total(self):
		frappe.set_user("teddy@upande.com")
		result = hr_dashboard.get_dashboard_data(page_length=1)
		breakdown_sum = sum(row["count"] for row in result["kpis"]["gender_breakdown"])
		self.assertEqual(breakdown_sum, result["total"])


class IntegrationTestHRDashboardDataCompanyScoping(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_company_restricted_user_sees_only_their_company(self):
		frappe.set_user("pkiarie@karenroses.com")
		expected_total = frappe.db.count("Employee", {"company": "Karen Roses"})
		result = hr_dashboard.get_dashboard_data(page_length=1)
		self.assertEqual(result["total"], expected_total)
		for employee in result["employees"]:
			self.assertEqual(employee["company"], "Karen Roses")

	def test_company_restricted_user_requesting_other_company_gets_nothing(self):
		frappe.set_user("pkiarie@karenroses.com")
		result = hr_dashboard.get_dashboard_data(company="Kaitet Ltd.", page_length=1)
		self.assertEqual(result["total"], 0)
		self.assertEqual(result["employees"], [])
