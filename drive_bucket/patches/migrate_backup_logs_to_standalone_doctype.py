from __future__ import annotations

import frappe


def execute() -> None:
	if not frappe.db.table_exists("Backup Log"):
		return

	if not frappe.db.has_column("Backup Log", "cloud_storage_account"):
		return

	rows = frappe.db.sql(
		"""
		select name, parent
		from `tabBackup Log`
		where ifnull(cloud_storage_account, '') = ''
		  and parenttype = 'Cloud Storage Account'
		  and ifnull(parent, '') != ''
		""",
		as_dict=True,
	)
	if not rows:
		return

	for row in rows:
		account_email = frappe.db.get_value("Cloud Storage Account", row.parent, "account_email")
		frappe.db.set_value(
			"Backup Log",
			row.name,
			{
				"cloud_storage_account": row.parent,
				"account_email": account_email,
			},
			update_modified=False,
		)

	if frappe.db.has_column("Backup Log", "docstatus"):
		frappe.db.sql("update `tabBackup Log` set docstatus = 0 where docstatus is null")
	if frappe.db.has_column("Backup Log", "owner"):
		frappe.db.sql("update `tabBackup Log` set owner = 'Administrator' where ifnull(owner, '') = ''")
	if frappe.db.has_column("Backup Log", "modified_by"):
		frappe.db.sql("update `tabBackup Log` set modified_by = 'Administrator' where ifnull(modified_by, '') = ''")
