// Copyright (c) 2026, Upande and contributors
// For license information, please see license.txt

frappe.query_reports["Absence Leave Deductions"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Deducted", "Flagged", "Reversed", "Error"],
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "status" && data) {
			const color = { Deducted: "green", Flagged: "orange", Reversed: "gray", Error: "red" }[data.status];
			if (color) value = `<span class="indicator-pill ${color}">${value}</span>`;
		}
		return value;
	},
};
