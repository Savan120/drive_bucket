from __future__ import annotations

from io import BytesIO
from typing import Any
from urllib.parse import quote
from zipfile import ZIP_DEFLATED, ZipFile

import frappe
import requests
from frappe.query_builder import DocType
from frappe.utils import add_days, cint, flt, get_datetime, getdate, now_datetime, nowdate
from frappe.utils.file_manager import save_file

from drive_bucket.cloud_backup.api.google_auth import (
	ACCOUNT_DOCTYPE,
	GOOGLE_FILES_URL,
	GoogleDriveError,
	_get_accessible_account,
	_google_get,
	_get_valid_access_token,
)
from drive_bucket.cloud_backup.tasks import _is_account_full, backup_account_files, process_queued_file_upload

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
GOOGLE_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


@frappe.whitelist(methods=["GET","POST"])
def get_console_data() -> dict[str, Any]:
	file_table = DocType("File")
	accessible_accounts = frappe.get_list(
		ACCOUNT_DOCTYPE,
		fields=["name"],
		order_by="is_default_upload desc, fallback_priority asc, modified desc",
	)
	account_names = [row.name if hasattr(row, "name") else row.get("name") for row in accessible_accounts]
	file_metrics = _get_file_metrics_by_account(account_names, file_table) if account_names else {}
	user_labels = _get_account_user_labels(account_names) if account_names else {}
	module_options = set()

	accounts = frappe.get_list(
		ACCOUNT_DOCTYPE,
		fields=[
			"name",
			"account_email",
			"linked_user",
			"route_module",
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
			"is_default_backup_drive",
			"backup_every_days",
			"last_backup_on",
			"backup_folder_id",
			"token_expiry",
		],
		order_by="is_default_upload desc, fallback_priority asc, modified desc",
	)

	account_docs = []
	for row in accounts:
		account_doc = frappe.get_doc(ACCOUNT_DOCTYPE, row["name"])
		account_modules = [module_row.module for module_row in (account_doc.get("module_routes") or []) if module_row.module]
		module_options.update(account_modules)
		row["is_full"] = _is_account_full(row)
		row["free_space_gb"] = round(max(flt(row.total_quota) - flt(row.used_space), 0), 3)
		row["usage_percent"] = round((flt(row.used_space) / flt(row.total_quota)) * 100, 2) if flt(row.total_quota) else 0
		row["module_routes"] = account_modules
		row["folder_links"] = _build_folder_links(row)
		row["access_summary"] = _build_access_summary(account_doc, user_labels.get(row["name"], {}))
		row.update(file_metrics.get(row["name"], _default_file_metrics()))
		row["health_warnings"] = _build_health_warnings(row)
		if not row.get("status_note"):
			if row["is_full"]:
				row["status_note"] = "Quota is exhausted. New uploads will move to the default fallback drive."
			elif row["connection_status"] != "Connected":
				row["status_note"] = "Drive needs attention before it can accept new uploads."
		logs = frappe.get_all(
			"Backup Log",
			filters={"cloud_storage_account": row["name"]},
			fields=["name", "file_name", "folder_type", "status", "error_message", "timestamp"],
			order_by="timestamp desc",
			limit=6,
		)
		_attach_recent_file_context(row["name"], logs, file_table)
		row["recent_logs"] = logs
		row["recent_log_count"] = frappe.db.count("Backup Log", filters={"cloud_storage_account": row["name"]})
		row["backup_summary"] = _build_backup_summary(row)
		account_docs.append(row)

	return {
		"summary": {
			"connected_accounts": sum(1 for row in account_docs if row["connection_status"] == "Connected"),
			"default_account": next((row["account_email"] for row in account_docs if row["is_default_upload"]), None),
			"total_used_space_gb": round(sum(flt(row["used_space"]) for row in account_docs), 3),
			"total_quota_gb": round(sum(flt(row["total_quota"]) for row in account_docs), 3),
			"fallback_accounts": sum(1 for row in account_docs if row["allow_fallback"]),
			"queued_uploads": sum(cint(row.get("queued_upload_count")) for row in account_docs),
			"failed_uploads": sum(cint(row.get("failed_upload_count")) for row in account_docs),
			"uploaded_today": sum(cint(row.get("uploaded_today_count")) for row in account_docs),
			"backup_due_accounts": sum(1 for row in account_docs if row.get("backup_due")),
		},
		"accounts": account_docs,
		"module_options": sorted(module_options),
		"policies": [
			"Uploads route by document module first, then fall back to unrestricted drives when needed.",
			"If a module-specific drive is full or unavailable, the system uses the default fallback drive.",
			"Direct Google Drive import can attach files to any document you have write access to.",
		],
	}


