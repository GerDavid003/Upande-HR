frappe.listview_settings["Employee Contract"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colors = {
			Draft: "red",
			Active: "green",
			Renewed: "blue",
			Confirmed: "purple",
			Expired: "orange",
			Cancelled: "gray",
		};
		return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
	},
};
