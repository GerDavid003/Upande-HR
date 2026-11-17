import frappe
from frappe import _


def validate_reason_for_exit(doc, method=None):
	"""Server-side twin of the field's mandatory_depends_on, which Frappe only enforces in the browser."""
	if doc.status == "Left" and not doc.get("reason_for_exit"):
		frappe.throw(
			_("{0} is mandatory when Status is Left").format(frappe.bold(_("Reason for Exit"))),
			frappe.MandatoryError,
		)
