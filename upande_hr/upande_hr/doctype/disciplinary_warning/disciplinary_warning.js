// Copyright (c) 2026, Upande and contributors
// For license information, please see license.txt

frappe.ui.form.on("Disciplinary Warning", {
	issue_date(frm) {
		set_expiry(frm);
	},
	validity_months(frm) {
		set_expiry(frm);
	},
});

function set_expiry(frm) {
	if (frm.doc.issue_date && frm.doc.validity_months) {
		frm.set_value("expiry_date", frappe.datetime.add_months(frm.doc.issue_date, frm.doc.validity_months));
	}
}