def _attach_recent_file_context(account_name: str, logs: list[dict[str, Any]], file_table) -> None:
	file_names = [log.get("file_name") for log in logs if log.get("file_name")]
	if not file_names:
		return

	doctype_table = DocType("DocType")
	file_rows = (
		frappe.qb.from_(file_table)
		.left_join(doctype_table)
		.on(file_table.attached_to_doctype == doctype_table.name)
		.select(
			file_table.name,
			file_table.file_name,
			file_table.file_url,
			file_table.attached_to_doctype,
			file_table.attached_to_name,
			file_table.is_private,
			file_table.owner,
			file_table.drive_bucket_google_file_id,
			file_table.drive_bucket_google_file_link,
			file_table.drive_bucket_google_account,
			file_table.modified,
			doctype_table.module.as_("module_name"),
		)
		.where(
			(file_table.drive_bucket_google_account == account_name)
			& (file_table.file_name.isin(file_names))
			& (file_table.uploaded_to_google_drive == 1)
		)
		.orderby(file_table.modified, order=frappe.qb.desc)
	).run(as_dict=True)

	file_map: dict[str, dict[str, Any]] = {}
	for row in file_rows:
		file_name = row.get("file_name")
		if file_name and file_name not in file_map:
			file_map[file_name] = row

	for log in logs:
		file_row = file_map.get(log.get("file_name"))
		if not file_row:
			log["attached_label"] = None
			log["attached_route"] = None
			log["preview_url"] = None
			log["file_record_name"] = None
			log["module_name"] = None
			log["is_private"] = None
			log["owner"] = None
			continue

		attached_to_doctype = file_row.get("attached_to_doctype")
		attached_to_name = file_row.get("attached_to_name")
		log["attached_label"] = (
			f"{attached_to_doctype} / {attached_to_name}"
			if attached_to_doctype and attached_to_name
			else None
		)
		log["attached_route"] = (
			{"doctype": attached_to_doctype, "name": attached_to_name}
			if attached_to_doctype and attached_to_name
			else None
		)
		log["preview_url"] = _build_drive_preview_url(file_row.get("drive_bucket_google_file_id"), file_row.get("drive_bucket_google_file_link") or file_row.get("file_url"))
		log["file_record_name"] = file_row.get("name")
		log["module_name"] = file_row.get("module_name")
		log["is_private"] = cint(file_row.get("is_private"))
		log["owner"] = file_row.get("owner")


def _get_file_metrics_by_account(account_names: list[str], file_table) -> dict[str, dict[str, Any]]:
	metrics = {account_name: _default_file_metrics() for account_name in account_names}
	if not account_names:
		return metrics

	today_start = f"{nowdate()} 00:00:00"
	doctype_table = DocType("DocType")

	file_rows = (
		frappe.qb.from_(file_table)
		.left_join(doctype_table)
		.on(file_table.attached_to_doctype == doctype_table.name)
		.select(
			file_table.name,
			file_table.file_name,
			file_table.drive_bucket_google_account,
			file_table.drive_bucket_drive_status,
			file_table.creation,
			file_table.modified,
			file_table.file_url,
			file_table.drive_bucket_google_file_id,
			file_table.drive_bucket_google_file_link,
			file_table.attached_to_doctype,
			file_table.attached_to_name,
			file_table.is_private,
			file_table.owner,
			doctype_table.module.as_("module_name"),
		)
		.where(file_table.drive_bucket_google_account.isin(account_names))
		.orderby(file_table.modified, order=frappe.qb.desc)
	).run(as_dict=True)

	for row in file_rows:
		account_name = row.get("drive_bucket_google_account")
		if account_name not in metrics:
			continue

		status = row.get("drive_bucket_drive_status") or ""
		if status == "Queued":
			metrics[account_name]["queued_upload_count"] += 1

		if len(metrics[account_name]["search_seed_uploads"]) < 5:
			metrics[account_name]["search_seed_uploads"].append(_serialize_file_row(row))

	log_rows = frappe.get_all(
		"Backup Log",
		filters={"cloud_storage_account": ["in", account_names]},
		fields=["cloud_storage_account", "file_name", "folder_type", "size", "status", "timestamp", "error_message"],
		order_by="timestamp desc",
		limit=500,
	)

	for row in log_rows:
		account_name = row.get("cloud_storage_account")
		if account_name not in metrics:
			continue
		folder_type = row.get("folder_type")
		status = row.get("status")
		timestamp = row.get("timestamp")
		if folder_type in {"Private", "Public"} and status == "Success" and timestamp and getdate(timestamp) == getdate(nowdate()):
			metrics[account_name]["uploaded_today_count"] += 1
		if folder_type in {"Private", "Public"} and status == "Failed":
			metrics[account_name]["failed_upload_count"] += 1

		if folder_type == "Database" and not metrics[account_name].get("latest_backup_log"):
			metrics[account_name]["latest_backup_log"] = row
		if status == "Failed" and not metrics[account_name].get("latest_failure_log"):
			metrics[account_name]["latest_failure_log"] = row

	return metrics


