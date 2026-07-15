import frappe


def before_uninstall():
	for name in frappe.get_all("Custom Field", filters={"module": "Upande Hr"}, pluck="name"):
		frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
