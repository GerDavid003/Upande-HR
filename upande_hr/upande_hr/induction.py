"""Induction sessions and policy acknowledgment."""

import frappe
from frappe import _
from frappe.utils import now_datetime

DECLARATION = (
	"I confirm that I have read, understood and agree to comply with this document "
	"as part of my terms of employment."
)


def session_on_submit(doc, method=None):
	"""Create a draft Policy Acknowledgment for each attendee x policy."""
	policies = [row.policy for row in (doc.topics or []) if row.policy]

	required = []
	if policies:
		required = frappe.get_all(
			"Policy Document",
			filters={
				"name": ["in", policies],
				"requires_acknowledgment": 1,
				"disabled": 0,
			},
			pluck="name",
		)

	created = 0

	for attendee in doc.attendees or []:
		if not attendee.employee:
			continue

		# Attendance is often ticked before submit, so write both flags here rather
		# than waiting for on_update_after_submit, which only fires on a later edit.
		frappe.db.set_value(
			"Employee",
			attendee.employee,
			{
				"custom_induction_session": doc.name,
				"custom_induction_completed": int(bool(attendee.attended)),
			},
		)

		for policy in required:
			already = frappe.db.exists(
				"Policy Acknowledgment",
				{
					"employee": attendee.employee,
					"policy": policy,
					"docstatus": ["<", 2],
				},
			)
			if already:
				continue

			ack = frappe.new_doc("Policy Acknowledgment")
			ack.update(
				{
					"employee": attendee.employee,
					"policy": policy,
					"induction_session": doc.name,
					"declaration": DECLARATION,
				}
			)
			ack.flags.ignore_permissions = True
			ack.insert()
			created += 1

	if created:
		frappe.msgprint(
			_("{0} acknowledgment records created for signing.").format(created),
			alert=True,
			indicator="green",
		)


def session_on_update_after_submit(doc, method=None):
	"""Reflect later edits to the attendance register back onto the Employee record."""
	for attendee in doc.attendees or []:
		if not attendee.employee:
			continue
		frappe.db.set_value(
			"Employee",
			attendee.employee,
			"custom_induction_completed",
			int(bool(attendee.attended)),
		)


def session_on_cancel(doc, method=None):
	"""Clear the induction flags when a session is cancelled."""
	for attendee in doc.attendees or []:
		if not attendee.employee:
			continue
		current = frappe.db.get_value("Employee", attendee.employee, "custom_induction_session")
		if current == doc.name:
			frappe.db.set_value(
				"Employee",
				attendee.employee,
				{"custom_induction_session": None, "custom_induction_completed": 0},
			)


def acknowledgment_before_submit(doc, method=None):
	"""Stamp who signed and when. A signature is mandatory."""
	if not doc.signature:
		frappe.throw(_("A signature is required before submitting an acknowledgment."))

	doc.acknowledged_on = now_datetime()
	doc.acknowledged_by = frappe.session.user


def acknowledgment_on_change(doc, method=None):
	update_policy_flag(doc.employee)


def update_policy_flag(employee):
	"""Set Employee.custom_policies_acknowledged when every required policy is signed."""
	if not employee:
		return

	required = frappe.get_all(
		"Policy Document",
		filters={"requires_acknowledgment": 1, "disabled": 0},
		pluck="name",
	)
	if not required:
		return

	signed = frappe.get_all(
		"Policy Acknowledgment",
		filters={"employee": employee, "docstatus": 1},
		pluck="policy",
	)

	complete = set(required).issubset(set(signed))
	frappe.db.set_value("Employee", employee, "custom_policies_acknowledged", int(complete))