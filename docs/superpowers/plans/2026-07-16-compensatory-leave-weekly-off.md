# Compensatory Leave Request Weekly-Off Bypass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an employee submit a Compensatory Leave Request without an Attendance record when every day in the requested range is both a holiday and that employee's weekly-off, while leaving all other validation paths on `Compensatory Leave Request` (from the `hrms` app) untouched.

**Architecture:** Add a Python package `upande_hr/overrides/` containing `CustomCompensatoryLeaveRequest`, a subclass of HRMS's `CompensatoryLeaveRequest` that overrides only `validate_attendance()`. Register it via the `override_doctype_class` hook in `upande_hr/hooks.py`, following the existing convention already used by `upande_kaitet` and `upande_webshop` in this bench. No `hrms` source file is modified.

**Tech Stack:** Frappe framework (Python), `bench run-tests` / `FrappeTestCase` (via `hrms.tests.utils.HRMSTestSuite`) for automated tests, MariaDB via `bench mariadb` for manual verification.

## Global Constraints

- Bypass fires **only** when every day in `work_from_date`..`work_end_date` is the employee's weekly-off (per spec: `docs/superpowers/specs/2026-07-16-compensatory-leave-weekly-off-design.md`). A mixed range (any day not weekly-off) must fall through to the original, unmodified `validate_attendance()`.
- Must use `override_doctype_class` — not `doc_events`, not monkeypatching. The override class must subclass `hrms.hr.doctype.compensatory_leave_request.compensatory_leave_request.CompensatoryLeaveRequest`.
- `get_holiday_list_for_employee` must be imported from `erpnext.setup.doctype.employee.employee` (the hook-dispatching entry point), not from `hrms.utils.holiday_list` directly — this matches what `hrms/hr/utils.py` itself does.
- When the bypass fires, append an explanatory note to the existing `reason` field (Small Text) on the request. Must be idempotent: saving/validating the same document twice must not duplicate the note.
- Site under test: `otieno.local`. It has `developer_mode` **off**, so `frappe.get_hooks()` reads a Redis-cached `app_hooks` blob (see `apps/frappe/frappe/__init__.py:996-1009`) that is **not** invalidated just by editing `hooks.py` — any task that changes `override_doctype_class` in `hooks.py` must be followed by `bench --site otieno.local clear-cache` before tests will observe it.
- `otieno.local` currently has tests disabled (`bench --site otieno.local run-tests` prints "Testing is disabled for the site!"). Task 1 enables this once, site-wide, via `bench --site otieno.local set-config allow_tests true` — do not repeat this in later tasks.

---

### Task 1: Enable tests on the site, then wire up `override_doctype_class` with a pass-through subclass

**Files:**
- Create: `apps/upande_hr/upande_hr/overrides/__init__.py`
- Create: `apps/upande_hr/upande_hr/overrides/compensatory_leave_request.py`
- Modify: `apps/upande_hr/upande_hr/hooks.py` (add `override_doctype_class` block after the existing `fixtures` block, before the `# Installation` section)
- Test: `apps/upande_hr/upande_hr/overrides/test_compensatory_leave_request.py`

**Interfaces:**
- Produces: `upande_hr.overrides.compensatory_leave_request.CustomCompensatoryLeaveRequest` — a class, subclass of `hrms.hr.doctype.compensatory_leave_request.compensatory_leave_request.CompensatoryLeaveRequest`. Tasks 2-4 add methods to this same class.

- [ ] **Step 1: Enable tests on the site (one-time)**

Run: `bench --site otieno.local set-config allow_tests true`
Expected: command exits with no error (it silently writes `allow_tests: true` into `sites/otieno.local/site_config.json`).

- [ ] **Step 2: Write the failing test**

Create `apps/upande_hr/upande_hr/overrides/test_compensatory_leave_request.py`:

```python
import frappe
from hrms.tests.utils import HRMSTestSuite

from upande_hr.overrides.compensatory_leave_request import CustomCompensatoryLeaveRequest


class TestCustomCompensatoryLeaveRequest(HRMSTestSuite):
	def test_controller_override_is_active(self):
		doc = frappe.new_doc("Compensatory Leave Request")
		self.assertIsInstance(doc, CustomCompensatoryLeaveRequest)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `bench --site otieno.local run-tests --module upande_hr.overrides.test_compensatory_leave_request`
Expected: FAIL — `ModuleNotFoundError: No module named 'upande_hr.overrides'` (the package doesn't exist yet).

- [ ] **Step 4: Create the overrides package and pass-through class**

Create `apps/upande_hr/upande_hr/overrides/__init__.py` (empty file).

Create `apps/upande_hr/upande_hr/overrides/compensatory_leave_request.py`:

```python
from hrms.hr.doctype.compensatory_leave_request.compensatory_leave_request import (
	CompensatoryLeaveRequest,
)


