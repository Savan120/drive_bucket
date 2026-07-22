from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

MODULE_NAME = "Drive Bucket"
ROLE_NAME = "Storage Admin"
DASHBOARD_NAME = "Cloud Backup"
CHART_NAME = "Cloud Storage Usage Trend"
LEGACY_NUMBER_CARDS = ["Connected Accounts", "Total Used Space", "Total Quota"]


def after_install() -> None:
	bootstrap_cloud_backup()


def after_migrate() -> None:
	bootstrap_cloud_backup()


def bootstrap_cloud_backup() -> None:
	ensure_storage_admin_role()
	ensure_file_custom_fields()
	cleanup_legacy_dashboard()


def ensure_storage_admin_role() -> None:
	if frappe.db.exists("Role", ROLE_NAME):
		return
	role = frappe.get_doc({"doctype": "Role", "role_name": ROLE_NAME, "desk_access": 1})
	role.insert(ignore_permissions=True)


def cleanup_legacy_dashboard() -> None:
	if frappe.db.exists("Dashboard", DASHBOARD_NAME):
		frappe.delete_doc("Dashboard", DASHBOARD_NAME, ignore_permissions=True, force=True)

	if frappe.db.exists("Dashboard Chart", CHART_NAME):
		frappe.delete_doc("Dashboard Chart", CHART_NAME, ignore_permissions=True, force=True)

	for card_name in LEGACY_NUMBER_CARDS:
		if frappe.db.exists("Number Card", card_name):
			frappe.delete_doc("Number Card", card_name, ignore_permissions=True, force=True)


def ensure_file_custom_fields() -> None:
	custom_fields = {
		"File": [
			{
				"fieldname": "drive_bucket_section",
				"label": "Drive Bucket",
				"fieldtype": "Section Break",
				"insert_after": "uploaded_to_google_drive",
			},
			{
				"fieldname": "drive_bucket_google_account",
				"label": "Uploaded Drive Account",
				"fieldtype": "Link",
				"options": "Cloud Storage Account",
				"read_only": 1,
				"insert_after": "drive_bucket_section",
			},
			{
				"fieldname": "drive_bucket_google_file_id",
				"label": "Google Drive File ID",
				"fieldtype": "Data",
				"read_only": 1,
				"insert_after": "drive_bucket_google_account",
			},
			{
				"fieldname": "drive_bucket_google_file_link",
				"label": "Google Drive File Link",
				"fieldtype": "Data",
				"read_only": 1,
				"insert_after": "drive_bucket_google_file_id",
			},
			{
				"fieldname": "drive_bucket_drive_status",
				"label": "Drive Upload Status",
				"fieldtype": "Select",
				"options": "Queued\nUploaded\nFailed",
				"read_only": 1,
				"insert_after": "drive_bucket_google_file_link",
			},
			{
				"fieldname": "drive_bucket_last_shared_at",
				"label": "Last Shared At",
				"fieldtype": "Datetime",
				"read_only": 1,
				"insert_after": "drive_bucket_drive_status",
			},
		]
	}
	create_custom_fields(custom_fields, update=True)
