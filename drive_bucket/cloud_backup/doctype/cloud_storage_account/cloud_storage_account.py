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
		connection_status: DF.Literal["Connected", "Expired", "Revoked", "Failed"] | None
		last_synced: DF.Datetime | None
		linked_user: DF.Link | None
		private_folder_id: DF.Data | None
		public_folder_id: DF.Data | None
		refresh_token: DF.Password | None
		token_expiry: DF.Datetime | None
		total_quota: DF.Float
		used_space: DF.Float
	# end: auto-generated types

	def validate(self) -> None:
		if not self.linked_user and frappe.session.user and frappe.session.user != "Guest":
			self.linked_user = frappe.session.user

	def get_access_token_value(self) -> str | None:
		return self.get_password("access_token", raise_exception=False)

	def get_refresh_token_value(self) -> str | None:
		return self.get_password("refresh_token", raise_exception=False)
