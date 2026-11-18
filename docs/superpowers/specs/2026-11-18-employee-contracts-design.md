# Employee Contracts & Expiry Reminders — Design

Date: 2026-11-18 · App: `upande_hr` · Module: `Upande Hr` · Dev site: `otieno.local` (my-bench)

## Intent

Most Upande clients hire people as temporary workers, then move them through a chain of
fixed-term contracts before confirming them as permanent. Typical path: 3-month contract →
3-month contract → confirmed; some clients add a 2-month probation contract as a third step.
The number of contracts and their lengths vary per client and per employee.

Today Employee only has single-value fields (`contract_end_date`, `scheduled_confirmation_date`,
`final_confirmation_date`, `employment_type`). Every renewal overwrites the last, history is
lost, and nothing warns HR before a contract lapses. HR needs (1) a history of each employee's
contracts, (2) a clean way to renew or confirm, and (3) reminders before each contract expires,
sent to configurable roles / role profiles.

## Goals

- Record every contract an employee has as its own document, in sequence.
- One-click **Renew** (next contract) and **Confirm as Permanent** from a running contract.
- Keep Employee's standard fields (`contract_end_date`, `employment_type`,
  `final_confirmation_date`) in sync automatically — no double entry.
- New single doctype **Upande HR Settings**, tabbed like HRMS `HR Settings`; first tab
  configures contract-expiry reminders: the set points (days before expiry) and recipients
  (Roles and/or Role Profiles).
- Reminders at each configured point before a contract's end date.
- Everything is withdrawn cleanly when `upande_hr` is uninstalled (standing rule).

## Non-goals (for now)

- Preset contract "paths" per company (e.g. 3+3+2 template). Each renewal chooses its own
  length; presets can come later.
- Periodic digest emails (daily/weekly list). Possible later addition.
- Contract letter print format beyond Frappe's default print view.
- Approval workflow and role design — roles/permissions are configured per client at deployment.
- Payroll / salary-structure changes on renewal.

## Anti-goals

- Must not leave Employee's standard fields stale or contradicting the latest contract.
- Must not send the same reminder twice, or silently skip a reminder because the scheduler
  missed a day.
- Must not email HR users about companies they have no access to.
- Must not leave orphan records, columns, scheduled jobs or templates after uninstall.

## Approaches considered

| | Approach | Trade-off | Verdict |
|---|---|---|---|
| A | Child table "contract history" on Employee | Simple, all on one form; no submit/audit trail, no cross-employee list of expiring contracts without a custom report, weak renew/confirm flow | Rejected |
| **B** | **Separate submittable `Employee Contract` doctype linked to Employee** (same pattern as HRMS Employee Promotion/Transfer) | Slightly more to build; gives list/filter of expiring contracts, audit trail, print view, natural Renew/Confirm actions | **Chosen** (user accepted recommendation) |

Reminder frequency — user chose **reminders at set points before expiry** over a periodic digest.

## Design

### 1. `Employee Contract` (submittable doctype, module Upande Hr)

Naming: `HR-CON-.YYYY.-.#####`

Fields:
- `employee` (Link Employee, reqd), `employee_name` (fetch, read-only), `company` (fetch,
  read-only), `department` (fetch, read-only)
- `contract_number` (Int, read-only) — sequence per employee: 1, 2, 3 … computed on insert as
  (count of non-cancelled contracts for that employee) + 1
- `employment_type` (Link Employment Type, reqd) — e.g. Contract, Probation
- `start_date` (Date, reqd), `duration_months` (Int, optional helper), `end_date` (Date, reqd).
  Entering `duration_months` sets `end_date = start_date + N months − 1 day` client-side;
  `end_date` remains editable.
- `previous_contract` (Link Employee Contract, read-only)
- `status` (Select, read-only, allow_on_submit): Draft / Active / Renewed / Confirmed /
  Expired / Cancelled
- `confirmation_date` (Date, read-only, allow_on_submit) — set when confirmed permanent
- `confirmed_employment_type` (Link Employment Type, read-only, allow_on_submit) — the permanent
  type chosen in the Confirm dialog, stored so Employee can be re-synced deterministically
- `signed_contract` (Attach), `remarks` (Small Text)
- `last_reminder_days` (Int, hidden, allow_on_submit, no_copy) — reminder bookkeeping (§4)

