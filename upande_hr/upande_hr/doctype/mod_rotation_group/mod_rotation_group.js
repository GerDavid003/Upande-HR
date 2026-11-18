// Copyright (c) 2026, Upande and contributors
// For license information, please see license.txt

frappe.ui.form.on("MOD Rotation Group", {
	refresh(frm) {
		frm.add_custom_button(__("MOD Roster"), () =>
			frappe.set_route("query-report", "MOD Roster", { group: frm.doc.name })
		);
	},
});
