# Compassionate Leave Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild Karen Roses' Compassionate Leave feature (checkbox on Annual Leave applications that mirrors the deduction into the Compassionate Leave balance) cleanly in `upande_hr`, dropping the unused custom tracker doctype in favor of HRMS's native Leave Policy/Allocation balance system, and retire the buggy `upande_kaitet` version.

**Architecture:** A single `override_doctype_class` override of `LeaveApplication` in `upande_hr`, plus two Custom Fields on `Leave Application` (checkbox + read-only note). No new doctype: Compassionate Leave's 12-day, policy-renewing entitlement is already live HRMS infrastructure (Leave Type + Leave Policy + Leave Policy Assignment), so "balance remaining" is answered by HRMS's own `get_leave_balance_on()`, the same function core `validate_balance_leaves()` already uses.

**Tech Stack:** Frappe/ERPNext/HRMS (Python), `bench run-tests` (Python `unittest` via Frappe's test runner).

## Global Constraints

- Checkbox only visible when `leave_type == "Annual Leave"` AND `company == "Karen Roses"` (exact string match on Company name).
- Exceeding the employee's actual current Compassionate Leave balance is a hard block (`frappe.throw`) — matches `Compassionate Leave`'s existing `allow_negative: 0` and Sick Leave's precedent. The balance checked must come from `get_leave_balance_on()` (i.e. the employee's real, current Leave Policy Assignment), never a hardcoded number.
- Annual Leave's own balance validation is unchanged — already `allow_negative: 1`, so insufficient Annual balance only warns.
- The tenure bypass (`validate_applicable_after`) is carried over unchanged from the old `upande_kaitet` override — not being revisited this round.
- No new custom doctype. Reporting "days used/remaining" for Compassionate Leave is a standard HRMS leave-balance query, not custom-maintained fields.
- `upande_kaitet` has no git — edit its files on disk directly, no commit possible there. `upande_hr` is a git repo (branch `upande-kaitet` — same local-branch-naming quirk as `upande_stores`, harmless) — commit changes there.
- Site to verify against: `david.local`. Known transient `bench migrate` issue on this bench: `frappe.exceptions.QueueOverloaded: Too many queued background jobs (550)`. Fix: `bench --site david.local set-config max_queued_jobs 5000`, retry, then `bench --site david.local set-config max_queued_jobs 500` afterward. Don't leave it raised.
- JSON files in this codebase are formatted exactly like `frappe.as_json`: `json.dumps(data, indent=1, sort_keys=True, ensure_ascii=True, separators=(",", ": "))`.

---

### Task 1: Remove the old Compassionate Leave customization from `upande_kaitet`

**Files:**
- Modify: `apps/upande_kaitet/upande_kaitet/upande_kaitet/custom/leave_application.json`
- Modify: `apps/upande_kaitet/upande_kaitet/hooks.py:146-150`
- Delete: `apps/upande_kaitet/upande_kaitet/overrides/leave_application.py`
- Delete: `apps/upande_kaitet/upande_kaitet/upande_kaitet/doctype/compassionate_leave_tracker/` (entire directory)
- Delete: `apps/upande_kaitet/upande_kaitet/upande_kaitet/doctype/compassionate_leave_application/` (entire directory)
- Test: none (JSON validity + content checks below; live DB effects happen in Task 3)

**Interfaces:**
- Produces: `leave_application.json` with exactly 2 custom_fields (`custom_mobile_number`, `workflow_state` — unrelated fields, untouched), `links: []`, and the `links_order` property setter value `"[]"`.

- [ ] **Step 1: Confirm zero live records before deleting (safety check)**

```bash
bench --site david.local mariadb -e "SELECT COUNT(*) FROM \`tabCompassionate Leave Tracker\`; SELECT COUNT(*) FROM \`tabCompassionate Leave Application\`;"
```

Expected output: both counts `0`. If either is non-zero, STOP and escalate — this plan assumes no real data exists in these doctypes (confirmed at plan-writing time).

- [ ] **Step 2: Transform `leave_application.json`** — remove the 2 custom fields, the stale link, and empty `links_order`

