import frappe
from hrms.tests.utils import HRMSTestSuite

from upande_hr.install import set_default_reminder_days


class TestUpandeHRSettings(HRMSTestSuite):
	def setUp(self):
		super().setUp()
		frappe.clear_document_cache("Upande HR Settings")
		self.settings = frappe.get_doc("Upande HR Settings")
		self.settings.enable_contract_expiry_reminders = 0
		self.settings.notify_reporting_manager = 0
		self.settings.set("contract_reminder_days", [])
		self.settings.set("contract_reminder_recipients", [])

	def test_rejects_negative_days(self):
		self.settings.append("contract_reminder_days", {"days_before": -1})
		self.assertRaises(frappe.ValidationError, self.save)

	def test_rejects_duplicate_days(self):
		self.settings.append("contract_reminder_days", {"days_before": 7})
		self.settings.append("contract_reminder_days", {"days_before": 7})
		self.assertRaises(frappe.ValidationError, self.save)

	def test_enabled_requires_days_and_recipient(self):
		self.settings.enable_contract_expiry_reminders = 1
		self.assertRaises(frappe.ValidationError, self.save)

		self.settings.append("contract_reminder_days", {"days_before": 7})
		self.assertRaises(frappe.ValidationError, self.save)

		self.settings.notify_reporting_manager = 1
		self.save()

	def test_default_days(self):
		frappe.db.delete("Contract Reminder Day")
		set_default_reminder_days()
		self.assertEqual(self.days(), [0, 7, 14, 30])
		set_default_reminder_days()
		self.assertEqual(self.days(), [0, 7, 14, 30])

	def save(self):
		# a failed save leaves a bumped `modified` on the in-memory doc; resync it
		self.settings.modified = frappe.db.get_single_value("Upande HR Settings", "modified")
		self.settings.save()

	def days(self):
		frappe.clear_document_cache("Upande HR Settings")
		settings = frappe.get_doc("Upande HR Settings")
		return sorted(d.days_before for d in settings.contract_reminder_days)
