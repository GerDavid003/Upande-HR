import os
import frappe
from frappe.utils import add_days, formatdate, today
from hrms.hr.doctype.attendance_request.test_attendance_request import get_employee
from hrms.tests.utils import HRMSTestSuite

from unittest.mock import MagicMock, patch

from upande_hr.contracts.reminders import (
	due_point,
	get_recipients,
	mark_expired_contracts,
	send_contract_reminders,
)
from upande_hr.upande_hr.doctype.employee_contract.test_employee_contract import make_contract


def make_user(email, roles=(), role_profile=None, enabled=1):
	if frappe.db.exists("User", email):
		frappe.delete_doc("User", email, force=True)
	user = frappe.get_doc(
		{"doctype": "User", "email": email, "first_name": email.split("@")[0], "enabled": enabled, "send_welcome_email": 0}
	)
	for r in roles:
		user.append("roles", {"role": r})
	if role_profile:
		user.append("role_profiles", {"role_profile": role_profile})
	user.insert(ignore_permissions=True)
	return user.name


def ensure_role(name):
	if not frappe.db.exists("Role", name):
		frappe.get_doc({"doctype": "Role", "role_name": name}).insert()


class TestContractReminders(HRMSTestSuite):
	def setUp(self):
		super().setUp()
		for name in ("Contract", "Probation", "Full-time"):
			if not frappe.db.exists("Employment Type", name):
				frappe.get_doc({"doctype": "Employment Type", "employee_type_name": name}).insert()
		self.employee = get_employee()
		frappe.db.set_value(
			"Employee", self.employee.name, {"date_of_joining": "2020-01-01", "status": "Active", "reports_to": None}
		)
		for c in frappe.get_all("Employee Contract", {"employee": self.employee.name}, pluck="name"):
			frappe.db.delete("Employee Contract", {"name": c})
		ensure_role("Test Contract Role X")
		ensure_role("Test Contract Role P")
		if not frappe.db.exists("Role Profile", "Test Contract Profile P"):
			frappe.get_doc(
				{
					"doctype": "Role Profile",
					"role_profile": "Test Contract Profile P",
					"roles": [{"role": "Test Contract Role P"}],
				}
			).insert()

	def set_settings(self, enabled=1, points=(30, 14, 7, 0), roles=(), profiles=(), manager=0, template=None):
		frappe.clear_document_cache("Upande HR Settings")
		s = frappe.get_doc("Upande HR Settings")
		s.enable_contract_expiry_reminders = 0
		s.notify_reporting_manager = 0
		s.set("contract_reminder_days", [])
		s.set("contract_reminder_recipients", [])
		s.modified = frappe.db.get_single_value("Upande HR Settings", "modified")
		s.save()
		s.enable_contract_expiry_reminders = enabled
		s.notify_reporting_manager = manager
		s.contract_reminder_email_template = template
		for p in points:
			s.append("contract_reminder_days", {"days_before": p})
		for r in roles:
			s.append("contract_reminder_recipients", {"recipient_type": "Role", "recipient": r})
		for p in profiles:
			s.append("contract_reminder_recipients", {"recipient_type": "Role Profile", "recipient": p})
		s.save()

	def test_due_point(self):
		pts = [30, 14, 7, 0]
		self.assertEqual(due_point(20, pts, None), 30)
		self.assertEqual(due_point(14, pts, 30), 14)
		self.assertIsNone(due_point(14, pts, 14))
		self.assertEqual(due_point(5, pts, 30), 7)
		self.assertIsNone(due_point(-1, pts, None))
		self.assertIsNone(due_point(40, pts, None))

	def test_mark_expired(self):
		e = self.employee.name
		old = make_contract(e, add_days(today(), -60), add_days(today(), -1))
		self.assertEqual(old.status, "Active")
		mark_expired_contracts()
		self.assertEqual(frappe.db.get_value("Employee Contract", old.name, "status"), "Expired")
		cur = make_contract(e, today(), add_days(today(), 0))
		mark_expired_contracts()
		self.assertEqual(frappe.db.get_value("Employee Contract", cur.name, "status"), "Active")

	def test_recipients_role_and_profile(self):
		c = make_contract(self.employee.name, add_days(today(), -30), add_days(today(), 10))
		other = frappe.get_all("Company", filters={"name": ["!=", c.company]}, pluck="name", limit=1)
		if not other:
			other = [frappe.get_doc({"doctype": "Company", "company_name": "Test Other Co", "default_currency": "INR", "country": "India"}).insert().name]
		a = make_user("rem_a@example.com", ["Test Contract Role X"])
		b = make_user("rem_b@example.com", role_profile="Test Contract Profile P")
		make_user("rem_c@example.com", ["Test Contract Role X"], enabled=0)
		d = make_user("rem_d@example.com", ["Test Contract Role X"])
		e = make_user("rem_e@example.com", ["Test Contract Role X"])
		frappe.get_doc({"doctype": "User Permission", "user": d, "allow": "Company", "for_value": other[0]}).insert()
		frappe.get_doc({"doctype": "User Permission", "user": e, "allow": "Company", "for_value": c.company}).insert()
		self.set_settings(roles=["Test Contract Role X"], profiles=["Test Contract Profile P"])
		recipients = get_recipients(c)
		self.assertEqual(sorted(recipients), sorted([a, b, e]))
		self.assertEqual(len(recipients), len(set(recipients)))

	def test_reporting_manager_added(self):
		mgr_emp = frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": "Rem Manager",
				"gender": "Female",
				"date_of_birth": "1985-01-01",
				"date_of_joining": "2019-01-01",
				"company": self.employee.company,
			}
		)
		mgr_user = make_user("rem_mgr@example.com")
		mgr_emp.user_id = mgr_user
		mgr_emp.insert()
		frappe.db.set_value("Employee", self.employee.name, "reports_to", mgr_emp.name)
		c = make_contract(self.employee.name, add_days(today(), -30), add_days(today(), 10))
		other = frappe.get_all("Company", filters={"name": ["!=", c.company]}, pluck="name", limit=1)
		if other:
			frappe.get_doc({"doctype": "User Permission", "user": mgr_user, "allow": "Company", "for_value": other[0]}).insert()
		self.set_settings(roles=["Test Contract Role X"], manager=1)
		self.assertIn(mgr_user, get_recipients(c))

	def email_count(self, c):
		return frappe.db.count("Email Queue", {"reference_doctype": "Employee Contract", "reference_name": c.name})

	def test_send_once_per_point(self):
		a = make_user("rem_a@example.com", ["Test Contract Role X"])
		self.set_settings(roles=["Test Contract Role X"])
		c = make_contract(self.employee.name, add_days(today(), -30), add_days(today(), 10))
		send_contract_reminders()
		self.assertEqual(self.email_count(c), 1)
		self.assertEqual(
			frappe.db.count(
				"Notification Log",
				{"document_type": "Employee Contract", "document_name": c.name, "for_user": a, "type": "Alert"},
			),
			1,
		)
		self.assertEqual(frappe.db.get_value("Employee Contract", c.name, "last_reminder_days"), 14)
		send_contract_reminders()
		self.assertEqual(self.email_count(c), 1)

	def test_zero_point_sent_once(self):
		make_user("rem_a@example.com", ["Test Contract Role X"])
		self.set_settings(roles=["Test Contract Role X"])
		c = make_contract(self.employee.name, add_days(today(), -30), today())
		send_contract_reminders()
		send_contract_reminders()
		self.assertEqual(self.email_count(c), 1)

	def test_recipients_legacy_role_profile_name(self):
		c = make_contract(self.employee.name, add_days(today(), -30), add_days(today(), 10))
		u = make_user("rem_f@example.com")
		frappe.db.set_value("User", u, "role_profile_name", "Test Contract Profile P")
		self.set_settings(profiles=["Test Contract Profile P"])
		self.assertIn(u, get_recipients(c))

	def test_no_recipients_still_marks(self):
		self.set_settings(roles=["Test Contract Role P"])
		c = make_contract(self.employee.name, add_days(today(), -30), add_days(today(), 10))
		send_contract_reminders()
		self.assertEqual(self.email_count(c), 0)
		self.assertEqual(frappe.db.get_value("Employee Contract", c.name, "last_reminder_days"), 14)

	def test_disabled_sends_nothing(self):
		make_user("rem_a@example.com", ["Test Contract Role X"])
		self.set_settings(enabled=0, roles=["Test Contract Role X"])
		c = make_contract(self.employee.name, add_days(today(), -30), add_days(today(), 10))
		send_contract_reminders()
		self.assertEqual(self.email_count(c), 0)
		self.assertFalse(frappe.db.get_value("Employee Contract", c.name, "last_reminder_days"))

	def test_company_permission_for_other_doctype_ignored(self):
		c = make_contract(self.employee.name, add_days(today(), -30), add_days(today(), 10))
		other = frappe.get_all("Company", filters={"name": ["!=", c.company]}, pluck="name", limit=1)[0]
		u = make_user("rem_g@example.com", ["Test Contract Role X"])
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": u,
				"allow": "Company",
				"for_value": other,
				"apply_to_all_doctypes": 0,
				"applicable_for": "Leave Application",
			}
		).insert()
		self.set_settings(roles=["Test Contract Role X"])
		self.assertIn(u, get_recipients(c))

	def test_one_failing_contract_does_not_abort(self):
		make_user("rem_a@example.com", ["Test Contract Role X"])
		self.set_settings(roles=["Test Contract Role X"])
		c1 = make_contract(self.employee.name, add_days(today(), -30), add_days(today(), 10))
		emp2 = frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": "Rem Second",
				"gender": "Female",
				"date_of_birth": "1985-01-01",
				"date_of_joining": "2019-01-01",
				"company": self.employee.company,
			}
		).insert()
		frappe.db.set_value("Employee", emp2.name, {"date_of_joining": "2020-01-01", "status": "Active"})
		c2 = make_contract(emp2.name, add_days(today(), -30), add_days(today(), 10))
		real = frappe.sendmail

		def flaky(*a, **kw):
			if kw.get("reference_name") == c1.name:
				raise Exception("boom")
			return real(*a, **kw)

		with patch("upande_hr.contracts.reminders.frappe.sendmail", side_effect=flaky):
			send_contract_reminders()
		self.assertEqual(self.email_count(c1), 0)
		self.assertFalse(frappe.db.get_value("Employee Contract", c1.name, "last_reminder_days"))
		self.assertEqual(self.email_count(c2), 1)
		self.assertEqual(frappe.db.get_value("Employee Contract", c2.name, "last_reminder_days"), 14)

	def test_subject_singular_for_one_day(self):
		make_user("rem_a@example.com", ["Test Contract Role X"])
		self.set_settings(roles=["Test Contract Role X"], points=(1,))
		c = make_contract(self.employee.name, add_days(today(), -30), add_days(today(), 1))
		send_contract_reminders()
		subject = frappe.db.get_value(
			"Notification Log", {"document_type": "Employee Contract", "document_name": c.name}, "subject"
		)
		self.assertTrue(subject.startswith("Contract ending in 1 day:"), subject)

	def test_email_body_escaped(self):
		make_user("rem_a@example.com", ["Test Contract Role X"])
		self.set_settings(roles=["Test Contract Role X"])
		c = make_contract(self.employee.name, add_days(today(), -30), add_days(today(), 10))
		frappe.db.set_value("Employee Contract", c.name, "employee_name", "<b>x</b>")
		send_contract_reminders()
		msg = frappe.db.get_value(
			"Email Queue", {"reference_doctype": "Employee Contract", "reference_name": c.name}, "message"
		)
		self.assertIn("&lt;b&gt;", msg)
		self.assertIn("&lt;b&gt;x&lt;/b&gt; (", msg)

	def make_template(self, subject, body, use_html=0):
		name = "UHR Reminder Test Template"
		if frappe.db.exists("Email Template", name):
			frappe.delete_doc("Email Template", name, force=True)
		doc = {"doctype": "Email Template", "name": name, "subject": subject, "use_html": use_html}
		doc["response_html" if use_html else "response"] = body
		return frappe.get_doc(doc).insert(ignore_permissions=True).name

	def queued_message(self, c):
		return frappe.db.get_value(
			"Email Queue", {"reference_doctype": "Employee Contract", "reference_name": c.name}, "message"
		)

	def log_subject(self, c):
		return frappe.db.get_value(
			"Notification Log", {"document_type": "Employee Contract", "document_name": c.name}, "subject"
		)

	def test_custom_email_template_used(self):
		make_user("rem_a@example.com", ["Test Contract Role X"])
		tpl = self.make_template(
			"Heads up: {{ employee_name }} in {{ days_left }}",
			"<p>Custom body for {{ employee_name }}, ends {{ end_date }}, #{{ contract_number }} {{ link }}</p>",
		)
		self.set_settings(roles=["Test Contract Role X"], template=tpl)
		c = make_contract(self.employee.name, add_days(today(), -30), add_days(today(), 10))
		send_contract_reminders()
		self.assertEqual(self.log_subject(c), f"Heads up: {c.employee_name} in 10")
		msg = self.queued_message(c)
		self.assertIn("Custom body for", msg)
		self.assertIn(formatdate(c.end_date), msg)
		self.assertIn(c.name, msg)

	def test_custom_html_email_template_used(self):
		make_user("rem_a@example.com", ["Test Contract Role X"])
		tpl = self.make_template("S {{ days_left }}", "<div>Raw html {{ employee }}</div>", use_html=1)
		self.set_settings(roles=["Test Contract Role X"], template=tpl)
		c = make_contract(self.employee.name, add_days(today(), -30), add_days(today(), 10))
		send_contract_reminders()
		self.assertIn(f"Raw html {self.employee.name}", self.queued_message(c))

	def test_custom_template_body_escaped(self):
		make_user("rem_a@example.com", ["Test Contract Role X"])
		tpl = self.make_template("S", "<p>Name: {{ employee_name }}</p>")
		self.set_settings(roles=["Test Contract Role X"], template=tpl)
		c = make_contract(self.employee.name, add_days(today(), -30), add_days(today(), 10))
		frappe.db.set_value("Employee Contract", c.name, "employee_name", "<b>x</b>")
		send_contract_reminders()
		self.assertIn("Name: &lt;b&gt;x&lt;/b&gt;", self.queued_message(c))

	def test_default_template_seeded_and_linked(self):
		from upande_hr.install import DEFAULT_EMAIL_TEMPLATE, set_default_email_template

		self.set_settings(enabled=0)
		frappe.delete_doc_if_exists("Email Template", DEFAULT_EMAIL_TEMPLATE, force=True)
		set_default_email_template()
		self.assertTrue(frappe.db.exists("Email Template", DEFAULT_EMAIL_TEMPLATE))
		self.assertEqual(
			frappe.db.get_single_value("Upande HR Settings", "contract_reminder_email_template"),
			DEFAULT_EMAIL_TEMPLATE,
		)

		# re-running keeps the client's edits and their chosen template
		frappe.db.set_value("Email Template", DEFAULT_EMAIL_TEMPLATE, "subject", "Edited")
		other = self.make_template("S", "B")
		frappe.db.set_single_value("Upande HR Settings", "contract_reminder_email_template", other)
		set_default_email_template()
		self.assertEqual(frappe.db.get_value("Email Template", DEFAULT_EMAIL_TEMPLATE, "subject"), "Edited")
		self.assertEqual(
			frappe.db.get_single_value("Upande HR Settings", "contract_reminder_email_template"), other
		)

	def test_seeded_template_matches_builtin_email(self):
		from upande_hr.install import DEFAULT_EMAIL_TEMPLATE, set_default_email_template

		frappe.delete_doc_if_exists("Email Template", DEFAULT_EMAIL_TEMPLATE, force=True)
		set_default_email_template()
		make_user("rem_a@example.com", ["Test Contract Role X"])
		self.set_settings(roles=["Test Contract Role X"], template=DEFAULT_EMAIL_TEMPLATE, points=(1,))
		c = make_contract(self.employee.name, add_days(today(), -30), add_days(today(), 1))
		send_contract_reminders()
		self.assertTrue(self.log_subject(c).startswith("Contract ending in 1 day:"), self.log_subject(c))
		self.assertIn("Open contract", self.queued_message(c))

	def test_uninstall_removes_seeded_template_only(self):
		from upande_hr.install import DEFAULT_EMAIL_TEMPLATE, set_default_email_template

		frappe.delete_doc_if_exists("Email Template", DEFAULT_EMAIL_TEMPLATE, force=True)
		set_default_email_template()
		client_tpl = self.make_template("S", "B")
		self._run_uninstall(installed=True)
		self.assertTrue(frappe.db.exists("Email Template", DEFAULT_EMAIL_TEMPLATE))
		self._run_uninstall(installed=False)
		self.assertFalse(frappe.db.exists("Email Template", DEFAULT_EMAIL_TEMPLATE))
		self.assertTrue(frappe.db.exists("Email Template", client_tpl))

	def _run_uninstall(self, installed):
		from upande_hr import install

		ddl = []
		original = frappe.db.sql_ddl
		original_commit = frappe.db.commit
		frappe.db.sql_ddl = lambda sql, *a, **kw: ddl.append(sql)
		self.commit_mock = MagicMock()
		frappe.db.commit = self.commit_mock
		self.addCleanup(frappe.db.rollback)
		try:
			with patch.object(install, "_app_installed", return_value=installed):
				install.before_uninstall()
				install.after_uninstall()
		finally:
			frappe.db.sql_ddl = original
			frappe.db.commit = original_commit
		return ddl

	def _make_log(self):
		c = make_contract(self.employee.name, add_days(today(), -30), add_days(today(), 10))
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"subject": "x",
				"for_user": "Administrator",
				"type": "Alert",
				"document_type": "Employee Contract",
				"document_name": c.name,
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Property Setter",
				"doc_type": "Employee Contract",
				"property": "max_attachments",
				"property_type": "Int",
				"value": "3",
				"doctype_or_field": "DocType",
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Comment",
				"comment_type": "Info",
				"reference_doctype": "Employee Contract",
				"reference_name": c.name,
				"content": "x",
			}
		).insert(ignore_permissions=True)
		eq = frappe.get_doc(
			{
				"doctype": "Email Queue",
				"reference_doctype": "Employee Contract",
				"reference_name": c.name,
				"sender": "a@example.com",
				"message": "x",
				"status": "Sent",
				"recipients": [{"recipient": "b@example.com"}],
			}
		).insert(ignore_permissions=True)
		self.eq_name = eq.name
		f = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "contract_uninstall_test.txt",
				"content": "hello",
				"attached_to_doctype": "Employee Contract",
				"attached_to_name": c.name,
				"is_private": 1,
			}
		).insert(ignore_permissions=True)
		self.file_name = f.name
		frappe.get_doc(
			{"doctype": "Error Log", "method": "Contract reminder failed: X", "error": "x"}
		).insert(ignore_permissions=True)
		frappe.db.sql("insert into `tabSeries` (name, current) values ('HR-CON-2099-', 5) on duplicate key update current=5")

	def _leftovers(self):
		return {
			"property_setter": frappe.db.exists("Property Setter", {"doc_type": "Employee Contract"}),
			"comment": frappe.db.exists("Comment", {"reference_doctype": "Employee Contract"}),
			"email_queue": frappe.db.exists("Email Queue", {"reference_doctype": "Employee Contract"}),
			"email_recipient": frappe.db.exists("Email Queue Recipient", {"parent": self.eq_name}),
			"file": frappe.db.exists("File", {"attached_to_doctype": "Employee Contract"}),
			"error_log": frappe.db.exists("Error Log", {"method": ["like", "Contract reminder failed%"]}),
			"series": frappe.db.exists("Series", {"name": ["like", "HR-CON-%"]}),
		}

	def _attach(self, doctype, docname, file_name, content):
		return frappe.get_doc(
			{
				"doctype": "File",
				"file_name": file_name,
				"content": content,
				"attached_to_doctype": doctype,
				"attached_to_name": docname,
				"is_private": 1,
			}
		).insert(ignore_permissions=True)

	def test_real_uninstall_removes_attachment_from_disk(self):
		c = make_contract(self.employee.name, add_days(today(), -30), add_days(today(), 10))
		f = self._attach("Employee Contract", c.name, "contract_disk_test.txt", "unique contract scan " + frappe.generate_hash())
		path = f.get_full_path()
		self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
		self.assertTrue(os.path.exists(path))
		# on a real uninstall the Employee Contract DocType is already gone; emulate that with a
		# doctype that does not exist (frappe.delete_doc("File") fails on it before touching disk)
		from upande_hr import install

		frappe.db.set_value("File", f.name, "attached_to_doctype", "Removed Contract Doctype")
		with patch.object(install, "CONTRACT", "Removed Contract Doctype"):
			self._run_uninstall(installed=False)
		self.assertFalse(frappe.db.exists("File", f.name))
		self.assertFalse(os.path.exists(path))

	def test_real_uninstall_keeps_file_shared_with_other_record(self):
		c = make_contract(self.employee.name, add_days(today(), -30), add_days(today(), 10))
		content = "shared scan " + frappe.generate_hash()
		mine = self._attach("Employee Contract", c.name, "shared_scan.txt", content)
		other = self._attach("Employee", self.employee.name, "shared_scan.txt", content)
		path = other.get_full_path()
		self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
		self._run_uninstall(installed=False)
		self.assertFalse(frappe.db.exists("File", mine.name))
		self.assertTrue(frappe.db.exists("File", other.name))
		self.assertTrue(os.path.exists(path))

	def test_dry_run_keeps_attachment_on_disk(self):
		c = make_contract(self.employee.name, add_days(today(), -30), add_days(today(), 10))
		f = self._attach("Employee Contract", c.name, "dry_run_scan.txt", "dry run scan " + frappe.generate_hash())
		path = f.get_full_path()
		self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
		self._run_uninstall(installed=True)
		self.assertTrue(os.path.exists(path))

	def test_dry_run_uninstall_changes_nothing(self):
		self._make_log()
		before = frappe.db.count("Custom Field", {"module": "Upande Hr"})
		ddl = self._run_uninstall(installed=True)
		self.assertEqual(ddl, [])
		self.commit_mock.assert_not_called()
		self.assertEqual(frappe.db.count("Custom Field", {"module": "Upande Hr"}), before)
		self.assertTrue(frappe.db.exists("Notification Log", {"document_type": "Employee Contract"}))
		self.assertTrue(all(self._leftovers().values()), self._leftovers())

	def test_real_uninstall_cleans_up(self):
		self._make_log()
		self.assertTrue(all(self._leftovers().values()), self._leftovers())
		ddl = self._run_uninstall(installed=False)
		self.commit_mock.assert_called()
		dropped = {s.split("DROP COLUMN")[1].strip(" `") for s in ddl}
		self.assertEqual(dropped, {
				"reason_for_exit", "national_id", "tax_id", "nssf_no", "sha_no",
				"custom_comp_off_request", "custom_comp_off_override",
			},
		)
		self.assertFalse(frappe.db.exists("Notification Log", {"document_type": "Employee Contract"}))
		self.assertEqual(frappe.db.count("Scheduled Job Type", {"method": ["like", "upande_hr.%"]}), 0)
		self.assertFalse(any(self._leftovers().values()), self._leftovers())
