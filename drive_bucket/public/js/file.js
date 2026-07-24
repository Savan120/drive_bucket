frappe.ui.form.on("File", {
	refresh(frm) {
		add_drive_bucket_actions(frm);
	},
});

function add_drive_bucket_actions(frm) {
	if (!frm.doc.uploaded_to_google_drive || !frm.doc.drive_bucket_google_file_id) {
		return;
	}

	if (frm.doc.drive_bucket_google_file_link) {
		frm.add_custom_button(__("Open in Google Drive"), () => {
			window.open(frm.doc.drive_bucket_google_file_link, "_blank", "noopener,noreferrer");
		}, __("Drive Bucket"));
	}

	if (!frm.doc.is_private) {
		frm.add_custom_button(__("Enable Public Link"), async () => {
			const { message } = await frappe.call({
				method: "drive_bucket.cloud_backup.api.file_access.enable_public_link",
				args: { file_name: frm.doc.name },
			});
			frappe.show_alert({ message: __("Public Google Drive link enabled."), indicator: "green" });
			if (message?.google_file_link) {
				await frm.reload_doc();
			}
		}, __("Drive Bucket"));
	}

	frm.add_custom_button(__("View Drive Access"), async () => {
		const { message } = await frappe.call({
			method: "drive_bucket.cloud_backup.api.file_access.get_drive_access",
			args: { file_name: frm.doc.name },
		});

		const permissions = message?.permissions || [];
		if (!permissions.length) {
			frappe.msgprint(__("No Google Drive access entries were returned for this file."));
			return;
		}

		const rows = permissions
			.map((permission) => {
				const label = permission.emailAddress || permission.displayName || permission.type || __("Unknown");
				return `<tr><td>${frappe.utils.escape_html(label)}</td><td>${frappe.utils.escape_html(permission.role || "-")}</td></tr>`;
			})
			.join("");

		frappe.msgprint({
			title: __("Google Drive Access"),
			message: `
				<div style="max-height: 320px; overflow: auto;">
					<table class="table table-bordered">
						<thead>
							<tr><th>${__("Person / Target")}</th><th>${__("Role")}</th></tr>
						</thead>
						<tbody>${rows}</tbody>
					</table>
				</div>
			`,
		});
	}, __("Drive Bucket"));

	frm.add_custom_button(__("Grant Drive Access"), () => {
		open_grant_access_dialog(frm);
	}, __("Drive Bucket"));
}

function open_grant_access_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Grant Google Drive Access"),
		fields: [
			{
				fieldname: "user",
				fieldtype: "Link",
				label: __("ERPNext User"),
				options: "User",
				description: __("Optional. If selected, the user's email will receive access."),
			},
			{
				fieldname: "email_address",
				fieldtype: "Data",
				label: __("Google Email"),
				description: __("Use this when the recipient is not an ERPNext user."),
			},
			{
				fieldname: "access_role",
				fieldtype: "Select",
				label: __("Access Role"),
				options: "reader\ncommenter\nwriter",
				default: "reader",
				reqd: 1,
			},
			{
				fieldname: "send_notification_email",
				fieldtype: "Check",
				label: __("Send Google Notification Email"),
				default: 1,
			},
		],
		primary_action_label: __("Grant Access"),
		primary_action: async (values) => {
			await frappe.call({
				method: "drive_bucket.cloud_backup.api.file_access.grant_drive_access",
				args: {
					file_name: frm.doc.name,
					user: values.user,
					email_address: values.email_address,
					access_role: values.access_role,
					send_notification_email: values.send_notification_email,
				},
			});
			dialog.hide();
			frappe.show_alert({ message: __("Google Drive access granted."), indicator: "green" });
			await frm.reload_doc();
		},
	});

	dialog.show();
}
