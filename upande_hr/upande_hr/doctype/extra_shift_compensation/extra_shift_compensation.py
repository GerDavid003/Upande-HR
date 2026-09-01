# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, cint, flt, format_date, get_link_to_form, getdate, today
from hrms.hr.utils import create_additional_leave_ledger_entry, get_leave_period

OFF_DAY = "Worked on Off Day"
LEAVE_DAY = "Reported on Leave Day"
DOUBLE_SHIFT = "Double Shift"

SETTINGS = "Extra Shift Compensation Settings"

# Attendance statuses that mean the employee was recorded as working.
PRESENT = "Present"


def get_settings():
	"""Settings singleton, falling back to the doctype defaults on a site where the
	single has never been saved."""
	settings = frappe.get_cached_doc(SETTINGS)
	return frappe._dict(
		leave_type=settings.leave_type or "Compensatory Off Day",
		max_backdate_days=cint(settings.max_backdate_days) or 30,
		overtime_overlap_action=settings.overtime_overlap_action or "Block",
	)


class ExtraShiftCompensation(Document):
	def validate(self):
		self.set_requested_by()
		self.number_of_entries = len(self.entries or [])

		settings = get_settings()
		for row in self.entries:
			self.validate_row_dates(row, settings)
			self.validate_row_days_awarded(row)
			self.validate_no_duplicate_entry(row)
			self.set_verification_note(row, settings)
			self.check_overtime_overlap(row, settings)

	def before_submit(self):
		if not any(row.row_status == "Approved" for row in self.entries):
			frappe.throw(
				_("At least one entry must be marked {0} before this request can be submitted.").format(
					frappe.bold(_("Approved"))
				)
			)

	def on_submit(self):
		settings = get_settings()
		for row in self.entries:
			if row.row_status != "Approved":
				continue
			allocation = self.credit_comp_off(row, settings)
			row.db_set("leave_allocation", allocation.name)
			if row.reason == LEAVE_DAY:
				self.override_attendance(row)

	def on_cancel(self):
		# Attendance rows point back here through custom_comp_off_request; the reversal
		# below clears those links, and on_cancel runs before frappe's back-link check.
		for row in self.entries:
			if row.reason == LEAVE_DAY:
				self.restore_attendance(row)
			if row.leave_allocation:
				self.debit_comp_off(row)

	# ------------------------------------------------------------------ validation

	def set_requested_by(self):
		if self.requested_by:
			return
		self.requested_by = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")

	def validate_row_dates(self, row, settings):
		if not row.work_date:
			return

		work_date = getdate(row.work_date)
		if work_date > getdate(today()):
			frappe.throw(
				_("Row #{0} ({1}): Work Date {2} is in the future.").format(
					row.idx, self.row_label(row), frappe.bold(format_date(work_date))
				)
			)

		oldest_allowed = add_days(today(), -settings.max_backdate_days)
		if work_date < getdate(oldest_allowed):
			frappe.throw(
				_(
					"Row #{0} ({1}): Work Date {2} is older than the {3} day backdating limit. "
					"The earliest date that can be claimed today is {4}."
				).format(
					row.idx,
					self.row_label(row),
					frappe.bold(format_date(work_date)),
					frappe.bold(settings.max_backdate_days),
					frappe.bold(format_date(oldest_allowed)),
				)
			)

	def validate_row_days_awarded(self, row):
		if flt(row.days_awarded) <= 0:
			frappe.throw(
				_("Row #{0} ({1}): Days Awarded must be greater than zero.").format(
					row.idx, self.row_label(row)
				)
			)

	def validate_no_duplicate_entry(self, row):
		"""One submitted award per employee per date.

		Rejected rows are ignored: they credited nothing, so the same date may be
		claimed again."""
		if not (row.employee and row.work_date):
			return

		Entry = frappe.qb.DocType("Extra Shift Compensation Entry")
		Parent = frappe.qb.DocType("Extra Shift Compensation")
		duplicate = (
			frappe.qb.from_(Entry)
			.join(Parent)
			.on(Entry.parent == Parent.name)
			.select(Parent.name)
			.where(
				(Entry.employee == row.employee)
				& (Entry.work_date == getdate(row.work_date))
				& (Entry.row_status != "Rejected")
				& (Parent.docstatus == 1)
				& (Parent.name != (self.name or ""))
			)
			.limit(1)
		).run(pluck=True)

		if duplicate:
			frappe.throw(
				_("Row #{0} ({1}): {2} is already claimed on {3}.").format(
					row.idx,
					self.row_label(row),
					frappe.bold(format_date(row.work_date)),
					get_link_to_form("Extra Shift Compensation", duplicate[0]),
				)
			)

	def set_verification_note(self, row, settings):
		"""Rebuild the note from scratch on every save so it always describes the
		current employee/date/reason rather than accumulating stale text."""
		if not (row.employee and row.work_date and row.reason):
			return

		if row.reason == OFF_DAY:
			row.verification_note = self.verify_off_day(row)
		elif row.reason == LEAVE_DAY:
			row.verification_note = self.verify_leave_day(row)
		elif row.reason == DOUBLE_SHIFT:
			row.verification_note = self.describe_punches(row)

	def verify_off_day(self, row):
		# as_on matters: Holiday List Assignment is date-effective, so a backdated
		# work_date must be checked against the list in force on that date.
		holiday_list = get_holiday_list_for_employee(
			row.employee, raise_exception=False, as_on=getdate(row.work_date)
		)
		if not holiday_list:
			frappe.throw(
				_(
					"Row #{0} ({1}): no Holiday List is set on the employee or their company, "
					"so an off day cannot be verified."
				).format(row.idx, self.row_label(row))
			)

		holiday = frappe.db.get_value(
			"Holiday",
			{"parent": holiday_list, "holiday_date": getdate(row.work_date)},
			["name", "weekly_off", "description"],
			as_dict=True,
		)
		if not holiday:
			frappe.throw(
				_("Row #{0} ({1}): {2} is not an off day on Holiday List {3}.").format(
					row.idx,
					self.row_label(row),
					frappe.bold(format_date(row.work_date)),
					frappe.bold(holiday_list),
				)
			)

		if not holiday.weekly_off:
			frappe.throw(
				_(
					"Row #{0} ({1}): {2} is the gazetted public holiday {3}, not a weekly off. "
					"Public holidays are compensated at 2:1 through a {4} instead."
				).format(
					row.idx,
					self.row_label(row),
					frappe.bold(format_date(row.work_date)),
					frappe.bold(holiday.description or holiday.name),
					f"""<a href="/app/compensatory-leave-request/new">{_("Compensatory Leave Request")}</a>""",
				),
				title=_("Use Compensatory Leave Request"),
			)

		return _("Weekly off on Holiday List {0}{1}.").format(
			holiday_list, f" ({holiday.description})" if holiday.description else ""
		)

	def verify_leave_day(self, row):
		leave = frappe.db.get_value(
			"Leave Application",
			{
				"employee": row.employee,
				"docstatus": 1,
				"status": "Approved",
				"from_date": ("<=", getdate(row.work_date)),
				"to_date": (">=", getdate(row.work_date)),
			},
			["name", "leave_type", "from_date", "to_date"],
			as_dict=True,
		)
		if not leave:
			frappe.throw(
				_(
					"Row #{0} ({1}): no approved Leave Application covers {2}, "
					"so there is no leave day to compensate."
				).format(row.idx, self.row_label(row), frappe.bold(format_date(row.work_date)))
			)

		return _("Reported for duty during {0} on Leave Application {1} ({2} to {3}).").format(
			leave.leave_type,
			leave.name,
			format_date(leave.from_date),
			format_date(leave.to_date),
		)

	def describe_punches(self, row):
		"""Double shifts are not machine-verifiable here: the rota is barely loaded and
		punch data is noisy, so record what the punches say and let the approver judge."""
		work_date = getdate(row.work_date)
		punches = frappe.get_all(
			"Employee Checkin",
			filters={
				"employee": row.employee,
				"time": ("between", [f"{work_date} 00:00:00", f"{work_date} 23:59:59"]),
			},
			pluck="time",
			order_by="time asc",
		)

		if not punches:
			return _("No Employee Checkin records on {0} — no punch data to verify against.").format(
				format_date(work_date)
			)

		first, last = punches[0], punches[-1]
		span_hours = flt((last - first).total_seconds() / 3600.0, 2)
		return _(
			"{0} check-in(s) on {1}, first {2} to last {3} — span {4} hrs. Verify before approving."
		).format(
			len(punches),
			format_date(work_date),
			first.strftime("%H:%M"),
			last.strftime("%H:%M"),
			span_hours,
		)

	def check_overtime_overlap(self, row, settings):
		"""Bulk Overtime lives in upande_ta. Guard the read so this never hard-fails on
		a bench without that app."""
		if settings.overtime_overlap_action == "Ignore":
			return
		if not (row.employee and row.work_date):
			return
		if not frappe.db.exists("DocType", "Bulk Overtime Entry"):
			return

		# Bulk Overtime Entry is a child table, so its own row mirrors the parent docstatus.
		overlap = frappe.db.get_value(
			"Bulk Overtime Entry",
			{
				"employee": row.employee,
				"overtime_date": getdate(row.work_date),
				"docstatus": 1,
			},
			["parent", "name"],
			as_dict=True,
		)
		if not overlap:
			return

		message = _("Row #{0} ({1}): overtime is already claimed for {2} on Bulk Overtime {3}.").format(
			row.idx,
			self.row_label(row),
			frappe.bold(format_date(row.work_date)),
			get_link_to_form("Bulk Overtime", overlap.parent),
		)

		if settings.overtime_overlap_action == "Warn":
			frappe.msgprint(message, title=_("Overtime Already Claimed"), indicator="orange")
		else:
			frappe.throw(message, title=_("Overtime Already Claimed"))

	def row_label(self, row):
		return row.employee_name or row.employee

	# ---------------------------------------------------------------- leave balance

	def credit_comp_off(self, row, settings):
		"""Add days_awarded to the employee's existing Compensatory Off Day allocation,
		or create one. Mirrors CompensatoryLeaveRequest.on_submit() so the leave ledger
		entry is written the same way."""
		valid_from = add_days(getdate(row.work_date), 1)
		company = frappe.db.get_value("Employee", row.employee, "company") or self.company
		leave_period = get_leave_period(valid_from, valid_from, company)

		if not leave_period:
			frappe.throw(
				_(
					"Row #{0} ({1}): the compensatory day earned on {2} would be valid from {3}, "
					"and there is no active Leave Period covering that date. "
					"Create a {4} for {3} first."
				).format(
					row.idx,
					self.row_label(row),
					frappe.bold(format_date(row.work_date)),
					frappe.bold(format_date(valid_from)),
					f"""<a href="/app/leave-period">{_("Leave Period")}</a>""",
				),
				title=_("No Leave Period Found"),
			)

		days = flt(row.days_awarded)
		allocation = self.get_existing_allocation(row, settings.leave_type, valid_from)

		if not allocation:
			return self.create_leave_allocation(row, settings.leave_type, leave_period, valid_from, days)

		# Increment, never replace: allocations on this leave type also carry entitlement
		# granted outside this feature.
		allocation.new_leaves_allocated = flt(allocation.new_leaves_allocated) + days
		allocation.validate()
		allocation.db_set("new_leaves_allocated", allocation.new_leaves_allocated)
		allocation.db_set("total_leaves_allocated", allocation.total_leaves_allocated)

		# Ledger entry for the delta only. Note this mutates the in-memory allocation,
		# so it must run after the db_set calls above and the doc is not reused after.
		create_additional_leave_ledger_entry(allocation, days, valid_from)
		return allocation

	def debit_comp_off(self, row):
		allocation = frappe.get_doc("Leave Allocation", row.leave_allocation)
		if allocation.docstatus != 1:
			return

		days = flt(row.days_awarded)
		new_leaves = max(flt(allocation.new_leaves_allocated) - days, 0)

		# Deliberately not calling allocation.validate(): once `Compensatory Off Day` is
		# no longer flagged is_compensatory, Leave Allocation.set_total_leaves_allocated()
		# throws when the total reaches zero, which would make this request impossible to
		# cancel. Recompute the total directly instead.
		allocation.db_set("new_leaves_allocated", new_leaves)
		allocation.db_set("total_leaves_allocated", flt(allocation.unused_leaves) + new_leaves)

		create_additional_leave_ledger_entry(allocation, days * -1, add_days(getdate(row.work_date), 1))
		row.db_set("leave_allocation", None)

	def get_existing_allocation(self, row, leave_type, valid_from):
		name = frappe.db.get_value(
			"Leave Allocation",
			{
				"employee": row.employee,
				"leave_type": leave_type,
				"from_date": ("<=", valid_from),
				"to_date": (">=", valid_from),
				"docstatus": 1,
			},
			"name",
		)
		return frappe.get_doc("Leave Allocation", name) if name else None

	def create_leave_allocation(self, row, leave_type, leave_period, valid_from, days):
		allocation = frappe.get_doc(
			{
				"doctype": "Leave Allocation",
				"employee": row.employee,
				"employee_name": row.employee_name,
				"leave_type": leave_type,
				"from_date": valid_from,
				"to_date": leave_period[0].to_date,
				"carry_forward": cint(frappe.db.get_value("Leave Type", leave_type, "is_carry_forward")),
				"new_leaves_allocated": days,
				"total_leaves_allocated": days,
				"description": _("Extra Shift Compensation {0}: {1} on {2}").format(
					self.name, row.reason, format_date(row.work_date)
				),
			}
		)
		allocation.insert(ignore_permissions=True)
		allocation.submit()
		return allocation

	# ------------------------------------------------------------------- attendance

	def override_attendance(self, row):
		"""She reported for duty, so the day should read Present rather than On Leave.

		The flip is held in place by the Attendance validate hook in
		upande_hr.overrides.attendance — without it, check_leave_record() puts the day
		back On Leave the next time anyone saves the record."""
		work_date = getdate(row.work_date)
		attendance = frappe.db.get_value(
			"Attendance",
			{"employee": row.employee, "attendance_date": work_date, "docstatus": 1},
			["name", "status", "leave_application"],
			as_dict=True,
		)

		if not attendance:
			self.create_present_attendance(row, work_date)
			return

		# Saved before the flip so on_cancel can put the record back as it was.
		row.db_set("original_attendance_status", attendance.status)
		row.db_set("original_leave_application", attendance.leave_application)

		frappe.get_doc("Attendance", attendance.name).db_set(
			{
				"status": PRESENT,
				"leave_type": None,
				"leave_application": None,
				"custom_comp_off_override": 1,
				"custom_comp_off_request": self.name,
			},
			notify=True,
		)

	def create_present_attendance(self, row, work_date):
		attendance = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": row.employee,
				"employee_name": row.employee_name,
				"attendance_date": work_date,
				"status": PRESENT,
				"company": frappe.db.get_value("Employee", row.employee, "company") or self.company,
				"custom_comp_off_override": 1,
				"custom_comp_off_request": self.name,
			}
		)
		# check_leave_record() will try to set this to On Leave during validate; the
		# doc_events hook runs afterwards and puts it back to Present.
		attendance.insert(ignore_permissions=True)
		attendance.submit()

	def restore_attendance(self, row):
		work_date = getdate(row.work_date)
		name = frappe.db.get_value(
			"Attendance",
			{
				"employee": row.employee,
				"attendance_date": work_date,
				"custom_comp_off_request": self.name,
				"docstatus": 1,
			},
			"name",
		)
		if not name:
			return

		attendance = frappe.get_doc("Attendance", name)

		if not row.original_attendance_status:
			# No Attendance existed before submit, so there is nothing to restore to.
			attendance.db_set({"custom_comp_off_override": 0, "custom_comp_off_request": None})
			attendance.flags.ignore_permissions = True
			attendance.cancel()
			return

		leave_application = row.original_leave_application or None
		attendance.db_set(
			{
				"status": row.original_attendance_status,
				"leave_application": leave_application,
				"leave_type": frappe.db.get_value("Leave Application", leave_application, "leave_type")
				if leave_application
				else None,
				"custom_comp_off_override": 0,
				"custom_comp_off_request": None,
			},
			notify=True,
		)
		row.db_set("original_attendance_status", None)
		row.db_set("original_leave_application", None)
