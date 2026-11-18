import frappe
from frappe import _


def validate_reason_for_exit(doc, method=None):
	"""Server-side twin of the field's mandatory_depends_on, which Frappe only enforces in the browser."""
	if doc.status == "Left" and not doc.get("reason_for_exit"):
		frappe.throw(
			_("{0} is mandatory when Status is Left").format(frappe.bold(_("Reason for Exit"))),
			frappe.MandatoryError,
		)


def validate_family_tree_upi(doc, method=None):
	"""UPI Number must be unique within one employee's Family Tree (not site-wide,
	since related employees can legitimately share relatives)."""
	seen = {}
	for row in doc.get("family_tree") or []:
		upi = (row.upi_number or "").strip()
		row.upi_number = upi or None
		if not upi:
			continue
		key = upi.upper()
		if key in seen:
			frappe.throw(
				_("Family Tree row {0}: UPI Number {1} is already used in row {2}").format(
					row.idx, frappe.bold(upi), seen[key]
				),
				frappe.UniqueValidationError,
			)
		seen[key] = row.idx
