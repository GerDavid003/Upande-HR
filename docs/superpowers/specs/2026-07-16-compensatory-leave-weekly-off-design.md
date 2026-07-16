# Compensatory Leave Request: skip attendance check for weekly-off holidays

## Problem

HRMS's `Compensatory Leave Request` doctype requires two things to hold for every
day in `work_from_date`..`work_end_date` before it lets an employee submit a
request:

1. `validate_holidays()` — every day must be a holiday (weekly-off or regular)
   on the employee's assigned Holiday List.
2. `validate_attendance()` — every day must have a submitted `Attendance`
   record with status Present / Work From Home / Half Day.

This means an employee who worked on their own weekly-off day cannot claim
compensatory leave unless someone has separately logged an Attendance record
for that day — which typically doesn't happen for weekly-off days, since
attendance isn't normally tracked on days nobody is expected to work.

## Desired behavior

| Day in range is... | Attendance present? | Outcome |
|---|---|---|
| Not a holiday at all | — | Rejected (unchanged — `validate_holidays` already blocks this) |
| A holiday, not the employee's weekly-off | Yes | Accepted (unchanged) |
| A holiday, not the employee's weekly-off | No | **Rejected** (unchanged) |
| A holiday **and** the employee's weekly-off | Yes | Accepted (unchanged) |
| A holiday **and** the employee's weekly-off | No | **Accepted — new behavior** |

The bypass only applies when **every** day in the requested range is the
employee's weekly-off. A mixed range (e.g. one weekly-off day plus one regular
public holiday) still requires attendance for all days, i.e. falls through to
the existing, unmodified check.

When the bypass fires, a note is appended to the request's existing `reason`
field (Small Text) explaining why attendance wasn't required, so HR reviewers
don't have to cross-reference the Holiday List manually. The append is
idempotent — re-saving the same request does not duplicate the note.

This is a customization of the `upande_hr` app and must not require editing
`hrms` source, so it keeps working across HRMS updates.

## Mechanism: `override_doctype_class`

Frappe lets an app declare a controller class that Frappe instantiates in
place of the original, provided it subclasses the original (Frappe enforces
this with `issubclass()` and throws otherwise). This is the established
convention already used in this bench — `upande_kaitet` and `upande_webshop`
both override doctype controllers (`Item Price`, `Leave Application`, etc.)
this way today.

Two alternatives were considered and rejected:

- **`doc_events` (`validate`) hook** — doesn't work. Hooks run *alongside* a
  doctype's own `validate()`; they cannot stop
  `CompensatoryLeaveRequest.validate()` from calling its own
  `self.validate_attendance()`. There's no flag in that method to short-circuit
  from outside.
- **Raw monkeypatching** (`CompensatoryLeaveRequest.validate_attendance = ...`
  at import time) — achieves the same result but bypasses Frappe's own
  override bookkeeping: no `issubclass` safety check, and no `bench migrate`
  warning if a future app collides on the same doctype override. Strictly
  worse than the hook mechanism for no benefit.

No other installed app currently overrides `Compensatory Leave Request`, so
there is no override collision today. (Note: `Item Price` already has a
collision between `upande_kaitet` and `upande_webshop` — unrelated to this
change, not addressed here.)

## Implementation

New files in `upande_hr`:

- `upande_hr/overrides/__init__.py` — empty
- `upande_hr/overrides/compensatory_leave_request.py`:

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

`get_holiday_list_for_employee` is imported from
`erpnext.setup.doctype.employee.employee` — the same import HRMS's own
`hr/utils.py` uses — because that's the hook-dispatching entry point
(`employee_holiday_list` hook) that correctly resolves the employee's
assigned Holiday List rather than querying `Employee.holiday_list` directly.

`upande_hr/hooks.py` addition:

```python
override_doctype_class = {
    "Compensatory Leave Request": "upande_hr.overrides.compensatory_leave_request.CustomCompensatoryLeaveRequest"
}
```

### Why this is safe to layer on top of existing validation

`validate()` on `CompensatoryLeaveRequest` calls `validate_holidays()` before
`validate_attendance()`. By the time our overridden `validate_attendance()`
runs, `validate_holidays()` has already confirmed every day in the range is a
valid holiday (weekly-off or otherwise) for the employee — so
`is_weekly_off_request()` only has to decide *which kind* of holiday it is,
not re-derive holiday-ness from scratch.

### Operational note

After deploying this change, sites need `bench migrate` (clears the Redis
`app_hooks` cache) followed by a worker restart (`bench restart`) — a
long-running gunicorn/worker process holds the previously resolved controller
class in memory (`frappe.controllers[site][doctype]`) until restarted, so
`bench migrate` alone is not sufficient to pick up a *new* `override_doctype_class`
entry on an already-running process.

## Testing plan

On `otieno.local`, using a real Employee with an assigned Holiday List:

1. Request spanning a single day that is both a holiday and the employee's
   weekly-off, no Attendance record — expect: accepted, `reason` gets the
   auto-note appended.
2. Request spanning a day that is a regular public holiday (not weekly-off),
   no Attendance record — expect: rejected, same as current behavior
   (regression check).
3. Request spanning a day that is a regular public holiday, with a valid
   Attendance record — expect: accepted, unchanged.
4. Save the weekly-off request (case 1) twice — expect: note appears once in
   `reason`, not duplicated.

## Out of scope

- Mixed-range requests (part weekly-off, part regular holiday) — always fall
  through to the existing attendance check, per explicit confirmation.
- Resolving the pre-existing `Item Price` override collision between
  `upande_kaitet` and `upande_webshop`.
- Any UI/reporting changes (e.g. a dedicated filter for "weekly-off exempted"
  requests) beyond the `reason` field note.