def _default_file_metrics() -> dict[str, Any]:
	return {
		"uploaded_today_count": 0,
		"failed_upload_count": 0,
		"queued_upload_count": 0,
		"latest_backup_log": None,
		"latest_failure_log": None,
		"search_seed_uploads": [],
	}


def _serialize_file_row(row: dict[str, Any]) -> dict[str, Any]:
	attached_to_doctype = row.get("attached_to_doctype")
	attached_to_name = row.get("attached_to_name")
	return {
		"name": row.get("name"),
		"file_name": row.get("file_name"),
		"status": row.get("drive_bucket_drive_status"),
		"modified": row.get("modified"),
		"module_name": row.get("module_name"),
		"is_private": cint(row.get("is_private")),
		"owner": row.get("owner"),
		"attached_label": f"{attached_to_doctype} / {attached_to_name}" if attached_to_doctype and attached_to_name else None,
		"attached_route": {"doctype": attached_to_doctype, "name": attached_to_name} if attached_to_doctype and attached_to_name else None,
		"preview_url": _build_drive_preview_url(row.get("drive_bucket_google_file_id"), row.get("drive_bucket_google_file_link") or row.get("file_url")),
	}


def _build_drive_preview_url(file_id: str | None, fallback_url: str | None = None) -> str | None:
	if file_id:
		return f"https://drive.google.com/file/d/{quote(file_id, safe='')}/view"
	return fallback_url


def _get_account_user_labels(account_names: list[str]) -> dict[str, dict[str, str]]:
	if not account_names:
		return {}

	access_table = DocType("Cloud Storage Account User Access")
	access_rows = (
		frappe.qb.from_(access_table)
		.select(access_table.parent, access_table.user)
		.where(
			(access_table.parent.isin(account_names))
			& (access_table.parenttype == ACCOUNT_DOCTYPE)
		)
	).run(as_dict=True)

	user_names = sorted({row.get("user") for row in access_rows if row.get("user")})
	if not user_names:
		return {}

	user_table = DocType("User")
	user_rows = (
		frappe.qb.from_(user_table)
		.select(user_table.name, user_table.full_name)
		.where(user_table.name.isin(user_names))
	).run(as_dict=True)

	name_map = {
		row.get("name"): (row.get("full_name") or row.get("name"))
		for row in user_rows
	}

	account_user_labels: dict[str, dict[str, str]] = {}
	for row in access_rows:
		parent = row.get("parent")
		user = row.get("user")
		if not parent or not user:
			continue
		account_user_labels.setdefault(parent, {})[user] = name_map.get(user, user)
	return account_user_labels


def _build_access_summary(account_doc, label_map: dict[str, str]) -> dict[str, Any]:
	rows = account_doc.get("user_access") or []
	users = []
	view_count = upload_count = download_count = manage_count = 0
	for row in rows:
		user = row.user
		if not user:
			continue
		users.append(label_map.get(user, user))
		view_count += cint(row.can_view)
		upload_count += cint(row.can_upload)
		download_count += cint(row.can_download)
		manage_count += cint(row.can_manage)

	linked_user = account_doc.linked_user
	if linked_user and linked_user not in label_map and linked_user not in users:
		users.insert(0, linked_user)

	return {
		"user_count": len(users),
		"users": users[:4],
		"has_more_users": len(users) > 4,
		"view_count": view_count,
		"upload_count": upload_count,
		"download_count": download_count,
		"manage_count": manage_count,
	}


