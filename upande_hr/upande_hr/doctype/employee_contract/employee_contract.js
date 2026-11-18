frappe.ui.form.on("Employee Contract", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;

		if (frm.doc.status === "Active" && frappe.model.can_create("Employee Contract")) {
			frm.add_custom_button(__("Renew"), () => {
				frappe.call({
					method: "upande_hr.upande_hr.doctype.employee_contract.employee_contract.make_renewal",
					args: { source_name: frm.doc.name },
					freeze: true,
					callback(r) {
						if (!r.message) return;
						const doc = frappe.model.sync(r.message)[0];
						frappe.set_route("Form", doc.doctype, doc.name);
					},
				});
			});
		}

		if (["Active", "Expired"].includes(frm.doc.status) && frm.perm[0] && frm.perm[0].submit) {
			frm.add_custom_button(__("Confirm as Permanent"), () => frm.trigger("confirm_as_permanent"));
		}
	},

	start_date(frm) {
		frm.trigger("set_end_date");
	},

	duration_months(frm) {
		frm.trigger("set_end_date");
	},

	set_end_date(frm) {
		if (frm.doc.start_date && frm.doc.duration_months > 0) {
			// last day of the term: start + N months - 1 day
			const end = frappe.datetime.add_days(
				frappe.datetime.add_months(frm.doc.start_date, frm.doc.duration_months),
				-1
			);
			frm.set_value("end_date", end);
		}
	},

	confirm_as_permanent(frm) {
		const d = new frappe.ui.Dialog({
			title: __("Confirm as Permanent"),
			fields: [
				{
					fieldname: "confirmation_date",
					fieldtype: "Date",
					label: __("Confirmation Date"),
					reqd: 1,
					default: frm.doc.end_date ? frappe.datetime.add_days(frm.doc.end_date, 1) : undefined,
				},
				{
					fieldname: "employment_type",
					fieldtype: "Link",
					options: "Employment Type",
					label: __("Employment Type"),
					reqd: 1,
				},
			],
			primary_action_label: __("Confirm"),
			primary_action(values) {
				frappe.call({
					method: "upande_hr.upande_hr.doctype.employee_contract.employee_contract.confirm_as_permanent",
					args: {
						contract: frm.doc.name,
						confirmation_date: values.confirmation_date,
						employment_type: values.employment_type,
					},
					freeze: true,
					callback() {
						d.hide();
						frm.reload_doc();
					},
				});
			},
		});
		d.show();
	},
});
