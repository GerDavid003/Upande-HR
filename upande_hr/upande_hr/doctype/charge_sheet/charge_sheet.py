# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Charge Sheet - recovering the cost of lost, broken, misplaced or under-charged items.

Flow ("Charge Sheet Workflow"): Draft -> Pending Employee Acknowledgement -> Pending PD
Review -> Approved (submit) -> Closed (Finance Controller signs). The signature dates are
stamped here from the state transition rather than typed in, so they record when each
person actually acted.

On submit one Additional Salary is created per deduction row, against the "Charge Sheet
Recovery" deduction component, so the recovery reaches payroll with no one touching a
Salary Slip. Cancelling the sheet cancels them again.

issued_by carries ignore_user_permissions. An Employee User Permission is checked against
every Employee link on a document, so without it the charged employee's permission fails
on the HOD's link and they cannot open the sheet they are asked to acknowledge. Who sees
a sheet is decided by get_permission_query_conditions / has_permission below instead.

ERPNext/HRMS has no native equivalent: Expense Claim runs the wrong way, Additional
Salary alone has no approval or itemisation, and Employee Grievance is not for this.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, today

SALARY_COMPONENT = "Charge Sheet Recovery"
PRIVILEGED_ROLES = {
	"HR Manager",
	"HR User",
	"People Development",
	"Finance Controller",
	"HOD",
	"System Manager",
}

# workflow_state reached -> the date field that transition signs
SIGNATURES = {
	"Pending Employee Acknowledgement": "manager_signature_date",
	"Pending PD Review": "employee_signature_date",
	"Approved": "pd_signature_date",
	"Closed": "fc_signature_date",
}


class ChargeSheet(Document):
	def validate(self):
		self.payroll_number = self.employee
		self.validate_employee_edit()
		self.validate_issuer()
		self.validate_schedule()
		self.stamp_signature()

	def on_update_after_submit(self):
		self.stamp_signature(db=True)

	def validate_employee_edit(self):
		"""The charged employee has write permission only so the Acknowledge transition
		can save. They may move the workflow on, never change what they are charged."""
		if self.is_new() or is_privileged(frappe.session.user):
			return
		before = self.get_doc_before_save()
		if not before:
			return
		changed = [
			field
			for field in ("employee", "amount", "reason", "incident_date", "nature_of_incident", "issued_by")
			if self.get(field) != before.get(field)
		]
		if changed or get_schedule(self) != get_schedule(before):
			frappe.throw(
				_("You can acknowledge this charge sheet but not change it."), frappe.PermissionError
			)

	def validate_issuer(self):
		if self.issued_by and self.issued_by == self.employee:
			frappe.throw(_("A charge sheet cannot be issued by the employee it is raised against."))

	def validate_schedule(self):
		scheduled = flt(sum(flt(row.amount) for row in self.deductions), 2)
		if scheduled != flt(self.amount, 2):
			frappe.throw(
				_("The deduction schedule adds up to {0} but the amount to recover is {1}.").format(
					frappe.format(scheduled, {"fieldtype": "Currency"}),
					frappe.format(self.amount, {"fieldtype": "Currency"}),
				)
			)
		months = [getdate(row.payroll_date).strftime("%Y-%m") for row in self.deductions]
		if len(months) != len(set(months)):
			frappe.throw(_("Each month can appear only once in the deduction schedule."))

	def stamp_signature(self, db=False):
		field = SIGNATURES.get(self.workflow_state)
		if not field or self.get(field):
			return
		if db:
			self.db_set(field, today())
		else:
			self.set(field, today())

	def on_submit(self):
		self.create_additional_salaries()

	def on_cancel(self):
		self.cancel_additional_salaries()

	def create_additional_salaries(self):
		for row in self.deductions:
			additional_salary = frappe.get_doc(
				{
					"doctype": "Additional Salary",
					"employee": self.employee,
					"company": self.company,
					"salary_component": SALARY_COMPONENT,
					"type": "Deduction",
					"amount": row.amount,
					"payroll_date": row.payroll_date,
					"overwrite_salary_structure_amount": 0,
					"ref_doctype": self.doctype,
					"ref_docname": self.name,
				}
			)
			additional_salary.flags.ignore_permissions = True
			additional_salary.insert()
			additional_salary.submit()
			row.db_set("additional_salary", additional_salary.name)

	def cancel_additional_salaries(self):
		self.flags.ignore_links = True
		for row in self.deductions:
			if not row.additional_salary:
				continue
			additional_salary = frappe.get_doc("Additional Salary", row.additional_salary)
			if additional_salary.docstatus == 1:
				additional_salary.flags.ignore_permissions = True
				additional_salary.cancel()


def get_schedule(doc) -> list[tuple]:
	return [(str(row.payroll_date), flt(row.amount)) for row in doc.deductions]


def is_privileged(user: str) -> bool:
	if user == "Administrator":
		return True
	return bool(PRIVILEGED_ROLES.intersection(frappe.get_roles(user)))


def get_permission_query_conditions(user: str | None = None) -> str:
	"""Employees see only the charge sheets raised against them."""
	user = user or frappe.session.user
	if is_privileged(user):
		return ""
	return f"`tabCharge Sheet`.employee_user = {frappe.db.escape(user)}"


def has_permission(doc, ptype=None, user=None) -> bool:
	user = user or frappe.session.user
	if is_privileged(user):
		return True
	return doc.get("employee_user") == user
