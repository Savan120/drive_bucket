from __future__ import annotations

import frappe
from frappe.model.document import Document


class CloudStorageAccount(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF
		from drive_bucket.cloud_backup.doctype.cloud_storage_account_user_access.cloud_storage_account_user_access import (
			CloudStorageAccountUserAccess,
		)
		from drive_bucket.cloud_backup.doctype.cloud_storage_module_route.cloud_storage_module_route import (
			CloudStorageModuleRoute,
		)

		account_email: DF.Data
		access_token: DF.Password | None
		backup_every_days: DF.Int
		backup_folder_id: DF.Data | None
		connection_status: DF.Literal["Connected", "Expired", "Revoked", "Failed"] | None
		is_default_backup_drive: DF.Check
		last_backup_on: DF.Date | None
		last_synced: DF.Datetime | None
		linked_user: DF.Link | None
		module_routes: DF.Table[CloudStorageModuleRoute]
		private_folder_id: DF.Data | None
		public_folder_id: DF.Data | None
		refresh_token: DF.Password | None
		route_module: DF.Literal[
			"",
			"Accounts",
			"Assets",
			"Automation",
			"Bulk Transaction",
			"Buying",
			"Communication",
			"Contacts",
			"Core",
			"CRM",
			"CSF KE",
			"Custom",
			"Desk",
			"Drive Bucket",
			"EDI",
			"Email",
			"ERPNext Integrations",
			"Erpnext Kra Integration",
			"eTims",
			"Geo",
			"HR",
			"Integrations",
			"Maintenance",
			"Manufacturing",
			"Offline Sync Core",
			"Payroll",
			"Portal",
			"Printing",
			"Projects",
			"Quality Management",
			"Regional",
			"Selling",
			"Setup",
			"Stock",
			"Subcontracting",
			"Support",
			"Telephony",
			"Utilities",
			"Website",
			"Workflow",
		] | None
		token_expiry: DF.Datetime | None
		total_quota: DF.Float
		user_access: DF.Table[CloudStorageAccountUserAccess]
		used_space: DF.Float
	# end: auto-generated types

	def validate(self) -> None:
		if not self.linked_user and frappe.session.user and frappe.session.user != "Guest":
			self.linked_user = frappe.session.user
		self.backup_every_days = max(int(self.backup_every_days or 1), 1)
		self._normalize_user_access()
		self._validate_user_access()
		self._sync_legacy_route_module()
		self._validate_module_routes()

	def _sync_legacy_route_module(self) -> None:
		if not self.route_module:
			return
		if any((row.module or "") == self.route_module for row in self.module_routes or []):
			return

		self.append("module_routes", {"module": self.route_module})

	def _validate_module_routes(self) -> None:
		modules = set()
		for row in self.module_routes or []:
			module_name = (row.module or "").strip()
			if not module_name:
				continue
			if module_name in modules:
				frappe.throw(f"Module route {module_name} is already configured for this drive account.")
			modules.add(module_name)

	def _normalize_user_access(self) -> None:
		for row in self.user_access or []:
			if row.can_manage:
				row.can_view = 1
				row.can_upload = 1
				row.can_download = 1
				continue

			if row.can_upload or row.can_download:
				row.can_view = 1
			elif not row.can_view:
				row.can_view = 1

	def _validate_user_access(self) -> None:
		seen_users = set()
		for row in self.user_access or []:
			user = (row.user or "").strip()
			if not user:
				continue
			if user == self.linked_user:
				frappe.throw("Linked User already has full access. Remove them from the User Access table.")
			if user in seen_users:
				frappe.throw(f"User access for {user} is already configured on this drive account.")
			seen_users.add(user)

	def get_access_token_value(self) -> str | None:
		return self.get_password("access_token", raise_exception=False)

	def get_refresh_token_value(self) -> str | None:
		return self.get_password("refresh_token", raise_exception=False)
