from __future__ import annotations

from typing import Any

import frappe

from drive_bucket.cloud_backup.api.google_auth import ACCOUNT_DOCTYPE
from drive_bucket.cloud_backup.tasks import (
	GoogleDriveError,
	_resolve_drive_link,
	_resolve_target_folder_id,
	_select_target_account_name,
	_upload_file_to_drive,
	_ensure_public_file_permission,
	ensure_backup_folders,
	refresh_account_access_token,
	sync_quota,
)


def write_file(*args, **kwargs):
	if args and getattr(args[0], "doctype", None) == "File":
		return _write_file_doc(args[0])
	return _write_file_from_bytes(*args, **kwargs)


def _write_file_doc(file_doc) -> dict[str, Any]:
	if getattr(file_doc, "file_url", None):
		return file_doc.save_file_on_filesystem()

	account_name = _get_target_account_name(file_doc)
	if not account_name:
		return file_doc.save_file_on_filesystem()

	upload_data = _upload_to_drive(
		account_name=account_name,
		file_name=file_doc.file_name,
		content=file_doc._content,
		is_private=file_doc.is_private,
		file_doc=file_doc,
	)
	_apply_drive_metadata(file_doc, upload_data)
	return {"file_name": file_doc.file_name, "file_url": file_doc.file_url}


def _write_file_from_bytes(
	file_name: str,
	content: bytes,
	*,
	content_type: str | None = None,
	is_private: int = 0,
) -> dict[str, Any]:
	del content_type
	account_name = _get_target_account_name()
	if not account_name:
		return _save_file_on_filesystem(file_name, content, is_private=is_private)

	return _upload_to_drive(
		account_name=account_name,
		file_name=file_name,
		content=content,
		is_private=is_private,
	)


def _get_target_account_name(file_doc=None) -> str | None:
	if not frappe.db.exists("DocType", ACCOUNT_DOCTYPE):
		return None

	return _select_target_account_name(file_doc=file_doc)


def _upload_to_drive(*, account_name: str, file_name: str, content: bytes, is_private: int, file_doc=None) -> dict[str, Any]:
	account = frappe.get_doc(ACCOUNT_DOCTYPE, account_name)
	refresh_account_access_token(account.name)
	ensure_backup_folders(account.name)
	account.reload()

	access_token = account.get_password("access_token")
	if not access_token:
		raise GoogleDriveError(f"Access token is missing for {account.name}.")

	target_folder_id = _resolve_target_folder_id(account, file_doc, access_token)
	upload_result = _upload_file_to_drive(
		access_token=access_token,
		folder_id=target_folder_id,
		file_name=file_name,
		file_handle=content,
		file_size=len(content),
	)
	if not is_private:
		_ensure_public_file_permission(access_token, upload_result)
	sync_quota(account.name)

	drive_link = _resolve_drive_link(upload_result, is_private=bool(is_private))
	return {
		"file_name": file_name,
		"file_url": drive_link,
		"uploaded_to_google_drive": 1,
		"drive_bucket_google_account": account.name,
		"drive_bucket_google_file_id": upload_result.get("id"),
		"drive_bucket_google_file_link": drive_link,
		"drive_bucket_drive_status": "Uploaded",
	}


def _apply_drive_metadata(file_doc, upload_data: dict[str, Any]) -> None:
	file_doc.file_url = upload_data["file_url"]
	file_doc.uploaded_to_google_drive = upload_data["uploaded_to_google_drive"]
	file_doc.drive_bucket_google_account = upload_data["drive_bucket_google_account"]
	file_doc.drive_bucket_google_file_id = upload_data["drive_bucket_google_file_id"]
	file_doc.drive_bucket_google_file_link = upload_data["drive_bucket_google_file_link"]
	file_doc.drive_bucket_drive_status = upload_data["drive_bucket_drive_status"]


def _save_file_on_filesystem(file_name: str, content: bytes, *, is_private: int) -> dict[str, Any]:
	from frappe.utils.file_manager import save_file_on_filesystem

	return save_file_on_filesystem(file_name, content, is_private=is_private)
