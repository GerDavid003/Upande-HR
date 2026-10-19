// Copyright (c) 2026, Upande and contributors
// For license information, please see license.txt

frappe.query_reports["Custom Appraisal Overview"] = {
	filters: [
		{
			fieldname: "appraisal_cycle",
			label: __("Appraisal Cycle"),
			fieldtype: "Link",
			options: "Appraisal Cycle",
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
		},
		{
			fieldname: "designation",
			label: __("Designation"),
			fieldtype: "Link",
			options: "Designation",
		},
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
		},
	],
};