class CustomCompensatoryLeaveRequest(CompensatoryLeaveRequest):
	pass
```

- [ ] **Step 5: Register the override in hooks.py**

In `apps/upande_hr/upande_hr/hooks.py`, add this block immediately after the `fixtures = [...]` block (added in the previous feature) and before the `# Installation` section:

```python
# Doctype Class Overrides
# ------------------------

override_doctype_class = {
	"Compensatory Leave Request": "upande_hr.overrides.compensatory_leave_request.CustomCompensatoryLeaveRequest"
}
```

- [ ] **Step 6: Clear the site's cached hooks**

Run: `bench --site otieno.local clear-cache`
Expected: command exits with no error.

- [ ] **Step 7: Run test to verify it passes**

Run: `bench --site otieno.local run-tests --module upande_hr.overrides.test_compensatory_leave_request`
Expected: PASS (1 test).

- [ ] **Step 8: Commit**

```bash
cd apps/upande_hr
git add upande_hr/overrides/__init__.py upande_hr/overrides/compensatory_leave_request.py upande_hr/hooks.py
git commit -m "Wire up Compensatory Leave Request controller override"
```

---

### Task 2: `is_weekly_off_request()` — detect an all-weekly-off date range

**Files:**
- Modify: `apps/upande_hr/upande_hr/overrides/compensatory_leave_request.py`
- Test: `apps/upande_hr/upande_hr/overrides/test_compensatory_leave_request.py`

**Interfaces:**
- Consumes: `CustomCompensatoryLeaveRequest` (from Task 1).
- Produces: `CustomCompensatoryLeaveRequest.is_weekly_off_request(self) -> bool`. Task 3 calls this from `validate_attendance()`.

- [ ] **Step 1: Write the failing tests**

Add to `apps/upande_hr/upande_hr/overrides/test_compensatory_leave_request.py` (keep the existing import block, add these new imports and test methods):

```python
from frappe.utils import add_days, add_months, today

from hrms.hr.doctype.attendance_request.test_attendance_request import get_employee
from hrms.hr.doctype.holiday_list_assignment.test_holiday_list_assignment import (
	create_holiday_list_assignment,
)
from hrms.hr.doctype.leave_period.test_leave_period import create_leave_period


def create_holiday_list_with_weekly_off(weekly_off_date, holiday_list_name="_Test Upande HR Weekly Off"):
	if frappe.db.exists("Holiday List", holiday_list_name):
		frappe.db.delete("Holiday List", holiday_list_name)
		frappe.db.delete("Holiday", {"parent": holiday_list_name})

	holiday_list = frappe.get_doc(
		{
			"doctype": "Holiday List",
			"holiday_list_name": holiday_list_name,
			"from_date": add_months(today(), -3),
			"to_date": add_months(today(), 3),
			"holidays": [
				{
					"description": "Weekly Off",
					"holiday_date": weekly_off_date,
					"weekly_off": 1,
				},
				{
					"description": "Regular Holiday",
					"holiday_date": add_days(weekly_off_date, -1),
					"weekly_off": 0,
				},
			],
		}
	)
	holiday_list.save()
	return holiday_list
```

```python
	def test_is_weekly_off_request_true_when_range_is_all_weekly_off(self):
		create_leave_period(add_months(today(), -3), add_months(today(), 3), "_Test Company")
		weekly_off_date = today()
		holiday_list = create_holiday_list_with_weekly_off(weekly_off_date)
		employee = get_employee()
		create_holiday_list_assignment("Employee", employee.name, holiday_list.name)

		doc = frappe.new_doc("Compensatory Leave Request")
		doc.update(
			{
				"employee": employee.name,
				"leave_type": "Compensatory Off",
				"work_from_date": weekly_off_date,
				"work_end_date": weekly_off_date,
				"reason": "test",
			}
		)
		self.assertTrue(doc.is_weekly_off_request())

	def test_is_weekly_off_request_false_for_regular_holiday(self):
		create_leave_period(add_months(today(), -3), add_months(today(), 3), "_Test Company")
		weekly_off_date = today()
		regular_holiday_date = add_days(weekly_off_date, -1)
		holiday_list = create_holiday_list_with_weekly_off(weekly_off_date)
		employee = get_employee()
		create_holiday_list_assignment("Employee", employee.name, holiday_list.name)

		doc = frappe.new_doc("Compensatory Leave Request")
		doc.update(
			{
				"employee": employee.name,
				"leave_type": "Compensatory Off",
				"work_from_date": regular_holiday_date,
				"work_end_date": regular_holiday_date,
				"reason": "test",
			}
		)
		self.assertFalse(doc.is_weekly_off_request())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bench --site otieno.local run-tests --module upande_hr.overrides.test_compensatory_leave_request`