Validation:
- `end_date >= start_date`; `start_date >= employee.date_of_joining`.
- No overlap with another submitted, non-cancelled contract of the same employee.
- Employee must not be `Left`.
- Employee must not already have a Confirmed (non-cancelled) contract — once confirmed
  permanent, no further contracts can be created (Renew button hidden too).

Lifecycle:
- **Submit** → status Active. If `previous_contract` set and that contract is Active, mark it
  Renewed. Sync Employee (§3).
- **Renew** button (submitted + Active): opens a new draft with same employee/type,
  `previous_contract` = this, `start_date` = this.end_date + 1 day.
- **Confirm as Permanent** button (only on the employee's latest submitted contract, status
  Active or Expired): dialog asks Confirmation Date (default this.end_date + 1) and Employment
  Type (no default — required; the user picks the client's own term, e.g. Full-time or
  Permanent). Sets
  status Confirmed, `confirmation_date`, `confirmed_employment_type`; syncs Employee (§3).
  Earlier contracts' statuses are untouched. A Confirmed contract gets no reminders and is
  ignored by the expiry job. Whitelisted server method; checks the caller's normal Frappe
  permission on the contract (`submit` right), not hard-coded roles.
- **Renew** is shown to anyone with `create` permission on Employee Contract.
- **Cancel** → status Cancelled; if it had renewed a previous contract, previous goes back to
  Active (or Expired if its end date has passed). Cancelling a Confirmed contract is not a
  separate action: confirmation is undone by cancelling that contract (amend to redo).
  Re-sync Employee from the latest remaining submitted contract.
- **Daily job** marks Active contracts whose `end_date < today` as Expired.

Permissions: **no role restrictions designed in.** The doctype ships with a single System
Manager permission row (Frappe needs at least one); each client's roles are granted at
deployment via Role Permission Manager. Code never checks role names — only Frappe permissions.

### 2. Employee form

- Connections dashboard on Employee gets an "Employee Contract" link (via
  `override_doctype_dashboards` hook — disappears with the app).
- No new Employee fields. Standard `contract_end_date`, `employment_type`,
  `final_confirmation_date` are kept in sync by §3.

### 3. Employee sync rules

Source of truth = the employee's latest submitted, non-cancelled contract (highest
`contract_number`).
- Latest is Active/Renewed/Expired → `employee.contract_end_date = end_date`,
  `employee.employment_type = contract.employment_type`, `final_confirmation_date` cleared
  only if it was set by a contract that's now cancelled.
- Latest is Confirmed → `employee.final_confirmation_date = confirmation_date`,
  `employee.employment_type = confirmed_employment_type`,
  `employee.contract_end_date` cleared.
