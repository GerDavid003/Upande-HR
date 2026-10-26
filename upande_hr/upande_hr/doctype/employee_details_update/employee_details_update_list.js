// Copyright (c) 2026, Upande and contributors
// For license information, please see license.txt

// An employee with a form still open lands on it rather than on the list. HR, who file
// forms for others, see the list as usual. The new-form redirect is in
// employee_details_update.js, for entry points that skip the list.
frappe.listview_settings["Employee Details Update"] = {
	onload() {
		if (
			frappe.session.user === "Administrator" ||
			frappe.user.has_role(["HR User", "HR Manager"])
		) {
			return;
		}
		frappe
			.call(
				"upande_hr.upande_hr.doctype.employee_details_update.employee_details_update.get_active_submission"
			)
			.then((r) => {
				if (!r.message) return;
				// Replace, not push, so Back does not land on the list and bounce again.
				frappe.route_flags.replace_route = true;
				frappe.set_route("Form", "Employee Details Update", r.message);
			});
	},
};