```bash
cd /home/david/frappe/kaitet-bench
python3 <<'EOF'
import json

path = "apps/upande_kaitet/upande_kaitet/upande_kaitet/custom/leave_application.json"
with open(path) as f:
    data = json.load(f)

REMOVE_FIELDS = {"custom_is_compassionate", "custom_compassionate_balance_note"}
before = len(data["custom_fields"])
data["custom_fields"] = [f for f in data["custom_fields"] if f["fieldname"] not in REMOVE_FIELDS]
assert before - len(data["custom_fields"]) == 2, f"expected to remove 2 fields, removed {before - len(data['custom_fields'])}"

assert len(data["links"]) == 1 and data["links"][0]["link_doctype"] == "Compassionate Leave Tracker"
data["links"] = []

for p in data["property_setters"]:
    if p["name"] == "Leave Application-main-links_order":
        p["value"] = json.dumps([])

with open(path, "w") as f:
    f.write(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=True, separators=(",", ": ")))
    f.write("\n")

print("leave_application.json: OK,", len(data["custom_fields"]), "custom_fields, links:", data["links"])
EOF
```

Expected output: `leave_application.json: OK, 2 custom_fields, links: []`

- [ ] **Step 3: Verify remaining fields and no dangling references**

```bash
python3 -c "
import json
data = json.load(open('/home/david/frappe/kaitet-bench/apps/upande_kaitet/upande_kaitet/upande_kaitet/custom/leave_application.json'))
names = {f['fieldname'] for f in data['custom_fields']}
assert names == {'custom_mobile_number', 'workflow_state'}, names
assert data['links'] == []
for p in data['property_setters']:
    if p['name'] == 'Leave Application-main-links_order':
        assert json.loads(p['value']) == []
print('OK: only custom_mobile_number and workflow_state remain, links empty')
"
```

Expected output: `OK: only custom_mobile_number and workflow_state remain, links empty`

- [ ] **Step 4: Delete the old override file and the two doctype directories**

```bash
rm /home/david/frappe/kaitet-bench/apps/upande_kaitet/upande_kaitet/overrides/leave_application.py
rm -rf /home/david/frappe/kaitet-bench/apps/upande_kaitet/upande_kaitet/upande_kaitet/doctype/compassionate_leave_tracker
rm -rf /home/david/frappe/kaitet-bench/apps/upande_kaitet/upande_kaitet/upande_kaitet/doctype/compassionate_leave_application
test ! -f /home/david/frappe/kaitet-bench/apps/upande_kaitet/upande_kaitet/overrides/leave_application.py && echo "OK: override file gone"
test ! -d /home/david/frappe/kaitet-bench/apps/upande_kaitet/upande_kaitet/upande_kaitet/doctype/compassionate_leave_tracker && echo "OK: tracker doctype gone"
test ! -d /home/david/frappe/kaitet-bench/apps/upande_kaitet/upande_kaitet/upande_kaitet/doctype/compassionate_leave_application && echo "OK: tracker child doctype gone"
```

Expected output: all three `OK:` lines.

- [ ] **Step 5: Remove the `"Leave Application"` entry from `override_doctype_class`**

Current content of `apps/upande_kaitet/upande_kaitet/hooks.py:146-150`:
```python
override_doctype_class = {
	"Item Price": "upande_kaitet.overrides.custom_item_price_naming.CustomItemPrice",
	"Asset Repair": "upande_kaitet.overrides.asset_repair.CustomAssetRepair",
	"Leave Application": "upande_kaitet.overrides.leave_application.CustomLeaveApplication"
	# "Customize Form": "upande_kaitet.customize_override.PatchedCustomizeForm"  # Replace 'your_app' with your actual app name
	# "Lead": "upande_kaitet.overrides.lead.Lead",
```

Change to:
```python
override_doctype_class = {
	"Item Price": "upande_kaitet.overrides.custom_item_price_naming.CustomItemPrice",
	"Asset Repair": "upande_kaitet.overrides.asset_repair.CustomAssetRepair"
	# "Customize Form": "upande_kaitet.customize_override.PatchedCustomizeForm"  # Replace 'your_app' with your actual app name
	# "Lead": "upande_kaitet.overrides.lead.Lead",
```

- [ ] **Step 6: Verify the hooks.py edit**

