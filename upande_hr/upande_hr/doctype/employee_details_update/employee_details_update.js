// Copyright (c) 2026, Upande and contributors
// For license information, please see license.txt

const EDU_METHOD = "upande_hr.upande_hr.doctype.employee_details_update.employee_details_update";

frappe.ui.form.on("Employee Details Update", {
	onload(frm) {
		if (!frm.is_new() || frm.doc.employee) return;
		frappe.call(`${EDU_METHOD}.get_session_employee`).then((r) => {
			if (r.message) frm.set_value("employee", r.message);
		});
	},

	employee(frm) {
		if (!frm.doc.employee || !frm.is_new()) return;
		frappe
			.call(`${EDU_METHOD}.get_current_details`, { employee: frm.doc.employee })
			.then((r) => {
				const details = r.message || {};
				for (const table of ["next_of_kin", "family_members"]) {
					frm.clear_table(table);
					(details[table] || []).forEach((row) => frm.add_child(table, row));
					delete details[table];
				}
				frm.set_value(details);
				frm.refresh_fields();
			});
	},
});
