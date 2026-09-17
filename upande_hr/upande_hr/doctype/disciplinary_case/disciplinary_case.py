# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today

CLOSED = "Closed"


class DisciplinaryCase(Document):
	def validate(self):
		self.validate_dates()
		self.stamp_closure()

	def validate_dates(self):
		if self.incident_date and self.date_reported and getdate(self.incident_date) > getdate(self.date_reported):
			frappe.throw(_("Incident Date cannot be after Date Reported."))

		if self.absence_from and self.absence_to and getdate(self.absence_from) > getdate(self.absence_to):
			frappe.throw(_("Absent From cannot be after Absent To."))

		for hearing in self.hearings:
			if hearing.hearing_date and self.date_reported and getdate(hearing.hearing_date) < getdate(self.date_reported):
				frappe.throw(
					_("Row {0}: Hearing Date cannot be before the case was reported.").format(hearing.idx)
				)

	def stamp_closure(self):
		"""closed_on is read-only on the form, so the workflow transition to Closed is
		what sets it. Cleared again if the case is ever reopened."""
		if self.workflow_state == CLOSED:
			if not self.closed_on:
				self.closed_on = today()
		else:
			self.closed_on = None