```bash
python3 -c "
import ast
tree = ast.parse(open('/home/david/frappe/kaitet-bench/apps/upande_kaitet/upande_kaitet/hooks.py').read())
print('syntax OK')
"
grep -n "Leave Application" /home/david/frappe/kaitet-bench/apps/upande_kaitet/upande_kaitet/hooks.py
```

Expected output: `syntax OK` followed by no matching lines (grep finds nothing — exit code 1 is fine, means the string is gone).

- [ ] **Step 7: No commit** — `upande_kaitet` has no `.git`. Leave the files edited on disk; they'll be picked up by `bench migrate` in Task 3.

---

### Task 2: One-time cleanup patch in `upande_kaitet`

**Files:**
- Create: `apps/upande_kaitet/upande_kaitet/patches/v1_1/remove_compassionate_leave_customization.py`
- Modify: `apps/upande_kaitet/upande_kaitet/patches.txt`

**Interfaces:**
- Consumes: nothing from Task 1 at import time; at runtime assumes Task 1's file edits are already on disk.
- Produces: `execute()` function, idempotent (every deletion guarded by an existence check).

- [ ] **Step 1: Create the `v1_1` patch folder (no `__init__.py` needed — matches the `v1_0` convention already in this app)**

```bash
mkdir -p /home/david/frappe/kaitet-bench/apps/upande_kaitet/upande_kaitet/patches/v1_1
```

- [ ] **Step 2: Write the patch**

Create `apps/upande_kaitet/upande_kaitet/patches/v1_1/remove_compassionate_leave_customization.py`:

```python
# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe


def execute():
	"""One-time cleanup after retiring the upande_kaitet Compassionate Leave
	customization in favor of a rebuilt version in upande_hr. The custom/*.json
	Customize-Form-export sync upserts fields that are still present in the
	file, but never deletes a Custom Field that's been removed from it --
	that's this patch's job. The two tracker doctypes are dropped outright
	(confirmed zero live records before this patch was written).
	"""

	removed_custom_fields = [
		("Leave Application", "custom_is_compassionate"),
		("Leave Application", "custom_compassionate_balance_note"),
	]
	for dt, fieldname in removed_custom_fields:
		name = frappe.db.get_value("Custom Field", {"dt": dt, "fieldname": fieldname})
		if name:
			frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)

	if frappe.db.exists("DocType Link", {"parent": "Leave Application", "link_doctype": "Compassionate Leave Tracker"}):
		frappe.db.delete(
			"DocType Link", {"parent": "Leave Application", "link_doctype": "Compassionate Leave Tracker"}
		)

	for doctype in ("Compassionate Leave Tracker", "Compassionate Leave Application"):
		if frappe.db.exists("DocType", doctype):
			frappe.delete_doc("DocType", doctype, ignore_permissions=True, force=True)
		frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `tab{doctype}`")

	frappe.db.commit()
```

- [ ] **Step 3: Register the patch**

Read current `apps/upande_kaitet/upande_kaitet/patches.txt` (already has one `[post_model_sync]` entry from an earlier migration — `upande_kaitet.patches.v1_0.remove_legacy_material_request_fields`). Add the new entry on its own line directly below it:

```
[pre_model_sync]
# Patches added in this section will be executed before doctypes are migrated
# Read docs to understand patches: https://frappeframework.com/docs/v14/user/en/database-migrations

[post_model_sync]
# Patches added in this section will be executed after doctypes are migrated
upande_kaitet.patches.v1_0.remove_legacy_material_request_fields
upande_kaitet.patches.v1_1.remove_compassionate_leave_customization
```

- [ ] **Step 4: Verify the patch module imports cleanly and patches.txt references it correctly**

```bash
cd /home/david/frappe/kaitet-bench
python3 -c "
import ast
ast.parse(open('apps/upande_kaitet/upande_kaitet/patches/v1_1/remove_compassionate_leave_customization.py').read())
print('syntax OK')
"
grep -n "remove_compassionate_leave_customization" apps/upande_kaitet/upande_kaitet/patches.txt
```

Expected output: `syntax OK` followed by the matching `patches.txt` line.

---

### Task 3: Add the new Custom Fields to `upande_hr`

**Files:**
- Create: `apps/upande_hr/upande_hr/upande_hr/custom/leave_application.json`

