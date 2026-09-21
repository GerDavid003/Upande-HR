import frappe
from frappe.tests import IntegrationTestCase

from upande_hr.www import hr_dashboard


class IntegrationTestHRDashboardContext(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_guest_is_redirected_to_login(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.Redirect):
			hr_dashboard.get_context({})
		self.assertEqual(
			frappe.local.flags.redirect_location, "/login?redirect-to=/hr-dashboard"
		)

	def test_hr_manager_context_flags_allowed(self):
		frappe.set_user("teddy@upande.com")
		context = frappe._dict()
		hr_dashboard.get_context(context)
		self.assertTrue(context.is_hr_manager)
		self.assertEqual(context.user_email, "teddy@upande.com")
		self.assertEqual(context.no_cache, 1)
		self.assertFalse(context.show_sidebar)

	def test_non_hr_manager_context_flags_denied(self):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": "no-hr-role-2@example.com",
				"first_name": "No HR Role 2",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
		frappe.set_user(user.name)
		context = frappe._dict()
		hr_dashboard.get_context(context)
		self.assertFalse(context.is_hr_manager)
