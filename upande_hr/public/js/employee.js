// Probation tab: live preview of the end date. The server recalculates it on save
// (upande_hr/employee/probation.py, calculate_end_date); keep the rule identical.
// Inclusive: a 90-day probation starting 1 Jan ends 31 Mar.

function upande_hr_set_probation_end_date(frm) {
	const start = frm.doc.custom_probation_start_date || frm.doc.date_of_joining;
	const period = cint(frm.doc.custom_probation_period_days);
	const end = start && period > 0 ? frappe.datetime.add_days(start, period - 1) : null;

	if ((frm.doc.custom_probation_end_date || null) !== end) {
		frm.set_value("custom_probation_end_date", end);
	}
}

frappe.ui.form.on("Employee", {
	custom_probation_start_date: upande_hr_set_probation_end_date,
	custom_probation_period_days: upande_hr_set_probation_end_date,
	date_of_joining: upande_hr_set_probation_end_date,
});