**Interfaces:**
- Produces: `custom_is_compassionate` (Check, `module: "Upande Hr"`, `insert_after: "custom_mobile_number"`, `depends_on: eval:doc.leave_type=="Annual Leave" && doc.company=="Karen Roses"`) and `custom_compassionate_balance_note` (Small Text, read-only, `insert_after: "custom_is_compassionate"`) — both consumed by Task 4's override via `self.get("custom_is_compassionate")` / `self.db_set("custom_compassionate_balance_note", ...)`.

- [ ] **Step 1: Create the `custom/` folder and write the file**

```bash
mkdir -p /home/david/frappe/kaitet-bench/apps/upande_hr/upande_hr/upande_hr/custom
```

Write `apps/upande_hr/upande_hr/upande_hr/custom/leave_application.json`:

```json
{
 "custom_fields": [
  {
   "_assign": null,
   "_comments": null,
   "_liked_by": null,
   "_user_tags": null,
   "alignment": "",
   "allow_in_quick_entry": 0,
   "allow_on_submit": 0,
   "bold": 0,
   "button_color": "",
   "collapsible": 0,
   "collapsible_depends_on": null,
   "columns": 0,
   "creation": "2026-07-17 00:00:00.000000",
   "default": null,
   "depends_on": "eval:doc.leave_type==\"Annual Leave\" && doc.company==\"Karen Roses\"",
   "description": null,
   "docstatus": 0,
   "dt": "Leave Application",
   "fetch_from": null,
   "fetch_if_empty": 0,
   "fieldname": "custom_is_compassionate",
   "fieldtype": "Check",
   "hidden": 0,
   "hide_border": 0,
   "hide_days": 0,
   "hide_seconds": 0,
   "idx": 0,
   "ignore_user_permissions": 0,
   "ignore_xss_filter": 0,
   "in_global_search": 0,
   "in_list_view": 0,
   "in_preview": 0,
   "in_standard_filter": 0,
   "insert_after": "custom_mobile_number",
   "is_system_generated": 0,
   "is_virtual": 0,
   "label": "Is Compassionate?",
   "length": 0,
   "link_filters": null,
   "mandatory_depends_on": null,
   "mask": 0,
   "modified": "2026-07-17 00:00:00.000000",
   "modified_by": "Administrator",
   "module": "Upande Hr",
   "name": "Leave Application-custom_is_compassionate",
   "no_copy": 0,
   "non_negative": 0,
   "options": null,
   "owner": "Administrator",
   "permlevel": 0,
   "placeholder": null,
   "precision": "",
   "print_hide": 0,
   "print_hide_if_no_value": 0,
   "print_width": null,
   "read_only": 0,
   "read_only_depends_on": null,
   "report_hide": 0,
   "reqd": 0,
   "search_index": 0,
   "set_only_once": 0,
   "show_dashboard": 0,
   "sort_options": 0,
   "translatable": 0,
   "unique": 0,
   "width": null
  },
  {
   "_assign": null,
   "_comments": null,
   "_liked_by": null,
   "_user_tags": null,
   "alignment": "",
   "allow_in_quick_entry": 0,
   "allow_on_submit": 1,
   "bold": 0,
   "button_color": "",
   "collapsible": 0,
   "collapsible_depends_on": null,
   "columns": 0,
   "creation": "2026-07-17 00:00:00.000000",
   "default": null,
   "depends_on": null,
   "description": null,
   "docstatus": 0,
   "dt": "Leave Application",
   "fetch_from": null,
   "fetch_if_empty": 0,
   "fieldname": "custom_compassionate_balance_note",
   "fieldtype": "Small Text",
   "hidden": 0,
   "hide_border": 0,
   "hide_days": 0,
   "hide_seconds": 0,
   "idx": 0,
   "ignore_user_permissions": 0,
   "ignore_xss_filter": 0,
   "in_global_search": 0,
   "in_list_view": 0,
   "in_preview": 0,
   "in_standard_filter": 0,
   "insert_after": "custom_is_compassionate",
   "is_system_generated": 0,
   "is_virtual": 0,
   "label": "Compassionate Balance Note",
   "length": 0,
   "link_filters": null,
   "mandatory_depends_on": null,
   "mask": 0,
   "modified": "2026-07-17 00:00:00.000000",
   "modified_by": "Administrator",
   "module": "Upande Hr",
   "name": "Leave Application-custom_compassionate_balance_note",
   "no_copy": 0,
   "non_negative": 0,
   "options": null,
   "owner": "Administrator",
   "permlevel": 0,
   "placeholder": null,
   "precision": "",
   "print_hide": 0,
   "print_hide_if_no_value": 0,
   "print_width": null,
   "read_only": 1,
   "read_only_depends_on": null,
   "report_hide": 0,
   "reqd": 0,
   "search_index": 0,
   "set_only_once": 0,
   "show_dashboard": 0,
   "sort_options": 0,
   "translatable": 0,
   "unique": 0,
   "width": null
  }
 ],
 "custom_perms": [],
 "doctype": "Leave Application",
 "links": [],
 "property_setters": [],
 "sync_on_migrate": 1
}
```

