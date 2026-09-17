# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Talent Pool - internal and external candidates in one list.

Employees and Job Applicants are queried separately and concatenated rather than joined
with a SQL UNION. The two column sets already diverge (department vs email, status vs
applied-for) and a UNION becomes unreadable the first time either side gains a field.

The applicant half is optional. upande_hr does not declare upande_ats in required_apps,
and the Job Applicant fields ship from this app's fixture, so on a site where they are
absent the report returns the employee half with a note instead of throwing.
"""

import frappe
from frappe import _

CHILD_DOCTYPE = "Talent Pool Designation"
DESIGNATIONS_FIELD = "custom_talent_pool_designations"
FLAG_FIELD = "custom_talent_pool"

EMPLOYEE = "Employee"
JOB_APPLICANT = "Job Applicant"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	source = filters.get("source") or "All"

	rows = []
	messages = []

	if source in ("All", "Employees"):
		rows += get_employees(filters)

	if source in ("All", "Job Applicants"):
		if has_talent_pool_fields(JOB_APPLICANT):
			rows += get_job_applicants(filters)
		else:
			messages.append(
				_("Job Applicant talent pool fields are not installed on this site; showing employees only.")
			)

	rows.sort(key=lambda r: (r.get("source") or "", r.get("person_name") or ""))
	return get_columns(), rows, "<br>".join(messages) or None


def has_talent_pool_fields(doctype: str) -> bool:
	"""True only if both the flag and the child rows can actually be read."""
	if not frappe.db.table_exists(doctype):
		return False
	return frappe.db.has_column(doctype, FLAG_FIELD)


def get_designation_map(parenttype: str, parents: list[str]) -> dict[str, list[str]]:
	"""Suitable designations per parent.

	Filtered by parenttype *and* parentfield: Employee and Job Applicant share this one
	child DocType, so an unfiltered query returns the other population's rows.
	"""
	if not parents:
		return {}

	rows = frappe.get_all(
		CHILD_DOCTYPE,
		filters={
			"parenttype": parenttype,
			"parentfield": DESIGNATIONS_FIELD,
			"parent": ["in", parents],
		},
		fields=["parent", "designation"],
		order_by="parent, idx",
	)

	grouped: dict[str, list[str]] = {}
	for row in rows:
		grouped.setdefault(row.parent, []).append(row.designation)
	return grouped


def filter_by_designation(names: list[str], designation_map: dict, designation: str) -> list[str]:
	if not designation:
		return names
	return [name for name in names if designation in designation_map.get(name, [])]


def get_employees(filters) -> list[dict]:
	conditions = {FLAG_FIELD: 1}

	status = filters.get("employee_status") or "Active"
	if status != "All":
		conditions["status"] = status

	employees = frappe.get_all(
		EMPLOYEE,
		filters=conditions,
		fields=["name", "employee_name", "designation", "department", "status", "modified"],
		order_by="employee_name",
	)
	if not employees:
		return []

	designation_map = get_designation_map(EMPLOYEE, [e.name for e in employees])
	keep = set(filter_by_designation([e.name for e in employees], designation_map, filters.get("designation")))

	return [
		{
			"source": _("Employee"),
			"record": employee.name,
			"record_doctype": EMPLOYEE,
			"person_name": employee.employee_name,
			"current_designation": employee.designation,
			"suitable_designations": ", ".join(designation_map.get(employee.name, [])),
			"detail": employee.department,
			"added_on": employee.modified,
		}
		for employee in employees
		if employee.name in keep
	]


def get_job_applicants(filters) -> list[dict]:
	applicants = frappe.get_all(
		JOB_APPLICANT,
		filters={FLAG_FIELD: 1},
		fields=["name", "applicant_name", "designation", "email_id", "status", "modified"],
		order_by="applicant_name",
	)
	if not applicants:
		return []

	designation_map = get_designation_map(JOB_APPLICANT, [a.name for a in applicants])
	keep = set(filter_by_designation([a.name for a in applicants], designation_map, filters.get("designation")))

	return [
		{
			"source": _("Job Applicant"),
			"record": applicant.name,
			"record_doctype": JOB_APPLICANT,
			"person_name": applicant.applicant_name,
			# Job Applicant.designation is the role applied for. job_title links to a
			# Job Opening, which is the vacancy rather than the role, so it is not it.
			"current_designation": applicant.designation,
			"suitable_designations": ", ".join(designation_map.get(applicant.name, [])),
			"detail": applicant.email_id,
			"added_on": applicant.modified,
		}
		for applicant in applicants
		if applicant.name in keep
	]


def get_columns() -> list[dict]:
	return [
		{"fieldname": "source", "label": _("Source"), "fieldtype": "Data", "width": 110},
		{
			"fieldname": "record",
			"label": _("ID"),
			"fieldtype": "Dynamic Link",
			"options": "record_doctype",
			"width": 150,
		},
		{"fieldname": "record_doctype", "label": _("Record DocType"), "fieldtype": "Data", "hidden": 1},
		{"fieldname": "person_name", "label": _("Name"), "fieldtype": "Data", "width": 200},
		{
			"fieldname": "current_designation",
			"label": _("Current / Applied-For Designation"),
			"fieldtype": "Link",
			"options": "Designation",
			"width": 220,
		},
		{
			"fieldname": "suitable_designations",
			"label": _("Suitable Designations"),
			"fieldtype": "Data",
			"width": 300,
		},
		{"fieldname": "detail", "label": _("Department / Email"), "fieldtype": "Data", "width": 220},
		{"fieldname": "added_on", "label": _("Added On"), "fieldtype": "Datetime", "width": 160},
	]
