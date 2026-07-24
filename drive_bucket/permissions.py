from __future__ import annotations

import frappe
from frappe.query_builder import DocType

ADMIN_ROLES = {"System Manager", "Storage Admin"}
ACCESS_DOCTYPE = "Cloud Storage Account User Access"
ACCOUNT_DOCTYPE = "Cloud Storage Account"
BACKUP_LOG_DOCTYPE = "Backup Log"
VIEW_PERMISSIONS = {"read", "print", "email", "export", "report", "share"}


def get_cloud_storage_account_permission_query(user: str | None = None) -> str:
	user = user or frappe.session.user
	if _is_admin(user):
		return ""

	account = DocType(ACCOUNT_DOCTYPE)
	access = DocType(ACCESS_DOCTYPE)
	access_exists = (
		frappe.qb.from_(access)
		.select(access.name)
		.where(
			(access.parent == account.name)
			& (access.parenttype == ACCOUNT_DOCTYPE)
			& (access.user == user)
		)
	)
	condition = (account.linked_user == user) | access_exists.exists()
	return condition.get_sql(quote_char="`")


def has_cloud_storage_account_permission(doc, user: str | None = None, permission_type: str | None = None) -> bool:
	user = user or frappe.session.user
	permtype = permission_type or "read"
	if permtype == "create":
		return _is_admin(user)
	access = get_cloud_storage_account_access(_get_account_name(doc), user=user)
	if permtype in VIEW_PERMISSIONS:
		return access["can_view"]
	return access["can_manage"]


def get_backup_log_permission_query(user: str | None = None) -> str:
	user = user or frappe.session.user
	if _is_admin(user):
		return ""

	backup_log = DocType(BACKUP_LOG_DOCTYPE)
	account = DocType(ACCOUNT_DOCTYPE)
	access = DocType(ACCESS_DOCTYPE)
	linked_account_exists = (
		frappe.qb.from_(account)
		.select(account.name)
		.where((account.name == backup_log.cloud_storage_account) & (account.linked_user == user))
	)
	access_exists = (
		frappe.qb.from_(access)
		.select(access.name)
		.where(
			(access.parent == backup_log.cloud_storage_account)
			& (access.parenttype == ACCOUNT_DOCTYPE)
			& (access.user == user)
		)
	)
	condition = linked_account_exists.exists() | access_exists.exists()
	return condition.get_sql(quote_char="`")


def has_backup_log_permission(doc, user: str | None = None, permission_type: str | None = None) -> bool:
	user = user or frappe.session.user
	if _is_admin(user):
		return True

	account_name = doc.get("cloud_storage_account") if isinstance(doc, dict) else getattr(doc, "cloud_storage_account", None)
	if not account_name:
		return False

	return has_cloud_storage_account_access(account_name, "view", user=user)


def get_cloud_storage_account_access(account_name: str | None, user: str | None = None) -> dict[str, bool]:
	user = user or frappe.session.user
	if not account_name:
		return _empty_access()
	if _is_admin(user):
		return _full_access()

	account = DocType(ACCOUNT_DOCTYPE)
	linked_user = (
		frappe.qb.from_(account)
		.select(account.linked_user)
		.where(account.name == account_name)
		.limit(1)
	).run(pluck=True)
	if linked_user and linked_user[0] == user:
		return _full_access()

	access = DocType(ACCESS_DOCTYPE)
	access_rows = (
		frappe.qb.from_(access)
		.select(access.can_view, access.can_upload, access.can_download, access.can_manage)
		.where(
			(access.parent == account_name)
			& (access.parenttype == ACCOUNT_DOCTYPE)
			& (access.user == user)
		)
		.limit(1)
	).run(as_dict=True)
	if not access_rows:
		return _empty_access()

	access_row = access_rows[0]
	can_manage = bool(access_row.can_manage)
	can_upload = can_manage or bool(access_row.can_upload)
	can_download = can_manage or bool(access_row.can_download)
	can_view = can_manage or can_upload or can_download or bool(access_row.can_view)
	return {
		"can_view": can_view,
		"can_upload": can_upload,
		"can_download": can_download,
		"can_manage": can_manage,
	}


def has_cloud_storage_account_access(account_name: str | None, permission: str, user: str | None = None) -> bool:
	access = get_cloud_storage_account_access(account_name, user=user)
	return access.get(f"can_{permission}", False)


def require_cloud_storage_account_access(account_name: str | None, permission: str, user: str | None = None) -> None:
	if has_cloud_storage_account_access(account_name, permission, user=user):
		return
	raise frappe.PermissionError(f"You do not have permission to {permission} this cloud storage account.")


def _is_admin(user: str) -> bool:
	return bool(ADMIN_ROLES.intersection(set(frappe.get_roles(user))))


def _get_account_name(doc) -> str | None:
	if isinstance(doc, dict):
		return doc.get("name")
	return getattr(doc, "name", None)


def _empty_access() -> dict[str, bool]:
	return {
		"can_view": False,
		"can_upload": False,
		"can_download": False,
		"can_manage": False,
	}


def _full_access() -> dict[str, bool]:
	return {
		"can_view": True,
		"can_upload": True,
		"can_download": True,
		"can_manage": True,
	}