Note: `allow_on_submit: 1` on `custom_compassionate_balance_note` is required — the override writes to this field via `db_set` after the document is already submitted (`on_submit`), so the field must be marked submittable-editable or the value would be silently rejected by Frappe's submitted-doc field-lock.

- [ ] **Step 2: Verify JSON validity and required keys**

```bash
python3 -c "
import json
data = json.load(open('/home/david/frappe/kaitet-bench/apps/upande_hr/upande_hr/upande_hr/custom/leave_application.json'))
names = {f['fieldname'] for f in data['custom_fields']}
assert names == {'custom_is_compassionate', 'custom_compassionate_balance_note'}, names
assert all(f['module'] == 'Upande Hr' for f in data['custom_fields'])
assert data['sync_on_migrate'] == 1
print('OK')
"
```

Expected output: `OK`

---

### Task 4: Write the `CustomLeaveApplication` override with tests

**Files:**
- Create: `apps/upande_hr/upande_hr/overrides/leave_application.py`
- Create: `apps/upande_hr/upande_hr/overrides/test_leave_application.py`
- Modify: `apps/upande_hr/upande_hr/hooks.py`

**Interfaces:**
- Consumes: `custom_is_compassionate` / `custom_compassionate_balance_note` fields from Task 3 (by fieldname, via `self.get(...)` / `self.db_set(...)`).
- Produces: `class CustomLeaveApplication(LeaveApplication)` with methods `_is_compassionate()`, `_validate_compassionate_balance()`, `_deduct_compassionate_leave_ledger()`, `_set_compassionate_balance_note()` — no other task depends on these directly, but the test in this task exercises all of them.

- [ ] **Step 1: Write the override**

Create `apps/upande_hr/upande_hr/overrides/leave_application.py`:

```python
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
```

Note on `on_cancel`: this override does **not** define `on_cancel`. HRMS's own `LeaveApplication.on_cancel()` calls `self.create_leave_ledger_entry(submit=False)`, which funnels into the module-level `create_leave_ledger_entry(ref_doc, args, submit=False)` in `hrms/hr/doctype/leave_ledger_entry/leave_ledger_entry.py` → `delete_ledger_entry(ledger)`, whose SQL is:
```sql
DELETE FROM `tabLeave Ledger Entry` WHERE `transaction_name`=%s OR `name`=%s
```
This deletes by `transaction_name` alone (no `leave_type` filter) — since both the Annual Leave entry and our mirrored Compassionate Leave entry share the same `transaction_name` (this Leave Application's `name`), a single cancel already removes both. Step 5 below writes a real test proving this; if it turns out wrong in practice, add this method and re-run the test:

```python
	def on_cancel(self):
		super().on_cancel()
		frappe.db.delete(
			"Leave Ledger Entry",
			{
				"transaction_type": "Leave Application",
				"transaction_name": self.name,
				"leave_type": COMPASSIONATE_LEAVE_TYPE,
			},
		)
```

- [ ] **Step 2: Wire the override into `upande_hr`'s hooks.py**

Current `apps/upande_hr/upande_hr/hooks.py` has:
```python
override_doctype_class = {
    "Compensatory Leave Request": "upande_hr.overrides.compensatory_leave_request.CustomCompensatoryLeaveRequest"
}
```

Change to:
```python
override_doctype_class = {
    "Compensatory Leave Request": "upande_hr.overrides.compensatory_leave_request.CustomCompensatoryLeaveRequest",
    "Leave Application": "upande_hr.overrides.leave_application.CustomLeaveApplication"
}
```

- [ ] **Step 3: Write the test file**

Create `apps/upande_hr/upande_hr/overrides/test_leave_application.py`:

```python
import frappe
from frappe.utils import add_days, getdate, nowdate
from hrms.tests.utils import HRMSTestSuite
from hrms.tests.test_utils import create_company
from erpnext.setup.doctype.employee.test_employee import make_employee
from hrms.hr.doctype.leave_type.test_leave_type import create_leave_type
from hrms.hr.doctype.leave_policy.test_leave_policy import create_leave_policy

from upande_hr.overrides.leave_application import CustomLeaveApplication

COMPANY = "_Test Karen Roses"


def setup_karen_roses_employee(annual_days=25, compassionate_days=12):
	"""Creates a fresh Company + Employee + Leave Policy Assignment granting
	both Annual Leave and Compassionate Leave, mirroring the real Karen Roses
	setup (Leave Policy with both leave types, Leave Policy Assignment)."""
	create_company(name=COMPANY)

	annual = create_leave_type(leave_type_name="Annual Leave", allow_negative=1)
	compassionate = create_leave_type(leave_type_name="Compassionate Leave", allow_negative=0)

	leave_policy = frappe.get_doc(
		{
			"doctype": "Leave Policy",
			"title": "_Test Karen Roses Leave Policy",
			"leave_policy_details": [
				{"leave_type": annual.name, "annual_allocation": annual_days},
				{"leave_type": compassionate.name, "annual_allocation": compassionate_days},
			],
		}
	).submit()

	employee_name = make_employee(
		"test_karen_roses_employee@example.com", company=COMPANY, date_of_joining=add_days(nowdate(), -365)
	)

	assignment = frappe.new_doc("Leave Policy Assignment")
	assignment.employee = employee_name
	assignment.leave_policy = leave_policy.name
	assignment.effective_from = add_days(nowdate(), -30)
	assignment.effective_to = add_days(nowdate(), 335)
	assignment.submit()

	return employee_name


def make_leave_application(employee, from_date, to_date, is_compassionate=0, company=COMPANY):
	doc = frappe.get_doc(
		{
			"doctype": "Leave Application",
			"employee": employee,
			"leave_type": "Annual Leave",
			"company": company,
			"from_date": from_date,
			"to_date": to_date,
			"status": "Approved",
			"custom_is_compassionate": is_compassionate,
		}
	)
	doc.insert()
	return doc


class TestCustomLeaveApplication(HRMSTestSuite):
	def test_controller_override_is_active(self):
		doc = frappe.new_doc("Leave Application")
		self.assertIsInstance(doc, CustomLeaveApplication)

	def test_checkbox_gate_matches_annual_leave_and_karen_roses_only(self):
		employee = setup_karen_roses_employee()
		doc = make_leave_application(employee, nowdate(), nowdate(), is_compassionate=1)
		self.assertTrue(doc._is_compassionate())

		doc.company = "_Test Company"
		self.assertFalse(doc._is_compassionate())

		doc.company = COMPANY
		doc.leave_type = "Compassionate Leave"
		self.assertFalse(doc._is_compassionate())

	def test_compassionate_application_deducts_both_ledgers(self):
		employee = setup_karen_roses_employee()
		doc = make_leave_application(
			employee, nowdate(), add_days(nowdate(), 4), is_compassionate=1
		)
		doc.submit()

		annual_entry = frappe.db.exists(
			"Leave Ledger Entry",
			{"transaction_name": doc.name, "leave_type": "Annual Leave", "docstatus": 1},
		)
		compassionate_entry = frappe.db.exists(
			"Leave Ledger Entry",
			{"transaction_name": doc.name, "leave_type": "Compassionate Leave", "docstatus": 1},
		)
		self.assertTrue(annual_entry)
		self.assertTrue(compassionate_entry)

		compassionate_leaves = frappe.db.get_value("Leave Ledger Entry", compassionate_entry, "leaves")
		self.assertEqual(compassionate_leaves, -5)

		doc.reload()
		self.assertIn("Compassionate Leave applied: 5", doc.custom_compassionate_balance_note)

	def test_compassionate_application_over_balance_is_blocked(self):
		employee = setup_karen_roses_employee(compassionate_days=3)
		doc = make_leave_application(
			employee, nowdate(), add_days(nowdate(), 4), is_compassionate=1
		)
		with self.assertRaises(frappe.ValidationError):
			doc.submit()

	def test_non_compassionate_annual_leave_untouched(self):
		employee = setup_karen_roses_employee()
		doc = make_leave_application(
			employee, nowdate(), add_days(nowdate(), 1), is_compassionate=0
		)
		doc.submit()

		compassionate_entry = frappe.db.exists(
			"Leave Ledger Entry",
			{"transaction_name": doc.name, "leave_type": "Compassionate Leave"},
		)
		self.assertFalse(compassionate_entry)

	def test_cancelling_compassionate_application_removes_both_ledger_entries(self):
		employee = setup_karen_roses_employee()
		doc = make_leave_application(
			employee, nowdate(), add_days(nowdate(), 2), is_compassionate=1
		)
		doc.submit()
		doc.cancel()

		annual_entry = frappe.db.exists(
			"Leave Ledger Entry",
			{"transaction_name": doc.name, "leave_type": "Annual Leave", "docstatus": 1},
		)
		compassionate_entry = frappe.db.exists(
			"Leave Ledger Entry",
			{"transaction_name": doc.name, "leave_type": "Compassionate Leave", "docstatus": 1},
		)
		self.assertFalse(annual_entry)
		self.assertFalse(compassionate_entry)
```

- [ ] **Step 4: Run the tests to verify they fail first where expected (TDD red)**

```bash
cd /home/david/frappe/kaitet-bench
bench --site david.local set-config allow_tests 1
bench --site david.local run-tests --app upande_hr --module upande_hr.overrides.test_leave_application
```

Expected: fails at collection/run time — `CustomLeaveApplication` import error or `override_doctype_class` not yet applied to a running site (the hooks.py change needs a `bench migrate`/cache clear to take effect). Note this and proceed to Step 5 before re-running.

- [ ] **Step 5: Run `bench migrate` so the new override and custom fields take effect, then re-run the tests**

```bash
cd /home/david/frappe/kaitet-bench
bench --site david.local migrate
```

If this fails with `QueueOverloaded`, apply the workaround from Global Constraints, then:

```bash
bench --site david.local run-tests --app upande_hr --module upande_hr.overrides.test_leave_application -v 2
```

Expected: all 6 tests pass. If `test_cancelling_compassionate_application_removes_both_ledger_entries` fails (the Compassionate Leave Ledger Entry is NOT removed on cancel), add the `on_cancel` method shown in Step 1's note, then re-run this exact command until it passes.

- [ ] **Step 6: Reset `allow_tests` and commit**

```bash
bench --site david.local set-config allow_tests 0
cd /home/david/frappe/kaitet-bench/apps/upande_hr
git add upande_hr/upande_hr/custom/leave_application.json \
        upande_hr/overrides/leave_application.py \
        upande_hr/overrides/test_leave_application.py \
        upande_hr/hooks.py
git status --short
git commit -m "$(cat <<'EOF'
Add Compassionate Leave override with real company gating

Rebuilds the Karen Roses compassionate-leave feature that previously lived
in upande_kaitet: a checkbox on Annual Leave applications (now correctly
gated to leave_type == "Annual Leave" && company == "Karen Roses", which the
old implementation never actually checked) that mirrors the deduction into
the employee's Compassionate Leave balance. No custom tracker doctype --
"days remaining" is answered by HRMS's own Leave Policy/Allocation balance,
same as every other leave type.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
git status --short
```

Expected output after commit: `git status --short` shows a clean tree.

---

### Task 5: Run migrate on `david.local` and verify the live site end-to-end

**Files:** none (verification only)

**Interfaces:**
- Consumes: all files from Tasks 1–4.

- [ ] **Step 1: Run the migration** (Task 4 Step 5 already ran one during test iteration — run again now that all files, including Task 1/2's `upande_kaitet` changes, are final, to be certain the whole set applies cleanly together)

```bash
cd /home/david/frappe/kaitet-bench
bench --site david.local migrate
echo "MIGRATE EXIT: $?"
```

Expected: ends with `MIGRATE EXIT: 0`. Apply the `QueueOverloaded` workaround from Global Constraints if needed, resetting `max_queued_jobs` back to 500 once it succeeds.

- [ ] **Step 2: Verify the old fields/doctypes are gone from the live DB**

```bash
bench --site david.local mariadb -e "
SELECT 'custom_is_compassionate' as check_name, COUNT(*) as remaining FROM \`tabCustom Field\` WHERE name='Leave Application-custom_is_compassionate'
UNION ALL
SELECT 'custom_compassionate_balance_note', COUNT(*) FROM \`tabCustom Field\` WHERE name='Leave Application-custom_compassionate_balance_note'
UNION ALL
SELECT 'Compassionate Leave Tracker doctype', COUNT(*) FROM \`tabDocType\` WHERE name='Compassionate Leave Tracker'
UNION ALL
SELECT 'Compassionate Leave Application doctype', COUNT(*) FROM \`tabDocType\` WHERE name='Compassionate Leave Application';
"
```

Expected output: all four rows show `remaining = 0`.

- [ ] **Step 3: Verify the new fields exist, owned by Upande Hr**

```bash
bench --site david.local mariadb -e "SELECT name, IFNULL(module,'NULL') FROM \`tabCustom Field\` WHERE dt='Leave Application' AND fieldname IN ('custom_is_compassionate','custom_compassionate_balance_note');"
```

Expected output: both rows show `module = Upande Hr`.

- [ ] **Step 4: Verify the override is active and the depends_on is correct**

```bash
bench --site david.local console <<'EOF'
doc = frappe.new_doc("Leave Application")
print("controller class:", type(doc).__name__)
meta = frappe.get_meta("Leave Application")
field = meta.get_field("custom_is_compassionate")
print("depends_on:", field.depends_on)

EOF
```

Expected output: `controller class: CustomLeaveApplication` and `depends_on: eval:doc.leave_type=="Annual Leave" && doc.company=="Karen Roses"`.

- [ ] **Step 5: Note remaining manual verification**

Record in the task report: actually applying and submitting a real Compassionate Leave application through the Desk UI against a real Karen Roses employee (not a test fixture) has not been exercised as part of this plan — recommend the user or QA do one real end-to-end submission on `david.local` before considering this fully verified in production, since Task 4's automated tests use freshly-created test fixtures, not real employee/allocation data.

---

### Task 6: Final commit check

**Files:** none — this task only confirms Task 4's commit already captured everything; `upande_kaitet`'s changes (Tasks 1–2) have no git to commit to.

- [ ] **Step 1: Confirm `upande_hr`'s tree is clean**

```bash
cd /home/david/frappe/kaitet-bench/apps/upande_hr
git status --short
git log --oneline -3
```

Expected: no output from `git status --short` (clean), and the compassionate-leave commit from Task 4 Step 6 at the top of `git log`.

---

## Self-Review Notes

- **Spec coverage:** Design's "Data model" (no new doctype) → Task 1/2 remove the old doctypes, Task 4's override relies purely on `get_leave_balance_on`. "Field customization" → Task 3. "Server logic" (validate/on_submit/on_cancel, gating, dynamic balance check) → Task 4. "Retiring the upande_kaitet version" → Tasks 1–2. All covered.
- **Placeholder scan:** none found — every step has literal file paths, literal code, and literal expected output. The one conditional (`on_cancel` added only if the cancellation test fails) carries the complete fallback code, not a vague instruction.
- **Type/name consistency:** `COMPASSIONATE_LEAVE_TYPE`/`COMPASSIONATE_GATED_COMPANY` constants used identically across `_is_compassionate`, `_validate_compassionate_balance`, `_deduct_compassionate_leave_ledger`; `custom_is_compassionate`/`custom_compassionate_balance_note` fieldnames match exactly between Task 3's JSON and Task 4's override/tests; the patch's deleted-field list matches Task 1's `REMOVE_FIELDS` set exactly.
