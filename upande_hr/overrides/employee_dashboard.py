from frappe import _


def get_dashboard_data(data):
	data.setdefault("transactions", []).append({"label": _("Contracts"), "items": ["Employee Contract"]})
	return data
