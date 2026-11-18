# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""MOD Roster.

Uses Altura's real rotation dates (Group 1 on duty Nov 7, 21, Dec 5, 19, Jan 2; Group 2
on Oct 31, Nov 14, 28; Dec 12 and Dec 26 public holidays). "Today" is frozen through
mod_roster.today, which every roster date decision goes through. Builds its own base
holiday lists and employees (Employee.holiday_list only, no assignments, as on Altura)
and rolls everything back after each test.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate
from hrms.utils.holiday_list import get_holiday_list_for_employee

from upande_hr.attendance import absent_deduction as ad
from upande_hr.attendance import mod_roster as mr
from upande_hr.attendance.test_absent_deduction import (
	AL,
	GRADE,
	allocate,
	configure,
	make_hr_manager,
	make_masters,
	mark_absent,
	raw_insert,
)
from upande_hr.upande_hr.report.mod_roster import mod_roster as report

BASE_2026 = "_Test MOD Base 2026"
BASE_2027 = "_Test MOD Base 2027"
PUBLIC_HOLIDAYS = {
	"2026-12-12": "Jamhuri Day",
	"2026-12-25": "Christmas Day",
	"2026-12-26": "Boxing Day",
	"2027-01-01": "New Year's Day",
}
TODAY = "2026-11-02"  # a Monday, before every Saturday below

G1_DUTY = ["2026-11-07", "2026-11-21", "2026-12-05", "2026-12-19", "2027-01-02"]
G1_OFF = ["2026-11-14", "2026-11-28"]
G2_DUTY = ["2026-11-14", "2026-11-28"]
G2_OFF = ["2026-11-07", "2026-11-21", "2026-12-05", "2026-12-19", "2027-01-02"]
SATURDAY_PHS = ["2026-12-12", "2026-12-26"]