Expected: FAIL — `AttributeError: 'CustomCompensatoryLeaveRequest' object has no attribute 'is_weekly_off_request'` (2 new failures, the Task 1 test still passes).

- [ ] **Step 3: Implement `is_weekly_off_request()`**

Replace the contents of `apps/upande_hr/upande_hr/overrides/compensatory_leave_request.py` with:

```python
import frappe
from frappe.utils import date_diff
from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee
from hrms.hr.doctype.compensatory_leave_request.compensatory_leave_request import (
	CompensatoryLeaveRequest,
)


class CustomCompensatoryLeaveRequest(CompensatoryLeaveRequest):
	def is_weekly_off_request(self):
		holiday_list = get_holiday_list_for_employee(self.employee, raise_exception=False)
		if not holiday_list:
			return False

		total_days = date_diff(self.work_end_date, self.work_from_date) + 1
		weekly_off_days = frappe.get_all(
			"Holiday",
			filters={
				"parent": holiday_list,
				"holiday_date": ("between", [self.work_from_date, self.work_end_date]),
				"weekly_off": 1,
			},
			pluck="holiday_date",
		)
		return len(weekly_off_days) == total_days
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `bench --site otieno.local run-tests --module upande_hr.overrides.test_compensatory_leave_request`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
cd apps/upande_hr
git add upande_hr/overrides/compensatory_leave_request.py upande_hr/overrides/test_compensatory_leave_request.py
git commit -m "Add is_weekly_off_request() detection to Compensatory Leave Request override"
```

---

### Task 3: Bypass `validate_attendance()` on an all-weekly-off range, preserve it otherwise

**Files:**
- Modify: `apps/upande_hr/upande_hr/overrides/compensatory_leave_request.py`
- Test: `apps/upande_hr/upande_hr/overrides/test_compensatory_leave_request.py`

**Interfaces:**
- Consumes: `CustomCompensatoryLeaveRequest.is_weekly_off_request()` (Task 2).
- Produces: `CustomCompensatoryLeaveRequest.validate_attendance(self)` override — no return value; raises `frappe.ValidationError` in the same cases the original method would, except when `is_weekly_off_request()` is true.

- [ ] **Step 1: Write the failing tests**

Add to `apps/upande_hr/upande_hr/overrides/test_compensatory_leave_request.py`:

```python
from hrms.hr.doctype.compensatory_leave_request.test_compensatory_leave_request import (
	mark_attendance,
)
```

