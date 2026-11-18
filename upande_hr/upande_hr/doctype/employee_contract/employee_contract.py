# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, add_months, getdate, today

from upande_hr.contracts.sync import sync_employee


class EmployeeContract(Document):
	def before_insert(self):
		self.set_contract_number()

	def validate(self):
		self.set_end_date_from_duration()
		self.validate_dates()
		self.validate_employee()
		self.validate_previous_contract()
		self.validate_not_confirmed()
		self.validate_overlap()

	def on_submit(self):
		self.db_set("status", "Active")
		if self.previous_contract:
			prev = frappe.db.get_value("Employee Contract", self.previous_contract, ["status", "docstatus"], as_dict=True)
			if prev and prev.docstatus == 1 and prev.status == "Active":
				frappe.db.set_value("Employee Contract", self.previous_contract, "status", "Renewed")
		sync_employee(self.employee)

	def on_cancel(self):
		self.db_set("status", "Cancelled")
		if self.previous_contract:
			prev = frappe.db.get_value(
				"Employee Contract", self.previous_contract, ["status", "end_date", "docstatus"], as_dict=True
			)
			if prev and prev.docstatus == 1 and prev.status == "Renewed":
				restored = "Active" if getdate(prev.end_date) >= getdate(today()) else "Expired"
				frappe.db.set_value("Employee Contract", self.previous_contract, "status", restored)
		sync_employee(self.employee)

	def set_contract_number(self):
		count = frappe.db.count(
			"Employee Contract",
			{"employee": self.employee, "docstatus": ["in", [0, 1]], "name": ["!=", self.name or ""]},
		)
		self.contract_number = count + 1

	def set_end_date_from_duration(self):
		if not self.end_date and self.start_date and self.duration_months:
			self.end_date = add_days(add_months(getdate(self.start_date), self.duration_months), -1)

	def validate_dates(self):
		if not self.start_date or not self.end_date:
			return
		if getdate(self.end_date) < getdate(self.start_date):
			frappe.throw(_("End Date cannot be before Start Date"))
		joining = frappe.db.get_value("Employee", self.employee, "date_of_joining")
		if joining and getdate(self.start_date) < getdate(joining):
			frappe.throw(_("Start Date cannot be before the Employee's Date of Joining ({0})").format(joining))

	def validate_employee(self):
		if self._action == "update_after_submit":
			return
		if frappe.db.get_value("Employee", self.employee, "status") == "Left":
			frappe.throw(_("Cannot create a contract for an employee who has left"))

	def validate_previous_contract(self):
		if not self.previous_contract:
			return
		prev_employee = frappe.db.get_value("Employee Contract", self.previous_contract, "employee")
		if prev_employee != self.employee:
			frappe.throw(_("Previous Contract must belong to the same Employee"))

	def validate_not_confirmed(self):
		if self._action == "update_after_submit":
			return
		if has_confirmed_contract(self.employee, exclude=self.name):
			frappe.throw(_("Employee already has a Confirmed contract; no further contracts can be created"))

	def validate_overlap(self):
		if not self.start_date or not self.end_date:
			return
		overlap = frappe.db.get_value(
			"Employee Contract",
			{
				"employee": self.employee,
				"docstatus": 1,
				"name": ["!=", self.name or ""],
				"start_date": ["<=", self.end_date],
				"end_date": [">=", self.start_date],
			},
			"name",
		)
		if overlap:
			frappe.throw(_("Contract dates overlap with {0}").format(overlap))


def has_confirmed_contract(employee, exclude=None):
	return bool(
		frappe.db.exists(
			"Employee Contract",
			{"employee": employee, "docstatus": 1, "status": "Confirmed", "name": ["!=", exclude or ""]},
		)
	)


@frappe.whitelist()
def make_renewal(source_name: str) -> dict:
	frappe.has_permission("Employee Contract", "create", throw=True)
	frappe.has_permission("Employee Contract", "read", source_name, throw=True)
	source = frappe.get_doc("Employee Contract", source_name)
	if source.docstatus != 1 or source.status != "Active":
		frappe.throw(_("Only an Active contract can be renewed"))
	if has_confirmed_contract(source.employee):
		frappe.throw(_("Employee already has a Confirmed contract"))
	doc = frappe.new_doc("Employee Contract")
	doc.employee = source.employee
	doc.employment_type = source.employment_type
	doc.previous_contract = source.name
	doc.start_date = add_days(source.end_date, 1)
	return doc.as_dict()


@frappe.whitelist()
def confirm_as_permanent(contract: str, confirmation_date: str, employment_type: str) -> None:
	if not confirmation_date or not employment_type:
		frappe.throw(_("Confirmation Date and Employment Type are required"))
	doc = frappe.get_doc("Employee Contract", contract)
	doc.check_permission("submit")
	if doc.docstatus != 1 or doc.status not in ("Active", "Expired"):
		frappe.throw(_("Only an Active or Expired contract can be confirmed"))
	latest = frappe.db.get_value(
		"Employee Contract",
		{"employee": doc.employee, "docstatus": 1},
		"name",
		order_by="contract_number desc, creation desc",
	)
	if latest != doc.name:
		frappe.throw(_("Only the employee's latest contract can be confirmed"))
	if not frappe.db.exists("Employment Type", employment_type):
		frappe.throw(_("Employment Type {0} does not exist").format(employment_type))
	doc.db_set(
		{
			"status": "Confirmed",
			"confirmation_date": getdate(confirmation_date),
			"confirmed_employment_type": employment_type,
		}
	)
	sync_employee(doc.employee)
