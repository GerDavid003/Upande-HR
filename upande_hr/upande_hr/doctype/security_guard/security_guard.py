# Copyright (c) 2026, Upande LTD and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

PAYROLL_NUMBER_START = 30001
PAYROLL_NUMBER_RANGE = range(30000, 40000)


class SecurityGuard(Document):
	def validate(self):
		self.full_name = " ".join(
			filter(None, [self.first_name, self.middle_name, self.last_name])
		)

	def before_insert(self):
		# Ported from the "Security Guard - Generate Payroll Number" Server
		# Script: always assign a fresh number on insert (never copy the
		# previous doc's) so duplicating a record can't create two guards
		# sharing the same payroll number.
		last = frappe.db.sql(
			"""select series from `tabSecurity Guard`
			where series is not null and series != ''
			order by cast(series as unsigned) desc limit 1"""
		)
		try:
			next_number = int(last[0][0]) + 1 if last and last[0][0] else PAYROLL_NUMBER_START
		except (ValueError, TypeError):
			next_number = PAYROLL_NUMBER_START

		if next_number not in PAYROLL_NUMBER_RANGE:
			next_number = PAYROLL_NUMBER_START

		self.series = str(next_number)