```python
	def test_weekly_off_bypasses_attendance_check(self):
		create_leave_period(add_months(today(), -3), add_months(today(), 3), "_Test Company")
		weekly_off_date = today()
		holiday_list = create_holiday_list_with_weekly_off(weekly_off_date)
		employee = get_employee()
		create_holiday_list_assignment("Employee", employee.name, holiday_list.name)

		# no Attendance record created for weekly_off_date
		doc = frappe.get_doc(
			{
				"doctype": "Compensatory Leave Request",
				"employee": employee.name,
				"leave_type": "Compensatory Off",
				"work_from_date": weekly_off_date,
				"work_end_date": weekly_off_date,
				"reason": "test",
			}
		)
		doc.insert()
		doc.submit()  # must not raise

	def test_regular_holiday_without_attendance_still_blocked(self):
		create_leave_period(add_months(today(), -3), add_months(today(), 3), "_Test Company")
		weekly_off_date = today()
		regular_holiday_date = add_days(weekly_off_date, -1)
		holiday_list = create_holiday_list_with_weekly_off(weekly_off_date)
		employee = get_employee()
		create_holiday_list_assignment("Employee", employee.name, holiday_list.name)

		# no Attendance record created for regular_holiday_date
		doc = frappe.get_doc(
			{
				"doctype": "Compensatory Leave Request",
				"employee": employee.name,
				"leave_type": "Compensatory Off",
				"work_from_date": regular_holiday_date,
				"work_end_date": regular_holiday_date,
				"reason": "test",
			}
		)
		doc.insert()
		self.assertRaises(frappe.ValidationError, doc.submit)

	def test_regular_holiday_with_attendance_still_allowed(self):
		create_leave_period(add_months(today(), -3), add_months(today(), 3), "_Test Company")
		weekly_off_date = today()
		regular_holiday_date = add_days(weekly_off_date, -1)
		holiday_list = create_holiday_list_with_weekly_off(weekly_off_date)
		employee = get_employee()
		create_holiday_list_assignment("Employee", employee.name, holiday_list.name)
		mark_attendance(employee, date=regular_holiday_date)

		doc = frappe.get_doc(
			{
				"doctype": "Compensatory Leave Request",
				"employee": employee.name,
				"leave_type": "Compensatory Off",
				"work_from_date": regular_holiday_date,
				"work_end_date": regular_holiday_date,
				"reason": "test",
			}
		)
		doc.insert()
		doc.submit()  # must not raise
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `bench --site otieno.local run-tests --module upande_hr.overrides.test_compensatory_leave_request`
Expected: `test_weekly_off_bypasses_attendance_check` FAILS with `frappe.ValidationError: You are not present all day(s) between compensatory leave request days`. The other two new tests PASS already (they exercise unmodified behavior) — that's expected, they exist to lock in the regression guarantee before we touch the method.

- [ ] **Step 3: Implement the `validate_attendance()` override**

Add this method to `CustomCompensatoryLeaveRequest` in `apps/upande_hr/upande_hr/overrides/compensatory_leave_request.py` (keep `is_weekly_off_request` from Task 2):

```python
	def validate_attendance(self):
		if self.is_weekly_off_request():
			return
		super().validate_attendance()
