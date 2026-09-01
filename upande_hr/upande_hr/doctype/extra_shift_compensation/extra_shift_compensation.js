// Copyright (c) 2026, Upande and contributors
// For license information, please see license.txt

frappe.ui.form.on("Extra Shift Compensation", {
	setup(frm) {
		// Narrow the child Employee link to the department on the parent. HODs are
		// already scoped to their own department by User Permission; this just saves
		// them scrolling past everyone else in it.
		frm.set_query("employee", "entries", () => {
			const filters = { status: "Active" };
			if (frm.doc.department) {
				filters.department = frm.doc.department;
			}
			if (frm.doc.company) {
				filters.company = frm.doc.company;
			}
			return { filters: filters };
		});
	},
});
