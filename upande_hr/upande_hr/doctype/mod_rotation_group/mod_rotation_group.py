# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, formatdate, get_link_to_form, getdate

from upande_hr.attendance import mod_roster


class MODRotationGroup(Document):
	def validate(self):
		self.validate_rotation()
		self.validate_members()

	def validate_rotation(self):
		if cint(self.cycle_weeks) < 1:
			frappe.throw(_("Cycle (Weeks) must be at least 1."))
		if not 1 <= cint(self.duty_week) <= cint(self.cycle_weeks):
			frappe.throw(_("Duty Week must be between 1 and {0}.").format(cint(self.cycle_weeks)))

		duty_weekday = mod_roster.get_settings().duty_weekday
		if mod_roster.WEEKDAYS[getdate(self.anchor_date).weekday()] != duty_weekday:
			frappe.throw(
				_("Anchor Date {0} is a {1}; it must be a {2}, the MOD duty weekday in HR Settings.").format(
					formatdate(self.anchor_date),
					_(mod_roster.WEEKDAYS[getdate(self.anchor_date).weekday()]),
					_(duty_weekday),
				)
			)

	def validate_members(self):
		rows = []
		for row in self.members:
			if row.to_date and getdate(row.to_date) < getdate(row.from_date):
				frappe.throw(_("Row {0}: To Date cannot be before From Date.").format(row.idx))
			for other in rows:
				if other.employee == row.employee and overlaps(other, row):
					frappe.throw(
						_("Row {0}: {1} is already in this group for overlapping dates (row {2}).").format(
							row.idx, frappe.bold(row.employee_name or row.employee), other.idx
						)
					)
			rows.append(row)

		if not cint(self.is_active) or not self.members:
			return

		Group = frappe.qb.DocType(mod_roster.GROUP)
		Member = frappe.qb.DocType(mod_roster.MEMBER)
		others = (
			frappe.qb.from_(Member)
			.join(Group)
			.on(Group.name == Member.parent)
			.select(Member.employee, Member.from_date, Member.to_date, Group.name.as_("group"))
			.where(
				(Group.is_active == 1)
				& (Group.name != (self.name or ""))
				& (Member.parenttype == mod_roster.GROUP)
				& (Member.employee.isin([r.employee for r in self.members]))
			)
		).run(as_dict=True)
		for row in self.members:
			for other in others:
				if other.employee == row.employee and overlaps(other, row):
					frappe.throw(
						_("Row {0}: {1} is already in the active group {2} for overlapping dates.").format(
							row.idx,
							frappe.bold(row.employee_name or row.employee),
							get_link_to_form(mod_roster.GROUP, other.group),
						)
					)

	def on_update(self):
		before = self.get_doc_before_save()
		employees = {r.employee for r in self.members}
		if before:
			employees |= {r.employee for r in before.members}
		regenerate(sorted(employees))

	def on_trash(self):
		self.flags.mod_employees = sorted({r.employee for r in self.members})

	def after_delete(self):
		regenerate(self.flags.mod_employees or [])


def overlaps(a, b) -> bool:
	a_end = getdate(a.to_date) if a.to_date else None
	b_end = getdate(b.to_date) if b.to_date else None
	return (a_end is None or getdate(b.from_date) <= a_end) and (
		b_end is None or getdate(a.from_date) <= b_end
	)


def regenerate(employees):
	if not employees or not mod_roster.get_settings().enabled:
		return
	result = mod_roster.regenerate(employees=employees)
	show_result(result)


def show_result(result):
	if result.cover:
		frappe.msgprint(
			mod_roster.cover_message(result.cover),
			title=_("Not enough MODs on duty"),
			indicator="orange",
		)
	if result.problems:
		frappe.msgprint("<br>".join(result.problems), title=_("MOD Roster"), indicator="orange")
