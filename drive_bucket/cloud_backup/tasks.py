from __future__ import annotations

import json
import mimetypes
import os
from pathlib import Path
from typing import BinaryIO
from urllib.parse import unquote

import frappe
import requests
from frappe.query_builder import DocType
from frappe.utils import add_days, cint, getdate, now_datetime, nowdate
from frappe.utils.backups import backup as create_site_backup

from drive_bucket.cloud_backup.api.google_auth import (
	ACCOUNT_DOCTYPE,
	GOOGLE_FILES_URL,
	GoogleDriveError,
	_create_drive_folder,
	ensure_backup_folders,
	_find_folder_id,
	refresh_account_access_token,
	sync_quota,
)

GOOGLE_RESUMABLE_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable"
GOOGLE_PERMISSIONS_URL_TEMPLATE = GOOGLE_FILES_URL + "/{file_id}/permissions"


def refresh_expiring_tokens() -> None:
	account_names = frappe.get_all(
		ACCOUNT_DOCTYPE,
		filters={"connection_status": ["in", ["Connected", "Expired"]]},
		pluck="name",
	)
	for account_name in account_names:
		try:
			refresh_account_access_token(account_name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Cloud Backup token refresh failed for {account_name}")


def run_daily_backup() -> None:
	account_names = frappe.get_all(
		ACCOUNT_DOCTYPE,
		filters={"connection_status": "Connected", "is_default_backup_drive": 1},
		pluck="name",
	)
	for account_name in account_names:
		if not _is_backup_due(account_name):
			continue
		try:
			backup_account_files(account_name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Cloud Backup daily backup failed for {account_name}")


def backup_account_files(account_name: str) -> None:
	account = frappe.get_doc(ACCOUNT_DOCTYPE, account_name)
	refresh_account_access_token(account.name)
	ensure_backup_folders(account.name)
	account.reload()
	access_token = account.get_password("access_token")
	if not access_token:
		raise GoogleDriveError(f"Access token is missing for {account.name}.")

	database_backup_folder_id = _prepare_backup_run_folder(account, access_token)
	backup_result = create_site_backup(with_files=False)
	database_backup_path = backup_result.get("backup_path_db")
	if not database_backup_path:
		raise GoogleDriveError("Frappe did not return a database backup path.")

	_upload_database_backup(account, Path(database_backup_path), access_token, database_backup_folder_id)

	sync_quota(account.name)
	account.db_set("last_backup_on", nowdate(), update_modified=False)


def enqueue_file_upload(file_doc, method: str | None = None) -> None:
	del method
	if getattr(file_doc, "is_folder", 0) or not file_doc.file_url or file_doc.uploaded_to_google_drive:
		return
	frappe.db.set_value("File", file_doc.name, "drive_bucket_drive_status", "Queued", update_modified=False)

	frappe.enqueue(
		"drive_bucket.cloud_backup.tasks.process_queued_file_upload",
		queue="default",
		timeout=900,
		enqueue_after_commit=True,
		job_id=f"drive_bucket:file_upload:{file_doc.name}",
		deduplicate=True,
		file_name=file_doc.name,
	)


def process_queued_file_upload(file_name: str) -> None:
	file_doc = frappe.get_doc("File", file_name)
	if file_doc.is_folder or not file_doc.file_url or file_doc.uploaded_to_google_drive:
		return

	account_name = _select_target_account_name(file_doc=file_doc)
	if not account_name:
		return

	all_success = True
	try:
		account = frappe.get_doc(ACCOUNT_DOCTYPE, account_name)
		refresh_account_access_token(account.name)
		ensure_backup_folders(account.name)
		account.reload()
		_upload_file_for_account(account, file_doc)
		sync_quota(account.name)
	except Exception:
		all_success = False
		frappe.log_error(frappe.get_traceback(), f"Cloud Backup auto upload failed for {file_doc.name} -> {account_name}")

	if all_success:
		frappe.db.set_value("File", file_doc.name, "uploaded_to_google_drive", 1, update_modified=False)


def upload_file_to_linked_accounts(file_name: str) -> None:
	# Backward-compatible wrapper for any queued jobs created before the rename.
	process_queued_file_upload(file_name)


def _get_files_to_backup():
	return frappe.get_all(
		"File",
		filters={"is_folder": 0, "uploaded_to_google_drive": 0},
		fields=["name", "file_name", "file_url", "is_private"],
	)


def _resolve_file_path(file_doc) -> Path:
	if not file_doc.file_url:
		raise GoogleDriveError(f"File URL missing for {file_doc.name}.")
	file_name = Path(unquote(file_doc.file_url)).name
	if file_doc.is_private:
		return Path(frappe.get_site_path("private", "files", file_name))
	return Path(frappe.get_site_path("public", "files", file_name))


def _is_backup_due(account_name: str) -> bool:
	account_table = DocType(ACCOUNT_DOCTYPE)
	rows = (
		frappe.qb.from_(account_table)
		.select(account_table.backup_every_days, account_table.last_backup_on)
		.where(account_table.name == account_name)
		.limit(1)
	).run(as_dict=True)
	if not rows:
		return False

	row = rows[0]
	interval_days = max(cint(row.backup_every_days) or 1, 1)
	last_backup_on = row.last_backup_on
	if not last_backup_on:
		return True

	return getdate(last_backup_on) <= add_days(getdate(nowdate()), -interval_days)


def _prepare_backup_run_folder(account, access_token: str) -> str:
	backup_root_folder_id = getattr(account, "backup_folder_id", None)
	if not backup_root_folder_id:
		raise GoogleDriveError("Backup folder is not configured for this account.")

	run_folder_name = nowdate()
	run_folder_id = _find_folder_id(access_token, run_folder_name, parent_id=backup_root_folder_id)
	if not run_folder_id:
		run_folder_id = _create_drive_folder(access_token, run_folder_name, parent_id=backup_root_folder_id)
	return run_folder_id


def _upload_file_to_drive(
	*,
	access_token: str,
	folder_id: str | None,
	file_name: str,
	file_handle: BinaryIO,
	file_size: int,
) -> dict:
	if not folder_id:
		raise GoogleDriveError("Target Google Drive folder is not configured.")

	content_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
	init_response = requests.post(
		GOOGLE_RESUMABLE_UPLOAD_URL,
		headers={
			"Authorization": f"Bearer {access_token}",
			"Content-Type": "application/json",
			"X-Upload-Content-Type": content_type,
			"X-Upload-Content-Length": str(file_size),
		},
		data=json.dumps({"name": file_name, "parents": [folder_id]}),
		timeout=30,
	)
	if not init_response.ok:
		raise GoogleDriveError(init_response.text)

	upload_url = init_response.headers.get("Location")
	if not upload_url:
		raise GoogleDriveError("Google Drive did not return an upload URL.")

	upload_response = requests.put(
		upload_url,
		headers={
			"Authorization": f"Bearer {access_token}",
			"Content-Length": str(file_size),
			"Content-Type": content_type,
		},
		data=file_handle,
		timeout=300,
	)
	if not upload_response.ok:
		raise GoogleDriveError(upload_response.text)
	result = upload_response.json()
	if result.get("id") and not result.get("webViewLink"):
		metadata_response = requests.get(
			f"{GOOGLE_FILES_URL}/{result['id']}",
			headers={"Authorization": f"Bearer {access_token}"},
			params={"fields": "id,webViewLink"},
			timeout=30,
		)
		if metadata_response.ok:
			result.update(metadata_response.json())
	return result


def _upload_file_for_account(account, file_doc) -> None:
	folder_type = "Private" if file_doc.is_private else "Public"
	file_path = _resolve_file_path(file_doc)
	file_size = float(os.path.getsize(file_path))
	original_file_url = file_doc.file_url
	try:
		access_token = account.get_password("access_token")
		target_folder_id = _resolve_target_folder_id(account, file_doc, access_token)
		with file_path.open("rb") as file_handle:
			upload_result = _upload_file_to_drive(
				access_token=access_token,
				folder_id=target_folder_id,
				file_name=file_doc.file_name or file_path.name,
				file_handle=file_handle,
				file_size=int(file_size),
			)
		if not file_doc.is_private:
			_ensure_public_file_permission(access_token, upload_result)
		_mark_file_uploaded(file_doc.name, account.name, upload_result, file_doc.is_private)
		_delete_local_file_copy(original_file_url, file_doc.is_private)
		_append_backup_log(account, file_doc.file_name or file_path.name, folder_type, file_size, "Success")
	except Exception as exc:
		_mark_file_upload_failed(file_doc.name)
		_append_backup_log(account, file_doc.file_name or file_path.name, folder_type, file_size, "Failed", str(exc))
		raise


def _upload_database_backup(account, backup_path: Path, access_token: str, target_folder_id: str) -> None:
	if not backup_path.exists():
		raise GoogleDriveError(f"Database backup file was not created: {backup_path}")

	file_size = float(os.path.getsize(backup_path))
	try:
		with backup_path.open("rb") as file_handle:
			_upload_file_to_drive(
				access_token=access_token,
				folder_id=target_folder_id,
				file_name=backup_path.name,
				file_handle=file_handle,
				file_size=int(file_size),
			)
		_append_backup_log(account, backup_path.name, "Database", file_size, "Success")
	except Exception as exc:
		_append_backup_log(account, backup_path.name, "Database", file_size, "Failed", str(exc))
		raise


def _append_backup_log(
	account,
	file_name: str,
	folder_type: str,
	size: float,
	status: str,
	error_message: str | None = None,
) -> None:
	frappe.get_doc(
		{
			"doctype": "Backup Log",
			"cloud_storage_account": account.name,
			"account_email": account.account_email,
			"file_name": file_name,
			"folder_type": folder_type,
			"size": size,
			"status": status,
			"error_message": error_message,
			"timestamp": now_datetime(),
		}
	).insert(ignore_permissions=True)


def _select_target_account_name(file_doc=None) -> str | None:
	file_module = _get_file_module(file_doc)
	connected_accounts = _get_connected_upload_accounts()

	target = _pick_best_account(_filter_accounts_for_module(connected_accounts, file_module))
	if target:
		return target.name

	fallback_accounts = _get_fallback_accounts()
	fallback_target = _pick_best_account(_filter_accounts_for_module(fallback_accounts, file_module))
	if fallback_target:
		return fallback_target.name

	fallback_target = _pick_best_account(_filter_accounts_for_module(fallback_accounts, None))
	if fallback_target:
		return fallback_target.name
	return None


def _get_connected_upload_accounts():
	return _get_upload_accounts({"connection_status": "Connected", "auto_sync_uploads": 1}, "modified desc")


def _get_fallback_accounts():
	return _get_upload_accounts(
		{"connection_status": "Connected", "allow_fallback": 1, "auto_sync_uploads": 1},
		"is_default_upload desc, fallback_priority asc, modified desc",
	)


def _get_upload_accounts(filters: dict, order_by: str):
	return frappe.get_all(
		ACCOUNT_DOCTYPE,
		filters=filters,
		fields=["name", "is_default_upload", "used_space", "total_quota", "reserve_space_gb", "fallback_priority", "modified"],
		order_by=order_by,
	)


def _pick_best_account(accounts) -> object | None:
	eligible_accounts = [account for account in accounts if not _is_account_full(account)]
	if not eligible_accounts:
		return None

	eligible_accounts.sort(
		key=lambda account: (
			0 if cint(account.is_default_upload) else 1,
			cint(account.fallback_priority or 100),
			-float(account.total_quota or 0) + float(account.used_space or 0),
		)
	)
	return eligible_accounts[0]


def _filter_accounts_for_module(accounts, file_module: str | None):
	if file_module:
		matching_account_names = _get_account_names_for_module(accounts, file_module)
		matching_accounts = [account for account in accounts if account.name in matching_account_names]
		if matching_accounts:
			return matching_accounts

	unrestricted_account_names = _get_account_names_without_module_routes(accounts)
	return [account for account in accounts if account.name in unrestricted_account_names]


def _is_account_full(account) -> bool:
	total_quota = float(account.total_quota or 0)
	used_space = float(account.used_space or 0)
	reserve_space = float(account.reserve_space_gb or 0)
	if total_quota <= 0:
		return False
	return used_space >= max(total_quota - reserve_space, 0)


def _get_file_module(file_doc) -> str | None:
	attached_to_doctype = getattr(file_doc, "attached_to_doctype", None) if file_doc else None
	if not attached_to_doctype:
		return None
	doctype_table = DocType("DocType")
	modules = (
		frappe.qb.from_(doctype_table)
		.select(doctype_table.module)
		.where(doctype_table.name == attached_to_doctype)
		.limit(1)
	).run(pluck=True)
	return modules[0] if modules else None


def _get_account_names_for_module(accounts, module_name: str) -> set[str]:
	account_names = [account.name for account in accounts]
	if not account_names:
		return set()
	module_route = DocType("Cloud Storage Module Route")
	return set(
		(
			frappe.qb.from_(module_route)
			.select(module_route.parent)
			.where(
				(module_route.parent.isin(account_names))
				& (module_route.parenttype == ACCOUNT_DOCTYPE)
				& (module_route.module == module_name)
			)
		).run(pluck=True)
	)


def _get_account_names_without_module_routes(accounts) -> set[str]:
	account_names = [account.name for account in accounts]
	if not account_names:
		return set()
	module_route = DocType("Cloud Storage Module Route")
	configured_account_names = set(
		(
			frappe.qb.from_(module_route)
			.select(module_route.parent)
			.where(
				(module_route.parent.isin(account_names))
				& (module_route.parenttype == ACCOUNT_DOCTYPE)
			)
		).run(pluck=True)
	)
	return {account_name for account_name in account_names if account_name not in configured_account_names}


def _resolve_target_folder_id(account, file_doc, access_token: str) -> str | None:
	file_module = _get_file_module(file_doc)
	if not file_module:
		return account.private_folder_id if file_doc.is_private else account.public_folder_id

	route_row = _get_module_route(account, file_module)
	if not route_row:
		return account.private_folder_id if file_doc.is_private else account.public_folder_id

	return _ensure_module_folder(account, route_row, access_token, is_private=bool(file_doc.is_private))


def _get_module_route(account, module_name: str):
	for row in account.get("module_routes") or []:
		if (row.module or "") == module_name:
			return row
	return None


def _ensure_module_folder(account, route_row, access_token: str, *, is_private: bool) -> str:
	fieldname = "private_folder_id" if is_private else "public_folder_id"
	root_folder_id = account.private_folder_id if is_private else account.public_folder_id
	if not root_folder_id:
		raise GoogleDriveError("Account root folder is not configured for module routing.")

	existing_folder_id = route_row.get(fieldname)
	if existing_folder_id:
		return existing_folder_id

	folder_id = _find_folder_id(access_token, route_row.module, parent_id=root_folder_id)
	if not folder_id:
		folder_id = _create_drive_folder(access_token, route_row.module, parent_id=root_folder_id)

	route_row.set(fieldname, folder_id)
	account.save(ignore_permissions=True, ignore_version=True)
	return folder_id


def _ensure_public_file_permission(access_token: str, upload_result: dict) -> None:
	file_id = upload_result.get("id")
	if not file_id:
		raise GoogleDriveError("Google Drive did not return a file ID for public sharing.")

	permissions_response = requests.get(
		GOOGLE_PERMISSIONS_URL_TEMPLATE.format(file_id=file_id),
		headers={"Authorization": f"Bearer {access_token}"},
		params={"fields": "permissions(id,type,role,allowFileDiscovery)"},
		timeout=30,
	)
	if not permissions_response.ok:
		raise GoogleDriveError(permissions_response.text)

	permissions = permissions_response.json().get("permissions") or []
	public_permission_exists = any(
		permission.get("type") == "anyone" and permission.get("role") == "reader"
		for permission in permissions
	)

	if not public_permission_exists:
		create_permission_response = requests.post(
			GOOGLE_PERMISSIONS_URL_TEMPLATE.format(file_id=file_id),
			headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
			params={"sendNotificationEmail": "false"},
			json={"role": "reader", "type": "anyone", "allowFileDiscovery": False},
			timeout=30,
		)
		if not create_permission_response.ok:
			raise GoogleDriveError(create_permission_response.text)

	metadata_response = requests.get(
		f"{GOOGLE_FILES_URL}/{file_id}",
		headers={"Authorization": f"Bearer {access_token}"},
		params={"fields": "id,webViewLink,webContentLink"},
		timeout=30,
	)
	if metadata_response.ok:
		upload_result.update(metadata_response.json())


def _mark_file_uploaded(file_name: str, account_name: str, upload_result: dict, is_private: bool) -> None:
	drive_link = _resolve_drive_link(upload_result, is_private=is_private)
	frappe.db.set_value(
		"File",
		file_name,
		{
			"file_url": drive_link,
			"uploaded_to_google_drive": 1,
			"drive_bucket_google_account": account_name,
			"drive_bucket_google_file_id": upload_result.get("id"),
			"drive_bucket_google_file_link": drive_link,
			"drive_bucket_drive_status": "Uploaded",
		},
		update_modified=False,
	)


def _mark_file_upload_failed(file_name: str) -> None:
	frappe.db.set_value(
		"File",
		file_name,
		{
			"drive_bucket_drive_status": "Failed",
		},
		update_modified=False,
	)


def _resolve_drive_link(upload_result: dict, *, is_private: bool) -> str:
	if is_private:
		return upload_result.get("webViewLink") or upload_result.get("webContentLink") or ""
	return upload_result.get("webContentLink") or upload_result.get("webViewLink") or ""


def _delete_local_file_copy(file_url: str | None, is_private: bool) -> None:
	if not file_url or file_url.startswith(("http://", "https://")):
		return

	try:
		file_name = Path(unquote(file_url)).name
		folder = "private" if is_private else "public"
		file_path = Path(frappe.get_site_path(folder, "files", file_name))
		if file_path.exists():
			file_path.unlink()
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Cloud Backup local cleanup failed for {file_url}")
