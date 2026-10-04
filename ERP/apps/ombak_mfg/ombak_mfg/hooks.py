app_name = "ombak_mfg"
app_title = "Ombak Mfg"
app_publisher = "Ombak Metal Works (demo)"
app_description = "Manufacturing extensions for Ombak Metal Works (demo)"
app_email = "dev@ombakmetal.example"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "ombak_mfg",
# 		"logo": "/assets/ombak_mfg/logo.png",
# 		"title": "Ombak Mfg",
# 		"route": "/ombak_mfg",
# 		"has_permission": "ombak_mfg.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/ombak_mfg/css/ombak_mfg.css"
# app_include_js = "/assets/ombak_mfg/js/ombak_mfg.js"

# include js, css files in header of web template
# web_include_css = "/assets/ombak_mfg/css/ombak_mfg.css"
# web_include_js = "/assets/ombak_mfg/js/ombak_mfg.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "ombak_mfg/public/scss/website"

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
# app_include_icons = "ombak_mfg/public/icons.svg"

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
# 	"methods": "ombak_mfg.utils.jinja_methods",
# 	"filters": "ombak_mfg.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "ombak_mfg.install.before_install"
# after_install = "ombak_mfg.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "ombak_mfg.uninstall.before_uninstall"
# after_uninstall = "ombak_mfg.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "ombak_mfg.utils.before_app_install"
# after_app_install = "ombak_mfg.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "ombak_mfg.utils.before_app_uninstall"
# after_app_uninstall = "ombak_mfg.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "ombak_mfg.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "ombak_mfg.notifications.get_notification_config"

# Awesome Bar
# -----------
# Extra search results: list of dicts with label, description, route, index.
# route: ["List", "ToDo"], "/desk/docs/some/page", or "https://example.com"
# awesomebar_search = ["ombak_mfg.search.awesomebar_results"]

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
# 		"ombak_mfg.tasks.all"
# 	],
# 	"daily": [
# 		"ombak_mfg.tasks.daily"
# 	],
# 	"hourly": [
# 		"ombak_mfg.tasks.hourly"
# 	],
# 	"weekly": [
# 		"ombak_mfg.tasks.weekly"
# 	],
# 	"monthly": [
# 		"ombak_mfg.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "ombak_mfg.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "ombak_mfg.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "ombak_mfg.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "ombak_mfg.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["ombak_mfg.utils.before_request"]
# after_request = ["ombak_mfg.utils.after_request"]

# Job Events
# ----------
# before_job = ["ombak_mfg.utils.before_job"]
# after_job = ["ombak_mfg.utils.after_job"]

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
# 	"ombak_mfg.auth.validate"
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


# Ombak demo: tests run against the same master data the demo uses
before_tests = "ombak_mfg.setup.masters.setup_masters"

scheduler_events = {
	"daily": ["ombak_mfg.tasks.notify_overdue_work_orders"],
}
