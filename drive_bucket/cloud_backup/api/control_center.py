from __future__ import annotations

from io import BytesIO
from typing import Any
from urllib.parse import quote

import frappe
import requests
from frappe.utils import flt
from frappe.utils.file_manager import save_file

from drive_bucket.cloud_backup.api.google_auth import (
	ACCOUNT_DOCTYPE,
	GOOGLE_FILES_URL,
	GoogleDriveError,
	_get_accessible_account,
	_get_valid_access_token,
)
from drive_bucket.cloud_backup.tasks import _is_account_full

GOOGLE_FILE_FIELDS = "files(id,name,mimeType,size,modifiedTime,webViewLink,owners(emailAddress,displayName)),nextPageToken"
GOOGLE_NATIVE_EXPORTS = {
	"application/vnd.google-apps.document": (
		"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
		".docx",
	),
	"application/vnd.google-apps.spreadsheet": (
		"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
		".xlsx",
	),
	"application/vnd.google-apps.presentation": (
		"application/vnd.openxmlformats-officedocument.presentationml.presentation",
		".pptx",
	),
	"application/vnd.google-apps.drawing": ("image/png", ".png"),
}


@frappe.whitelist(methods=["GET","POST"])
def get_console_data() -> dict[str, Any]:
	accounts = frappe.get_all(
		ACCOUNT_DOCTYPE,
		fields=[
			"name",
			"account_email",
			"linked_user",
			"connection_status",
			"used_space",
			"total_quota",
			"last_synced",
			"is_default_upload",
			"allow_fallback",
			"auto_sync_uploads",
			"reserve_space_gb",
			"fallback_priority",
			"private_folder_id",
			"public_folder_id",
			"status_note",
		],
		order_by="is_default_upload desc, fallback_priority asc, modified desc",
	)

	recent_logs = frappe.get_all(
		"Cloud Storage Account",
		fields=["name"],
		limit=0,
	)
	del recent_logs  # keep linter calm; logs are fetched below per-account

	account_docs = []
	for row in accounts:
		row["is_full"] = _is_account_full(row)
		row["free_space_gb"] = round(max(flt(row.total_quota) - flt(row.used_space), 0), 3)
		row["usage_percent"] = round((flt(row.used_space) / flt(row.total_quota)) * 100, 2) if flt(row.total_quota) else 0
		if not row.get("status_note"):
			if row["is_full"]:
				row["status_note"] = "Quota is exhausted. New uploads will move to the default fallback drive."
			elif row["connection_status"] != "Connected":
				row["status_note"] = "Drive needs attention before it can accept new uploads."
		logs = frappe.get_all(
			"Backup Log",
			filters={"parent": row["name"], "parenttype": ACCOUNT_DOCTYPE},
			fields=["file_name", "folder_type", "status", "error_message", "timestamp"],
			order_by="timestamp desc",
			limit=5,
		)
		row["recent_logs"] = logs
		account_docs.append(row)

	return {
		"summary": {
			"connected_accounts": sum(1 for row in account_docs if row["connection_status"] == "Connected"),
			"default_account": next((row["account_email"] for row in account_docs if row["is_default_upload"]), None),
			"total_used_space_gb": round(sum(flt(row["used_space"]) for row in account_docs), 3),
			"total_quota_gb": round(sum(flt(row["total_quota"]) for row in account_docs), 3),
			"fallback_accounts": sum(1 for row in account_docs if row["allow_fallback"]),
		},
		"accounts": account_docs,
		"policies": [
			"Uploads route to the linked user's connected drive first.",
			"If the user's drive is unavailable or full, the system uses the default fallback drive.",
			"Direct Google Drive import can attach files to any document you have write access to.",
		],
	}


