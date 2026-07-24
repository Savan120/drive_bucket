from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote_plus, urlencode, urlsplit, urlunsplit

import frappe
import requests
from frappe.utils import get_url, now_datetime

from drive_bucket.cloud_backup.doctype.cloud_storage_account.cloud_storage_account import CloudStorageAccount
from drive_bucket.permissions import require_cloud_storage_account_access

GOOGLE_OAUTH_SCOPE = [
	"https://www.googleapis.com/auth/drive.file",
	"https://www.googleapis.com/auth/userinfo.email",
]
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_ABOUT_URL = "https://www.googleapis.com/drive/v3/about"
GOOGLE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
ACCOUNT_DOCTYPE = "Cloud Storage Account"
FOLDER_NAMES = {
	"private_folder_id": "erpnext_backup_private",
	"public_folder_id": "erpnext_backup_public",
}
BACKUP_FOLDER_NAME = "Database backup"
DEBUG_PREFIX = "[drive_bucket.google_auth]"
BYTES_IN_GB = 1024**3


class GoogleDriveError(frappe.ValidationError):
	"""Raised when Google OAuth or Drive calls fail."""


@dataclass
class GoogleCredentials:
	client_id: str
	client_secret: str
	redirect_uri: str


@frappe.whitelist(methods=["GET", "POST"])
def get_connect_url() -> dict[str, str]:
	credentials = _get_google_credentials()
	state = frappe.generate_hash(length=32)
	_set_oauth_state(state)
	_debug(
		"Generated connect URL state",
		user=frappe.session.user,
		redirect_uri=credentials.redirect_uri,
		client_id=credentials.client_id,
		state=state,
	)
	query = urlencode(
		{
			"client_id": credentials.client_id,
			"redirect_uri": credentials.redirect_uri,
			"response_type": "code",
			"scope": " ".join(GOOGLE_OAUTH_SCOPE),
			"access_type": "offline",
			"include_granted_scopes": "true",
			"prompt": "consent",
			"state": state,
		},
		quote_via=quote_plus,
	)
	return {"url": f"{GOOGLE_AUTH_URL}?{query}"}