```

- [ ] **Step 4: Run tests to verify they all pass**

Run: `bench --site otieno.local run-tests --module upande_hr.overrides.test_compensatory_leave_request`
Expected: PASS (6 tests).

- [ ] **Step 5: Regression-check the existing hrms test suite for this doctype**

Run: `bench --site otieno.local run-tests --module hrms.hr.doctype.compensatory_leave_request.test_compensatory_leave_request`
Expected: PASS, same as before the override existed — `override_doctype_class` swaps the controller for *every* instantiation of `Compensatory Leave Request`, including hrms's own tests, so this confirms nothing else broke.

- [ ] **Step 6: Commit**

```bash
cd apps/upande_hr
git add upande_hr/overrides/compensatory_leave_request.py upande_hr/overrides/test_compensatory_leave_request.py
git commit -m "Bypass attendance validation when Compensatory Leave Request range is all weekly-off"
```

---

### Task 4: Append an explanatory note to `reason`, idempotently

**Files:**
- Modify: `apps/upande_hr/upande_hr/overrides/compensatory_leave_request.py`
- Test: `apps/upande_hr/upande_hr/overrides/test_compensatory_leave_request.py`

**Interfaces:**
- Consumes: `CustomCompensatoryLeaveRequest.is_weekly_off_request()` (Task 2), `validate_attendance()` (Task 3).
- Produces: `CustomCompensatoryLeaveRequest.add_weekly_off_note(self)` — mutates `self.reason` in place, no return value.

- [ ] **Step 1: Write the failing tests**

Add to `apps/upande_hr/upande_hr/overrides/test_compensatory_leave_request.py`:

```python
	def test_weekly_off_note_added_to_reason(self):
		create_leave_period(add_months(today(), -3), add_months(today(), 3), "_Test Company")
		weekly_off_date = today()
		holiday_list = create_holiday_list_with_weekly_off(weekly_off_date)
		employee = get_employee()
		create_holiday_list_assignment("Employee", employee.name, holiday_list.name)

		doc = frappe.get_doc(
			{
				"doctype": "Compensatory Leave Request",
				"employee": employee.name,
				"leave_type": "Compensatory Off",
				"work_from_date": weekly_off_date,
				"work_end_date": weekly_off_date,
				"reason": "Worked on my weekly off",
			}
		)
		doc.insert()
		doc.submit()

		self.assertIn("Worked on my weekly off", doc.reason)
		self.assertIn("Attendance not required", doc.reason)

	def test_weekly_off_note_not_duplicated_on_resave(self):
		create_leave_period(add_months(today(), -3), add_months(today(), 3), "_Test Company")
		weekly_off_date = today()
		holiday_list = create_holiday_list_with_weekly_off(weekly_off_date)
		employee = get_employee()
		create_holiday_list_assignment("Employee", employee.name, holiday_list.name)

		doc = frappe.get_doc(
			{
				"doctype": "Compensatory Leave Request",
				"employee": employee.name,
				"leave_type": "Compensatory Off",
				"work_from_date": weekly_off_date,
				"work_end_date": weekly_off_date,
				"reason": "test",
			}
		)
		doc.insert()
		doc.save()  # validate() runs again on the same draft

		self.assertEqual(doc.reason.count("Attendance not required"), 1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bench --site otieno.local run-tests --module upande_hr.overrides.test_compensatory_leave_request`
Expected: FAIL — both new tests fail on `assertIn("Attendance not required", doc.reason)` / the count assertion, since no note is added yet.

- [ ] **Step 3: Implement `add_weekly_off_note()` and call it from `validate_attendance()`**

Replace `apps/upande_hr/upande_hr/overrides/compensatory_leave_request.py` with:

```python
import frappe
from frappe import _
from frappe.utils import date_diff
from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee
from hrms.hr.doctype.compensatory_leave_request.compensatory_leave_request import (
	CompensatoryLeaveRequest,
)


class CustomCompensatoryLeaveRequest(CompensatoryLeaveRequest):
	def validate_attendance(self):
		if self.is_weekly_off_request():
			self.add_weekly_off_note()
			return
		super().validate_attendance()

	def is_weekly_off_request(self):
		holiday_list = get_holiday_list_for_employee(self.employee, raise_exception=False)
		if not holiday_list:
			return False

		total_days = date_diff(self.work_end_date, self.work_from_date) + 1
		weekly_off_days = frappe.get_all(
			"Holiday",
			filters={
				"parent": holiday_list,
				"holiday_date": ("between", [self.work_from_date, self.work_end_date]),
				"weekly_off": 1,
			},
			pluck="holiday_date",
		)
		return len(weekly_off_days) == total_days

	def add_weekly_off_note(self):
		note = _("Attendance not required — {0} to {1} falls on {2}'s weekly off.").format(
			self.work_from_date, self.work_end_date, self.employee_name or self.employee
		)
		if note not in (self.reason or ""):
			self.reason = f"{self.reason}\n{note}".strip() if self.reason else note
```

- [ ] **Step 4: Run tests to verify they all pass**

Run: `bench --site otieno.local run-tests --module upande_hr.overrides.test_compensatory_leave_request`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
cd apps/upande_hr
git add upande_hr/overrides/compensatory_leave_request.py upande_hr/overrides/test_compensatory_leave_request.py
git commit -m "Append weekly-off exemption note to Compensatory Leave Request reason field"
```

---

### Task 5: Manual verification on real data and deploy

**Files:** none (verification only).

**Interfaces:** none — this task consumes the finished feature from Tasks 1-4 and produces no new interface.

- [ ] **Step 1: Full regression pass**

Run: `bench --site otieno.local run-tests --app upande_hr`
Expected: PASS, all tests in the app (including the new file) succeed.

Run: `bench --site otieno.local run-tests --module hrms.hr.doctype.compensatory_leave_request.test_compensatory_leave_request`
Expected: PASS — confirms the override still doesn't break hrms's own suite.

- [ ] **Step 2: Manual check with a real Employee on `otieno.local`**

Pick a real Employee that has a Holiday List assigned (or a Holiday List Assignment) with at least one date flagged `weekly_off = 1` in the near future. Using the Desk UI (or `bench --site otieno.local console`), create a new Compensatory Leave Request for that employee with `work_from_date` = `work_end_date` = that weekly-off date, no Attendance record for that date, and submit it. Confirm:
- The submission succeeds without an Attendance-related error.
- The `Reason` field shows the appended note.

Then create a second request for a date that is a regular holiday (not weekly-off) with no Attendance record, and confirm it is still rejected with the original "You are not present all day(s)..." error — this is the regression check on real (not test) data.

- [ ] **Step 3: Apply the operational cache/restart step**

Run: `bench --site otieno.local migrate`
Then: `bench restart`

Expected: both commands exit cleanly. This mirrors the design doc's operational note — `migrate` clears the Redis `app_hooks` cache and any other site-level caches; `restart` is required so already-running workers pick up the new controller class instead of the one memoized in `frappe.controllers[site][doctype]` from before this change.

- [ ] **Step 4: Final commit (if any manual-check fixes were needed)**

If Step 2 surfaced any issue requiring a code change, fix it, re-run the relevant task's tests, and commit with a message describing the fix. If no changes were needed, this step is a no-op — the feature is complete as of Task 4's commit.