@frappe.whitelist(methods=["POST"])
def set_default_upload_account(account_name: str) -> dict[str, str]:
	if "Storage Admin" not in frappe.get_roles() and "System Manager" not in frappe.get_roles():
		raise frappe.PermissionError("Only Storage Admin or System Manager can change the default upload drive.")

	for name in frappe.get_all(ACCOUNT_DOCTYPE, filters={"is_default_upload": 1}, pluck="name"):
		if name == account_name:
			continue
		account = frappe.get_doc(ACCOUNT_DOCTYPE, name)
		account.is_default_upload = 0
		account.save(ignore_permissions=True, ignore_version=True)

	target = frappe.get_doc(ACCOUNT_DOCTYPE, account_name)
	target.is_default_upload = 1
	target.save(ignore_permissions=True, ignore_version=True)
	return {"account_name": target.name}


@frappe.whitelist(methods=["GET","POST"])
def list_drive_files(account_name: str, query: str | None = None, page_token: str | None = None) -> dict[str, Any]:
	account = _get_accessible_account(account_name)
	access_token = _get_valid_access_token(account)

	search_parts = ["trashed = false"]
	if query:
		safe_query = query.replace("'", "\\'")
		search_parts.append(f"name contains '{safe_query}'")

	response = requests.get(
		GOOGLE_FILES_URL,
		headers={"Authorization": f"Bearer {access_token}"},
		params={
			"q": " and ".join(search_parts),
			"fields": GOOGLE_FILE_FIELDS,
			"pageSize": 20,
			"orderBy": "modifiedTime desc",
			"pageToken": page_token,
		},
		timeout=30,
	)
	if not response.ok:
		raise GoogleDriveError(response.text)

	payload = response.json()
	return {"files": payload.get("files", []), "next_page_token": payload.get("nextPageToken")}


@frappe.whitelist(methods=["GET","POST"])
def import_drive_file(
	account_name: str,
	drive_file_id: str,
	attached_to_doctype: str,
	attached_to_name: str,
	attached_to_field: str | None = None,
	is_private: int | str = 1,
) -> dict[str, Any]:
	account = _get_accessible_account(account_name)
	if not frappe.has_permission(attached_to_doctype, "write", attached_to_name):
		raise frappe.PermissionError("You do not have permission to attach files to this document.")

	access_token = _get_valid_access_token(account)
	metadata = _get_drive_file_metadata(access_token, drive_file_id)
	content, file_name = _download_drive_file(access_token, drive_file_id, metadata)

	saved = save_file(
		file_name,
		content.getvalue(),
		attached_to_doctype,
		attached_to_name,
		is_private=frappe.utils.cint(is_private),
		df=attached_to_field,
	)
	return {
		"file_name": saved.file_name,
		"file_url": saved.file_url,
		"attached_to_doctype": attached_to_doctype,
		"attached_to_name": attached_to_name,
	}


def _get_drive_file_metadata(access_token: str, drive_file_id: str) -> dict[str, Any]:
	response = requests.get(
		f"{GOOGLE_FILES_URL}/{quote(drive_file_id, safe='')}",
		headers={"Authorization": f"Bearer {access_token}"},
		params={"fields": "id,name,mimeType,size"},
		timeout=30,
	)
	if not response.ok:
		raise GoogleDriveError(response.text)
	return response.json()


def _download_drive_file(access_token: str, drive_file_id: str, metadata: dict[str, Any]) -> tuple[BytesIO, str]:
	mime_type = metadata.get("mimeType")
	file_name = metadata.get("name") or drive_file_id

	if mime_type in GOOGLE_NATIVE_EXPORTS:
		export_mime, extension = GOOGLE_NATIVE_EXPORTS[mime_type]
		response = requests.get(
			f"{GOOGLE_FILES_URL}/{quote(drive_file_id, safe='')}/export",
			headers={"Authorization": f"Bearer {access_token}"},
			params={"mimeType": export_mime},
			timeout=120,
		)
		if not response.ok:
			raise GoogleDriveError(response.text)
		if not file_name.endswith(extension):
			file_name = f"{file_name}{extension}"
		return BytesIO(response.content), file_name

	response = requests.get(
		f"{GOOGLE_FILES_URL}/{quote(drive_file_id, safe='')}",
		headers={"Authorization": f"Bearer {access_token}"},
		params={"alt": "media"},
		timeout=120,
	)
	if not response.ok:
		raise GoogleDriveError(response.text)
	return BytesIO(response.content), file_name
