# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Custom Appraisal Overview - brand (Marafiki) and KPI scores side by side.

Named "Custom Appraisal Overview" because "Appraisal Overview" is a standard HRMS report;
a report of that name shipped from here would fight HRMS for the same row on migrate.

Brand scores are computed live from submitted Marafiki Brand Assessments rather than
read off the Appraisal's custom_brand_* fields. Those fields are written by the
"MBA Submit - Sync Brand Score" and "Nightly - Sync Brand Scores" Server Scripts, which
skip an employee until at least one assessment is submitted and stop updating once the
Appraisal is Completed. The arithmetic below is kept identical to those scripts so the
figures agree with the Appraisal's Score tab:

- each criterion is averaged across raters (submitted assessments only)
- ARCS /40 and WROCCS /60 are the sums of those per-criterion averages
- Brand /100 = ARCS + WROCCS, Brand Contribution /20 = Brand / 5
- KPI /100 = custom_hod_hr_score (a 0-5 weighted score) / 5 * 100, KPI /80 = KPI * 0.8
"""

import frappe
from frappe import _
from frappe.utils import flt

MBA = "Marafiki Brand Assessment"

ARCS_FIELDS = ["arcs_authenticity", "arcs_resourcefulness", "arcs_craftsmanship", "arcs_sparkle"]
WROCCS_FIELDS = [
	"wroccs_work_smart",
	"wroccs_respectful",
	"wroccs_open_minded",
	"wroccs_candid",
	"wroccs_communicative",
	"wroccs_systematic",
]


def execute(filters=None):
	filters = frappe._dict(filters or {})
	appraisals = get_appraisals(filters)
	brand = get_brand_scores(appraisals)

	rows = []
	for apr in appraisals:
		scores = brand.get((apr.employee, apr.appraisal_cycle), {})
		kpi_100 = flt(flt(apr.custom_hod_hr_score) / 5 * 100, 2)
		rows.append(
			{
				"appraisal": apr.name,
				"employee": apr.employee,
				"employee_name": apr.employee_name,
				"department": apr.department,
				"designation": apr.designation,
				"appraisal_template": apr.appraisal_template,
				"appraisal_cycle": apr.appraisal_cycle,
				"workflow_state": apr.workflow_state,
				"raters_submitted": scores.get("raters", 0),
				"avg_arcs": scores.get("avg_arcs"),
				"arcs_40": scores.get("arcs_40"),
				"avg_wroccs": scores.get("avg_wroccs"),
				"wroccs_60": scores.get("wroccs_60"),
				"brand_100": scores.get("brand_100"),
				"brand_20": scores.get("brand_20"),
				"kpi_80": flt(kpi_100 * 0.8, 2),
				"kpi_100": kpi_100,
				"final_score": flt(kpi_100 * 0.8 + flt(scores.get("brand_100")) * 0.2, 2),
			}
		)

	return get_columns(), rows


def get_appraisals(filters) -> list:
	conditions = {"docstatus": ["<", 2]}
	for key in ("appraisal_cycle", "employee", "department", "designation", "company"):
		if filters.get(key):
			conditions[key] = filters.get(key)

	return frappe.get_all(
		"Appraisal",
		filters=conditions,
		fields=[
			"name",
			"employee",
			"employee_name",
			"department",
			"designation",
			"appraisal_template",
			"appraisal_cycle",
			"workflow_state",
			"custom_hod_hr_score",
		],
		order_by="department, employee_name",
	)


def get_brand_scores(appraisals) -> dict:
	"""Per (employee, cycle): rater count, averages and sums, from submitted MBAs."""
	if not appraisals:
		return {}

	cycles = list({a.appraisal_cycle for a in appraisals if a.appraisal_cycle})
	employees = list({a.employee for a in appraisals})
	if not cycles:
		return {}

	rows = frappe.get_all(
		MBA,
		filters={
			"docstatus": 1,
			"appraisal_cycle": ["in", cycles],
			"subject_employee": ["in", employees],
		},
		fields=["subject_employee", "appraisal_cycle", *ARCS_FIELDS, *WROCCS_FIELDS],
	)

	grouped: dict[tuple, list] = {}
	for row in rows:
		grouped.setdefault((row.subject_employee, row.appraisal_cycle), []).append(row)

	out = {}
	for key, assessments in grouped.items():
		n = len(assessments)
		criterion_avg = {
			field: flt(sum(flt(a.get(field)) for a in assessments) / n, 2)
			for field in ARCS_FIELDS + WROCCS_FIELDS
		}
		arcs = flt(sum(criterion_avg[f] for f in ARCS_FIELDS), 2)
		wroccs = flt(sum(criterion_avg[f] for f in WROCCS_FIELDS), 2)
		brand = flt(arcs + wroccs, 2)
		out[key] = {
			"raters": n,
			"avg_arcs": flt(arcs / len(ARCS_FIELDS), 3),
			"arcs_40": arcs,
			"avg_wroccs": flt(wroccs / len(WROCCS_FIELDS), 3),
			"wroccs_60": wroccs,
			"brand_100": brand,
			"brand_20": flt(brand / 5, 2),
		}
	return out


def get_columns() -> list[dict]:
	return [
		{
			"fieldname": "appraisal",
			"label": _("Appraisal"),
			"fieldtype": "Link",
			"options": "Appraisal",
			"width": 160,
		},
		{
			"fieldname": "employee",
			"label": _("Employee"),
			"fieldtype": "Link",
			"options": "Employee",
			"width": 120,
		},
		{"fieldname": "employee_name", "label": _("Employee Name"), "fieldtype": "Data", "width": 180},
		{
			"fieldname": "department",
			"label": _("Department"),
			"fieldtype": "Link",
			"options": "Department",
			"width": 150,
		},
		{
			"fieldname": "designation",
			"label": _("Designation"),
			"fieldtype": "Link",
			"options": "Designation",
			"width": 150,
		},
		{
			"fieldname": "appraisal_template",
			"label": _("Appraisal Template"),
			"fieldtype": "Link",
			"options": "Appraisal Template",
			"width": 160,
		},
		{"fieldname": "workflow_state", "label": _("Status"), "fieldtype": "Data", "width": 130},
		{"fieldname": "raters_submitted", "label": _("Raters"), "fieldtype": "Int", "width": 70},
		{
			"fieldname": "avg_arcs",
			"label": _("Avg ARCS (/10)"),
			"fieldtype": "Float",
			"precision": 3,
			"width": 110,
		},
		{
			"fieldname": "arcs_40",
			"label": _("ARCS (/40)"),
			"fieldtype": "Float",
			"precision": 2,
			"width": 100,
		},
		{
			"fieldname": "avg_wroccs",
			"label": _("Avg WROCCS (/10)"),
			"fieldtype": "Float",
			"precision": 3,
			"width": 120,
		},
		{
			"fieldname": "wroccs_60",
			"label": _("WROCCS (/60)"),
			"fieldtype": "Float",
			"precision": 2,
			"width": 110,
		},
		{
			"fieldname": "brand_100",
			"label": _("Avg Marafiki (/100)"),
			"fieldtype": "Float",
			"precision": 2,
			"width": 130,
		},
		{
			"fieldname": "brand_20",
			"label": _("Brand Contribution (/20)"),
			"fieldtype": "Float",
			"precision": 2,
			"width": 150,
		},
		{
			"fieldname": "kpi_80",
			"label": _("KPI Score (/80)"),
			"fieldtype": "Float",
			"precision": 2,
			"width": 110,
		},
		{
			"fieldname": "kpi_100",
			"label": _("KPI Score (/100)"),
			"fieldtype": "Float",
			"precision": 2,
			"width": 120,
		},
		{
			"fieldname": "final_score",
			"label": _("Final Score (/100)"),
			"fieldtype": "Float",
			"precision": 2,
			"width": 130,
		},
	]
