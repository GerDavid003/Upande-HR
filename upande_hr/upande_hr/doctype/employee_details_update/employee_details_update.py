# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Employee Details Update - employees confirm or correct their own record once a year.

On submit the form is written back to the Employee and Employee.custom_details_confirmed_on
is set to today. Leave Application is gated on that date being in the current calendar
year (see gate_leave_application below), so everyone re-locks on 1 January without a
reset job.

Bank details (salary mode, bank, branch, account) and M-Pesa are the fraud-sensitive
part: payroll pays into whatever is on the Employee. validate() flags bank_details_changed when they differ from the Employee,
and the "Employee Details Update Approval" Workflow routes a flagged form through
Pending HR Review instead of letting the employee submit it straight to Approved.

Emergency Contacts are copied into Employee.custom_emergency_contacts, which replaces the
standard single-contact fields.

Next of Kin is copied into Employee.custom_next_of_kin, an upande_ats field. upande_hr
does not declare upande_ats in required_apps, so the form carries its own child table and
the copy is skipped when the field is not on the site.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr, flt, getdate, today

CONFIRMED_ON = "custom_details_confirmed_on"
EMPLOYEE_NOK_FIELD = "custom_next_of_kin"
EMPLOYEE_FAMILY_FIELD = "custom_family_members"
EMPLOYEE_EC_FIELD = "custom_emergency_contacts"

# form field -> Employee field
FIELD_MAP = {
	"first_name": "first_name",
	"middle_name": "middle_name",
	"last_name": "last_name",
	"gender": "gender",
	"date_of_birth": "date_of_birth",
	"marital_status": "marital_status",
	"national_id_no": "custom_national_id_no",
	"nationality": "custom_nationality",
	"kra_pin": "custom_kra_pin",
	"nssf_no": "custom_nssf_no",
	"sha_no": "custom_sha_no",
	"cell_number": "cell_number",
	"personal_email": "personal_email",
	"alt_phone": "custom_alt_phone",
	"estate_village": "custom_estate_village",
	"nearest_town": "custom_nearest_town",
	"landmark": "custom_landmark",
	"county": "custom_county",
	"sub_county": "custom_sub_county",
	"postal_address": "custom_postal_address",
	"salary_mode": "salary_mode",
	# Employee.bank_name is a Link to Bank on TSH (Property Setter), not the free-text
	# name the label suggests. custom_bank_branch is an Upande Payroll field.
	"bank": "bank_name",
	"bank_branch": "custom_bank_branch",
	"bank_ac_no": "bank_ac_no",
	"mpesa_number": "custom_mpesa_number",
}
BANK_FIELDS = ("salary_mode", "bank", "bank_branch", "bank_ac_no", "mpesa_number")
NOK_FIELDS = ("full_name", "relationship", "national_id_no", "phone_no", "allocation_percentage")
FAMILY_FIELDS = ("full_name", "relationship", "id_number")
EC_FIELDS = ("contact_name", "relationship", "phone")
# An employee may have one form open at a time. Approved (submitted), Rejected and
# cancelled forms are finished; anything else - Draft, Pending HR Review - is still open.
# Rejected is the only finished state that stays a draft, hence docstatus 0 below.
REJECTED = "Rejected"


