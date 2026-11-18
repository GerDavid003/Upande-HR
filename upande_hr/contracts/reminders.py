import frappe
from frappe.utils import date_diff, formatdate, get_url_to_form, getdate, today

EMAIL_TEMPLATE = """
<p>The following employee contract is ending {% if days_left == 0 %}today{% else %}in {{ days_left }} day(s){% endif %}.</p>
<table>
<tr><td><b>Employee</b></td><td>{{ employee_name | e }} ({{ employee | e }})</td></tr>
<tr><td><b>Company</b></td><td>{{ (company or "") | e }}</td></tr>
<tr><td><b>Department</b></td><td>{{ (department or "") | e }}</td></tr>
<tr><td><b>Contract</b></td><td>#{{ contract_number | e }} ({{ employment_type | e }})</td></tr>
<tr><td><b>Start date</b></td><td>{{ start_date | e }}</td></tr>
<tr><td><b>End date</b></td><td>{{ end_date | e }}</td></tr>
<tr><td><b>Days left</b></td><td>{{ days_left }}</td></tr>
</table>
<p><a href="{{ link | e }}">Open contract</a></p>
"""


# `last_reminder_days` is an Int column and cannot hold NULL (it reads 0 when never set), so
# 0 means "nothing sent yet" and a sent point of 0 is stored as -1.
def _decode_last(raw):
	if raw == -1:
		return 0
	return raw or None


def _encode_last(point):
	return -1 if point == 0 else point


def due_point(days_left, points, last_sent):
	if days_left < 0:
		return None
	candidates = [p for p in points if p >= days_left]
	if not candidates:
		return None
	p = min(candidates)
	if last_sent is not None and p >= last_sent:
		return None
	return p


def mark_expired_contracts(on_date=None):
	on_date = getdate(on_date or today())
	for name in frappe.get_all(
		"Employee Contract",
		filters={"status": "Active", "docstatus": 1, "end_date": ["<", on_date]},
		pluck="name",
	):
		frappe.db.set_value("Employee Contract", name, "status", "Expired", update_modified=False)


def get_recipients(contract):
	settings = frappe.get_doc("Upande HR Settings")
	roles = [r.recipient for r in settings.contract_reminder_recipients if r.recipient_type == "Role"]
	profiles = [r.recipient for r in settings.contract_reminder_recipients if r.recipient_type == "Role Profile"]

	users = set()
	if roles:
		users.update(frappe.get_all("Has Role", {"role": ["in", roles], "parenttype": "User"}, pluck="parent"))
	if profiles:
		users.update(frappe.get_all("User", {"role_profile_name": ["in", profiles]}, pluck="name"))
		users.update(
			frappe.get_all("User Role Profile", {"role_profile": ["in", profiles], "parenttype": "User"}, pluck="parent")
		)

	valid = set()
	if users:
		valid = set(
			frappe.get_all(
				"User",
				{"name": ["in", list(users)], "enabled": 1, "email": ["is", "set"]},
				pluck="name",
			)
		)
		valid -= {"Guest", "Administrator"}

	if valid:
		restricted = {}
		for up in frappe.get_all(
			"User Permission",
			{"user": ["in", list(valid)], "allow": "Company"},
			["user", "for_value", "apply_to_all_doctypes", "applicable_for"],
		):
			if not up.apply_to_all_doctypes and up.applicable_for not in (None, "", "Employee Contract"):
				continue
			restricted.setdefault(up.user, set()).add(up.for_value)
		valid = {u for u in valid if u not in restricted or contract.company in restricted[u]}

	if settings.notify_reporting_manager:
		reports_to = frappe.db.get_value("Employee", contract.employee, "reports_to")
		manager_user = reports_to and frappe.db.get_value("Employee", reports_to, "user_id")
		if manager_user and manager_user not in ("Guest", "Administrator"):
			enabled, email = frappe.db.get_value("User", manager_user, ["enabled", "email"]) or (0, None)
			if enabled and email:
				valid.add(manager_user)

	return sorted(valid)


def send_contract_reminders(on_date=None):
	settings = frappe.get_doc("Upande HR Settings")
	if not settings.enable_contract_expiry_reminders:
		return
	on_date = getdate(on_date or today())
	points = [d.days_before for d in settings.contract_reminder_days]

	contracts = frappe.get_all(
		"Employee Contract",
		filters={"status": "Active", "docstatus": 1},
		fields=[
			"name", "employee", "employee_name", "company", "department", "contract_number",
			"employment_type", "start_date", "end_date", "last_reminder_days",
		],
	)
	for c in contracts:
		frappe.db.savepoint("contract_reminder")
		try:
			_process_contract(c, points, on_date)
		except Exception:
			frappe.db.rollback(save_point="contract_reminder")
			frappe.log_error(title=f"Contract reminder failed: {c.name}")


def _process_contract(c, points, on_date):
	if frappe.db.get_value("Employee", c.employee, "status") != "Active":
		return
	days_left = date_diff(c.end_date, on_date)
	p = due_point(days_left, points, _decode_last(c.last_reminder_days))
	if p is None:
		return

	recipients = get_recipients(c)
	subject = message = None
	if recipients:
		prefix = "Contract ends today" if days_left == 0 else f"Contract ending in {days_left} day{'s' if days_left != 1 else ''}"
		subject = f"{prefix}: {c.employee_name} ({c.employee}), contract #{c.contract_number}"
		link = get_url_to_form("Employee Contract", c.name)
		message = frappe.render_template(EMAIL_TEMPLATE, {**c, "start_date": formatdate(c.start_date), "end_date": formatdate(c.end_date), "days_left": days_left, "link": link})

	# bookkeeping and logs first, sendmail last: if anything fails the savepoint rolls
	# everything back, so the reminder is retried next run without a duplicate.
	frappe.db.set_value("Employee Contract", c.name, "last_reminder_days", _encode_last(p), update_modified=False)
	for user in recipients:
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"type": "Alert",
				"for_user": user,
				"subject": subject,
				"document_type": "Employee Contract",
				"document_name": c.name,
			}
		).insert(ignore_permissions=True)
	if recipients:
		frappe.sendmail(
			recipients=recipients,
			subject=subject,
			message=message,
			reference_doctype="Employee Contract",
			reference_name=c.name,
		)


def run_daily():
	mark_expired_contracts()
	send_contract_reminders()
