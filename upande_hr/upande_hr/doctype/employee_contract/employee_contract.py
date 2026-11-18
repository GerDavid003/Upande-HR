# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, add_months, getdate


class EmployeeContract(Document):
	def before_insert(self):
		self.set_contract_number()

	def validate(self):
		self.set_end_date_from_duration()
		self.validate_dates()
		self.validate_employee()
		self.validate_overlap()

	def on_submit(self):
		self.db_set("status", "Active")

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
		if getdate(self.end_date) < getdate(self.start_date):
			frappe.throw(_("End Date cannot be before Start Date"))
		joining = frappe.db.get_value("Employee", self.employee, "date_of_joining")
		if joining and getdate(self.start_date) < getdate(joining):
			frappe.throw(_("Start Date cannot be before the Employee's Date of Joining ({0})").format(joining))

	def validate_employee(self):
		if frappe.db.get_value("Employee", self.employee, "status") == "Left":
			frappe.throw(_("Cannot create a contract for an employee who has left"))

	def validate_overlap(self):
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
