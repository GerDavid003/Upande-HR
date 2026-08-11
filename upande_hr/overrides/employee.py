import frappe
from frappe import _


def validate_reason_for_exit_when_left(doc, method=None):
	"""Employee validate hook: Reason for Exit is required once Status is
	set to "Left". mandatory_depends_on is client-side-JS-only and is never
	enforced server-side (frappe.model.base_document.BaseDocument's
	_get_missing_mandatory_fields only ever checks the static reqd flag),
	so this is enforced here explicitly instead.
	"""
	if doc.status == "Left" and not doc.reason_for_exit:
		frappe.throw(_("Reason for Exit is required when Status is set to Left."))
