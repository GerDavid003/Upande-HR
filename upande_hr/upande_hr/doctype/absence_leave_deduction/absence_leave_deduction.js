// Copyright (c) 2026, Upande and contributors
// For license information, please see license.txt

frappe.ui.form.on("Absence Leave Deduction", {
	refresh(frm) {
		if (frm.doc.leave_application) {
			frm.add_custom_button(__("Leave Application"), () =>
				frappe.set_route("Form", "Leave Application", frm.doc.leave_application)
			);
		}
	},
});