def _build_folder_links(row: dict[str, Any]) -> dict[str, str]:
	return {
		"private": _drive_folder_link(row.get("private_folder_id")),
		"public": _drive_folder_link(row.get("public_folder_id")),
		"backup": _drive_folder_link(row.get("backup_folder_id")),
	}


def _drive_folder_link(folder_id: str | None) -> str:
	if not folder_id:
		return ""
	return f"https://drive.google.com/drive/folders/{folder_id}"


def _build_backup_summary(row: dict[str, Any]) -> dict[str, Any]:
	latest_backup = row.get("latest_backup_log")
	return {
		"last_backup_on": str(row.get("last_backup_on") or ""),
		"backup_every_days": cint(row.get("backup_every_days")) or 1,
		"backup_due": bool(row.get("backup_due")),
		"latest_file_name": latest_backup.get("file_name") if latest_backup else None,
		"latest_size": latest_backup.get("size") if latest_backup else None,
		"latest_timestamp": latest_backup.get("timestamp") if latest_backup else None,
		"latest_status": latest_backup.get("status") if latest_backup else None,
		"folder_link": row.get("folder_links", {}).get("backup"),
	}


def _build_health_warnings(row: dict[str, Any]) -> list[str]:
	warnings: list[str] = []
	if row.get("connection_status") != "Connected":
		warnings.append("Drive connection needs attention.")
	if flt(row.get("usage_percent")) >= 90:
		warnings.append("Quota is above 90%.")
	if not row.get("private_folder_id") or not row.get("public_folder_id"):
		warnings.append("Private or public Drive folder is missing.")
	row["backup_due"] = _is_backup_due_row(row)
	if row.get("is_default_backup_drive"):
		if not row.get("backup_folder_id"):
			warnings.append("Database backup folder is missing.")
		if row.get("backup_due"):
			warnings.append("Database backup is overdue.")
	return warnings


def _is_backup_due_row(row: dict[str, Any]) -> bool:
	if not row.get("is_default_backup_drive"):
		return False

	interval_days = max(cint(row.get("backup_every_days")) or 1, 1)
	last_backup_on = row.get("last_backup_on")
	if not last_backup_on:
		return True

	return getdate(last_backup_on) <= add_days(getdate(nowdate()), -interval_days)


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


@frappe.whitelist(methods=["POST"])
def run_account_backup(account_name: str) -> dict[str, str]:
	account = _get_accessible_account(account_name, permission="manage")
	if not account.is_default_backup_drive:
		frappe.throw("Enable Default Backup Drive on this account before running a backup.")

	backup_account_files(account.name)
	account.reload()
	return {
		"account_name": account.name,
		"last_backup_on": str(account.last_backup_on or ""),
	}


@frappe.whitelist(methods=["POST"])
def retry_failed_upload(account_name: str, file_record_name: str) -> dict[str, str]:
	_get_accessible_account(account_name, permission="manage")
	file_doc = frappe.get_doc("File", file_record_name)
	process_queued_file_upload(file_doc.name)
	return {"file_name": file_doc.name}


@frappe.whitelist(methods=["GET","POST"])
def list_drive_files(account_name: str, query: str | None = None, page_token: str | None = None) -> dict[str, Any]:
	account = _get_accessible_account(account_name, permission="view")
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


