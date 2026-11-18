// Copyright (c) 2026, Upande and contributors
// For license information, please see license.txt

const MOD_ROSTER_COLORS = { WD: "blue", OFF: "orange", PH: "purple", WO: "gray", L: "yellow" };

frappe.query_reports["MOD Roster"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.month_start(),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.month_end(
				frappe.datetime.add_months(frappe.datetime.get_today(), 1)
			),
		},
		{
			fieldname: "group",
			label: __("Group"),
			fieldtype: "Link",
			options: "MOD Rotation Group",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (data.is_header || data.is_total) return `<b>${value}</b>`;
		if (column.fieldname && column.fieldname.startsWith("d") && data[column.fieldname]) {
			const color = MOD_ROSTER_COLORS[String(data[column.fieldname]).replace(/[*!]/g, "")];
			if (color) return `<span class="indicator-pill ${color}">${value}</span>`;
		}
		return value;
	},
};
