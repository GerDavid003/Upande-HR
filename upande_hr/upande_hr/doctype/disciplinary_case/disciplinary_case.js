// Copyright (c) 2026, Upande and contributors
// For license information, please see license.txt

frappe.ui.form.on("Disciplinary Case", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Warning"), () => {
			frappe.new_doc("Disciplinary Warning", {
				employee: frm.doc.employee,
				disciplinary_case: frm.doc.name,
				reason: frm.doc.description,
			});
		}, __("Create"));
	},
});
