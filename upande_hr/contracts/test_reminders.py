import frappe
from frappe.utils import add_days, today
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

	def set_settings(self, enabled=1, points=(30, 14, 7, 0), roles=(), profiles=(), manager=0):
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
