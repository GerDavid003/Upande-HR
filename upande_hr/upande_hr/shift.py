"""Default shift resolution and automatic Shift Assignment creation."""

import frappe
from frappe import _
from frappe.utils import getdate

# Criteria compared between a Default Shift Rule and an Employee.
# An empty value on the rule means "match anything".
MATCH_FIELDS = ("company", "branch", "department", "designation", "employment_type")


def get_matching_shift(doc):
	"""Return the Shift Type of the best-matching Default Shift Rule, or None.

	Specificity wins: the rule matching the most set criteria is chosen.
	`priority` breaks ties and can override specificity (weighted x10).
	"""
	rules = frappe.get_all(
		"Default Shift Rule",
		filters={"disabled": 0},
		fields=["name", "priority", "shift_type", *MATCH_FIELDS],
	)

	best = None
	best_score = -1

	for rule in rules:
		score = 0
		matched = True

		for field in MATCH_FIELDS:
			value = rule.get(field)
			if not value:
				continue
			if value != doc.get(field):
				matched = False
				break
			score += 1

		if not matched:
			continue

		score += (rule.priority or 0) * 10

		if score > best_score:
			best = rule
			best_score = score

	return best.shift_type if best else None


def employee_validate(doc, method=None):
	"""Resolve default_shift from rules and default the shift start date to DOJ."""
	if doc.status != "Active":
		return

	if not doc.default_shift:
		doc.default_shift = get_matching_shift(doc)

	if not doc.default_shift:
		doc.custom_shift_start_date = None
		doc.custom_shift_end_date = None
		return

	if not doc.custom_shift_start_date:
		doc.custom_shift_start_date = doc.date_of_joining

	start = doc.custom_shift_start_date
	end = doc.custom_shift_end_date
	if end and start and getdate(end) < getdate(start):
		frappe.throw(_("Shift End Date cannot be before Shift Start Date"))


def employee_on_update(doc, method=None):
	"""Keep the submitted Shift Assignment in step with the Employee record."""
	if not frappe.db.get_single_value("HR Settings", "custom_auto_create_shift_assignment"):
		return

	if doc.status != "Active":
		return

	if not doc.default_shift or not doc.custom_shift_start_date:
		return

	changed = any(
		doc.has_value_changed(fieldname)
		for fieldname in ("default_shift", "custom_shift_start_date", "custom_shift_end_date")
	)

	if changed:
		sync_shift_assignment(doc)


def sync_shift_assignment(doc):
	"""Cancel any open/overlapping assignment that no longer matches, then create one."""
	start = getdate(doc.custom_shift_start_date)
	end = getdate(doc.custom_shift_end_date) if doc.custom_shift_end_date else None

	open_ended = frappe.get_all(
		"Shift Assignment",
		filters=[
			["employee", "=", doc.name],
			["docstatus", "=", 1],
			["end_date", "is", "not set"],
		],
		fields=["name", "shift_type", "start_date", "end_date"],
	)

	overlapping = frappe.get_all(
		"Shift Assignment",
		filters=[
			["employee", "=", doc.name],
			["docstatus", "=", 1],
			["end_date", ">=", start],
		],
		fields=["name", "shift_type", "start_date", "end_date"],
	)

	seen = set()
	for row in open_ended + overlapping:
		if row.name in seen:
			continue
		seen.add(row.name)

		row_end = getdate(row.end_date) if row.end_date else None
		in_sync = (
			row.shift_type == doc.default_shift
			and getdate(row.start_date) == start
			and row_end == end
		)
		if in_sync:
			# Nothing to do; the current assignment already reflects the Employee.
			return

		frappe.get_doc("Shift Assignment", row.name).cancel()

	assignment = frappe.new_doc("Shift Assignment")
	assignment.update(
		{
			"employee": doc.name,
			"company": doc.company,
			"shift_type": doc.default_shift,
			"start_date": start,
			"end_date": end,
			"status": "Active",
		}
	)
	assignment.flags.ignore_permissions = True
	assignment.insert()
	assignment.submit()

	frappe.msgprint(
		_("Shift Assignment {0} created and submitted.").format(assignment.name),
		alert=True,
		indicator="green",
	)