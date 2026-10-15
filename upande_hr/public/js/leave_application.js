// Copyright (c) 2026, Upande and contributors
// For license information, please see license.txt

// Cosmetic only: the server-side gate (gate_leave_application, before_insert) is what
// actually refuses the leave. This just tells the employee before they fill the form in.
frappe.ui.form.on("Leave Application", {
	onload(frm) {
		if (!frm.is_new()) return;
		frappe
			.call(
				"upande_hr.upande_hr.doctype.employee_details_update.employee_details_update.leave_gate_blocks_me"
			)
			.then((r) => {
				if (!r.message) return;
				frappe.msgprint({
					title: __("Personal Details Required"),
					indicator: "orange",
					message: __(
						"Please confirm your personal details for this year before applying for leave."
					),
					primary_action: {
						label: __("Update now"),
						action: () => frappe.new_doc("Employee Details Update"),
					},
				});
			});
	},
});
