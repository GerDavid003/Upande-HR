# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import formatdate, getdate

from upande_hr.attendance import mod_roster
from upande_hr.upande_hr.doctype.mod_rotation_group.mod_rotation_group import show_result


class MODDutySwap(Document):
	def validate(self):
		if self.off_employee == self.cover_employee:
			frappe.throw(_("Going Off and Covering must be different employees."))

		roster = mod_roster.Roster()
		day = getdate(self.date)
		if day.weekday() != roster.duty_weekday:
			frappe.throw(
				_("{0} is a {1}; swaps are for the MOD duty weekday ({2}).").format(
					formatdate(day), _(mod_roster.WEEKDAYS[day.weekday()]), _(roster.settings.duty_weekday)
				)
			)

		for employee, expected, label in (
			(self.off_employee, mod_roster.DUTY, _("on duty")),
			(self.cover_employee, mod_roster.OFF, _("off")),
		):
			status = roster.day_status(employee, day, exclude_swap=self.name)
			name = frappe.bold(roster.employee(employee).employee_name or employee)
			if not status.membership:
				frappe.throw(_("{0} is not on an active MOD rotation on {1}.").format(name, formatdate(day)))
			if status.code == mod_roster.PUBLIC_HOLIDAY:
				frappe.throw(
					_("{0} is a public holiday for {1}; there is nothing to swap.").format(
						formatdate(day), name
					)
				)
			if status.code != expected:
				frappe.throw(
					_("{0} is not rostered {1} on {2}{3}.").format(
						name,
						label,
						formatdate(day),
						_(" (already swapped by {0})").format(status.swap) if status.swap else "",
					)
				)

	def on_submit(self):
		self.db_set("approved_by", frappe.session.user)
		self.apply()

	def on_cancel(self):
		self.apply()

	def apply(self):
		"""Rewrite both lists from the swap's own date, even if it is in the past."""
		if not mod_roster.get_settings().enabled:
			return
		result = mod_roster.regenerate(
			employees=[self.off_employee, self.cover_employee], from_date=self.date
		)
		show_result(result)
