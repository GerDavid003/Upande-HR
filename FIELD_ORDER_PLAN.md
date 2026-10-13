# Employee field_order plan: Marginpar employee form feedback

Apply to the `Employee-main-field_order` Property Setter on **Marginpar Staging**
via MCP. Do not ship it from the app; see the note in `hooks.py`.

Applied and verified on the local site (`marginpar.localhost`) on 2026-10-12. The
notes below include what that run turned up.

## Before you apply

1. **Check for another app shipping an Employee field_order.** upande_agriculture
   (branch `live`) ships `custom/employee.json` with `sync_on_migrate: 1` and its own
   `Employee-main-field_order`, a 322-field list from another client. Every
   `bench migrate` deletes the site's field_order and re-inserts that one, so
   anything applied here is lost on the next deploy. The fix is on upande_agriculture
   branch `fix/remove-employee-field-order`
   (`0001-fix-stop-shipping-the-Employee-field_order-Property-.patch`). If staging
   runs that app, deploy the fix **before** applying this plan.
2. Deploy upande_hr and run `bench migrate`, so all 18 new Employee Custom Fields
   exist.
3. Read **both** of these:
   - `get_document("Property Setter", "Employee-main-field_order")`, the stored
     array.
   - The rendered field order: `get_doctype_info("Employee")` / `frappe.get_meta`.

   If the stored array has fewer entries than the doctype has fields, work from the
   **rendered** order instead. The missing fields are only placed by the
   insert_after fallback. Writing a short array back would leave them there, and
   they would move whenever the anchors shift. Locally the stored array had 154
   entries against 191 fields, including non-new ones like `basic_pay`,
   `union_member` and `custom_greenhouse`. The array written back listed all 191.

   **Pitfall:** the rendered position of a field that's missing from the stored
   array is only as good as its insert_after anchor. `custom_greenhouse`
   (upande_agriculture) is anchored on `custom_location`, which doesn't exist on
   Marginpar, so it renders at the very end of the form, after `connections_tab`.
   Copying that position into the array pins it there, which is what happened
   locally the first time. Before writing, check every field that renders after
   `connections_tab` and put it back where it belongs (see section 7).
4. Edit the array only as described below: insert the new fieldnames and move the
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

Check where `contract_end_date` actually is. Locally it had been sitting in the right
column, after `column_break_32`, and needed moving. If it already follows
`final_confirmation_date`, inserting the two new fields leaves it in the right place.

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

Once section 3 is applied, Attendance & Leaves opens directly with
`attendance_device_id`. That's correct, and no new Section Break is needed: a Tab
Break always starts its own implicit section in the form layout (`layout.js`
`make_tab` → `make_section`). The tab only showed the Next of Kin heading because
the Next of Kin fields were sitting inside it.

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
`shift_request_approver`) stay under Attendance & Leaves, in their existing order.
`holiday_list` also stays, beside Device ID (decided 2026-10-12). If staging has
other shift-related fields from upande_ta near `default_shift`, leave them where they
are unless told otherwise.

Resulting sequence locally, from the emergency contact block to the Salary tab:

```
emergency_contact_details, person_to_be_contacted, column_break_55, emergency_phone_number,
column_break_19, relation,
custom_next_of_kin_section, custom_next_of_kin_name, custom_next_of_kin_col_break_1,
custom_next_of_kin_contact, custom_next_of_kin_col_break_2, custom_next_of_kin_relationship,
attendance_and_leave_details, attendance_device_id, column_break_44, holiday_list,
approvers_section, expense_approver, leave_approver, column_break_45, shift_request_approver,
custom_shift_tab, custom_shift_section, default_shift, custom_shift_start_date, custom_shift_end_date,
salary_information
```

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

## 7. Company Details: Unit and Block (added 2026-10-13)

| Fieldname           | Type          | Place after         |
|---------------------|---------------|---------------------|
| `custom_greenhouse` | (existing, **move only if misplaced**) | `custom_category` |
| `custom_unit`       | Link → Unit   | `custom_greenhouse` |
| `custom_block`      | Link → Block  | `custom_unit`       |

Target, in the left column of Company Details:

```
... reports_to, custom_skilllevel, custom_category, custom_greenhouse, custom_unit, custom_block, column_break_18, ...
```

This was the site's original Greenhouse position before the local rebuild. If
staging already has `custom_greenhouse` in Company Details and its stored array is
complete, the two new fields land after it through insert_after, and adding them to
the array just makes that explicit. That adds 2 to the count check below.

## Check after applying

- If you worked from the rendered order: `len(new_array)` equals the rendered field
  count, and the rendered count is the same before and after. If you worked from a
  complete stored array: `len(new_array) == len(old_array) + 20` (18 from the form
  feedback, plus `custom_unit` and `custom_block`), since moves don't change the
  count.
- `set(old_order) <= set(new_array)`: nothing was dropped.
- Each fieldname appears exactly once.
- Clear the cache, reload an Employee, and check that Next of Kin is on Address &
  Contacts, the Shift tab sits between Attendance & Leaves and Salary, and Unit and
  Block are in Company Details.
- Nothing renders after `connections_tab`.
- Run `bench migrate`, then compare the stored array with what you wrote. If they
  differ, something is still syncing a field_order (see step 1). Locally, two
  migrates in a row left it unchanged.
