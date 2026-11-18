# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class UpandeHRSettings(Document):
	def validate(self):
		self.validate_reminder_days()
		self.validate_reminders_enabled()

	def validate_reminder_days(self):
		seen = set()
		for row in self.contract_reminder_days:
			if row.days_before < 0:
				frappe.throw(_("Row #{0}: Days Before Expiry cannot be negative").format(row.idx))
			if row.days_before in seen:
				frappe.throw(_("Row #{0}: Duplicate Days Before Expiry {1}").format(row.idx, row.days_before))
			seen.add(row.days_before)

	def validate_reminders_enabled(self):
		if not self.enable_contract_expiry_reminders:
			return
		if not self.contract_reminder_days:
			frappe.throw(_("Add at least one reminder day to enable contract expiry reminders"))
		if not self.contract_reminder_recipients and not self.notify_reporting_manager:
			frappe.throw(
				_("Add at least one recipient or enable Notify Reporting Manager to enable contract expiry reminders")
			)
