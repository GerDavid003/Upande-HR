import frappe
from frappe import _
from frappe.permissions import get_user_permissions

STATUS_OPTIONS = ["Active", "Inactive", "Suspended", "Left"]


def check_hr_manager():
	if "HR Manager" not in frappe.get_roles():
		frappe.throw(
			_("You are not permitted to access the HR Dashboard."), frappe.PermissionError
		)


def _allowed_companies():
	"""None means unrestricted (sees all companies). Otherwise a list of
	company names this session's user is explicitly restricted to, per
	their Company User Permission records. Company User Permissions in
	this system are scoped with applicable_for="Company" so Frappe's
	ambient permission engine does NOT cascade them onto the Employee
	doctype on its own -- this dashboard enforces the restriction itself.
	"""
	user = frappe.session.user
	if user in ("Administrator", "Guest"):
		return None
	permissions = get_user_permissions(user).get("Company")
	if not permissions:
		return None
	return [permission.doc for permission in permissions]


def _company_conditions(conditions, requested_company):
	allowed = _allowed_companies()
	if allowed is None:
		if requested_company:
			conditions.append(["company", "=", requested_company])
		return conditions
	if requested_company:
		effective = [requested_company] if requested_company in allowed else []
	else:
		effective = allowed
	conditions.append(["company", "in", effective])
	return conditions


@frappe.whitelist()
def get_filter_options():
	check_hr_manager()
	allowed = _allowed_companies()
	company_conditions = [["name", "in", allowed]] if allowed is not None else []
	company_field_conditions = [["company", "in", allowed]] if allowed is not None else []
	return {
		"companies": frappe.get_list(
			"Company", filters=company_conditions, pluck="name", order_by="name"
		),
		"departments": frappe.get_list(
			"Department", filters=company_field_conditions, pluck="name", order_by="name"
		),
		"employee_categories": frappe.get_list(
			"Employee Category", filters=company_field_conditions, pluck="name", order_by="name"
		),
		"statuses": STATUS_OPTIONS,
	}
