import frappe


def get_employee_dashboard(data=None):
	data = data or {}
	data.setdefault("transactions", [])
	data.setdefault("non_standard_fieldnames", {})

	data["transactions"].append(
		{
			"label": frappe._("Induction & Policies"),
			"items": ["Policy Acknowledgment", "Induction Session"],
		}
	)
	data["non_standard_fieldnames"]["Induction Session"] = "employee"
	return data
