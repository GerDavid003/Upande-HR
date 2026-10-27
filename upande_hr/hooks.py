app_name = "upande_hr"
app_title = "Upande Hr"
app_publisher = "Upande"
app_description = "HR customisations for Upande"
app_email = "otieno@upande.com"
app_license = "mit"

# Apps
# ------------------

# Bulk Overtime Entry (upande_ta) is read when checking for an overtime overlap on
# the same employee/date. Every read of it is still guarded with frappe.db.exists so
# the check degrades quietly rather than hard-failing.
required_apps = ["upande_ta"]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "upande_hr",
# 		"logo": "/assets/upande_hr/logo.png",
# 		"title": "Upande Hr",
# 		"route": "/upande_hr",
# 		"has_permission": "upande_hr.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/upande_hr/css/upande_hr.css"
# app_include_js = "/assets/upande_hr/js/upande_hr.js"

# include js, css files in header of web template
# web_include_css = "/assets/upande_hr/css/upande_hr.css"
# web_include_js = "/assets/upande_hr/js/upande_hr.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "upande_hr/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {"Leave Application": "public/js/leave_application.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "upande_hr/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "upande_hr.utils.jinja_methods",
# 	"filters": "upande_hr.utils.jinja_filters"
# }

# Fixtures
# ------------

