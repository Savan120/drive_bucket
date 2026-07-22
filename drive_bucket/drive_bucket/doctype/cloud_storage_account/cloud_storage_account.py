from __future__ import annotations

import frappe
from frappe.model.document import Document


class CloudStorageAccount(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		account_email: DF.Data
		access_token: DF.Password | None
		auto_sync_uploads: DF.Check
		allow_fallback: DF.Check
		fallback_priority: DF.Int
		connection_status: DF.Literal["Connected", "Expired", "Revoked", "Failed"] | None
		is_default_upload: DF.Check
		last_synced: DF.Datetime | None
		linked_user: DF.Link | None
		private_folder_id: DF.Data | None
		public_folder_id: DF.Data | None
		refresh_token: DF.Password | None
		reserve_space_gb: DF.Float
		status_note: DF.SmallText | None
		token_expiry: DF.Datetime | None
		total_quota: DF.Float
		used_space: DF.Float
	# end: auto-generated types

	def validate(self) -> None:
		if not self.linked_user and frappe.session.user and frappe.session.user != "Guest":
			self.linked_user = frappe.session.user
		self.reserve_space_gb = float(self.reserve_space_gb or 0)
		self.fallback_priority = int(self.fallback_priority or 100)
		self._validate_default_upload_uniqueness()

	def _validate_default_upload_uniqueness(self) -> None:
		if not self.is_default_upload:
			return

		existing = frappe.db.get_value(
			self.doctype,
			{
				"is_default_upload": 1,
				"name": ["!=", self.name],
			},
			["name", "account_email"],
			as_dict=True,
		)
		if existing:
			frappe.throw(
				f"Default upload drive is already set to {existing.account_email}. Remove it there before assigning a new default."
			)

	def get_access_token_value(self) -> str | None:
		return self.get_password("access_token", raise_exception=False)

	def get_refresh_token_value(self) -> str | None:
		return self.get_password("refresh_token", raise_exception=False)