# drive_bucket.cloud_backup.api.google_auth.oauth_callback
@frappe.whitelist(allow_guest=True, methods=["GET"])
def oauth_callback(code: str | None = None, state: str | None = None, error: str | None = None) -> dict[str, Any]:
	state_data = _consume_oauth_state(state)
	linked_user = state_data.get("user") if state_data else None
	account: CloudStorageAccount | None = None
	_debug(
		"OAuth callback received",
		user=frappe.session.user,
		linked_user=linked_user,
		has_code=bool(code),
		has_state=bool(state),
		error=error,
	)
	if error:
		return _redirect_after_oauth(error=f"Google OAuth failed: {error}")
	if not code:
		return _redirect_after_oauth(error="Missing OAuth authorization code.")
	if not linked_user:
		return _redirect_after_oauth(error="OAuth state is invalid or has expired.")

	try:
		credentials = _get_google_credentials()
		token_payload = {
			"code": code,
			"client_id": credentials.client_id,
			"client_secret": credentials.client_secret,
			"redirect_uri": credentials.redirect_uri,
			"grant_type": "authorization_code",
		}
		token_data = _post_form(GOOGLE_TOKEN_URL, token_payload)
		access_token = token_data.get("access_token")
		refresh_token = token_data.get("refresh_token")
		expires_in = token_data.get("expires_in")
		_debug(
			"Token exchange complete",
			linked_user=linked_user,
			has_access_token=bool(access_token),
			has_refresh_token=bool(refresh_token),
			expires_in=expires_in,
		)
		if not access_token:
			raise GoogleDriveError("Google did not return an access token.")

		profile = _google_get(GOOGLE_USERINFO_URL, access_token)
		account_email = profile.get("email")
		_debug("Fetched Google profile", linked_user=linked_user, account_email=account_email)
		if not account_email:
			raise GoogleDriveError("Google did not return the account email.")

		account = _get_or_create_account(account_email)
		_debug("Loaded account doc", account_name=account.name, existing_linked_user=account.linked_user)
		if account.linked_user and account.linked_user != linked_user and not _is_storage_admin(linked_user):
			raise frappe.PermissionError("This Google Drive account is already linked to another user.")

		account.linked_user = linked_user
		account.access_token = access_token
		if refresh_token:
			account.refresh_token = refresh_token
		elif not account.get_refresh_token_value():
			raise GoogleDriveError("Google did not return a refresh token.")
		account.token_expiry = _expiry_from_seconds(expires_in)
		account.connection_status = "Connected"
		account.save(ignore_permissions=True, ignore_version=True)
		frappe.db.commit()
		_debug(
			"Account saved after OAuth",
			account_name=account.name,
			account_email=account.account_email,
			linked_user=account.linked_user,
			status=account.connection_status,
		)

		try:
			_debug("Starting folder ensure", account_name=account.name)
			_ensure_backup_folders(account)
			frappe.db.commit()
			_debug(
				"Folder ensure complete",
				account_name=account.name,
				private_folder_id=account.private_folder_id,
				public_folder_id=account.public_folder_id,
			)
			_debug("Starting quota sync", account_name=account.name)
			_sync_quota(account)
			frappe.db.commit()
			_debug(
				"Quota sync complete",
				account_name=account.name,
				used_space=account.used_space,
				total_quota=account.total_quota,
			)
		except Exception:
			account.connection_status = "Failed"
			account.save(ignore_permissions=True, ignore_version=True)
			frappe.db.commit()
			_debug("Post-connect setup failed", account_name=account.name, status=account.connection_status)
			raise
	except Exception as exc:
		_debug("OAuth callback failed", account_name=account.name if account else None, error=str(exc))
		frappe.log_error(frappe.get_traceback(), "Cloud Backup OAuth Callback Failed")
		return _redirect_after_oauth(account_name=account.name if account else None, error=str(exc))

	return _redirect_after_oauth(account_name=account.name, success_message=f"Connected {account.account_email}")


@frappe.whitelist(methods=["POST"])
def sync_quota(account_name: str) -> dict[str, Any]:
	account = _get_accessible_account(account_name, permission="manage")
	return _sync_quota(account)


def _sync_quota(account: CloudStorageAccount) -> dict[str, Any]:
	access_token = _get_valid_access_token(account)
	_debug("Sync quota request", account_name=account.name)
	response = _google_get(GOOGLE_ABOUT_URL, access_token, params={"fields": "storageQuota"})
	storage_quota = response.get("storageQuota") or {}
	total_quota_bytes = float(storage_quota.get("limit") or 0)
	used_space_bytes = float(storage_quota.get("usage") or 0)
	total_quota = round(total_quota_bytes / BYTES_IN_GB, 3) if total_quota_bytes else 0.0
	used_space = round(used_space_bytes / BYTES_IN_GB, 3) if used_space_bytes else 0.0

	account.total_quota = total_quota
	account.used_space = used_space
	account.last_synced = now_datetime()
	account.connection_status = "Connected"
	account.save(ignore_permissions=True, ignore_version=True)
	_debug(
		"Quota values prepared",
		account_name=account.name,
		total_quota_bytes=total_quota_bytes,
		used_space_bytes=used_space_bytes,
		total_quota_gb=total_quota,
		used_space_gb=used_space,
	)

	return {
		"account_name": account.name,
		"total_quota": account.total_quota,
		"used_space": account.used_space,
		"last_synced": account.last_synced,
	}


@frappe.whitelist(methods=["POST"])
def ensure_backup_folders(account_name: str) -> dict[str, str]:
	account = _get_accessible_account(account_name, permission="manage")
	return _ensure_backup_folders(account)


