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
