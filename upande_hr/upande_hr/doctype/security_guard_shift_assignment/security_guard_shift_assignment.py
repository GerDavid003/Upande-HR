# Copyright (c) 2026, Upande LTD and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SecurityGuardShiftAssignment(Document):
	def on_submit(self):
		# Security Guard.security_guard_shift_assignment is read-only and has
		# nothing else to populate it -- submitting this assignment makes it
		# the guard's active one. A later assignment's submit simply
		# overwrites this pointer with itself. active_assignment's
		# "fetch_from: security_guard_shift_assignment.shift_type" only fires
		# during a full document save cycle, not a raw db.set_value on the
		# source field, so it's set explicitly here alongside the pointer.
		frappe.db.set_value(
			"Security Guard",
			self.security_guard,
			{"security_guard_shift_assignment": self.name, "active_assignment": self.shift_type},
		)

	def on_cancel(self):
		# Only clear the pointer if it's still pointing at this exact
		# assignment -- a later assignment may have already superseded it.
		if frappe.db.get_value("Security Guard", self.security_guard, "security_guard_shift_assignment") == self.name:
			frappe.db.set_value(
				"Security Guard",
				self.security_guard,
				{"security_guard_shift_assignment": None, "active_assignment": None},
			)
