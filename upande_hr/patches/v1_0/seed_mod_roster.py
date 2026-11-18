from upande_hr.attendance.mod_roster import get_settings, seed_altura_mod_groups, seed_settings


def execute():
	"""Store the MOD Roster defaults. Creates Altura's groups only if the roster is
	already switched on (it ships off, so normally this only stores defaults; HR seeds
	the groups with seed_altura_mod_groups after reviewing a dry run)."""
	import frappe

	if not frappe.get_meta("HR Settings").has_field("custom_mod_duty_weekday"):
		from frappe.utils.fixtures import sync_fixtures

		sync_fixtures("upande_hr")
		frappe.clear_cache(doctype="HR Settings")

	seed_settings()
	if not get_settings().enabled:
		return
	result = seed_altura_mod_groups(dry_run=1)
	if not result["problems"]:
		seed_altura_mod_groups(dry_run=0)