def _ensure_backup_folders(account: CloudStorageAccount) -> dict[str, str]:
	access_token = _get_valid_access_token(account)
	updated = False

	for fieldname, folder_name in FOLDER_NAMES.items():
		folder_id = getattr(account, fieldname, None)
		if folder_id and _folder_exists(access_token, folder_id, parent_id="root"):
			_debug("Folder already present", account_name=account.name, fieldname=fieldname, folder_id=folder_id)
		else:
			if folder_id:
				_debug(
					"Stored folder missing, recreating",
					account_name=account.name,
					fieldname=fieldname,
					folder_id=folder_id,
				)
			existing_folder_id = _find_folder_id(access_token, folder_name, parent_id="root")
			if existing_folder_id:
				setattr(account, fieldname, existing_folder_id)
				updated = True
				_debug("Found existing folder", account_name=account.name, fieldname=fieldname, folder_id=existing_folder_id)
			else:
				created_folder_id = _create_drive_folder(access_token, folder_name, parent_id="root")
				setattr(account, fieldname, created_folder_id)
				updated = True
				_debug("Created folder", account_name=account.name, fieldname=fieldname, folder_id=created_folder_id)

	if account.is_default_backup_drive:
		backup_folder_id = getattr(account, "backup_folder_id", None)
		if backup_folder_id and _folder_exists(access_token, backup_folder_id, parent_id="root"):
			_debug("Backup folder already present", account_name=account.name, folder_id=backup_folder_id)
		else:
			existing_backup_folder_id = _find_folder_id(access_token, BACKUP_FOLDER_NAME, parent_id="root")
			if existing_backup_folder_id:
				account.backup_folder_id = existing_backup_folder_id
				updated = True
				_debug("Found existing backup folder", account_name=account.name, folder_id=existing_backup_folder_id)
			else:
				account.backup_folder_id = _create_drive_folder(access_token, BACKUP_FOLDER_NAME, parent_id="root")
				updated = True
				_debug("Created backup folder", account_name=account.name, folder_id=account.backup_folder_id)

	_ensure_module_route_folders(account, access_token)

	if updated:
		account.save(ignore_permissions=True, ignore_version=True)

	return {
		"backup_folder_id": account.backup_folder_id or "",
		"private_folder_id": account.private_folder_id or "",
		"public_folder_id": account.public_folder_id or "",
	}


def _ensure_module_route_folders(account: CloudStorageAccount, access_token: str) -> None:
	module_routes = account.get("module_routes") or []
	if not module_routes:
		return

	updated = False
	for row in module_routes:
		module_name = (row.module or "").strip()
		if not module_name:
			continue

		for fieldname, parent_folder_id in (
			("private_folder_id", account.private_folder_id),
			("public_folder_id", account.public_folder_id),
		):
			if not parent_folder_id:
				continue
			folder_id = row.get(fieldname)
			if folder_id and _folder_exists(access_token, folder_id, parent_id=parent_folder_id):
				continue
			existing_folder_id = _find_folder_id(access_token, module_name, parent_id=parent_folder_id)
			if existing_folder_id:
				row.set(fieldname, existing_folder_id)
			else:
				row.set(fieldname, _create_drive_folder(access_token, module_name, parent_id=parent_folder_id))
			updated = True

	if updated:
		account.save(ignore_permissions=True, ignore_version=True)


def _folder_exists(access_token: str, folder_id: str, parent_id: str | None = None) -> bool:
	response = requests.get(
		f"{GOOGLE_FILES_URL}/{folder_id}",
		headers={"Authorization": f"Bearer {access_token}"},
		params={"fields": "id,trashed,mimeType,parents"},
		timeout=30,
	)
	if not response.ok:
		return False
	payload = response.json()
	return (
		payload.get("mimeType") == "application/vnd.google-apps.folder"
		and not payload.get("trashed")
		and (not parent_id or parent_id in (payload.get("parents") or []))
	)


