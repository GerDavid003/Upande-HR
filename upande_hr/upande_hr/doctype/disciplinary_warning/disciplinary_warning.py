# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_months, cint, getdate, today

ACTIVE = "Active"
EXPIRED = "Expired"
WITHDRAWN = "Withdrawn"


class DisciplinaryWarning(Document):
	def validate(self):
		self.set_expiry_date()
		self.validate_acknowledgement()
		self.set_status()

	def set_expiry_date(self):
		"""Mirrors the client script so a warning created by import, API or the mobile
		app still lapses on schedule. A date typed by hand is left alone."""
		if self.expiry_date:
			return
		if self.issue_date and cint(self.validity_months):
			self.expiry_date = add_months(getdate(self.issue_date), cint(self.validity_months))

	def validate_acknowledgement(self):
		if self.acknowledged and not self.acknowledged_on:
			self.acknowledged_on = today()

		if self.acknowledged_on and self.issue_date and getdate(self.acknowledged_on) < getdate(self.issue_date):
			frappe.throw(_("Acknowledged On cannot be before the Issue Date."))

	def set_status(self):
		"""Withdrawn is a human decision and is never overwritten here."""
		if self.status == WITHDRAWN:
			return
		if self.expiry_date and getdate(self.expiry_date) <= getdate(today()):
			self.status = EXPIRED
		else:
			self.status = ACTIVE


def lapse_expired_warnings():
	"""Daily. Flips Active warnings to Expired once their expiry date has passed, so a
	lapsed warning stops counting towards the next escalation on its own."""
	stale = frappe.get_all(
		"Disciplinary Warning",
		filters={"status": ACTIVE, "expiry_date": ["<=", today()], "docstatus": ["<", 2]},
		pluck="name",
	)
	for name in stale:
		frappe.db.set_value("Disciplinary Warning", name, "status", EXPIRED, update_modified=False)
