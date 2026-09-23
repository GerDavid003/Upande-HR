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
# doctype_js = {"doctype" : "public/js/doctype.js"}
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
# Every item inside the "in" list is a Custom Field NAME, a plain string. A dict here
# is passed straight into the SQL IN clause and the export dies with a syntax error -
# fixture entries for other doctypes are siblings of this block, not members of it.
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
					# Two more adopted hand-made Desk fields, kept under their existing
					# fieldnames so the records already carrying values keep working.
					# custom_skilllevel is missing an underscore; renaming it would need a
					# data migration, so it ships as-is. custom_category links to the
					# Job Category doctype this app now owns.
					"Employee-custom_skilllevel",
					"Employee-custom_category",
					# Shift window, anchored on the HRMS-shipped default_shift. Both are
					# Date fields rather than breaks, so the Section Break walk above does
					# not apply. shift.py defaults the start date to date_of_joining and
					# drives the submitted Shift Assignment off this pair.
					"Employee-custom_shift_start_date",
					"Employee-custom_shift_end_date",
					# Probation, its own collapsible section on the Joining tab. Anchored
					# on final_confirmation_date: column_break_32 follows it, so the
					# Section Break walk stops there instead of crossing into the next tab.
					# notice_number_of_days looked safe but is last in its section, and the
					# walk carried the whole block into Address & Contacts.
					"Employee-custom_probation_section",
					"Employee-custom_probation_status",
					"Employee-custom_probation_start_date",
					"Employee-custom_probation_period_months",
					"Employee-custom_probation_col_break",
					"Employee-custom_probation_end_date",
					"Employee-custom_probation_review_date",
					# Induction. All four are read-only flags written by induction.py;
					# the evidence lives in the Policy Acknowledgment records, surfaced on
					# the Connections tab by dashboard.py.
					"Employee-custom_induction_section",
					"Employee-custom_induction_session",
					"Employee-custom_induction_completed",
					"Employee-custom_policies_acknowledged",
					# HR Settings tunables. Defaults on a Custom Field only apply to new
					# records, and HR Settings is a Single that already exists on every
					# site, so these have to be set by hand after deployment.
					"HR Settings-custom_upande_hr_section",
					"HR Settings-custom_auto_create_shift_assignment",
					"HR Settings-custom_default_probation_months",
					"HR Settings-custom_probation_review_lead_days",
				],
			]
		],
	},
	# The whole Employee field order, not just this app's fields. Section Break and
	# Column Break placement on the standard fields (the Company Details columns, the
	# Joining tab date order, Statutory Details) cannot be expressed with insert_after
	# on a Custom Field, so the layout has to ship as this row.
	#
	# It carries upande_ta and upande_ats fields too. Acceptable on mgp, which serves
	# one client; do not copy this entry to a shared branch.
		{
		"doctype": "Workflow",
		"filters": [
			["name", "in", ["Extra Shift Compensation Approval", "Disciplinary Case Workflow"]]
		],
	},
	# The Disciplinary Case workflow references states and actions that do not ship with
	# Frappe, and a Workflow fixture does not pull its masters along. Without these two
	# the workflow imports against rows that do not exist and the transitions never bind.
	# "Open" is a stock Workflow State and is deliberately not re-shipped.
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
				],
			]
		],
	},
]

# Job Category permissions are NOT fixtured. They live in the doctype's own JSON at
# upande_hr/upande_hr/doctype/job_category/job_category.json, which migrate syncs.
# A Custom DocPerm fixture would override that JSON on every migrate and make the two
# sources of truth drift.

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
	"Employee Grievance": "upande_hr.overrides.employee_grievance.get_permission_query_conditions"
}

has_permission = {"Employee Grievance": "upande_hr.overrides.employee_grievance.has_permission"}

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Attendance": {
		# Runs after Attendance.validate(), so it gets the last word over
		# check_leave_record() reassigning status back to "On Leave".
		"validate": "upande_hr.overrides.attendance.reassert_comp_off_override"
	},
	# One "Employee" key only. A Python dict silently keeps the last duplicate, so a
	# second block here would drop set_years_of_service without any error.
	"Employee": {
		# set_years_of_service runs on validate rather than on the nightly job alone,
		# so the figure is right the moment a joining date is entered or corrected.
		# employee_validate resolves default_shift from Default Shift Rule; it runs
		# before set_probation_dates but the two do not share any field.
		"validate": [
			"upande_hr.overrides.employee.set_years_of_service",
			"upande_hr.upande_hr.shift.employee_validate",
			"upande_hr.upande_hr.probation.set_probation_dates",
		],
		# On on_update rather than validate: the Shift Assignment has to reference a
		# saved Employee, and the old assignment is cancelled before the new one is
		# submitted, which cannot happen mid-validate.
		"on_update": "upande_hr.upande_hr.shift.employee_on_update",
	},
	"Induction Session": {
		"on_submit": "upande_hr.upande_hr.induction.session_on_submit",
		"on_update_after_submit": "upande_hr.upande_hr.induction.session_on_update_after_submit",
		"on_cancel": "upande_hr.upande_hr.induction.session_on_cancel",
	},
	"Policy Acknowledgment": {
		"before_submit": "upande_hr.upande_hr.induction.acknowledgment_before_submit",
		"on_submit": "upande_hr.upande_hr.induction.acknowledgment_on_change",
		"on_cancel": "upande_hr.upande_hr.induction.acknowledgment_on_change",
	},
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"daily": [
		"upande_hr.upande_hr.doctype.disciplinary_warning.disciplinary_warning.lapse_expired_warnings",
		"upande_hr.overrides.employee.refresh_years_of_service",
	]
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

# Dashboards
# ------------------------------
#
# Each overriding function accepts a `data` argument generated from the base
# implementation of the doctype dashboard, along with any modifications made in other
# Frappe apps. One key per doctype - a duplicate is silently dropped, as with doc_events.
#
# Policy Acknowledgment is one row per employee per policy, so it belongs on the
# Connections tab rather than in a Link field on Employee.
override_doctype_dashboards = {
	"Employee": "upande_hr.upande_hr.dashboard.get_employee_dashboard",
}

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