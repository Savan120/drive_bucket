from __future__ import annotations

import json
import mimetypes
import os
from pathlib import Path
from typing import BinaryIO
from urllib.parse import unquote

import frappe
import requests
from frappe.utils import cint, now_datetime

from drive_bucket.cloud_backup.api.google_auth import (
	ACCOUNT_DOCTYPE,
	GOOGLE_FILES_URL,
	GoogleDriveError,
	ensure_backup_folders,
	refresh_account_access_token,
	sync_quota,
)

GOOGLE_RESUMABLE_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable"


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
	account_names = frappe.get_all(ACCOUNT_DOCTYPE, filters={"connection_status": "Connected"}, pluck="name")
	for account_name in account_names:
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

	for file_doc in _get_files_to_backup():
		_upload_file_for_account(account, file_doc)

	sync_quota(account.name)


def enqueue_file_upload(file_doc, method: str | None = None) -> None:
	if getattr(file_doc, "is_folder", 0) or not file_doc.file_url or file_doc.uploaded_to_google_drive:
		return
	frappe.db.set_value("File", file_doc.name, "drive_bucket_drive_status", "Queued", update_modified=False)

	user_candidates = _get_candidate_users(file_doc)
	frappe.enqueue(
		"drive_bucket.cloud_backup.tasks.upload_file_to_linked_accounts",
		queue="default",
		timeout=900,
		enqueue_after_commit=True,
		job_id=f"drive_bucket:file_upload:{file_doc.name}",
		deduplicate=True,
		file_name=file_doc.name,
		user_candidates=user_candidates,
	)


def upload_file_to_linked_accounts(file_name: str, user_candidates: list[str] | None = None) -> None:
	file_doc = frappe.get_doc("File", file_name)
	if file_doc.is_folder or not file_doc.file_url or file_doc.uploaded_to_google_drive:
		return

	account_name = _select_target_account_name(user_candidates or _get_candidate_users(file_doc))
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
	target_folder_id = account.private_folder_id if file_doc.is_private else account.public_folder_id
	file_path = _resolve_file_path(file_doc)
	file_size = float(os.path.getsize(file_path))
	try:
		with file_path.open("rb") as file_handle:
			upload_result = _upload_file_to_drive(
				access_token=account.get_password("access_token"),
				folder_id=target_folder_id,
				file_name=file_doc.file_name or file_path.name,
				file_handle=file_handle,
				file_size=int(file_size),
			)
		_mark_file_uploaded(file_doc.name, account.name, upload_result)
		_append_backup_log(account, file_doc.file_name or file_path.name, folder_type, file_size, "Success")
	except Exception as exc:
		_mark_file_upload_failed(file_doc.name)
		_append_backup_log(account, file_doc.file_name or file_path.name, folder_type, file_size, "Failed", str(exc))
		raise


def _append_backup_log(
	account,
	file_name: str,
	folder_type: str,
	size: float,
	status: str,
	error_message: str | None = None,
) -> None:
	account.append(
		"backup_logs",
		{
			"file_name": file_name,
			"folder_type": folder_type,
			"size": size,
			"status": status,
			"error_message": error_message,
			"timestamp": now_datetime(),
		},
	)
	account.save(ignore_permissions=True, ignore_version=True)


def _select_target_account_name(user_candidates: list[str]) -> str | None:
	user_accounts = _get_candidate_accounts(user_candidates)
	user_target = _pick_best_account(user_accounts)
	if user_target:
		return user_target.name

	fallback_accounts = _get_fallback_accounts()
	fallback_target = _pick_best_account(fallback_accounts)
	if fallback_target:
		return fallback_target.name
	return None


def _get_candidate_users(file_doc) -> list[str]:
	candidates = []
	for user in [file_doc.owner, file_doc.modified_by, frappe.session.user]:
		if user and user != "Guest" and user not in candidates:
			candidates.append(user)
	return candidates


def _get_candidate_accounts(user_candidates: list[str]):
	accounts = []
	seen = set()
	for user in user_candidates:
		for account in frappe.get_all(
			ACCOUNT_DOCTYPE,
			filters={"connection_status": "Connected", "linked_user": user, "auto_sync_uploads": 1},
			fields=["name", "is_default_upload", "used_space", "total_quota", "reserve_space_gb", "fallback_priority", "modified"],
			order_by="modified desc",
		):
			if account.name not in seen:
				accounts.append(account)
				seen.add(account.name)
	return accounts


def _get_fallback_accounts():
	return frappe.get_all(
		ACCOUNT_DOCTYPE,
		filters={"connection_status": "Connected", "allow_fallback": 1, "auto_sync_uploads": 1},
		fields=["name", "is_default_upload", "used_space", "total_quota", "reserve_space_gb", "fallback_priority", "modified"],
		order_by="is_default_upload desc, fallback_priority asc, modified desc",
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


def _is_account_full(account) -> bool:
	total_quota = float(account.total_quota or 0)
	used_space = float(account.used_space or 0)
	reserve_space = float(account.reserve_space_gb or 0)
	if total_quota <= 0:
		return False
	return used_space >= max(total_quota - reserve_space, 0)


def _mark_file_uploaded(file_name: str, account_name: str, upload_result: dict) -> None:
	frappe.db.set_value(
		"File",
		file_name,
		{
			"uploaded_to_google_drive": 1,
			"drive_bucket_google_account": account_name,
			"drive_bucket_google_file_id": upload_result.get("id"),
			"drive_bucket_google_file_link": upload_result.get("webViewLink"),
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