- No contracts remain → leave Employee fields as they are (don't wipe manual data).
- Written with `frappe.db.set_value` on Employee (no full Employee save → avoids tripping
  unrelated Employee validations such as Reason for Exit).

### 4. Reminders

Daily scheduler job (`scheduler_events["daily"]`), runs only if enabled in settings.

For each Active, submitted contract whose employee is Active:
- `days_left = end_date − today`
- Configured points, e.g. `[30, 14, 7, 0]`. Due point = the smallest configured point `p`
  with `p >= days_left`.
- Send if a due point exists and (`last_reminder_days` is null or `p < last_reminder_days`);
  then set `last_reminder_days = p`. This sends each point once and catches up if the
  scheduler missed a day (only the most urgent missed point is sent, not a burst).
- Contracts with `days_left < 0` are not reminded (they get marked Expired).
- Renewal: a new contract starts with `last_reminder_days` null, so it gets its own reminders.
- A contract submitted late (e.g. 5 days left with points 30/14/7/0) gets the 7-day reminder on
  the next run — intended. Changing the points mid-contract applies from the next run.

Recipients:
- Union of enabled users having any configured **Role**, and enabled users whose **Role
  Profile** is any configured profile; plus the employee's reporting manager's user if
  "Also notify reporting manager" is ticked. Excludes Guest/Administrator/disabled users and
  users without an email.
- Company scoping: if a recipient has User Permissions on Company, they only receive
  reminders for contracts in those companies. Users without Company restrictions receive all. Only Company-level User Permissions are
  considered (Employee/Department-level ones are ignored for this). The reporting manager is
  exempt from scoping.

Delivery:
- One email per contract per point per recipient batch (`frappe.sendmail`, recipients list),
  subject e.g. "Contract ending in 14 days: Jane Doe (HR-EMP-0003), contract #2". Body: employee,
  company, department, contract number & type, start/end dates, days left, link to the
  contract. Body built in code (Jinja string in the app) — **no Email Template record**, so
  nothing orphaned on uninstall.
- Also a system notification (Notification Log, type Alert — exists in v16) per recipient,
  with `document_type`/`document_name` pointing at the contract, for the bell icon.

### 5. `Upande HR Settings` (single doctype, module Upande Hr)

Tabbed like HRMS HR Settings. Only tabs we actually build are added; first tab:

**Contracts** tab → section "Contract Expiry Reminders":
- `enable_contract_expiry_reminders` (Check)
- `contract_reminder_days` (Table → child doctype `Contract Reminder Day`: `days_before`
  Int, reqd, ≥ 0, unique within table). Defaults on install: 30, 14, 7, 0.
- `contract_reminder_recipients` (Table → child doctype `Contract Reminder Recipient`:
  `recipient_type` Select Role / Role Profile, reqd; `recipient` Dynamic Link on
  `recipient_type`, reqd). **No default recipients** — the client chooses at deployment.
- `notify_reporting_manager` (Check)
- Validation: if enabled, at least one day and at least one recipient (or reporting manager).

Permissions: System Manager row only; client grants others at deployment.

Default reminder points are written by an `after_install` hook (new `after_install` in existing
`upande_hr/install.py`) (and by a `post_model_sync` patch for sites
where the app is already installed) only if the settings are empty.

### 6. Uninstall (no orphans)

- All four doctypes (`Employee Contract`, `Upande HR Settings`, `Contract Reminder Day`,
  `Contract Reminder Recipient`) are in module Upande Hr → Frappe's `remove_app` deletes them,
  drops their tables and the single's values in `tabSingles`.
- Scheduler job, dashboard override and doc hooks are hook-based → gone with the app.
- No new Custom Fields on Employee → no columns to drop.
- `before_uninstall` additionally deletes app-generated records that would outlive the
  doctype: Notification Log entries whose `document_type = "Employee Contract"`, and
  Scheduled Job Type rows for this app's methods (Frappe normally cleans these on
  migrate, but delete explicitly).
- Data consequence (document in release notes): contract history is lost on uninstall;
  Employee's synced standard fields keep their last values (they're ERPNext's fields).

### 7. Backfill of existing employees (user decision)

For client sites where employees are already mid-contract: a one-time backfill creates and
submits contract #1 for each employee that has `status = Active`, a `contract_end_date`, and no
Employee Contract yet.
- `start_date = date_of_joining`, `end_date = contract_end_date`,
  `employment_type = employee.employment_type`, falling back to "Contract" if that exists, else
  the employee is skipped and listed in the output.
- Skipped (and logged) if `contract_end_date < date_of_joining` or required data is missing.
- If `end_date < today`, it is submitted then marked Expired (no reminders).
- `remarks = "Auto-created from Employee Contract End Date"`.
- Employee sync on these submits is a no-op in effect (same values).
- Runs from both `after_install` and a `post_model_sync` patch (patch runs once per site;
  the function itself is idempotent).
- Uninstall deletes these with the rest of the doctype; Employee's own fields keep their values.

## Constraints

- Frappe/ERPNext v16, HRMS 16.12.x (my-bench). Multi-company: 22 companies on the dev site.
- Server-side validation must not rely on browser-only `mandatory_depends_on` behaviour.
- Verification follows the bench's manual approach (temp script with frappe.init/connect,
  rollback; stub `frappe.db.sql_ddl` if testing DDL) unless `bench run-tests` works here.

## Calls I made (user to check)

- Doctype name **Employee Contract**; naming series `HR-CON-.YYYY.-.#####`.
- Default reminder points 30/14/7/0 days; no default recipients (user decision).
- Catch-up rule sends only the most urgent missed point.
- Company scoping via existing User Permissions on Company.
- Confirm dialog Employment Type has no default; user picks (user decision).
- No contracts after confirmation; undo confirmation by cancelling that contract.
- No hard-coded roles anywhere; permissions configured per client (user decision).
- Reporting manager is not company-scoped; only Company User Permissions scope recipients.
- Reminders also appear in the bell (Notification Log), not only email.

- Backfill employment-type fallback is "Contract"; employees without a usable type are skipped
  and listed rather than guessed.

## Left to the builder

- Exact email wording/layout; list view indicators & colours; form field layout/columns.
- Whether `duration_months` helper also lives server-side.
- Test structure.
