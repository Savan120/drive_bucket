from __future__ import annotations

import frappe

ADMIN_ROLES = {"System Manager", "Storage Admin"}


def get_cloud_storage_account_permission_query(user: str | None = None) -> str:
	user = user or frappe.session.user
	if _is_admin(user):
		return ""
	return f"`tabCloud Storage Account`.`linked_user` = {frappe.db.escape(user)}"


def has_cloud_storage_account_permission(doc, user: str | None = None, permission_type: str | None = None) -> bool:
	user = user or frappe.session.user
	if _is_admin(user):
		return True
	linked_user = doc.get("linked_user") if isinstance(doc, dict) else getattr(doc, "linked_user", None)
	return bool(linked_user and linked_user == user)


def _is_admin(user: str) -> bool:
	return bool(ADMIN_ROLES.intersection(set(frappe.get_roles(user))))
