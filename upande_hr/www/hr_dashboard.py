import frappe


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/hr-dashboard"
		raise frappe.Redirect

	context.no_cache = 1
	context.show_sidebar = False
	context.is_hr_manager = "HR Manager" in frappe.get_roles()
	context.user_email = frappe.session.user
	return context
