from __future__ import annotations

import frappe


def execute() -> None:
	if not frappe.db.has_column("Cloud Storage Account", "route_module"):
		return

	account_names = frappe.get_all(
		"Cloud Storage Account",
		filters={"route_module": ["!=", ""]},
		pluck="name",
	)
	for account_name in account_names:
		account = frappe.get_doc("Cloud Storage Account", account_name)
		module_name = (account.get("route_module") or "").strip()
		if not module_name:
			continue
		if any((row.module or "") == module_name for row in account.get("module_routes") or []):
			continue

		account.append("module_routes", {"module": module_name})
		account.save(ignore_permissions=True, ignore_version=True)
