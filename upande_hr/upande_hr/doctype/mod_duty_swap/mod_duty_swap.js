// Copyright (c) 2026, Upande and contributors
// For license information, please see license.txt

frappe.ui.form.on("MOD Duty Swap", {
	setup(frm) {
		const members = { query: "upande_hr.attendance.mod_roster.member_query" };
		frm.set_query("off_employee", () => members);
		frm.set_query("cover_employee", () => members);
	},
});
