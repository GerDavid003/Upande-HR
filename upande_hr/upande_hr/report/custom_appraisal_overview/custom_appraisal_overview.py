# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Custom Appraisal Overview - per-criterion brand (Marafiki) scores and KPI side by side.

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
- KPI /100 = custom_hod_hr_score (a 0-5 weighted score) / 5 * 100

Each criterion has its own column, labelled in full (Authenticity, not A): WROCCS shares
the initials R and C with ARCS, and query reports have no column-group headers to tell
them apart.
"""

import frappe
from frappe import _
from frappe.utils import flt

MBA = "Marafiki Brand Assessment"

# MBA criterion field -> column label, in the order the columns render.
ARCS_LABELS = {
	"arcs_authenticity": "Authenticity",
	"arcs_resourcefulness": "Resourcefulness",
	"arcs_craftsmanship": "Craftsmanship",
	"arcs_sparkle": "Sparkle",
}
WROCCS_LABELS = {
	"wroccs_work_smart": "Work-Smart",
	"wroccs_respectful": "Respectful",
	"wroccs_open_minded": "Open-Minded",
	"wroccs_candid": "Candid",
	"wroccs_communicative": "Communicative",
	"wroccs_systematic": "Systematic",
}
ARCS_FIELDS = list(ARCS_LABELS)
WROCCS_FIELDS = list(WROCCS_LABELS)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	appraisals = get_appraisals(filters)
	brand = get_brand_scores(appraisals)

	rows = []
	for apr in appraisals:
		scores = brand.get((apr.employee, apr.appraisal_cycle), {})
		rows.append(
			{
				"employee": apr.employee,
				"employee_name": apr.employee_name,
				"department": apr.department,
				"designation": apr.designation,
				"appraisal_template": apr.appraisal_template,
				**scores,
				"kpi_100": flt(flt(apr.custom_hod_hr_score) / 5 * 100, 2),
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
			**criterion_avg,
			"arcs_40": arcs,
			"wroccs_60": wroccs,
			"brand_100": brand,
			"brand_20": flt(brand / 5, 2),
		}
	return out


def get_columns() -> list[dict]:
	return [
		{
			"fieldname": "employee",
			"label": _("Employee No"),
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
		*[score_column(field, label, 10) for field, label in ARCS_LABELS.items()],
		score_column("arcs_40", "ARCS Avg", 40),
		*[score_column(field, label, 10) for field, label in WROCCS_LABELS.items()],
		score_column("wroccs_60", "WROCCS Avg", 60),
		score_column("brand_100", "Brand Score", 100),
		score_column("brand_20", "Brand Contribution", 20),
		score_column("kpi_100", "KPI", 100),
	]


def score_column(fieldname: str, label: str, out_of: int) -> dict:
	return {
		"fieldname": fieldname,
		"label": _(label) + f" (/{out_of})",
		"fieldtype": "Float",
		"precision": 2,
		"width": max(110, 9 * len(label) + 50),
	}
