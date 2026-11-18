import frappe
from frappe.utils import getdate, today

REMARKS = "Auto-created from Employee Contract End Date"
FALLBACK_TYPE = "Contract"


def backfill_contracts():
	"""Create contract #1 for Active employees that have a contract end date but no contracts."""
	created, skipped = [], []
	employees = frappe.get_all(
		"Employee",
		filters={"status": "Active", "contract_end_date": ["is", "set"]},
		fields=["name", "employment_type", "date_of_joining", "contract_end_date"],
	)
	for emp in employees:
		if frappe.db.exists("Employee Contract", {"employee": emp.name}):
			continue
		savepoint = "backfill_contract"
		frappe.db.savepoint(savepoint)
		try:
			employment_type = emp.employment_type
			if not employment_type:
				if frappe.db.exists("Employment Type", FALLBACK_TYPE):
					employment_type = FALLBACK_TYPE
				else:
					raise ValueError("No employment type and no 'Contract' Employment Type exists")
			if not emp.date_of_joining:
				raise ValueError("Employee has no date of joining")
			if getdate(emp.contract_end_date) < getdate(emp.date_of_joining):
				raise ValueError("Contract end date is before date of joining")

			doc = frappe.get_doc(
				{
					"doctype": "Employee Contract",
					"employee": emp.name,
					"employment_type": employment_type,
					"start_date": emp.date_of_joining,
					"end_date": emp.contract_end_date,
					"remarks": REMARKS,
				}
			)
			doc.insert(ignore_permissions=True)
			doc.submit()
			if getdate(emp.contract_end_date) < getdate(today()):
				doc.db_set("status", "Expired")
			created.append(doc.name)
		except Exception as e:
			frappe.db.rollback(save_point=savepoint)
			skipped.append((emp.name, str(e)))

	print(f"Employee contract backfill: {len(created)} created, {len(skipped)} skipped")
	for name, reason in skipped:
		print(f"  skipped {name}: {reason}")
	return {"created": created, "skipped": skipped}
