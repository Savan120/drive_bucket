from __future__ import annotations

from typing import Any

import frappe
import requests
from frappe.utils import now_datetime

from drive_bucket.cloud_backup.api.google_auth import (
	ACCOUNT_DOCTYPE,
	GOOGLE_FILES_URL,
	GoogleDriveError,
	_get_valid_access_token,
)

GOOGLE_PERMISSIONS_FIELDS = "permissions(id,emailAddress,role,type,displayName)"


@frappe.whitelist(methods=["GET"])
def get_drive_access(file_name: str) -> dict[str, Any]:
	file_doc = _get_file_doc(file_name)
	account = _get_account_for_file(file_doc)
	access_token = _get_valid_access_token(account)

	response = requests.get(
		f"{GOOGLE_FILES_URL}/{file_doc.drive_bucket_google_file_id}/permissions",
		headers={"Authorization": f"Bearer {access_token}"},
		params={"fields": GOOGLE_PERMISSIONS_FIELDS},
		timeout=30,
	)
	if not response.ok:
		raise GoogleDriveError(response.text)

	return {
		"file_name": file_doc.name,
		"google_file_id": file_doc.drive_bucket_google_file_id,
		"google_file_link": file_doc.drive_bucket_google_file_link,
		"permissions": response.json().get("permissions", []),
	}


@frappe.whitelist(methods=["POST"])
def grant_drive_access(
	file_name: str,
	access_role: str = "reader",
	user: str | None = None,
	email_address: str | None = None,
	send_notification_email: int | str = 1,
) -> dict[str, Any]:
	file_doc = _get_file_doc(file_name)
	account = _get_account_for_file(file_doc)
	access_token = _get_valid_access_token(account)

	target_email = (email_address or "").strip()
	if not target_email and user:
		target_email = (frappe.db.get_value("User", user, "email") or "").strip()
	if not target_email:
		frappe.throw("Choose a user or enter an email address to grant access.")

	payload = {"role": access_role, "type": "user", "emailAddress": target_email}
	response = requests.post(
		f"{GOOGLE_FILES_URL}/{file_doc.drive_bucket_google_file_id}/permissions",
		headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
		params={"sendNotificationEmail": int(send_notification_email)},
		json=payload,
		timeout=30,
	)
	if not response.ok:
		raise GoogleDriveError(response.text)

	frappe.db.set_value("File", file_doc.name, "drive_bucket_last_shared_at", now_datetime(), update_modified=False)
	return {"email_address": target_email, "role": access_role}


def _get_file_doc(file_name: str):
	file_doc = frappe.get_doc("File", file_name)
	if not file_doc.has_permission("read"):
		raise frappe.PermissionError("You do not have permission to view this file.")
	if not file_doc.drive_bucket_google_file_id:
		frappe.throw("This file is not linked to a Google Drive file yet.")
	return file_doc


def _get_account_for_file(file_doc):
	account_name = file_doc.drive_bucket_google_account
	if not account_name:
		frappe.throw("No Google Drive account is linked to this file.")
	if not frappe.db.exists(ACCOUNT_DOCTYPE, account_name):
		frappe.throw("The linked Google Drive account could not be found.")
	return frappe.get_doc(ACCOUNT_DOCTYPE, account_name)
