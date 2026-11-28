# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Probation tab on Employee: the end date is derived on save and can't be set directly.

Run: bench --site kentrout.local run-tests --module upande_hr.employee.test_probation
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from upande_hr.employee.probation import END_DATE, PERIOD_DAYS, START_DATE, calculate_end_date

JOINED = "2026-02-01"


class TestProbation(IntegrationTestCase):
	def setUp(self):
		frappe.db.savepoint("probation_test")
		frappe.set_user("Administrator")
		self.company = frappe.db.get_value("Company", {}, "name", order_by="creation")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="probation_test")

	def make_employee(self, **values):
		doc = frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": f"_Test Probation {frappe.generate_hash(length=5)}",
				"gender": frappe.db.get_value("Gender", {}, "name"),
				"date_of_birth": "1990-01-01",
				"date_of_joining": JOINED,
				"company": self.company,
				"status": "Active",
				**values,
			}
		)
		return doc.insert()

	def end_date(self, employee):
		value = frappe.db.get_value("Employee", employee, END_DATE)
		return getdate(value) if value else None

	def test_rule_is_inclusive(self):
		self.assertEqual(calculate_end_date("2026-01-01", 90), getdate("2026-03-31"))
		self.assertEqual(calculate_end_date("2026-01-01", 1), getdate("2026-01-01"))
		self.assertEqual(calculate_end_date("2028-02-01", 29), getdate("2028-02-29"))
		self.assertIsNone(calculate_end_date(None, 90))
		self.assertIsNone(calculate_end_date("2026-01-01", 0))

	def test_end_date_from_explicit_start(self):
		emp = self.make_employee(**{START_DATE: "2026-01-01", PERIOD_DAYS: 90})
		self.assertEqual(self.end_date(emp.name), getdate("2026-03-31"))

	def test_falls_back_to_date_of_joining(self):
		emp = self.make_employee(**{PERIOD_DAYS: 90})
		# 1 Feb + 90 days inclusive = 1 May
		self.assertEqual(self.end_date(emp.name), getdate("2026-05-01"))

	def test_blank_without_period(self):
		emp = self.make_employee(**{START_DATE: "2026-01-01"})
		self.assertIsNone(self.end_date(emp.name))

		# Clearing the period on an employee who had one blanks the end date again.
		emp.set(PERIOD_DAYS, 30)
		emp.save()
		self.assertEqual(self.end_date(emp.name), getdate("2026-01-30"))
		emp.set(PERIOD_DAYS, None)
		emp.save()
		self.assertIsNone(self.end_date(emp.name))

	def test_blank_without_any_start_and_no_error(self):
		# date_of_joining is mandatory on the form, so exercise the hook directly.
		from upande_hr.employee.probation import set_probation_end_date

		doc = frappe.new_doc("Employee")
		doc.set(PERIOD_DAYS, 90)
		doc.set(END_DATE, "2026-12-31")
		set_probation_end_date(doc)
		self.assertIsNone(doc.get(END_DATE))

	def test_recalculated_when_period_changes(self):
		emp = self.make_employee(**{START_DATE: "2026-01-01", PERIOD_DAYS: 90})
		emp.set(PERIOD_DAYS, 180)
		emp.save()
		self.assertEqual(self.end_date(emp.name), getdate("2026-06-29"))

	def test_recalculated_when_date_of_joining_changes(self):
		emp = self.make_employee(**{PERIOD_DAYS: 30})
		self.assertEqual(self.end_date(emp.name), getdate("2026-03-02"))
		emp.date_of_joining = "2026-03-01"
		emp.save()
		self.assertEqual(self.end_date(emp.name), getdate("2026-03-30"))

	def test_start_date_wins_over_date_of_joining(self):
		emp = self.make_employee(**{START_DATE: "2026-04-01", PERIOD_DAYS: 30})
		emp.date_of_joining = "2026-03-01"
		emp.save()
		self.assertEqual(self.end_date(emp.name), getdate("2026-04-30"))

	def test_end_date_cannot_be_set_through_api(self):
		emp = self.make_employee(**{START_DATE: "2026-01-01", PERIOD_DAYS: 90})

		frappe.client.set_value("Employee", emp.name, END_DATE, "2030-01-01")
		self.assertEqual(self.end_date(emp.name), getdate("2026-03-31"))

		doc = frappe.get_doc("Employee", emp.name).as_dict()
		doc[END_DATE] = "2030-01-01"
		frappe.client.save(doc)
		self.assertEqual(self.end_date(emp.name), getdate("2026-03-31"))

		# On insert too, and with no period it stays blank.
		other = self.make_employee(**{END_DATE: "2030-01-01"})
		self.assertIsNone(self.end_date(other.name))

	def test_negative_period_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self.make_employee(**{PERIOD_DAYS: -5})

		emp = self.make_employee(**{PERIOD_DAYS: 30})
		emp.set(PERIOD_DAYS, -1)
		with self.assertRaises(frappe.ValidationError):
			emp.save()

	def test_zero_period_means_not_set(self):
		# Int is stored NOT NULL DEFAULT 0: every employee without a period carries 0, so it
		# can't be an error or no existing employee could be saved.
		emp = self.make_employee(**{START_DATE: "2026-01-01", PERIOD_DAYS: 0})
		self.assertIsNone(self.end_date(emp.name))