class TestMODRoster(IntegrationTestCase):
	def setUp(self):
		frappe.db.savepoint("mod_test")
		frappe.set_user("Administrator")
		self.company = frappe.db.get_value("Company", {}, "name", order_by="creation")
		make_base_lists()
		frappe.db.set_single_value(
			"HR Settings",
			{
				mr.ENABLED: 1,
				mr.DUTY_WEEKDAY: "Saturday",
				mr.WEEKS_AHEAD: 8,
				mr.MIN_ON_DUTY: 1,
			},
		)
		self.hr_manager = make_hr_manager()
		self.set_today(TODAY)

		self.sent = []
		mailer = patch("frappe.sendmail", side_effect=lambda **kw: self.sent.append(kw))
		mailer.start()
		self.addCleanup(mailer.stop)

		self.philip = self.make_mod("Philip")
		self.olger = self.make_mod("Olger")
		self.yvonne = self.make_mod("Yvonne")

	def tearDown(self):
		frappe.db.rollback(save_point="mod_test")

	def set_today(self, day):
		if getattr(self, "_today", None):
			self._today.stop()
		self._today = patch.object(mr, "today", lambda: str(day))
		self._today.start()
		self.addCleanup(lambda: self._today.stop() if self._today else None)

	def make_mod(self, first_name, grade=None):
		return (
			frappe.get_doc(
				{
					"doctype": "Employee",
					"first_name": f"_Test MOD {first_name}",
					"gender": frappe.db.get_value("Gender", {}, "name"),
					"date_of_birth": "1985-01-01",
					"date_of_joining": "2024-01-01",
					"company": self.company,
					"status": "Active",
					"holiday_list": BASE_2026,
					"grade": grade,
					"personal_email": f"mod.{frappe.generate_hash(length=6)}@example.com",
					"prefered_contact_email": "Personal Email",
				}
			)
			.insert()
			.name
		)

	def altura_groups(self, olger_from=TODAY):
		g1 = make_group("_Test MOD G1", "2026-11-07", [(self.philip, TODAY), (self.olger, olger_from)])
		g2 = make_group("_Test MOD G2", "2026-10-31", [(self.yvonne, TODAY)])
		return g1, g2

	def codes(self, employee, dates):
		roster = mr.Roster()
		return [roster.day_status(employee, d).code for d in dates]

	# --- rotation ----------------------------------------------------------------

	def test_two_week_rotation_matches_altura_for_both_groups(self):
		self.altura_groups()
		for employee in (self.philip, self.olger):
			self.assertEqual(self.codes(employee, G1_DUTY), [mr.DUTY] * 5)
			self.assertEqual(self.codes(employee, G1_OFF), [mr.OFF] * 2)
		self.assertEqual(self.codes(self.yvonne, G2_DUTY), [mr.DUTY] * 2)
		self.assertEqual(self.codes(self.yvonne, G2_OFF), [mr.OFF] * 5)

		# Written into the holiday list in force for each of them.
		for employee, off, duty in ((self.philip, G1_OFF, G1_DUTY), (self.yvonne, G2_OFF, G2_DUTY)):
			rows = holidays(employee, 2026)
			for day in off:
				if day.startswith("2026") and day >= TODAY:
					self.assertEqual(rows.get(getdate(day)), mr.MOD_OFF, (employee, day))
			for day in duty:
				if day.startswith("2026"):
					self.assertNotIn(getdate(day), rows, (employee, day))
			self.assertEqual(rows[getdate("2026-11-08")], "Sunday")  # base weekly off kept
			self.assertEqual(in_force(employee, "2026-11-14"), mr.list_name(employee, 2026))

		# Before the roster started, the base list stays in force (backfilled assignment),
		# not the MOD list HRMS would otherwise fall back to.
		self.assertEqual(in_force(self.philip, "2026-10-31"), BASE_2026)

	def test_three_group_three_week_cycle(self):
		extra = [self.make_mod(f"Extra {i}") for i in range(3)]
		for week, employee in enumerate(extra, 1):
			make_group(f"_Test MOD C{week}", "2026-11-07", [(employee, TODAY)], cycle=3, duty_week=week)
		# Dec 12 (public holiday, nobody on duty) is skipped; Dec 19 is week 1 again.
		saturdays = [add_days(getdate("2026-11-07"), 7 * i) for i in (0, 1, 2, 3, 4, 6)]
		roster = mr.Roster()
		on_duty = [[e for e in extra if roster.day_status(e, d).code == mr.DUTY] for d in saturdays]
		self.assertEqual(on_duty, [[extra[0]], [extra[1]], [extra[2]], [extra[0]], [extra[1]], [extra[0]]])
		self.assertEqual([roster.day_status(e, "2026-12-12").code for e in extra], [mr.PUBLIC_HOLIDAY] * 3)
		self.assertEqual(mr.cover_warnings(), [])

	def test_public_holiday_overrides_duty_and_off(self):
		self.altura_groups()
		# Dec 12: Group 1 rostered OFF, Group 2 on duty; Dec 26 the other way round.
		for employee in (self.philip, self.yvonne):
			self.assertEqual(self.codes(employee, SATURDAY_PHS), [mr.PUBLIC_HOLIDAY] * 2)
			rows = holidays(employee, 2026)
			self.assertEqual(rows[getdate("2026-12-12")], "Jamhuri Day")
			self.assertEqual(rows[getdate("2026-12-26")], "Boxing Day")

	def test_group_validation(self):
		self.altura_groups()
		with self.assertRaisesRegex(frappe.ValidationError, "must be a Saturday"):
			make_group("_Test MOD Friday", "2026-11-06", [])
		with self.assertRaisesRegex(frappe.ValidationError, "already in the active group"):
			make_group("_Test MOD Dup", "2026-11-07", [(self.philip, "2026-12-01")])
		with self.assertRaisesRegex(frappe.ValidationError, "Duty Week must be between 1 and 2"):
			make_group("_Test MOD Week", "2026-11-07", [], duty_week=3)
		# Consecutive, non-overlapping membership in another group is fine.
		g1 = frappe.get_doc(mr.GROUP, "_Test MOD G1")
		g1.members[0].to_date = "2026-11-30"
		g1.save()
		make_group("_Test MOD Next", "2026-11-07", [(self.philip, "2026-12-01")], duty_week=2)
		self.assertEqual(self.codes(self.philip, ["2026-12-05", "2026-12-19"]), [mr.OFF, mr.OFF])
		self.assertEqual(self.codes(self.philip, ["2026-11-28", "2026-12-26"]), [mr.OFF, mr.PUBLIC_HOLIDAY])

		# The duty weekday cannot move away from the groups' anchors.
		settings = frappe.get_doc("HR Settings")
		settings.set(mr.DUTY_WEEKDAY, "Sunday")
		with self.assertRaisesRegex(frappe.ValidationError, "MOD Duty Weekday cannot be Sunday"):
			mr.validate_hr_settings(settings)

	# --- swaps -------------------------------------------------------------------

	def test_swap_flips_one_date_for_two_people_and_cancel_reverts(self):
		self.altura_groups()
		before = {e: holidays(e, 2026) for e in (self.philip, self.yvonne, self.olger)}

		swap = make_swap("2026-11-21", off=self.philip, cover=self.yvonne)
		after = {e: holidays(e, 2026) for e in before}
		nov21 = getdate("2026-11-21")
		self.assertEqual(after[self.philip][nov21], f"{mr.MOD_OFF} (swap {swap.name})")
		self.assertNotIn(nov21, after[self.yvonne])
		for employee in before:
			self.assertEqual(
				{d: v for d, v in after[employee].items() if d != nov21},
				{d: v for d, v in before[employee].items() if d != nov21},
			)
		self.assertEqual(after[self.olger], before[self.olger])
		self.assertEqual(swap.approved_by, "Administrator")

		swap.reload()
		swap.cancel()
		self.assertEqual({e: holidays(e, 2026) for e in before}, before)

	def test_swap_validation(self):
		self.altura_groups()
		cases = [
			("2026-11-20", self.philip, self.yvonne, "swaps are for the MOD duty weekday"),
			("2026-11-21", self.yvonne, self.philip, "is not rostered on duty"),  # Yvonne is off
			("2026-11-21", self.philip, self.olger, "is not rostered off"),  # both on duty
			("2026-12-12", self.yvonne, self.philip, "public holiday"),
		]
		for day, off, cover, message in cases:
			with self.subTest(day=day), self.assertRaisesRegex(frappe.ValidationError, message):
				make_swap(day, off=off, cover=cover)

	# --- membership dates --------------------------------------------------------

	def test_new_member_mid_cycle_starts_from_their_from_date(self):
		self.altura_groups(olger_from="2026-11-23")
		rows = holidays(self.olger, 2026)
		self.assertEqual(rows.get(getdate("2026-11-28")), mr.MOD_OFF)
		self.assertEqual(self.codes(self.olger, ["2026-11-14", "2026-11-21"]), [mr.DAY, mr.DAY])
		self.assertEqual(in_force(self.olger, "2026-11-21"), BASE_2026)
		self.assertEqual(in_force(self.olger, "2026-11-23"), mr.list_name(self.olger, 2026))

	def test_member_to_date_goes_back_to_base_list(self):
		g1, _g2 = self.altura_groups()
		g1.members[0].to_date = "2026-11-30"
		g1.save()
		self.assertEqual(in_force(self.philip, "2026-11-28"), mr.list_name(self.philip, 2026))
		self.assertEqual(in_force(self.philip, "2026-12-01"), BASE_2026)
		self.assertTrue(
			frappe.db.exists(
				mr.HLA,
				{
					"assigned_to": self.philip,
					"from_date": "2026-12-01",
					"holiday_list": BASE_2026,
					mr.ROSTER_FLAG: 1,
				},
			)
		)
		# Ending it again later moves the switch, cancelling the old one.
		g1.reload()
		g1.members[0].to_date = "2026-12-06"
		g1.save()
		self.assertEqual(in_force(self.philip, "2026-12-05"), mr.list_name(self.philip, 2026))
		self.assertEqual(in_force(self.philip, "2026-12-07"), BASE_2026)

	def test_deactivating_a_group_puts_members_back_from_today(self):
		g1, _g2 = self.altura_groups()
		self.set_today("2026-11-16")
		g1.reload()
		g1.is_active = 0
		g1.save()
		self.assertEqual(in_force(self.philip, "2026-11-14"), mr.list_name(self.philip, 2026))
		self.assertEqual(in_force(self.philip, "2026-11-16"), BASE_2026)

	def test_past_dates_are_never_changed_by_regeneration(self):
		g1, _g2 = self.altura_groups()
		hla_before = frappe.get_all(
			mr.HLA, filters={"assigned_to": self.philip, "docstatus": 1}, pluck="name"
		)

		self.set_today("2026-11-20")
		g1.reload()
		g1.anchor_date = "2026-11-14"  # Group 1 now on duty Nov 14 and 28, off Nov 21
		g1.save()

		rows = holidays(self.philip, 2026)
		self.assertEqual(rows.get(getdate("2026-11-14")), mr.MOD_OFF)  # past: untouched
		self.assertEqual(rows.get(getdate("2026-11-21")), mr.MOD_OFF)  # future: new rotation
		self.assertNotIn(getdate("2026-11-28"), rows)
		self.assertEqual(
			frappe.get_all(
				mr.HLA,
				filters={"assigned_to": self.philip, "docstatus": 1, "from_date": ["<", "2026-11-20"]},
				pluck="name",
			),
			hla_before,
		)

	def test_late_swap_over_deducted_absence_flags_hr_and_keeps_the_leave(self):
		self.altura_groups()
		log = frappe.new_doc("Absence Leave Deduction")
		log.update(
			{
				"name": f"{self.philip}-2026-11-21",
				"employee": self.philip,
				"absence_date": "2026-11-21",
				"status": "Deducted",
				"leave_application": "_Test MOD LA",
			}
		)
		log.db_insert()

		self.set_today("2026-11-25")
		make_swap("2026-11-21", off=self.philip, cover=self.yvonne)

		log.reload()
		self.assertEqual((log.status, log.leave_application), ("Deducted", "_Test MOD LA"))
		self.assertEqual(log.mod_roster_conflict, 1)
		self.assertIn("MOD Off", log.mod_roster_note)
		[mail] = [m for m in self.sent if "MOD Off day" in m["subject"]]
		self.assertIn(self.hr_manager, mail["recipients"])
		self.assertIn(log.name, mail["message"])

	# --- cover ---------------------------------------------------------------------

	def test_cover_warning_fires_and_is_emailed_daily(self):
		self.altura_groups()
		self.assertEqual(mr.cover_warnings(), [])

		frappe.db.set_single_value("HR Settings", mr.MIN_ON_DUTY, 2)
		raw_insert(
			"Leave Application",
			employee=self.philip,
			leave_type=AL,
			from_date="2026-11-21",
			to_date="2026-11-21",
			status="Approved",
			docstatus=1,
		)
		warned = {str(w.date): w.on_duty for w in mr.cover_warnings()}
		# Group 2 days have one MOD on duty; Nov 21 lost Philip to leave; PH Saturdays skipped.
		self.assertEqual(
			warned,
			{"2026-11-14": 1, "2026-11-21": 1, "2026-11-28": 1},
		)

		mr.run_daily()
		[mail] = [m for m in self.sent if "need attention" in m["subject"]]
		for day in ("2026-11-14", "2026-11-21", "2026-11-28"):
			self.assertIn(frappe.utils.formatdate(day), mail["message"])
		self.assertEqual(mail["message"].count("<li>"), 3)

		# And on save of a group.
		frappe.local.message_log = []
		make_group("_Test MOD G3", "2026-11-07", [(self.make_mod("Late"), "2026-12-07")])
		self.assertIn("Not enough MODs on duty", str(frappe.local.message_log))

	# --- end to end with the absent deduction ------------------------------------------

	def test_absent_deduction_skips_off_saturday_and_deducts_missed_duty(self):
		make_masters(self.company)
		configure(
			{
				ad.SETTINGS_FLAG: 1,
				"custom_absence_deduction_start_date": "2026-10-01",
				"custom_absence_deduction_leave_type": AL,
			},
			grades=[GRADE],
			exempt=[],
		)
		frappe.db.set_value("Employee", self.philip, "grade", GRADE)
		for i in range(3):
			self.make_mod(f"Bystander {i}", grade=GRADE)
		allocate(self.philip, AL, 5)
		self.altura_groups()

		mark_absent(self.philip, "2026-11-07")  # WD Saturday, missed
		mark_absent(self.philip, "2026-11-14")  # OFF Saturday

		result = ad._run(getdate("2026-11-02"), getdate("2026-11-15"), dry_run=0)
		rows = {str(r.absence_date): r for r in result["rows"] if r.employee == self.philip}
		self.assertEqual(
			(rows["2026-11-14"].action, rows["2026-11-14"].reason),
			(ad.ACTION_EXCUSED, "Holiday / Weekly Off"),
		)
		self.assertEqual(
			(rows["2026-11-07"].action, rows["2026-11-07"].status), (ad.ACTION_DEDUCT, ad.DEDUCTED)
		)
		self.assertEqual(
			frappe.db.get_value(
				"Leave Application", rows["2026-11-07"].leave_application, "total_leave_days"
			),
			1,
		)

	# --- year rollover -------------------------------------------------------------

	def test_year_rollover_creates_next_years_list(self):
		self.altura_groups()
		self.set_today("2026-12-10")
		mr.run_daily()
		self.assertFalse(frappe.db.exists("Holiday List", mr.list_name(self.philip, 2027)))
		[mail] = [m for m in self.sent if "need attention" in m["subject"]]
		self.assertIn("no base holiday list covers 2027", mail["message"])

		# HR points the Employee at next year's base list; the roster picks it up.
		employee = frappe.get_doc("Employee", self.philip)
		employee.holiday_list = BASE_2027
		employee.save()

		name = mr.list_name(self.philip, 2027)
		rows = holidays(self.philip, 2027)
		self.assertEqual(rows[getdate("2027-01-01")], "New Year's Day")
		self.assertNotIn(getdate("2027-01-02"), rows)  # Group 1 on duty
		self.assertEqual(rows[getdate("2027-01-09")], mr.MOD_OFF)
		self.assertEqual(rows[getdate("2027-01-03")], "Sunday")
		self.assertEqual(in_force(self.philip, "2027-01-09"), name)
		self.assertEqual(in_force(self.philip, "2026-12-31"), mr.list_name(self.philip, 2026))
		# 2026 still built from the 2026 base list (through the backfilled assignment).
		self.assertEqual(holidays(self.philip, 2026)[getdate("2026-12-25")], "Christmas Day")

	def test_missing_next_year_base_list_keeps_the_mod_on_last_years_list(self):
		"""1 January with no 2027 base list: no (empty) 2027 MOD list is built, the 2026
		assignment stays in force, the report flags the gap and HR keeps being emailed."""
		self.altura_groups()
		list_2026 = mr.list_name(self.philip, 2026)
		list_2027 = mr.list_name(self.philip, 2027)

		for day in ("2026-12-10", "2027-01-05"):
			with self.subTest(today=day):
				self.set_today(day)
				self.sent.clear()
				mr.run_daily()
				self.assertFalse(frappe.db.exists("Holiday List", list_2027))
				self.assertFalse(
					frappe.db.exists(mr.HLA, {"assigned_to": self.philip, "from_date": [">=", "2027-01-01"]})
				)
				self.assertEqual(in_force(self.philip, "2027-01-09"), list_2026)
				[mail] = [m for m in self.sent if "need attention" in m["subject"]]
				self.assertIn("no base holiday list covers", mail["message"])
				self.assertIn(self.philip, mail["message"])

		_columns, data, message = report.execute({"from_date": "2027-01-04", "to_date": "2027-01-10"})
		row = next(r for r in data if r.get("employee") == self.philip)
		self.assertEqual((row["d0"], row["d5"], row["d6"]), ("D!", "OFF!", "D!"))  # Jan 9 OFF, Jan 10 Sunday
		self.assertIn("No base holiday list covers", message)
		self.assertIn(self.philip, message)
		self.assertIsNone(report.execute({"from_date": "2026-12-01", "to_date": "2026-12-31"})[2])

		# HR adds next year's base list: the 2027 MOD list is built and assigned from today;
		# the days already past stay on the 2026 assignment.
		employee = frappe.get_doc("Employee", self.philip)
		employee.holiday_list = BASE_2027
		employee.save()
		self.assertEqual(holidays(self.philip, 2027)[getdate("2027-01-09")], mr.MOD_OFF)
		self.assertEqual(in_force(self.philip, "2027-01-09"), list_2027)
		self.assertEqual(in_force(self.philip, "2027-01-02"), list_2026)

	def test_base_list_change_reaches_the_mod_lists(self):
		self.altura_groups()
		base = frappe.get_doc("Holiday List", BASE_2026)
		base.append(
			"holidays", {"holiday_date": "2026-11-21", "description": "Surprise Holiday", "weekly_off": 0}
		)
		base.save()
		self.assertEqual(holidays(self.philip, 2026)[getdate("2026-11-21")], "Surprise Holiday")
		self.assertEqual(self.codes(self.philip, ["2026-11-21"]), [mr.PUBLIC_HOLIDAY])

	# --- guard, feature off, seed, report --------------------------------------------

	def test_other_assignments_for_an_active_mod_are_refused(self):
		self.altura_groups()
		hla = frappe.get_doc(
			{
				"doctype": mr.HLA,
				"applicable_for": "Employee",
				"assigned_to": self.philip,
				"holiday_list": BASE_2026,
				"from_date": "2026-12-01",
			}
		)
		with self.assertRaisesRegex(frappe.ValidationError, "MOD roster"):
			hla.insert()
		outsider = self.make_mod("Outsider")
		hla.assigned_to = outsider
		hla.insert()  # not a MOD: allowed

	def test_feature_off_is_a_noop(self):
		frappe.db.set_single_value("HR Settings", mr.ENABLED, 0)
		self.altura_groups()
		make_swap("2026-11-21", off=self.philip, cover=self.yvonne)
		mr.run_daily()
		self.assertFalse(frappe.db.exists("Holiday List", mr.list_name(self.philip, 2026)))
		self.assertFalse(frappe.db.exists(mr.HLA, {"assigned_to": self.philip}))
		self.assertEqual(self.sent, [])
		self.assertTrue(mr.regenerate().skipped)

		# Switching off later leaves the lists alone.
		frappe.db.set_single_value("HR Settings", mr.ENABLED, 1)
		mr.regenerate()
		before = holidays(self.philip, 2026)
		frappe.db.set_single_value("HR Settings", mr.ENABLED, 0)
		mr.regenerate()
		self.assertEqual(holidays(self.philip, 2026), before)

	def test_seed_dry_run_writes_nothing(self):
		groups = (
			{
				"group_name": "_Test MOD Seed 1",
				"anchor_date": "2026-11-07",
				"members": ("_Test MOD Philip", "_Test MOD Olger"),
			},
			{"group_name": "_Test MOD Seed 2", "anchor_date": "2026-10-31", "members": ("_Test MOD Yvonne",)},
		)
		with patch.object(mr, "ALTURA_GROUPS", groups):
			dry = mr.seed_altura_mod_groups(dry_run=1, from_date=TODAY)
			self.assertEqual(dry["problems"], [])
			self.assertEqual([len(g["members"]) for g in dry["groups"]], [2, 1])
			self.assertFalse(frappe.db.exists(mr.GROUP, "_Test MOD Seed 1"))

			mr.seed_altura_mod_groups(dry_run=0, from_date=TODAY)
			g1 = frappe.get_doc(mr.GROUP, "_Test MOD Seed 1")
			self.assertEqual((g1.cycle_weeks, g1.duty_week, str(g1.anchor_date)), (2, 1, "2026-11-07"))
			self.assertEqual(self.codes(self.yvonne, G2_DUTY), [mr.DUTY] * 2)

		with patch.object(
			mr,
			"ALTURA_GROUPS",
			({"group_name": "X", "anchor_date": "2026-11-07", "members": ("Nobody Here",)},),
		):
			self.assertIn("Nobody Here", mr.seed_altura_mod_groups(dry_run=1)["problems"][0])
			with self.assertRaises(frappe.ValidationError):
				mr.seed_altura_mod_groups(dry_run=0)

	def test_roster_report(self):
		self.altura_groups()
		swap = make_swap("2026-11-21", off=self.philip, cover=self.yvonne)
		raw_insert(
			"Leave Application",
			employee=self.olger,
			leave_type=AL,
			from_date="2026-11-18",
			to_date="2026-11-18",
			status="Approved",
			docstatus=1,
		)
		_columns, data, message = report.execute({"from_date": "2026-11-16", "to_date": "2026-11-22"})
		self.assertIsNone(message)  # every day has a base list
		header, *people, totals = data
		self.assertEqual(header["d0"], "16 Nov")
		by_id = {r["employee"]: r for r in people}
		self.assertEqual(by_id[self.philip]["d5"], "OFF*")
		self.assertEqual(by_id[self.yvonne]["d5"], "WD*")
		self.assertEqual(by_id[self.olger]["d5"], "WD")
		self.assertEqual(by_id[self.olger]["d2"], "L")
		self.assertEqual(by_id[self.philip]["d6"], "WO")
		self.assertEqual(totals["d5"], 2)
		self.assertEqual(totals["d2"], 2)  # Olger on leave
		self.assertTrue(swap.name)


