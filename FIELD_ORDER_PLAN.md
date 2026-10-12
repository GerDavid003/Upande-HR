# Employee field_order plan: Marginpar employee form feedback

Apply to the `Employee-main-field_order` Property Setter on **Marginpar Staging**
via MCP. Do not ship it from the app; see the note in `hooks.py`.

## Before you apply

1. Deploy this branch and run `bench migrate` first, so all 18 new Employee Custom
   Fields exist. Frappe ignores field_order entries that don't resolve to a field,
   but it's cleaner if they all resolve.
2. Run `get_document("Property Setter", "Employee-main-field_order")` and work on the
   full current array. Never rebuild it from scratch. The live array has fields from
   several apps that this repo can't see.
3. Edit the array only as described below: insert the new fieldnames and move the
   existing ones. Do not drop or reorder anything else.

All anchors are fieldnames. "After X" means immediately after X in the array.

## 1. Basic Details: Age

| Fieldname    | Type | Place after     |
|--------------|------|-----------------|
| `custom_age` | Int  | `date_of_birth` |

## 2. Joining (`employment_details` section): contract fields

Target sequence in the left column of the Joining section:

```
... final_confirmation_date, custom_contract_type, custom_contract_start_date, contract_end_date, column_break_32, ...
```

| Fieldname                    | Type      | Place after                  |
|------------------------------|-----------|------------------------------|
| `custom_contract_type`       | Link      | `final_confirmation_date`    |
| `custom_contract_start_date` | Date      | `custom_contract_type`       |
| `contract_end_date`          | (standard, **move**) | `custom_contract_start_date` |

`contract_end_date` already sits directly after `final_confirmation_date` in the
array, so inserting the two new fields leaves it in place. If it sits anywhere else
(for example in the right column after `column_break_32`), move it.

Full-width Contract History section, directly after the Joining section and before
Probation:

| Fieldname                         | Type          | Place after                       |
|-----------------------------------|---------------|-----------------------------------|
| `custom_contract_history_section` | Section Break | `date_of_retirement` (the last field before `custom_probation_section`) |
| `custom_contract_history`         | Table (read-only) | `custom_contract_history_section` |

## 3. Address & Contacts: Next of Kin, after Emergency Contact

**Required.** Without this, the section currently renders at the top of the
Attendance & Leaves tab. Its insert_after anchor, `relation`, is the last field on
its tab. Frappe's Section Break walk does not stop at a Tab Break, so it carries the
section past `attendance_and_leave_details`.

Insert this block after the last field of the `emergency_contact_details` section
(`relation` locally) and **before** `attendance_and_leave_details`:

| Fieldname                         | Type          | Place after                       |
|-----------------------------------|---------------|-----------------------------------|
| `custom_next_of_kin_section`      | Section Break | `relation`                        |
| `custom_next_of_kin_name`         | Data          | `custom_next_of_kin_section`      |
| `custom_next_of_kin_col_break_1`  | Column Break  | `custom_next_of_kin_name`         |
| `custom_next_of_kin_contact`      | Data (Phone)  | `custom_next_of_kin_col_break_1`  |
| `custom_next_of_kin_col_break_2`  | Column Break  | `custom_next_of_kin_contact`      |
| `custom_next_of_kin_relationship` | Select        | `custom_next_of_kin_col_break_2`  |

## 4. New Shift tab, after Attendance & Leaves

**Move** these three existing fields out of the `attendance_and_leave_details`
section, where they currently follow `holiday_list`:
`default_shift`, `custom_shift_start_date`, `custom_shift_end_date`.

Then insert this block after the last field of the Attendance & Leaves tab
(`shift_request_approver` locally), immediately **before** `salary_information`:

| Fieldname                 | Type                 | Place after               |
|---------------------------|----------------------|---------------------------|
| `custom_shift_tab`        | Tab Break            | last field of Attendance & Leaves tab (`shift_request_approver`) |
| `custom_shift_section`    | Section Break        | `custom_shift_tab`        |
| `default_shift`           | Link (HRMS, **move**) | `custom_shift_section`   |
| `custom_shift_start_date` | Date (**move**)      | `default_shift`           |
| `custom_shift_end_date`   | Date (**move**)      | `custom_shift_start_date` |

The approvers (`approvers_section`, `expense_approver`, `leave_approver`,
`shift_request_approver`) stay under Attendance & Leaves. If staging has other
shift-related fields from upande_ta near `default_shift`, leave them where they are
unless told otherwise.

## 5. Personal Details: Beneficiaries and Dependants

Directly after the existing Family Members table and before
`passport_details_section`:

| Fieldname                      | Type          | Place after                    |
|--------------------------------|---------------|--------------------------------|
| `custom_beneficiaries_section` | Section Break | `custom_family_members`        |
| `custom_beneficiaries`         | Table         | `custom_beneficiaries_section` |
| `custom_dependants_section`    | Section Break | `custom_beneficiaries`         |
| `custom_dependants`            | Table         | `custom_dependants_section`    |

## 6. Exit: Separation Type

| Fieldname                | Type | Place after               |
|--------------------------|------|---------------------------|
| `custom_separation_type` | Link | `resignation_letter_date` (now labelled "Separation Date") |

## Check after applying

- `len(new_array) == len(old_array) + 18`. There are 18 new fieldnames, and moves
  don't change the count. If staging's array already lists any of these fieldnames,
  adjust the count to match.
- `set(old_array) <= set(new_array)`: nothing was dropped.
- Each fieldname appears exactly once.
- Clear the cache, reload an Employee, and check that Next of Kin is on Address &
  Contacts and the Shift tab sits between Attendance & Leaves and Salary.