class EmployeeDetailsUpdate(Document):
	def before_insert(self):
		self.validate_one_open_form()

	def validate_one_open_form(self):
		"""Applies only to an employee filling in their own form, not HR filing for them."""
		own = get_session_employee()
		if not own or self.employee != own:
			return
		existing = get_open_form(own)
		if not existing:
			return
		link = f'<a href="/app/employee-details-update/{existing.name}">{existing.name}</a>'
		if existing.workflow_state == "Pending HR Review":
			next_step = _("You can start a new one once HR has approved or rejected it.")
		else:
			next_step = _("Please finish and submit it instead of starting a new one.")
		frappe.throw(
			_("You already have a Details Update form ({0}) in status {1}.").format(
				link, frappe.bold(existing.workflow_state or "Draft")
			)
			+ " "
			+ next_step,
			title=_("Active Submission Exists"),
		)

	def validate(self):
		self.validate_own_record()
		self.validate_emergency_contacts()
		self.validate_next_of_kin()
		self.bank_details_changed = int(self.has_bank_change())

	def validate_own_record(self):
		"""An employee may only update their own record; HR may update anyone's."""
		if frappe.session.user == "Administrator" or {"HR User", "HR Manager"} & set(frappe.get_roles()):
			return
		own = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
		if self.employee != own:
			frappe.throw(_("You can only update your own personal details."), frappe.PermissionError)

	def validate_emergency_contacts(self):
		if not self.emergency_contacts:
			frappe.throw(_("Please add at least one Emergency Contact."))

	def validate_next_of_kin(self):
		# Every next of kin needs a share, and the shares must account for the whole benefit.
		if not self.next_of_kin:
			frappe.throw(_("Please add at least one Next of Kin."))
		total = 0
		for row in self.next_of_kin:
			if flt(row.allocation_percentage) <= 0:
				frappe.throw(
					_("Row {0} in Next of Kin: Allocation (%) must be greater than 0.").format(row.idx)
				)
			total += flt(row.allocation_percentage)
		if flt(total, 2) != 100:
			frappe.throw(
				_("Next of Kin allocations must add up to exactly 100%. Current total: {0}%").format(
					flt(total, 2)
				)
			)

	def has_bank_change(self) -> bool:
		if not self.employee:
			return False
		employee = frappe.get_cached_doc("Employee", self.employee)
		return any(
			cstr(self.get(field)).strip() != cstr(employee.get(FIELD_MAP[field])).strip()
			for field in BANK_FIELDS
			if employee.meta.has_field(FIELD_MAP[field])
		)

	def before_submit(self):
		# The workflow picks Submit vs Submit for HR Review from bank_details_changed as
		# the client sent it. validate() has just recomputed it from the Employee, so a
		# crafted request cannot carry a bank change past HR.
		if self.bank_details_changed:
			previous_state = frappe.db.get_value(self.doctype, self.name, "workflow_state")
			if previous_state != "Pending HR Review":
				frappe.throw(_("Bank / M-Pesa changes must be reviewed by HR before they are applied."))

	def on_submit(self):
		self.write_back()

	def write_back(self):
		employee = frappe.get_doc("Employee", self.employee)
		for source, target in FIELD_MAP.items():
			if employee.meta.has_field(target):
				employee.set(target, self.get(source))

		if employee.meta.has_field(EMPLOYEE_EC_FIELD):
			employee.set(
				EMPLOYEE_EC_FIELD, [{f: row.get(f) for f in EC_FIELDS} for row in self.emergency_contacts]
			)
		if employee.meta.has_field(EMPLOYEE_NOK_FIELD):
			employee.set(
				EMPLOYEE_NOK_FIELD, [{f: row.get(f) for f in NOK_FIELDS} for row in self.next_of_kin]
			)
		if employee.meta.has_field(EMPLOYEE_FAMILY_FIELD):
			employee.set(
				EMPLOYEE_FAMILY_FIELD, [{f: row.get(f) for f in FAMILY_FIELDS} for row in self.family_members]
			)

		employee.set(CONFIRMED_ON, today())
		# The employee has no write permission on their own Employee record; the form's
		# own permissions, and HR review for bank changes, are the check.
		employee.flags.ignore_permissions = True
		employee.save()
		employee.add_comment("Info", _("Details updated from {0}.").format(frappe.bold(self.name)))


@frappe.whitelist()
def get_current_details(employee: str) -> dict:
	"""Current Employee values, shaped as this form, to prefill a new update."""
	if not frappe.has_permission("Employee", "read", employee):
		own = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
		if employee != own:
			frappe.throw(_("Not permitted"), frappe.PermissionError)

	doc = frappe.get_doc("Employee", employee)
	out = {source: doc.get(target) for source, target in FIELD_MAP.items() if doc.meta.has_field(target)}
	if doc.meta.has_field(EMPLOYEE_EC_FIELD):
		out["emergency_contacts"] = [{f: row.get(f) for f in EC_FIELDS} for row in doc.get(EMPLOYEE_EC_FIELD)]
	if doc.meta.has_field(EMPLOYEE_NOK_FIELD):
		out["next_of_kin"] = [{f: row.get(f) for f in NOK_FIELDS} for row in doc.get(EMPLOYEE_NOK_FIELD)]
	if doc.meta.has_field(EMPLOYEE_FAMILY_FIELD):
		out["family_members"] = [
			{f: row.get(f) for f in FAMILY_FIELDS} for row in doc.get(EMPLOYEE_FAMILY_FIELD)
		]
	return out


@frappe.whitelist()
def get_session_employee() -> str | None:
	return frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")


def get_open_form(employee: str):
	"""The employee's unfinished form, the most recent if there is more than one (forms
	made before the one-open-form rule may have left several)."""
	# Filtered here rather than in the query: a "!=" filter drops rows whose
	# workflow_state is NULL, and those are still open.
	drafts = frappe.get_all(
		"Employee Details Update",
		filters={"employee": employee, "docstatus": 0},
		fields=["name", "workflow_state"],
		order_by="modified desc",
	)
	return next((d for d in drafts if d.workflow_state != REJECTED), None)


@frappe.whitelist()
def get_active_submission() -> str | None:
	"""The session user's own unfinished form, for the list and new-form redirects."""
	employee = get_session_employee()
	form = get_open_form(employee) if employee else None
	return form.name if form else None


def details_confirmed_this_year(employee: str) -> bool:
	confirmed_on = frappe.db.get_value("Employee", employee, CONFIRMED_ON)
	return bool(confirmed_on) and getdate(confirmed_on).year == getdate(today()).year


@frappe.whitelist()
def leave_gate_blocks_me() -> bool:
	"""For the Leave Application client script - True when the session user's own leave
	would be refused by gate_leave_application."""
	employee = get_session_employee()
	return bool(employee) and not details_confirmed_this_year(employee)


def gate_leave_application(doc, method=None):
	"""Leave Application.before_insert - no leave until this year's details are confirmed.

	Applies only when an employee applies for themselves: HR applying on someone's
	behalf, and the weekly absent deduction (run as Administrator), pass through.
	"""
	if doc.get("custom_auto_deducted"):
		return
	own = get_session_employee()
	if not own or doc.employee != own:
		return
	if not details_confirmed_this_year(doc.employee):
		frappe.throw(
			_("Please update your Personal Details before applying for leave.")
			+ ' <a href="/app/employee-details-update/new">'
			+ _("Update now")
			+ "</a>",
			title=_("Personal Details Required"),
		)