def _find_folder_id(access_token: str, folder_name: str, parent_id: str | None = None) -> str | None:
	search_parts = [
		f"name = '{folder_name}'",
		"mimeType = 'application/vnd.google-apps.folder'",
		"trashed = false",
	]
	if parent_id:
		search_parts.append(f"'{parent_id}' in parents")

	params = {
		"q": " and ".join(search_parts),
		"fields": "files(id,name)",
		"pageSize": 1,
	}
	response = _google_get(GOOGLE_FILES_URL, access_token, params=params)
	files = response.get("files") or []
	return files[0]["id"] if files else None


def _create_drive_folder(access_token: str, folder_name: str, parent_id: str | None = None) -> str:
	payload = {"name": folder_name, "mimeType": "application/vnd.google-apps.folder"}
	if parent_id:
		payload["parents"] = [parent_id]
	response = requests.post(
		GOOGLE_FILES_URL,
		headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
		json=payload,
		timeout=30,
	)
	data = _parse_google_response(response)
	folder_id = data.get("id")
	if not folder_id:
		raise GoogleDriveError(f"Google Drive did not return a folder ID for {folder_name}.")
	return folder_id


def refresh_account_access_token(account_name: str) -> CloudStorageAccount:
	account = frappe.get_doc(ACCOUNT_DOCTYPE, account_name)
	refresh_token = account.get_refresh_token_value()
	_debug("Refreshing access token", account_name=account.name, has_refresh_token=bool(refresh_token))
	if not refresh_token:
		account.connection_status = "Expired"
		account.save(ignore_permissions=True, ignore_version=True)
		raise GoogleDriveError(f"Refresh token is missing for {account.name}.")

	credentials = _get_google_credentials()
	payload = {
		"client_id": credentials.client_id,
		"client_secret": credentials.client_secret,
		"refresh_token": refresh_token,
		"grant_type": "refresh_token",
	}
	try:
		token_data = _post_form(GOOGLE_TOKEN_URL, payload)
	except Exception:
		account.connection_status = "Expired"
		account.save(ignore_permissions=True, ignore_version=True)
		raise

	access_token = token_data.get("access_token")
	if not access_token:
		account.connection_status = "Expired"
		account.save(ignore_permissions=True, ignore_version=True)
		raise GoogleDriveError(f"Google did not return an access token for {account.name}.")

	account.access_token = access_token
	account.token_expiry = _expiry_from_seconds(token_data.get("expires_in"))
	account.connection_status = "Connected"
	account.save(ignore_permissions=True, ignore_version=True)
	_debug("Access token refreshed", account_name=account.name, expires_in=token_data.get("expires_in"))
	return account


def _get_or_create_account(account_email: str) -> CloudStorageAccount:
	name = frappe.db.exists(ACCOUNT_DOCTYPE, {"account_email": account_email})
	if name:
		return frappe.get_doc(ACCOUNT_DOCTYPE, name)
	account = frappe.new_doc(ACCOUNT_DOCTYPE)
	account.account_email = account_email
	return account


def _get_accessible_account(account_name: str, permission: str = "view") -> CloudStorageAccount:
	account = frappe.get_doc(ACCOUNT_DOCTYPE, account_name)
	require_cloud_storage_account_access(account.name, permission)
	return account


def _get_google_credentials() -> GoogleCredentials:
	settings = frappe.get_single("Google Settings")
	if not settings.enable:
		raise GoogleDriveError("Google Settings is disabled.")
	client_id = settings.client_id
	client_secret = settings.get_password("client_secret", raise_exception=False)
	if not client_id or not client_secret:
		raise GoogleDriveError("Google Settings must contain Client ID and Client Secret.")
	return GoogleCredentials(
		client_id=client_id,
		client_secret=client_secret,
		redirect_uri=_get_redirect_uri(),
	)


def _get_redirect_uri() -> str:
	return f"{_get_site_base_url()}/api/method/drive_bucket.cloud_backup.api.google_auth.oauth_callback"


