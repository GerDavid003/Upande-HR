// Copyright (c) 2026, Upande and contributors
// For license information, please see license.txt

frappe.query_reports["Talent Pool"] = {
	filters: [
		{
			fieldname: "source",
			label: __("Source"),
			fieldtype: "Select",
			options: ["All", "Employees", "Job Applicants"],
			default: "All",
			reqd: 1,
		},
		{
			fieldname: "designation",
			label: __("Suitable For Designation"),
			fieldtype: "Link",
			options: "Designation",
		},
		{
			fieldname: "employee_status",
			label: __("Employee Status"),
			fieldtype: "Select",
			options: ["Active", "Inactive", "Suspended", "Left", "All"],
			default: "Active",
		},
	],
};