# Filtered by name rather than by module: a module filter sweeps in every Custom Field
# anyone later tags to "Upande Hr", including ones this app never created.
#
# One Custom Field entry only. export_fixtures names the output file after the doctype
# (frappe.scrub) and opens it with "w", so a second {"doctype": "Custom Field"} block
# would silently overwrite this one on export. New Custom Fields go in the list below.
#
# The unprefixed statutory fields carried on main (national_id, tax_id, nssf_no, sha_no
# and custom_column_break_statutory) are deliberately NOT here — they duplicate the
# custom_-prefixed set below and must not ship to TSH.
fixtures = [
	{
		"doctype": "Custom Field",
		"filters": [
			[
				"name",
				"in",
				[
					"Attendance-custom_comp_off_override",
					"Attendance-custom_comp_off_request",
					# Employee statutory details, Personal Details tab. Ordered as the
					# section renders: section break, left column, column break, right
					# column. upande_ats anchors its Next of Kin section on
					# Employee-custom_sha_no, so this set has to ship intact.
					#
					# The anchor chain from here on is strictly linear - one dependant per
					# anchor - and every link after the first points at a Custom Field,
					# deliberately. Meta.sort_fields walks a Section Break or Column Break
					# forward from a *standard* anchor to the end of that section, and the
					# walk stops at a Section Break but not at a Tab Break, so such a field
					# anchored on the last field of a tab silently lands in the next tab.
					# custom_statutory_details anchored on place_of_issue did exactly that:
					# it walked past profile_tab and landed after bio, dragging the chain
					# into Profile. health_insurance_no is an HRMS Custom Field, not a
					# standard field, so the walk is skipped and the section stays put.
					"Employee-custom_statutory_details",
					"Employee-custom_national_id_no",
					"Employee-custom_kra_pin",
					"Employee-custom_column_break_7csev",
					"Employee-custom_nssf_no",
					"Employee-custom_sha_no",
					"Employee-custom_nationality",
					# Derived from date_of_joining by overrides/employee.py. Stored, not
					# virtual, so HR can filter and report on it.
					"Employee-custom_years_of_service",
					# Ethnicity sits next to Nationality. Sensitive personal data under
					# the Data Protection Act 2019, currently at permlevel 0.
					"Employee-custom_ethnicity",
					# Family Members, its own collapsible section so the Table does not
					# land inside someone else's two-column layout. Anchored on
					# Employee-custom_sha_no, which upande_hr ships itself - anchoring on
					# upande_ats' Next of Kin fields would be a dependency this app does
					# not declare in required_apps.
					"Employee-custom_family_members_section",
					"Employee-custom_family_members",
					# Salary tab. Its label was blanked by an Export Customizations pass
					# and is restored from here - see the note in fixtures/custom_field.json.
					"Employee-custom_appraisal_section",
					# Talent pool. Both fields sit at permlevel 1 on Employee, so the
					# permlevel-1 DocPerm rows added by
					# patches.v1_0.add_talent_pool_permlevel have to land or they are
					# invisible to everyone.
					"Employee-custom_talent_pool",
					"Employee-custom_talent_pool_designations",
					# upande_ats' candidate regret notification branches on
					# Job Applicant.custom_talent_pool, so this field must ship intact.
					# It was a hand-made Desk field on this site that no app shipped;
					# adopted here under its original name, type and anchor rather than
					# renamed, so that template keeps working on a fresh deploy.
					"Job Applicant-custom_talent_pool",
					"Job Applicant-custom_talent_pool_designations",
					# Another hand-made Desk field no app shipped, adopted under its
					# existing fieldname so the 13 flagged Employee records and the three
					# site Server Scripts that read it keep working. Re-anchored from
					# custom_group_name to department, where it belongs. A Check field, so
					# the Section Break walk above does not apply to it.
					"Employee-custom_is_hod",
					# MOD Off monthly allocation - see upande_hr/attendance/mod_off.py.
					"Employee-custom_is_mod",
					# Employee Details Update. custom_details_confirmed_on takes
					# custom_ethnicity's slot in the chain above and Family Members is
					# re-anchored onto it, keeping the chain one dependant per anchor.
					"Employee-custom_details_confirmed_on",
					"Employee-custom_alt_phone",
					"Employee-custom_mpesa_number",
					# Residence, a Section Break on the last standard field of Address, so
					# the walk stops at emergency_contact_details and it lands in between.
					"Employee-custom_residence_section",
					"Employee-custom_estate_village",
					"Employee-custom_nearest_town",
					"Employee-custom_landmark",
					"Employee-custom_column_break_residence",
					"Employee-custom_county",
					"Employee-custom_sub_county",
					"Employee-custom_postal_address",
					# Replaces the three single-contact standard fields, hidden by the
					# Property Setters below. A Table, not a break, so anchoring on the
					# standard relation field keeps it inside Emergency Contact.
					"Employee-custom_emergency_contacts",
					# Absent -> Annual Leave deduction and attendance labels, on an Upande
					# tab at the end of HR Settings.
					"HR Settings-custom_upande_tab",
					"HR Settings-custom_absent_deduction_section",
					"HR Settings-custom_enable_absent_al_deduction",
					"HR Settings-custom_mod_off_section",
					"HR Settings-custom_enable_mod_off_allocation",
					"HR Settings-custom_mod_off_leave_type",
					"HR Settings-custom_attendance_labels_section",
					"HR Settings-custom_attendance_label_map",
					"Leave Application-custom_auto_deducted",
					"Attendance-custom_attendance_label",
					# Away for Work on Attendance Request, built on the TSH UI and shipped
					# so other sites get it. The approver fields fetch from these two.
					# workflow_state is not here: the site's own workflow creates it.
					"Department-custom_hr_manager_approver",
					"Department-custom_hod_approver",
					"Attendance Request-custom_designation",
					"Attendance Request-custom_assignment_section",
					"Attendance Request-custom_contact_person",
					"Attendance Request-custom_contact_phone",
					"Attendance Request-custom_assignment_col",
					"Attendance Request-custom_departure_time",
					"Attendance Request-custom_expected_return_time",
					"Attendance Request-custom_confirmation_section",
					"Attendance Request-custom_declaration_html",
					"Attendance Request-custom_declaration_ack",
					"Attendance Request-custom_approval_section",
					"Attendance Request-custom_is_hod_request",
					"Attendance Request-custom_hod_approver",
					"Attendance Request-custom_hr_approver",
					# Live anchors this on custom_is_hod_request alongside
					# custom_hod_approver; re-anchored to keep the chain linear.
					"Attendance Request-custom_hod_approved_by",
					"Attendance Request-custom_hod_approved_on",
					"Attendance Request-custom_approval_col",
					"Attendance Request-custom_hr_approved_by",
					"Attendance Request-custom_hr_approved_on",
				],
			]
		],
	},
	# No Workflow fixture. Workflows are managed on each site's UI and a deploy must never
	# overwrite them; do not re-add one without an explicit decision to.
	#
	# The workflows built on the UI reference states and actions that do not ship with
	# Frappe, so these two masters still ship. "Open" is a stock Workflow State and is
	# deliberately not re-shipped. "Draft" is not stock - Frappe ships only Pending,
	# Approved and Rejected - so it ships here.
	{
		"doctype": "Workflow State",
		"filters": [
			[
				"name",
				"in",
				[
					"Under Investigation",
					"Hearing Scheduled",
					"Hearing Held",
					"Decision",
					"Appeal Requested",
					"Appeal Hearing",
					"Closed",
					"Draft",
					"Pending HR Review",
					"Pending Employee Acknowledgement",
					"Pending HOD Review",
					"Pending HRM Review",
					"Pending Group HR",
					"Pending Finance",
					# Stock (Approved) or already on the site (Cancelled), but with no style.
					# Shipped so the Charge Sheet workflow shows them green and red.
					"Approved",
					"Cancelled",
				],
			]
		],
	},
	{
		"doctype": "Workflow Action Master",
		"filters": [
			[
				"name",
				"in",
				[
					"Start Investigation",
					"Schedule Hearing",
					"Close - No Case",
					"Record Hearing",
					"Record Decision",
					"Close Case",
					"Request Appeal",
					"Schedule Appeal Hearing",
					"Submit",
					"Submit for HR Review",
					"Acknowledge",
					"Submit to HOD",
					"Submit to HRM",
					"Forward to HRM",
					"Forward to Employee",
					"Forward to Finance",
					"Cancel",
				],
			]
		],
	},
	# Charge Sheet permissions and the site's Charge Sheet workflow transitions name these.
	{
		"doctype": "Role",
		"filters": [["name", "in", ["People Development", "Finance Controller", "Group HR Manager"]]],
	},
	# One Notification per Charge Sheet workflow state. The workflow's own email alert is
	# off, so these are the only mails the sheet sends.
	{"doctype": "Notification", "filters": [["document_type", "=", "Charge Sheet"]]},
	# Hide Employee's standard single emergency contact in favour of
	# custom_emergency_contacts. The column breaks go too, so the table spans the section.
	# Existing values are moved into the table by patches.v1_0.move_emergency_contacts.
	{
		"doctype": "Property Setter",
		"filters": [
			[
				"name",
				"in",
				[
					"Employee-person_to_be_contacted-hidden",
					"Employee-column_break_55-hidden",
					"Employee-emergency_phone_number-hidden",
					"Employee-column_break_19-hidden",
					"Employee-relation-hidden",
				],
			]
		],
	},
	# A UI-made Query Report. "Appraisal Overview" is NOT here: that name is the stock
	# HRMS report, and ours ships as code, as Custom Appraisal Overview.
	{"doctype": "Report", "filters": [["name", "in", ["Appraisal Status"]]]},
]