def _set_oauth_state(state: str) -> None:
	frappe.cache().set_value(
		_oauth_state_cache_key(state),
		{"user": frappe.session.user},
		expires_in_sec=600,
	)


def _consume_oauth_state(state: str | None) -> dict[str, Any] | None:
	if not state:
		return None
	cache_key = _oauth_state_cache_key(state)
	stored_state = frappe.cache().get_value(cache_key)
	frappe.cache().delete_value(cache_key)
	return stored_state


def _oauth_state_cache_key(state: str) -> str:
	return f"drive_bucket:google_oauth_state:{state}"


def _expiry_from_seconds(expires_in: Any) -> datetime:
	seconds = int(expires_in or 3600)
	return now_datetime() + timedelta(seconds=seconds)


def _get_valid_access_token(account: CloudStorageAccount) -> str:
	if not account.token_expiry or account.token_expiry <= now_datetime() + timedelta(minutes=10):
		account = refresh_account_access_token(account.name)
	access_token = account.get_access_token_value()
	if not access_token:
		raise GoogleDriveError(f"Access token is missing for {account.name}.")
	return access_token


def _is_storage_admin(user: str | None = None) -> bool:
	return bool({"System Manager", "Storage Admin"}.intersection(set(frappe.get_roles(user))))


def _post_form(url: str, payload: dict[str, Any]) -> dict[str, Any]:
	_debug("POST form request", url=url, payload_keys=list(payload.keys()))
	response = requests.post(url, data=payload, timeout=30)
	return _parse_google_response(response)


def _google_get(url: str, access_token: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
	_debug("GET request", url=url, params=params)
	response = requests.get(
		url,
		headers={"Authorization": f"Bearer {access_token}"},
		params=params,
		timeout=30,
	)
	return _parse_google_response(response)


def _parse_google_response(response: requests.Response) -> dict[str, Any]:
	if response.ok:
		_debug("Google response OK", status_code=response.status_code, url=str(response.url))
		return response.json()
	try:
		payload = response.json()
	except ValueError:
		payload = {"error_description": response.text}
	error = payload.get("error")
	error_message = error.get("message") if isinstance(error, dict) else error
	message = payload.get("error_description") or error_message or response.text
	_debug("Google response failed", status_code=response.status_code, url=str(response.url), error_detail=message)
	raise GoogleDriveError(message)


def _redirect_after_oauth(account_name: str | None = None, success_message: str | None = None, error: str | None = None):
	if success_message:
		frappe.msgprint(success_message, alert=True, indicator="green")
	if error:
		frappe.msgprint(error, alert=True, indicator="red")
	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = _oauth_redirect_location(account_name, error)
	return {}


def _oauth_redirect_location(account_name: str | None, error: str | None) -> str:
	if account_name:
		base_url = f"{_get_site_base_url()}/app/cloud-storage-account/{account_name}"
	else:
		base_url = f"{_get_site_base_url()}/app/cloud-storage-account"
	query_parts = []
	if account_name:
		query_parts.append("oauth_status=connected")
	if error:
		query_parts.append(f"oauth_error={quote_plus(error)}")
	return f"{base_url}?{'&'.join(query_parts)}" if query_parts else base_url




def _get_site_base_url() -> str:
	host_name = (getattr(frappe.conf, "host_name", None) or "").rstrip("/")
	if host_name:
		return _normalize_public_url(host_name)
	return _normalize_public_url(get_url().rstrip("/"))


def _normalize_public_url(url: str) -> str:
	parts = urlsplit(url)
	netloc = parts.netloc
	if netloc.endswith(".ngrok-free.app:8000"):
		netloc = netloc.removesuffix(":8000")
	return urlunsplit((parts.scheme, netloc, parts.path.rstrip("/"), "", ""))


def _debug(message: str, **kwargs) -> None:
	details = ", ".join(f"{key}={value!r}" for key, value in kwargs.items())
	print(f"{DEBUG_PREFIX} {message}" + (f" | {details}" if details else ""))
