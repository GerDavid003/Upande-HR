# Employee Contracts & Expiry Reminders Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Track each employee's chain of fixed-term contracts as submittable `Employee Contract` documents, keep Employee's standard contract fields in sync, and send configurable reminders before each contract expires, configured in a new `Upande HR Settings` single doctype.

**Architecture:** Four new doctypes in module `Upande Hr` (so Frappe's `remove_app` drops them). Business logic lives in a small `upande_hr/contracts/` package (`sync.py`, `reminders.py`, `backfill.py`) called from the doctype controller, a daily scheduler hook, `after_install`, and a `post_model_sync` patch. No Custom Fields are added to Employee.

**Tech Stack:** Frappe/ERPNext v16, HRMS 16.12.x; `FrappeTestCase` via `hrms.tests.utils.HRMSTestSuite`; `bench run-tests`.

**Spec:** `docs/superpowers/specs/2026-11-18-employee-contracts-design.md`

## Global Constraints

- App `upande_hr`, module `Upande Hr`; all doctype folders under `upande_hr/upande_hr/doctype/`.
- Site: `otieno.local` (my-bench), `developer_mode` off, `allow_tests` already true. After editing `hooks.py` run `bench --site otieno.local clear-cache`; after adding/changing doctype JSON run `bench --site otieno.local migrate`.
- **No hard-coded role names anywhere in code.** Every new doctype ships with exactly one permission row: System Manager (full; plus submit/cancel/amend for Employee Contract). Server methods check `frappe.has_permission(...)` / `doc.check_permission(...)`, never roles.
- No default reminder recipients. Default reminder points: 30, 14, 7, 0.
- Confirm-as-Permanent Employment Type: required, **no default**.
- No Email Template / Notification records created — email body built in code.
- Uninstall must leave no orphans (see Task 7).
- Employee writes use `frappe.db.set_value("Employee", ...)`, never `employee.save()`.
- Tests: `bench --site otieno.local run-tests --module <dotted.module>`. If collection fails with a Price List `DuplicateEntryError`/`LinkValidationError` and 0 tests run, that is the known pre-existing bootstrap issue — fall back to a temp script using `frappe.init/connect` + rollback, and report it.

## Review Focus

1. **Overlapping or back-dated contracts** (renewal draft edited to overlap the previous one) → must be rejected on submit, not silently accepted. Test in Task 2.
2. **Cancelling the middle/latest contract** → previous contract's status and Employee fields restore correctly. Test in Task 3.
3. **Scheduler missed days** → only the most urgent missed point is sent, once; no re-send on the next day. Test in Task 5.
4. **Recipient resolution with disabled users / users without email / Company user permissions** → excluded/scoped correctly. Test in Task 5.
5. **Backfill run twice** (after_install + patch) → no duplicate contracts. Test in Task 6.

---

## File Structure

| Path (under `upande_hr/`) | Responsibility |
|---|---|
| `upande_hr/doctype/contract_reminder_day/` | Child: `days_before` |
| `upande_hr/doctype/contract_reminder_recipient/` | Child: `recipient_type`, `recipient` |
| `upande_hr/doctype/upande_hr_settings/` | Single settings doctype + validation |
| `upande_hr/doctype/employee_contract/` | Contract doctype, controller, form JS, tests |
| `contracts/__init__.py` | package |
| `contracts/sync.py` | Employee field sync |
| `contracts/reminders.py` | Expiry marking, due-point logic, recipients, sending |
| `contracts/backfill.py` | One-time creation of contract #1 |
| `contracts/test_reminders.py`, `contracts/test_backfill.py` | tests |
| `overrides/employee_dashboard.py` | Adds Employee Contract to Employee connections |
| `patches/backfill_employee_contracts.py` | post_model_sync patch |
| `install.py`, `hooks.py`, `patches.txt` | wiring |

---

### Task 1: Upande HR Settings + child doctypes

**Files:**
- Create: `upande_hr/upande_hr/doctype/contract_reminder_day/{__init__.py,contract_reminder_day.json,contract_reminder_day.py}`
- Create: `upande_hr/upande_hr/doctype/contract_reminder_recipient/{__init__.py,contract_reminder_recipient.json,contract_reminder_recipient.py}`
- Create: `upande_hr/upande_hr/doctype/upande_hr_settings/{__init__.py,upande_hr_settings.json,upande_hr_settings.py,upande_hr_settings.js,test_upande_hr_settings.py}`
- Modify: `upande_hr/install.py` (add `after_install`), `upande_hr/hooks.py` (uncomment/set `after_install`)

**Interfaces:**
- Produces: settings fields `enable_contract_expiry_reminders` (Check), `contract_reminder_days` (Table → Contract Reminder Day: `days_before` Int reqd), `contract_reminder_recipients` (Table → Contract Reminder Recipient: `recipient_type` Select `Role\nRole Profile` reqd, `recipient` Dynamic Link options `recipient_type` reqd), `notify_reporting_manager` (Check).
- Produces: `upande_hr.install.after_install() -> None`; `upande_hr.install.set_default_reminder_days() -> None` (adds 30/14/7/0 only if table empty).
- Layout: `issingle: 1`; first field a Tab Break `contracts_tab` "Contracts", then Section Break `contract_expiry_reminders_section` "Contract Expiry Reminders", fields in order above.

- [ ] **Step 1: Write failing tests** in `test_upande_hr_settings.py` (class `TestUpandeHRSettings(HRMSTestSuite)`):
  - `test_rejects_negative_days`: append `days_before=-1` → `save()` raises `frappe.ValidationError`.
  - `test_rejects_duplicate_days`: rows 7 and 7 → raises `frappe.ValidationError`.
  - `test_enabled_requires_days_and_recipient`: enabled, no days → raises; enabled, days but no recipients and `notify_reporting_manager=0` → raises; with `notify_reporting_manager=1` → saves.
  - `test_default_days`: clear table, call `set_default_reminder_days()`, assert sorted `days_before` == `[0, 7, 14, 30]`; call again, still 4 rows.
- [ ] **Step 2: Run** `bench --site otieno.local run-tests --module upande_hr.upande_hr.doctype.upande_hr_settings.test_upande_hr_settings` → FAIL (module/doctype missing).
- [ ] **Step 3: Implement** doctype JSONs (module `Upande Hr`, child doctypes `istable: 1`, permissions per Global Constraints) and `UpandeHRSettings.validate()`; `after_install` calls `set_default_reminder_days()`. Hook: `after_install = "upande_hr.install.after_install"`.
- [ ] **Step 4: Migrate, clear cache, re-run tests** → PASS.
- [ ] **Step 5: Commit** `feat: add Upande HR Settings with contract reminder configuration`

---

### Task 2: Employee Contract doctype — fields, numbering, validation, submit

**Files:**
- Create: `upande_hr/upande_hr/doctype/employee_contract/{__init__.py,employee_contract.json,employee_contract.py,test_employee_contract.py}`

**Interfaces:**
- Produces doctype `Employee Contract`: `is_submittable: 1`, `autoname: "naming_series:"`, `naming_series` options `HR-CON-.YYYY.-.#####`; fields exactly as spec §1: `employee` (Link, reqd), `employee_name`/`company`/`department` (fetch_from `employee.*`, read-only), `contract_number` (Int, read-only, no_copy), `employment_type` (Link Employment Type, reqd), `start_date` (Date reqd), `duration_months` (Int), `end_date` (Date reqd), `previous_contract` (Link Employee Contract, read-only), `status` (Select `Draft\nActive\nRenewed\nConfirmed\nExpired\nCancelled`, default Draft, read-only, allow_on_submit, no_copy, in_list_view, in_standard_filter), `confirmation_date` (Date, read-only, allow_on_submit, no_copy), `confirmed_employment_type` (Link Employment Type, read-only, allow_on_submit, no_copy), `signed_contract` (Attach, allow_on_submit), `remarks` (Small Text), `last_reminder_days` (Int, hidden, allow_on_submit, no_copy), `amended_from`.
- Produces: test helper `make_contract(employee: str, start_date, end_date, employment_type="Contract", submit=True, **kw) -> Document` in `test_employee_contract.py` (later tasks import it).

- [ ] **Step 1: Write failing tests** (`TestEmployeeContract(HRMSTestSuite)`; employee from `hrms.hr.doctype.attendance_request.test_attendance_request.get_employee`; ensure Employment Types "Contract" and "Probation" exist in `setUp`; delete the employee's contracts in `setUp`):
  - `test_contract_numbers_sequence`: three back-to-back submitted contracts → `contract_number` 1, 2, 3; a cancelled one is not counted for the next number.
  - `test_end_before_start_rejected`, `test_start_before_joining_rejected` → `frappe.ValidationError`.
  - `test_overlap_rejected` (Review Focus 1): submitted 2026-01-01→2026-03-31; new 2026-03-15→2026-06-30 → submit raises `frappe.ValidationError`. Touching ranges (next starts 2026-04-01) allowed.
  - `test_left_employee_rejected`: `frappe.db.set_value` employee status Left → insert raises.
  - `test_submit_sets_active`: status `Active` after submit.
  - `test_duration_months_sets_end_date`: insert with `start_date=2026-01-01, duration_months=3` and no `end_date` → `end_date == 2026-03-31`.
- [ ] **Step 2: Run** `bench --site otieno.local run-tests --module upande_hr.upande_hr.doctype.employee_contract.test_employee_contract` → FAIL.
- [ ] **Step 3: Implement** `EmployeeContract(Document)` with `before_insert` (contract_number = non-cancelled count + 1), `validate` (end_date from duration if missing: `add_days(add_months(start, n), -1)`; date rules; Left check; overlap check against docstatus=1 contracts of same employee excluding self), `on_submit` (`db_set("status", "Active")`).
- [ ] **Step 4: Migrate, re-run** → PASS.
- [ ] **Step 5: Commit** `feat: add Employee Contract doctype`

---

### Task 3: Employee sync, Renew, Confirm, Cancel

**Files:**
- Create: `upande_hr/contracts/__init__.py`, `upande_hr/contracts/sync.py`
- Modify: `employee_contract.py`, `test_employee_contract.py`

**Interfaces:**
- Consumes: `make_contract` (Task 2).
- Produces: `upande_hr.contracts.sync.sync_employee(employee: str) -> None` — latest submitted non-cancelled contract by `contract_number`; no-op if none. Latest Confirmed → `final_confirmation_date=confirmation_date`, `employment_type=confirmed_employment_type`, `contract_end_date=None`. Otherwise → `contract_end_date=end_date`, `employment_type=employment_type`, `final_confirmation_date=None`.
- Produces whitelisted: `upande_hr.upande_hr.doctype.employee_contract.employee_contract.make_renewal(source_name: str) -> dict` (unsaved doc dict: same employee/employment_type, `previous_contract=source_name`, `start_date=end_date+1`; requires `create` permission; throws if source isn't Active or employee has a Confirmed contract).
- Produces whitelisted: `...employee_contract.confirm_as_permanent(contract: str, confirmation_date: str, employment_type: str) -> None` (requires `submit` permission on the contract; both args required; contract must be employee's latest submitted and Active/Expired).
- Controller additions: `validate` rejects new contract when employee has a Confirmed contract; `on_submit` marks `previous_contract` Renewed if Active, then `sync_employee`; `on_cancel` sets status Cancelled, restores previous (Active if `end_date >= today` else Expired) when it is Renewed, then `sync_employee`.

- [ ] **Step 1: Write failing tests:**
  - `test_submit_syncs_employee`: Employee `contract_end_date` == contract end, `employment_type` == contract type.
  - `test_renewal_marks_previous_renewed`: `make_renewal(c1)` → start == c1.end+1; insert+submit → c1 status Renewed, employee end date == c2.end.
  - `test_confirm_sets_employee`: `confirm_as_permanent(c2, "2026-07-01", "Full-time")` (test `setUp` ensures Employment Type "Full-time" exists) → c2 status Confirmed, `confirmed_employment_type` "Full-time"; Employee `final_confirmation_date` 2026-07-01, `employment_type` "Full-time", `contract_end_date` None.
  - `test_confirm_requires_employment_type`: empty type → raises.
  - `test_no_contract_after_confirmed`: after confirm, new contract insert raises; `make_renewal` raises.
  - `test_cancel_latest_restores_previous` (Review Focus 2): c1, renew c2, cancel c2 → c1 Active (or Expired if past), employee end date == c1.end.
  - `test_cancel_confirmed_restores_previous`: c1, renew c2, confirm c2, cancel c2 → c1 status restored (Active/Expired by date), Employee `contract_end_date == c1.end_date`, `employment_type == c1.employment_type`, `final_confirmation_date` None.
  - `test_cancel_only_contract_leaves_employee`: single c1 submitted then cancelled → Employee fields unchanged from after-submit values (no contracts remain → no-op).
- [ ] **Step 2: Run** module tests → new tests FAIL.
- [ ] **Step 3: Implement** `sync.py` and controller/whitelisted methods per Interfaces.
- [ ] **Step 4: Re-run** → PASS.
- [ ] **Step 5: Commit** `feat: sync Employee from contracts; renew, confirm and cancel flows`

---

### Task 4: Form buttons and Employee connections

**Files:**
- Create: `upande_hr/upande_hr/doctype/employee_contract/employee_contract.js`, `upande_hr/overrides/employee_dashboard.py`
- Modify: `upande_hr/hooks.py` (`override_doctype_dashboards = {"Employee": "upande_hr.overrides.employee_dashboard.get_dashboard_data"}`)

**Interfaces:**
- Consumes: `make_renewal`, `confirm_as_permanent` (Task 3).
- Produces: `get_dashboard_data(data: dict) -> dict` — appends `{"label": _("Contracts"), "items": ["Employee Contract"]}` to `data["transactions"]` (keeps existing entries).

- [ ] **Step 1: Write failing test** `test_dashboard_includes_contracts` in `test_employee_contract.py`: `frappe.get_meta("Employee").get_dashboard_data()` transactions contain "Employee Contract".
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** dashboard override + JS: `duration_months`/`start_date` change sets `end_date`; on submitted Active doc with `frappe.model.can_create`: **Renew** button → `frappe.model.open_mapped_doc` style via `make_renewal`; on submitted Active/Expired doc with `frm.perm[0].submit`: **Confirm as Permanent** dialog (Confirmation Date default `end_date + 1`, Employment Type Link reqd, no default) → `confirm_as_permanent`, then `frm.reload_doc()`. List view indicator by status (builder's choice of colours).
- [ ] **Step 4: Migrate + clear-cache, re-run** → PASS. Manual check in browser on otieno.local: create → submit → Renew → Confirm; Employee Connections shows Contracts.
- [ ] **Step 5: Commit** `feat: contract form actions and Employee connections`

---

### Task 5: Expiry job and reminders

**Files:**
- Create: `upande_hr/contracts/reminders.py`, `upande_hr/contracts/test_reminders.py`
- Modify: `upande_hr/hooks.py` (`scheduler_events = {"daily": ["upande_hr.contracts.reminders.run_daily"]}`)

**Interfaces:**
- Produces:
  - `due_point(days_left: int, points: list[int], last_sent: int | None) -> int | None` — smallest `p` in points with `p >= days_left`; `None` if `days_left < 0`, no such `p`, or `last_sent is not None and p >= last_sent`.
  - `mark_expired_contracts(on_date=None) -> None` — Active, docstatus 1, `end_date < on_date` → Expired.
  - `get_recipients(contract) -> list[str]` — enabled users (not Guest/Administrator, with email) having any configured Role (`Has Role`) or configured Role Profile (either `User.role_profile_name` or a `User Role Profile` row in `User.role_profiles` — v16 has both); plus reporting manager's `user_id` if setting on. Role/profile users with Company User Permissions (`User Permission` allow=Company) only kept if `contract.company` is among them; reporting manager exempt.
  - `send_contract_reminders(on_date=None) -> None` — no-op unless enabled; for each Active submitted contract of an Active employee: compute `due_point`; if not None and recipients non-empty → `frappe.sendmail` (subject `Contract ending in {days_left} days: {employee_name} ({employee}), contract #{contract_number}`, `days_left == 0` → `Contract ends today: ...`; `reference_doctype/name` set) + one Notification Log (`type: "Alert"`, `document_type`/`document_name` = contract) per recipient; then `db_set("last_reminder_days", p)`. Even with no recipients, `last_reminder_days` is still set.
  - `run_daily() -> None` — `mark_expired_contracts()` then `send_contract_reminders()`.

- [ ] **Step 1: Write failing tests** (`TestContractReminders(HRMSTestSuite)`):
  - `test_due_point`: `due_point(20,[30,14,7,0],None)==30`; `(14,...,30)==14`; `(14,...,14) is None`; `(5,...,30)==7` (missed days — Review Focus 3); `(-1,...,None) is None`; `(40,...,None) is None`.
  - `test_mark_expired`: Active contract ending yesterday → Expired; ending today stays Active.
  - `test_recipients_role_and_profile` (Review Focus 4): users A (role X), B (role profile P), C (role X, disabled), D (role X, Company permission on other company), E (role X, Company permission on contract company); settings recipients Role X + Role Profile P → `{A, B, E}`.
  - `test_reporting_manager_added`: setting on, employee `reports_to` has user → included even with Company permission elsewhere.
  - `test_send_once_per_point`: settings enabled, points 30/14/7/0, recipient role X; contract ending in 10 days → one Email Queue + Notification Log, `last_reminder_days==14`; run again same day → no new Email Queue rows.
  - `test_disabled_sends_nothing`.
- [ ] **Step 2: Run** `bench --site otieno.local run-tests --module upande_hr.contracts.test_reminders` → FAIL.
- [ ] **Step 3: Implement** per Interfaces; email body as an inline Jinja string in `reminders.py` (employee, company, department, contract #, type, start, end, days left, link via `get_url_to_form`).
- [ ] **Step 4: clear-cache, re-run** → PASS. Confirm job registered: `bench --site otieno.local mariadb -e "select method from \`tabScheduled Job Type\` where method like 'upande_hr.contracts%'"` → 1 row after migrate.
- [ ] **Step 5: Commit** `feat: daily contract expiry marking and reminders`

---

### Task 6: Backfill existing employees

**Files:**
- Create: `upande_hr/contracts/backfill.py`, `upande_hr/contracts/test_backfill.py`, `upande_hr/patches/backfill_employee_contracts.py`
- Modify: `upande_hr/patches.txt` (under `[post_model_sync]`: `upande_hr.patches.backfill_employee_contracts`), `upande_hr/install.py` (`after_install` also calls backfill)

**Interfaces:**
- Produces: `backfill_contracts() -> dict` returning `{"created": [names], "skipped": [(employee, reason)]}`. Rules from spec §7: Active employees with `contract_end_date` and zero Employee Contracts (any docstatus); type = employee.employment_type, else "Contract" if exists, else skip; skip if end < joining; `remarks="Auto-created from Employee Contract End Date"`; submit; if end < today then status Expired. Prints a summary.
- Patch module exposes `execute()` calling `backfill_contracts()`.

- [ ] **Step 1: Write failing tests:**
  - `test_backfill_creates_contract`: employee with end date in future, no contracts → one submitted contract #1, start = joining, status Active.
  - `test_backfill_past_end_is_expired`.
  - `test_backfill_idempotent` (Review Focus 5): run twice → still one contract.
  - `test_backfill_skips_without_type`: no employment_type and "Contract" type absent (rename within test, rolled back) → in `skipped`.
  - `test_backfill_skips_end_before_joining`.
- [ ] **Step 2: Run** `bench --site otieno.local run-tests --module upande_hr.contracts.test_backfill` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Re-run** → PASS; `bench --site otieno.local migrate` runs the patch without error.
- [ ] **Step 5: Commit** `feat: backfill contract #1 for employees with an existing contract end date`

---

### Task 7: Uninstall cleanup and end-to-end verification

**Files:**
- Modify: `upande_hr/install.py` (`before_uninstall`, `after_uninstall`)

**Interfaces:**
- Consumes: existing `before_uninstall` (custom fields + column drop).
- `before_uninstall` performs NO writes and NO DDL (Frappe runs it even for `--dry-run`); it only records which custom-field columns to drop. All destructive work happens in `after_uninstall`, and only when `upande_hr` is no longer in installed apps (a real uninstall). It deletes app-generated records (Notification Log, Email Queue + recipients, Scheduled Job Type/Log, Custom DocPerm, Property Setter, File, Version, Comment, ToDo, DocShare, naming Series, Error Log), drops the custom columns, then calls `frappe.db.commit()` because `remove_app` commits before `after_uninstall` and `bench` does not commit afterwards. (Doctypes/tables/single values are dropped by `remove_app` itself.)

- [ ] **Step 1: Write failing test** `test_real_uninstall_cleans_up` / `test_dry_run_uninstall_changes_nothing` in `contracts/test_reminders.py`: create a Notification Log for a contract; stub `frappe.db.sql_ddl` and `frappe.db.commit`; call `before_uninstall()` then `after_uninstall()` (patch the installed-apps check); assert Notification Log gone, Scheduled Job Type count for `upande_hr.%` == 0; rollback.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run all app tests**: `bench --site otieno.local run-tests --app upande_hr` → all PASS.
- [ ] **Step 5: Uninstall verification**: do NOT run `bench uninstall-app` / `remove-app` in any form. Frappe runs `before_uninstall` and `after_uninstall` even on `--dry-run`, which can destroy data. Verify via the stubbed tests in Step 1 only.
- [ ] **Step 6: Commit** `feat: remove contract artifacts on uninstall`