# Doctype Class Overrides
# ------------------------

override_doctype_class = {
	"Compensatory Leave Request": "upande_hr.overrides.compensatory_leave_request.CustomCompensatoryLeaveRequest"
}

# Installation
# ------------

# before_install = "upande_hr.install.before_install"
after_install = "upande_hr.install.after_install"

# Tenure is an HRMS-shipped workspace, so the Case Management card cannot live in its
# JSON. It is re-asserted after every migrate instead: a workspace re-import from the
# shipped file replaces the row wholesale, which a one-shot patch would not survive.
after_migrate = "upande_hr.install.after_migrate"

# Uninstallation
# ------------

before_uninstall = "upande_hr.install.before_uninstall"
# after_uninstall = "upande_hr.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "upande_hr.utils.before_app_install"
# after_app_install = "upande_hr.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "upande_hr.utils.before_app_uninstall"
# after_app_uninstall = "upande_hr.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "upande_hr.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "upande_hr.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# Sexual-harassment grievances are visible only to HR Manager, Group HR Manager and
# System Manager. The query condition scopes list and report views; has_permission
# closes the direct-link route that a Permission Query alone leaves open.
permission_query_conditions = {
	"Employee Grievance": "upande_hr.overrides.employee_grievance.get_permission_query_conditions",
	# Employees see only the charge sheets raised against them.
	"Charge Sheet": "upande_hr.upande_hr.doctype.charge_sheet.charge_sheet.get_permission_query_conditions",
}

has_permission = {
	"Employee Grievance": "upande_hr.overrides.employee_grievance.has_permission",
	"Charge Sheet": "upande_hr.upande_hr.doctype.charge_sheet.charge_sheet.has_permission",
}

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Attendance": {
		# Runs after Attendance.validate(), so it gets the last word over
		# check_leave_record() reassigning status back to "On Leave".
		"validate": "upande_hr.overrides.attendance.reassert_comp_off_override"
	},
	"Employee": {
		# On validate rather than on the nightly job alone, so the figure is right the
		# moment a joining date is entered or corrected.
		"validate": "upande_hr.overrides.employee.set_years_of_service"
	},
	"Leave Application": {
		# No leave until this year's personal details are confirmed. A hook rather than a
		# Server Script so it ships with the app and does not need server_script_enabled.
		"before_insert": "upande_hr.upande_hr.doctype.employee_details_update.employee_details_update.gate_leave_application"
	},
	"Attendance Request": {
		# on_submit is the Approved transition; HRMS has created the Attendance by then.
		"on_submit": "upande_hr.attendance.labels.apply_attendance_label",
		"on_cancel": "upande_hr.attendance.labels.clear_attendance_label",
	},
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"daily": [
		"upande_hr.upande_hr.doctype.disciplinary_warning.disciplinary_warning.lapse_expired_warnings",
		"upande_hr.overrides.employee.refresh_years_of_service",
	],
	"cron": {
		# Sunday 23:59 - closes out the Monday-Sunday week. Gated on
		# HR Settings.custom_enable_absent_al_deduction inside the job.
		"59 23 * * 0": ["upande_hr.attendance.absent_deduction.run_weekly"],
		# 1st of the month, 00:01. Gated on HR Settings.custom_enable_mod_off_allocation.
		"1 0 1 * *": ["upande_hr.attendance.mod_off.run_monthly"],
	},
}

# scheduler_events = {
# 	"all": [
# 		"upande_hr.tasks.all"
# 	],
# 	"daily": [
# 		"upande_hr.tasks.daily"
# 	],
# 	"hourly": [
# 		"upande_hr.tasks.hourly"
# 	],
# 	"weekly": [
# 		"upande_hr.tasks.weekly"
# 	],
# 	"monthly": [
# 		"upande_hr.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "upande_hr.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "upande_hr.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "upande_hr.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "upande_hr.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["upande_hr.utils.before_request"]
# after_request = ["upande_hr.utils.after_request"]

# Job Events
# ----------
# before_job = ["upande_hr.utils.before_job"]
# after_job = ["upande_hr.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"upande_hr.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []
