import frappe
from frappe import _
from frappe.permissions import get_user_permissions
from frappe.utils import getdate, nowdate

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


EMPLOYEE_FIELDS = [
	"name",
	"employee_number",
	"employee_name",
	"gender",
	"employee_category",
	"employment_type",
	"designation",
	"department",
	"custom_farm",
	"date_of_joining",
	"status",
	"company",
	"national_id",
	"tax_id",
	"sha_no",
	"nssf_no",
]


def _build_employee_conditions(company, department, employee_category, status, search):
	conditions = []
	_company_conditions(conditions, company)
	if department:
		conditions.append(["department", "=", department])
	if employee_category:
		conditions.append(["employee_category", "=", employee_category])
	if status:
		conditions.append(["status", "=", status])

	or_filters = None
	if search:
		term = f"%{search}%"
		or_filters = [
			["employee_name", "like", term],
			["employee_number", "like", term],
			["national_id", "like", term],
		]
	return conditions, or_filters


def _count_employees(conditions, or_filters):
	return len(
		frappe.get_list(
			"Employee",
			filters=conditions,
			or_filters=or_filters,
			pluck="name",
			limit_page_length=0,
		)
	)


def _current_shifts(employee_names):
	if not employee_names:
		return {}
	today = nowdate()
	rows = frappe.get_list(
		"Shift Assignment",
		filters=[
			["employee", "in", employee_names],
			["status", "=", "Active"],
			["docstatus", "=", 1],
			["start_date", "<=", today],
		],
		or_filters=[["end_date", "is", "not set"], ["end_date", ">=", today]],
		fields=["employee", "shift_type"],
		order_by="creation desc",
	)
	by_employee = {}
	for row in rows:
		by_employee.setdefault(row.employee, row.shift_type)
	return by_employee


def _current_week_offs(employee_names):
	"""Holiday List Assignment.holiday_list_start/holiday_list_end are virtual
	fields (see holiday_list_assignment.py), not database columns, so they
	can't be used in a filter here. Instead: fetch the candidate assignments,
	then check each one's linked Holiday List's real from_date/to_date columns
	in Python.
	"""
	if not employee_names:
		return {}
	today = getdate()
	rows = frappe.get_list(
		"Holiday List Assignment",
		filters=[
			["applicable_for", "=", "Employee"],
			["assigned_to", "in", employee_names],
			["docstatus", "=", 1],
		],
		fields=["assigned_to", "holiday_list"],
		order_by="creation desc",
	)
	if not rows:
		return {}

	holiday_list_names = list({row.holiday_list for row in rows if row.holiday_list})
	holiday_lists = {
		holiday_list.name: holiday_list
		for holiday_list in frappe.get_list(
			"Holiday List",
			filters=[["name", "in", holiday_list_names]],
			fields=["name", "from_date", "to_date", "weekly_off"],
		)
	}

	by_employee = {}
	for row in rows:
		if row.assigned_to in by_employee:
			continue
		holiday_list = holiday_lists.get(row.holiday_list)
		if not holiday_list:
			continue
		if getdate(holiday_list.from_date) > today:
			continue
		if holiday_list.to_date and getdate(holiday_list.to_date) < today:
			continue
		by_employee[row.assigned_to] = holiday_list.weekly_off
	return by_employee


@frappe.whitelist()
def get_dashboard_data(
	company=None,
	department=None,
	employee_category=None,
	status=None,
	search=None,
	start=0,
	page_length=50,
):
	check_hr_manager()
	start = int(start)
	page_length = int(page_length)
	conditions, or_filters = _build_employee_conditions(
		company, department, employee_category, status, search
	)

	total = _count_employees(conditions, or_filters)

	employees = frappe.get_list(
		"Employee",
		filters=conditions,
		or_filters=or_filters,
		fields=EMPLOYEE_FIELDS,
		order_by="employee_name asc",
		start=start,
		limit=page_length,
	)

	page_names = [employee.name for employee in employees]
	shifts = _current_shifts(page_names)
	week_offs = _current_week_offs(page_names)
	for employee in employees:
		employee["shift"] = shifts.get(employee.name)
		employee["week_off"] = week_offs.get(employee.name)

	gender_breakdown = frappe.get_list(
		"Employee",
		filters=conditions,
		or_filters=or_filters,
		group_by="gender",
		# Dict syntax required for aggregates on this Frappe version -- a plain
		# string like "count(name) as count" raises ValidationError ("SQL
		# functions are not allowed as strings in SELECT"). Verified directly:
		# frappe.get_list("Employee", group_by="gender",
		#   fields=["gender", {"COUNT": "name", "as": "count"}]) returns
		# [{'gender': 'Female', 'count': 1357}, {'gender': 'Male', 'count': 1251}].
		fields=["gender", {"COUNT": "name", "as": "count"}],
		order_by="count desc",
	)

	kpis = {
		"total": total,
		"active": _count_employees(conditions + [["status", "=", "Active"]], or_filters),
		"left_or_inactive": _count_employees(
			conditions + [["status", "in", ["Left", "Inactive"]]], or_filters
		),
		"gender_breakdown": gender_breakdown,
	}

	return {"employees": employees, "total": total, "kpis": kpis}
