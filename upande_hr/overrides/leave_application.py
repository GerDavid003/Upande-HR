import frappe
from frappe import _
from frappe.utils import flt
from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee
from hrms.hr.doctype.leave_application.leave_application import (
	LeaveApplication,
	get_leave_balance_on,
)
from hrms.hr.doctype.leave_ledger_entry.leave_ledger_entry import create_leave_ledger_entry

COMPASSIONATE_LEAVE_TYPE = "Compassionate Leave"
COMPASSIONATE_GATED_COMPANY = "Karen Roses"


class CustomLeaveApplication(LeaveApplication):
	def _is_compassionate(self):
		return (
			self.leave_type == "Annual Leave"
			and self.company == COMPASSIONATE_GATED_COMPANY
			and bool(self.get("custom_is_compassionate"))
		)

	def validate(self):
		super().validate()
		if self._is_compassionate():
			self._validate_compassionate_balance()

	def validate_applicable_after(self):
		if self._is_compassionate():
			return
		super().validate_applicable_after()

	def _validate_compassionate_balance(self):
		balance = get_leave_balance_on(
			self.employee,
			COMPASSIONATE_LEAVE_TYPE,
			self.from_date,
			self.to_date,
			consider_all_leaves_in_the_allocation_period=True,
			for_consumption=True,
		)
		available = flt(balance.get("leave_balance_for_consumption"))
		if flt(self.total_leave_days) > available:
			frappe.throw(
				_(
					"Insufficient Compassionate Leave balance. {0} has {1} day(s) remaining, "
					"but this application is for {2} day(s)."
				).format(self.employee_name or self.employee, available, self.total_leave_days)
			)

	def on_submit(self):
		super().on_submit()
		if self._is_compassionate():
			self._deduct_compassionate_leave_ledger()
			self._set_compassionate_balance_note()

	def _deduct_compassionate_leave_ledger(self):
		create_leave_ledger_entry(
			self,
			{
				"leave_type": COMPASSIONATE_LEAVE_TYPE,
				"leaves": -self.total_leave_days,
				"from_date": self.from_date,
				"to_date": self.to_date,
				"holiday_list": get_holiday_list_for_employee(self.employee, raise_exception=False) or "",
			},
			submit=True,
		)

	def _set_compassionate_balance_note(self):
		annual_balance = flt(get_leave_balance_on(self.employee, "Annual Leave", self.to_date))
		compassionate_balance = flt(get_leave_balance_on(self.employee, COMPASSIONATE_LEAVE_TYPE, self.to_date))
		note = _(
			"Compassionate Leave applied: {0} day(s). Annual Leave balance: {1}. Compassionate Leave balance: {2}."
		).format(self.total_leave_days, annual_balance, compassionate_balance)
		self.db_set("custom_compassionate_balance_note", note, update_modified=False)