@frappe.whitelist(methods=["GET", "POST"])
def search_managed_uploads(
	query: str | None = None,
	module: str | None = None,
	account_name: str | None = None,
	status: str | None = None,
) -> dict[str, Any]:
	accessible_accounts = frappe.get_list(ACCOUNT_DOCTYPE, fields=["name"])
	account_names = [row.name if hasattr(row, "name") else row.get("name") for row in accessible_accounts]
	if account_name and account_name not in account_names:
		frappe.throw("You do not have access to that Drive account.")
	if account_name:
		account_names = [account_name]

	if not account_names:
		return {"files": []}

	file_table = DocType("File")
	doctype_table = DocType("DocType")
	managed_query = (
		frappe.qb.from_(file_table)
		.left_join(doctype_table)
		.on(file_table.attached_to_doctype == doctype_table.name)
		.select(
			file_table.name,
			file_table.file_name,
			file_table.drive_bucket_google_account,
			file_table.drive_bucket_drive_status,
			file_table.file_url,
			file_table.drive_bucket_google_file_link,
			file_table.attached_to_doctype,
			file_table.attached_to_name,
			file_table.is_private,
			file_table.owner,
			file_table.modified,
			doctype_table.module.as_("module_name"),
		)
		.where(
			(file_table.uploaded_to_google_drive == 1)
			& (file_table.drive_bucket_google_account.isin(account_names))
		)
	)

	if query:
		managed_query = managed_query.where(file_table.file_name.like(f"%{query}%"))
	if module:
		managed_query = managed_query.where(doctype_table.module == module)
	if status:
		managed_query = managed_query.where(file_table.drive_bucket_drive_status == status)

	rows = managed_query.orderby(file_table.modified, order=frappe.qb.desc).limit(20).run(as_dict=True)
	return {"files": [_serialize_file_row(row) | {"account_name": row.get("drive_bucket_google_account")} for row in rows]}


@frappe.whitelist(methods=["GET","POST"])
def import_drive_file(
	account_name: str,
	drive_file_id: str,
	attached_to_doctype: str,
	attached_to_name: str,
	attached_to_field: str | None = None,
	is_private: int | str = 1,
) -> dict[str, Any]:
	account = _get_accessible_account(account_name, permission="upload")
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


@frappe.whitelist(methods=["GET"])
def download_account_uploads_zip(account_name: str) -> None:
	account = _get_accessible_account(account_name, permission="download")
	access_token = _get_valid_access_token(account)

	archive = BytesIO()
	file_count = 0
	with ZipFile(archive, "w", compression=ZIP_DEFLATED) as zip_file:
		for folder_label, folder_id in (
			("private", account.private_folder_id),
			("public", account.public_folder_id),
		):
			if not folder_id:
				continue
			file_count += _write_folder_to_zip(
				zip_file=zip_file,
				access_token=access_token,
				folder_id=folder_id,
				zip_parts=[folder_label],
			)

	if not file_count:
		frappe.throw("No uploaded files were found in this Drive account.")

	archive.seek(0)
	frappe.response["filename"] = f"{_sanitize_zip_part(account.name)}_uploads.zip"
	frappe.response["filecontent"] = archive.getvalue()
	frappe.response["type"] = "download"
	frappe.response["content_type"] = "application/zip"


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


def _list_drive_children(access_token: str, folder_id: str) -> list[dict[str, Any]]:
	files: list[dict[str, Any]] = []
	page_token: str | None = None

	while True:
		response = _google_get(
			GOOGLE_FILES_URL,
			access_token,
			params={
				"q": f"'{folder_id}' in parents and trashed = false",
				"fields": "nextPageToken,files(id,name,mimeType)",
				"pageSize": 1000,
				"orderBy": "folder,name",
				"pageToken": page_token,
			},
		)
		files.extend(response.get("files") or [])
		page_token = response.get("nextPageToken")
		if not page_token:
			return files


def _write_folder_to_zip(
	zip_file: ZipFile,
	access_token: str,
	folder_id: str,
	zip_parts: list[str],
) -> int:
	file_count = 0
	for item in _list_drive_children(access_token, folder_id):
		item_name = _sanitize_zip_part(item.get("name") or item.get("id") or "untitled")
		if item.get("mimeType") == GOOGLE_FOLDER_MIME_TYPE:
			file_count += _write_folder_to_zip(
				zip_file=zip_file,
				access_token=access_token,
				folder_id=item["id"],
				zip_parts=[*zip_parts, item_name],
			)
			continue

		content, file_name = _download_drive_file(access_token, item["id"], item)
		zip_path = "/".join([*zip_parts, _sanitize_zip_part(file_name or item_name)])
		zip_file.writestr(zip_path, content.getvalue())
		file_count += 1

	return file_count


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


def _sanitize_zip_part(value: str) -> str:
	return (value or "untitled").replace("\\", "-").replace("/", "-").strip() or "untitled"
