// Karen Roses takes compassionate days via Annual Leave + "Is Compassionate?",
// so the Compassionate Leave type itself is hidden from their leave type picker.
// Keep in sync with upande_hr/overrides/leave_application.py.
const UPANDE_HR_COMPASSIONATE_LEAVE_TYPE = "Compassionate Leave";
const UPANDE_HR_COMPASSIONATE_GATED_COMPANY = "Karen Roses";

frappe.ui.form.on("Leave Application", {
	setup(frm) {
		upande_hr_hide_compassionate_leave_type(frm);
	},

	// HRMS's make_dashboard replaces the leave_type query with its own
	// "allocated types only" filter; this handler runs after it, so re-wrap.
	make_dashboard(frm) {
		upande_hr_hide_compassionate_leave_type(frm);
	},
});

function upande_hr_hide_compassionate_leave_type(frm) {
	const base_query = frm.fields_dict.leave_type.get_query;
	if (base_query && base_query.__upande_hr_wrapped) return;

	const wrapped = function (...args) {
		const query = (base_query ? base_query.apply(this, args) : null) || {};
		// Evaluated when the dropdown opens, so it reflects the current employee's company.
		if (frm.doc.company !== UPANDE_HR_COMPASSIONATE_GATED_COMPANY) return query;

		let filters = query.filters || [];
		if (!Array.isArray(filters)) {
			filters = Object.entries(filters).map(([field, value]) =>
				Array.isArray(value) ? [field, ...value] : [field, "=", value],
			);
		}
		return {
			...query,
			filters: [...filters, ["name", "!=", UPANDE_HR_COMPASSIONATE_LEAVE_TYPE]],
		};
	};
	wrapped.__upande_hr_wrapped = true;
	frm.set_query("leave_type", wrapped);
}
