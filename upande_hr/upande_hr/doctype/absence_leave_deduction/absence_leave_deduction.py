# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate


class AbsenceLeaveDeduction(Document):
	def autoname(self):
		# The primary key is the idempotency guarantee: one row per employee-date, ever.
		self.name = make_name(self.employee, self.absence_date)


def make_name(employee: str, absence_date) -> str:
	return f"{employee}-{getdate(absence_date)}"
