# Compassionate Leave: rebuild in upande_hr

## Problem

Karen Roses employees apply for Compassionate Leave through their Annual
Leave application (checking an "Is Compassionate?" box) rather than picking
Compassionate Leave directly as the leave type, so the same days get deducted
from both their Annual Leave and Compassionate Leave balances in one
submission.

An implementation of this already exists in `upande_kaitet`
(`overrides/leave_application.py` + `custom/leave_application.json` + two
custom doctypes), but it has real gaps found by inspection against the live
site:

- The checkbox and the Python logic both gate on `leave_type == "Annual
  Leave"` only — `company` is never checked anywhere, so today this fires for
  any company, not just Karen Roses.
- A custom `Compassionate Leave Tracker` doctype (+ `Compassionate Leave
  Application` child table) exists to hold `days_used`/`days_remaining`, but
  no code ever computes those fields — only the child rows get maintained.
  Zero tracker records exist in the live DB; this path has never actually run
  against real data.
- The 12-day cap is hardcoded in Python (`MAX_COMPASSIONATE_DAYS = 12`),
  disconnected from the tracker doctype's own (also hardcoded, also unused)
  `total_entitlement` default.
- `"Compassionate Leave"` is a hardcoded string, not looked up.
- `custom_compassionate_balance_note` exists on the form but is never
  written to — the informational message goes out as a comment/toast instead.

Separately: the live site already has a `Compassionate Leave` Leave Type with
a Leave Policy allocating 12 days per policy period, and at least one Karen
Roses employee has an active Leave Policy Assignment referencing it — the
same mechanism that drives Sick Leave. Renewal already happens whenever HR
reassigns the policy at the end of a period; this is not something the
customization needs to build.

## Desired behavior

| Condition | Outcome |
|---|---|
| `leave_type != "Annual Leave"` | Checkbox hidden. No compassionate logic runs. |
| `leave_type == "Annual Leave"`, `company != "Karen Roses"` | Checkbox hidden. |
| `leave_type == "Annual Leave"`, `company == "Karen Roses"` | Checkbox visible. |
| Checkbox checked, requested days ≤ employee's current Compassionate Leave balance | Submission proceeds. Annual Leave is deducted normally (unchanged core behavior — already `allow_negative: 1`, so it warns rather than blocks if Annual goes negative). A second, mirrored `Leave Ledger Entry` deducts the same number of days from Compassionate Leave. `custom_compassionate_balance_note` is populated with the resulting Annual and Compassionate balances. |
| Checkbox checked, requested days > employee's current Compassionate Leave balance | Rejected — matches `Compassionate Leave`'s existing `allow_negative: 0` (same as Sick Leave's precedent). The balance checked is the employee's *actual current* Leave Policy Assignment allocation, not a hardcoded number. |
| Compassionate Leave Application cancelled | The mirrored Compassionate Leave ledger entry is cancelled too. Annual Leave's own ledger reversal is unchanged core behavior. |

No new custom doctype. "Days used" / "days remaining" for Compassionate Leave
is answered by HRMS's own leave balance query against the existing Leave
Type/Policy/Allocation — the same query every other leave type already uses.

## Implementation

**New files in `upande_hr`:**
- `upande_hr/upande_hr/custom/leave_application.json` — `custom_is_compassionate`
  (Check, "Is Compassionate?", `depends_on:
  eval:doc.leave_type=="Annual Leave" && doc.company=="Karen Roses"`) and
  `custom_compassionate_balance_note` (Small Text, read-only), both `module:
  "Upande Hr"`, `sync_on_migrate: 1` — same ownership pattern used for every
  other re-homed field this session.
- `upande_hr/upande_hr/overrides/leave_application.py` — `class
  CustomLeaveApplication(LeaveApplication)`:
  - `_is_compassionate()`: `self.leave_type == "Annual Leave" and self.company
    == "Karen Roses" and self.get("custom_is_compassionate")`.
  - `validate()`: if compassionate, look up the employee's current
    Compassionate Leave balance via HRMS's `get_leave_balance_on` and throw if
    `total_leave_days` exceeds it; otherwise defer to the existing
    validation subset the old override used (skips
    `validate_applicable_after`, carried over unchanged — not something this
    round is revisiting). Non-compassionate applications are untouched
    (`super().validate()`).
  - `on_submit()`: `super().on_submit()` first (handles the normal Annual
    Leave ledger entry unchanged), then if compassionate: create and submit a
    second `Leave Ledger Entry` against `Compassionate Leave` for
    `-self.total_leave_days`, and write both resulting balances into
    `custom_compassionate_balance_note`.
  - `on_cancel()`: `super().on_cancel()`, then if compassionate: find and
    cancel the matching Compassionate Leave `Leave Ledger Entry`.
- Wired via `override_doctype_class` in `upande_hr/upande_hr/hooks.py`
  (same mechanism already used there for `Compensatory Leave Request`).

**Removed from `upande_kaitet`:**
- `custom_is_compassionate` / `custom_compassionate_balance_note` (+ their
  property setters, + the stale Leave Application → Compassionate Leave
  Tracker link) from `custom/leave_application.json`.
- The `Compassionate Leave Tracker` and `Compassionate Leave Application`
  doctypes, entirely (zero live records — confirmed via direct query before
  removal).
- The `"Leave Application": "...CustomLeaveApplication"` entry from
  `override_doctype_class` in `upande_kaitet/hooks.py`.
- A one-time patch in `upande_kaitet` deletes the resulting stale Custom
  Field / Property Setter DB rows and drops the two orphaned doctypes —
  same pattern as the Material Request field cleanup earlier this session.

## Out of scope

- Reconsidering the tenure bypass (`validate_applicable_after`) inherited
  from the old override — carried over as-is.
- Making Compassionate Leave directly selectable as its own leave type
  (considered and dropped during design).
- Any change to how Leave Policy Assignment renewal itself works — that's
  existing HR process, not something this customization touches.
