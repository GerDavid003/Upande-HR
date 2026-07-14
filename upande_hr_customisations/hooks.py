app_name = "upande_hr_customisations"
app_title = "Upande Hr Customisations"
app_publisher = "Upande"
app_description = "HR customisations for Upande"
app_email = "otieno@upande.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "upande_hr_customisations",
# 		"logo": "/assets/upande_hr_customisations/logo.png",
# 		"title": "Upande Hr Customisations",
# 		"route": "/upande_hr_customisations",
# 		"has_permission": "upande_hr_customisations.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/upande_hr_customisations/css/upande_hr_customisations.css"
# app_include_js = "/assets/upande_hr_customisations/js/upande_hr_customisations.js"

# include js, css files in header of web template
# web_include_css = "/assets/upande_hr_customisations/css/upande_hr_customisations.css"
# web_include_js = "/assets/upande_hr_customisations/js/upande_hr_customisations.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "upande_hr_customisations/public/scss/website"

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
# app_include_icons = "upande_hr_customisations/public/icons.svg"

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
# 	"methods": "upande_hr_customisations.utils.jinja_methods",
# 	"filters": "upande_hr_customisations.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "upande_hr_customisations.install.before_install"
# after_install = "upande_hr_customisations.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "upande_hr_customisations.uninstall.before_uninstall"
# after_uninstall = "upande_hr_customisations.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "upande_hr_customisations.utils.before_app_install"
# after_app_install = "upande_hr_customisations.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "upande_hr_customisations.utils.before_app_uninstall"
# after_app_uninstall = "upande_hr_customisations.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "upande_hr_customisations.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "upande_hr_customisations.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"upande_hr_customisations.tasks.all"
# 	],
# 	"daily": [
# 		"upande_hr_customisations.tasks.daily"
# 	],
# 	"hourly": [
# 		"upande_hr_customisations.tasks.hourly"
# 	],
# 	"weekly": [
# 		"upande_hr_customisations.tasks.weekly"
# 	],
# 	"monthly": [
# 		"upande_hr_customisations.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "upande_hr_customisations.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "upande_hr_customisations.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "upande_hr_customisations.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "upande_hr_customisations.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["upande_hr_customisations.utils.before_request"]
# after_request = ["upande_hr_customisations.utils.after_request"]

# Job Events
# ----------
# before_job = ["upande_hr_customisations.utils.before_job"]
# after_job = ["upande_hr_customisations.utils.after_job"]

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
# 	"upande_hr_customisations.auth.validate"
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

