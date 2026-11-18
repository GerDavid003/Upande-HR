# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Email Templates for the Absent -> Annual Leave deduction.

Shipped as create-if-missing records, not as a fixture: sync_fixtures imports with
force=True on every migrate, which would overwrite whatever wording HR has edited.
ensure_email_templates() runs after every migrate and only inserts a template that does
not exist, so HR owns the wording from then on. Deleting a template restores the
default on the next migrate.
"""

import frappe

EMPLOYEE_TEMPLATE = "Absence Leave Deduction"
HR_SUMMARY_TEMPLATE = "Absence Leave Deduction HR Summary"

TEMPLATES = {
	EMPLOYEE_TEMPLATE: {
		"subject": "Leave deducted for your absence on {{ absence_date }}",
		"response_html": """<p>Dear {{ employee_name }},</p>

<p>You were marked <b>Absent</b> on <b>{{ absence_date }}</b>, a working day with {{ reason }}.</p>

{% if is_lwp %}
<p>Your {{ deduction_leave_type }} balance was not enough to cover the day, so <b>1 full day</b> has been recorded as <b>{{ leave_type }}</b> (unpaid). Your {{ deduction_leave_type }} balance is <b>{{ balance_after }}</b> day(s).</p>
{% else %}
<p><b>1 full day</b> has been deducted from your <b>{{ leave_type }}</b>. Your remaining {{ leave_type }} balance is <b>{{ balance_after }}</b> day(s).</p>
{% endif %}

<p>If you believe this is wrong, for example because you were at work, on an approved gate pass or on approved leave, please contact HR. HR can reverse the deduction (Leave Application {{ leave_application }}).</p>
""",
	},
	HR_SUMMARY_TEMPLATE: {
		"subject": "Absence leave deduction: {{ rows|length }} day(s) need attention ({{ from_date }} to {{ to_date }})",
		"response_html": """<p>The weekly absence leave deduction for {{ from_date }} to {{ to_date }} could not deduct the days below.</p>

{% if outages %}
<p><b>Possible clock-in device or sync failure.</b> Nobody was deducted on {% for o in outages %}{{ o.date }} ({{ o.absent }} of {{ o.eligible }} eligible employees Absent){% if not loop.last %}, {% endif %}{% endfor %}. Check the devices and the attendance for these dates; once the attendance is corrected, re-run the deduction for them.</p>
{% endif %}

<table border="1" cellpadding="4" cellspacing="0" style="border-collapse: collapse;">
<tr><th>Employee</th><th>Name</th><th>Date</th><th>Status</th><th>Reason</th></tr>
{% for row in rows %}
<tr><td>{{ row.employee }}</td><td>{{ row.employee_name }}</td><td>{{ row.absence_date }}</td><td>{{ row.status }}</td><td>{{ row.reason }}</td></tr>
{% endfor %}
</table>

<p><b>Flagged</b>: nothing was deducted; the Reason column says why (not enough leave balance, no Holiday List Assignment, or the outage guard). <b>Error</b>: the deduction failed; see the Error field on the row. Both are listed in the Absence Leave Deductions report.</p>
""",
	},
}


def ensure_email_templates():
	"""after_migrate: insert any missing template, never touch an existing one."""
	for name, values in TEMPLATES.items():
		if frappe.db.exists("Email Template", name):
			continue
		frappe.get_doc({"doctype": "Email Template", "name": name, "use_html": 1, **values}).insert(
			ignore_permissions=True
		)


def render(name: str, context: dict) -> tuple[str, str]:
	"""(subject, message) from the site's template, or the shipped default if HR deleted it."""
	if frappe.db.exists("Email Template", name):
		template = frappe.get_doc("Email Template", name)
		body = template.response_html if template.use_html else template.response
		subject = template.subject
	else:
		subject, body = TEMPLATES[name]["subject"], TEMPLATES[name]["response_html"]

	return frappe.render_template(subject, context), frappe.render_template(body, context)
