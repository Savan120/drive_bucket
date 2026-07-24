app_name = "drive_bucket"
app_title = "Drive Bucket"
app_publisher = "Savan Patel"
app_description = "Unified storage orchestration app for managing bucket-backed file workflows across Drive and object storage providers."
app_email = "savan.p.solufy@gmail.com"
app_license = "mit"
after_install = "drive_bucket.install.after_install"
after_migrate = "drive_bucket.install.after_migrate"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "drive_bucket",
# 		"logo": "/assets/drive_bucket/logo.png",
# 		"title": "Drive Bucket",
# 		"route": "/drive_bucket",
# 		"has_permission": "drive_bucket.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/drive_bucket/css/drive_bucket.css"
# app_include_js = "/assets/drive_bucket/js/drive_bucket.js"

# include js, css files in header of web template
# web_include_css = "/assets/drive_bucket/css/drive_bucket.css"
# web_include_js = "/assets/drive_bucket/js/drive_bucket.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "drive_bucket/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {"File": "public/js/file.js"}
write_file = "drive_bucket.cloud_backup.file_writer.write_file"
write_file_keys = [
	"file_url",
	"file_name",
	"uploaded_to_google_drive",
	"drive_bucket_google_account",
	"drive_bucket_google_file_id",
	"drive_bucket_google_file_link",
	"drive_bucket_drive_status",
]
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "drive_bucket/public/icons.svg"

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
# 	"methods": "drive_bucket.utils.jinja_methods",
# 	"filters": "drive_bucket.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "drive_bucket.install.before_install"
required_apps = ["frappe"]

# Uninstallation
# ------------

# before_uninstall = "drive_bucket.uninstall.before_uninstall"
# after_uninstall = "drive_bucket.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "drive_bucket.utils.before_app_install"
# after_app_install = "drive_bucket.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "drive_bucket.utils.before_app_uninstall"
# after_app_uninstall = "drive_bucket.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "drive_bucket.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "drive_bucket.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

permission_query_conditions = {
	"Cloud Storage Account": "drive_bucket.permissions.get_cloud_storage_account_permission_query",
	"Backup Log": "drive_bucket.permissions.get_backup_log_permission_query",
}

has_permission = {
	"Cloud Storage Account": "drive_bucket.permissions.has_cloud_storage_account_permission",
	"Backup Log": "drive_bucket.permissions.has_backup_log_permission",
}

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"File": {
		"after_insert": "drive_bucket.cloud_backup.tasks.enqueue_file_upload",
	}
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"daily": [
		"drive_bucket.cloud_backup.tasks.run_daily_backup",
	],
	"hourly": [
		"drive_bucket.cloud_backup.tasks.refresh_expiring_tokens",
	],
}

# Testing
# -------

# before_tests = "drive_bucket.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "drive_bucket.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "drive_bucket.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "drive_bucket.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["drive_bucket.utils.before_request"]
# after_request = ["drive_bucket.utils.after_request"]

# Job Events
# ----------
# before_job = ["drive_bucket.utils.before_job"]
# after_job = ["drive_bucket.utils.after_job"]

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
# 	"drive_bucket.auth.validate"
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
