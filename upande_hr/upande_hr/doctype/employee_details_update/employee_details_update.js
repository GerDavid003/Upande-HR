// Copyright (c) 2026, Upande and contributors
// For license information, please see license.txt

const EDU_METHOD = "upande_hr.upande_hr.doctype.employee_details_update.employee_details_update";

frappe.ui.form.on("Employee Details Update", {
	setup(frm) {
		frm.set_query("bank_branch", () => ({
			filters: { bank: frm.doc.bank, disabled: 0 },
		}));
	},

	onload(frm) {
		if (!frm.is_new()) return;
		// One open form per employee (see validate_one_open_form). Send them to it here
		// rather than let them fill in a new one that will be refused on save. The leave
		// gate opens a new form directly, so the list's redirect alone does not cover it.
		if (
			frappe.session.user !== "Administrator" &&
			!frappe.user.has_role(["HR User", "HR Manager"])
		) {
			frappe.call(`${EDU_METHOD}.get_active_submission`).then((r) => {
				if (!r.message) return;
				frappe.route_flags.replace_route = true;
				frappe.set_route("Form", "Employee Details Update", r.message);
			});
		}
		if (frm.doc.employee) return;
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
				for (const table of ["emergency_contacts", "next_of_kin", "family_members"]) {
					frm.clear_table(table);
					(details[table] || []).forEach((row) => frm.add_child(table, row));
					delete details[table];
				}
				frm.set_value(details);
				frm.refresh_fields();
			});
	},

	bank(frm) {
		if (frm.doc.bank_branch) frm.set_value("bank_branch", null);
	},
});
