// Copyright (c) 2026, Upande and contributors
// For license information, please see license.txt

// Live feedback only. The server recomputes age and re-checks the beneficiary total on
// validate (upande_hr/upande_hr/employee_details.py), so nothing here is authoritative.

frappe.ui.form.on("Employee", {
	refresh(frm) {
		upande_hr_employee.show_beneficiary_total(frm);
	},

	date_of_birth(frm) {
		frm.set_value("custom_age", upande_hr_employee.age(frm.doc.date_of_birth));
	},
});

frappe.ui.form.on("Employee Beneficiary", {
	allocation_percentage(frm) {
		upande_hr_employee.show_beneficiary_total(frm);
	},
	custom_beneficiaries_add(frm) {
		upande_hr_employee.show_beneficiary_total(frm);
	},
	custom_beneficiaries_remove(frm) {
		upande_hr_employee.show_beneficiary_total(frm);
	},
});

const upande_hr_employee = {
	// Whole years, matching employee_details.calculate_age.
	age(date_of_birth) {
		if (!date_of_birth) return 0;

		const dob = frappe.datetime.str_to_obj(date_of_birth);
		const today = frappe.datetime.str_to_obj(frappe.datetime.get_today());
		if (today < dob) return 0;

		const years = today.getFullYear() - dob.getFullYear();
		const before_birthday =
			today.getMonth() < dob.getMonth() ||
			(today.getMonth() === dob.getMonth() && today.getDate() < dob.getDate());
		return before_birthday ? years - 1 : years;
	},

	show_beneficiary_total(frm) {
		if (!frm.fields_dict.custom_beneficiaries) return;

		const rows = frm.doc.custom_beneficiaries || [];
		let description = "";

		if (rows.length) {
			const total = rows.reduce((sum, row) => sum + flt(row.allocation_percentage), 0);
			const ok = Math.abs(total - 100) <= 0.01;
			const color = ok ? "green" : "red";
			const label = ok
				? __("Total allocation: {0}%", [flt(total, 2)])
				: __("Total allocation: {0}% (must be 100%)", [flt(total, 2)]);
			description = `<span class="indicator ${color}">${label}</span>`;
		}

		frm.set_df_property("custom_beneficiaries", "description", description);
	},
};