# --- helpers ---------------------------------------------------------------------------


def make_base_lists():
	for name, year in ((BASE_2026, 2026), (BASE_2027, 2027)):
		if frappe.db.exists("Holiday List", name):
			continue
		rows = [
			{"holiday_date": d, "description": "Sunday", "weekly_off": 1}
			for d in mr.date_range(f"{year}-01-01", f"{year}-12-31")
			if d.weekday() == 6
		]
		rows += [
			{"holiday_date": d, "description": desc, "weekly_off": 0}
			for d, desc in PUBLIC_HOLIDAYS.items()
			if d.startswith(str(year))
		]
		frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": name,
				"from_date": f"{year}-01-01",
				"to_date": f"{year}-12-31",
				"holidays": rows,
			}
		).insert()


def make_group(name, anchor, members, cycle=2, duty_week=1):
	return frappe.get_doc(
		{
			"doctype": mr.GROUP,
			"group_name": name,
			"is_active": 1,
			"cycle_weeks": cycle,
			"duty_week": duty_week,
			"anchor_date": anchor,
			"members": [{"employee": e, "from_date": f} for e, f in members],
		}
	).insert()


def make_swap(day, off, cover):
	return frappe.get_doc(
		{"doctype": mr.SWAP, "date": day, "off_employee": off, "cover_employee": cover, "reason": "Test"}
	).submit()


def holidays(employee, year) -> dict:
	return {
		getdate(h.holiday_date): h.description
		for h in frappe.get_all(
			"Holiday",
			filters={"parent": mr.list_name(employee, year)},
			fields=["holiday_date", "description"],
		)
	}


def in_force(employee, day):
	return get_holiday_list_for_employee(employee, raise_exception=False, as_on=day)
