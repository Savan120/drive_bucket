frappe.ui.form.on("Cloud Storage Account", {
	refresh(frm) {
		configure_form(frm);
		add_actions(frm);
		show_status_alerts(frm);
	},
});

function configure_form(frm) {
	if (frm.is_new()) {
		frm.disable_save();
		frm.set_intro(__("Use Connect Google Drive to create a linked account automatically."), "blue");
	} else {
		frm.enable_save();
		frm.set_intro("");
	}
}

function add_actions(frm) {
	frm.add_custom_button(__("Connect Google Drive"), async () => {
		await launch_google_connect();
	}, __("Actions"));

	if (frm.doc.name && !frm.is_new()) {
		frm.add_custom_button(__("Sync Quota"), async () => {
			await call_account_action(frm, "drive_bucket.cloud_backup.api.google_auth.sync_quota", {
				account_name: frm.doc.name,
			}, __("Quota synced successfully."));
		}, __("Actions"));

		frm.add_custom_button(__("Ensure Backup Folders"), async () => {
			await call_account_action(frm, "drive_bucket.cloud_backup.api.google_auth.ensure_backup_folders", {
				account_name: frm.doc.name,
			}, __("Backup folders verified successfully."));
		}, __("Actions"));

		frm.add_custom_button(__("Run Backup Now"), async () => {
			await call_account_action(frm, "drive_bucket.cloud_backup.api.control_center.run_account_backup", {
				account_name: frm.doc.name,
			}, __("Backup completed successfully."));
		}, __("Actions"));

		frm.add_custom_button(__("Download Uploads ZIP"), () => {
			download_account_uploads_zip(frm);
		}, __("Actions"));
	}
}

async function launch_google_connect() {
	const { message } = await frappe.call({
		method: "drive_bucket.cloud_backup.api.google_auth.get_connect_url",
	});

	if (!message?.url) {
		frappe.throw(__("Could not generate the Google connect URL."));
	}

	window.location.href = message.url;
}

async function call_account_action(frm, method, args, success_message) {
	await frappe.call({ method, args });
	frappe.show_alert({ message: success_message, indicator: "green" });
	await frm.reload_doc();
}

function download_account_uploads_zip(frm) {
	const method = "drive_bucket.cloud_backup.api.control_center.download_account_uploads_zip";
	const params = new URLSearchParams({ account_name: frm.doc.name });
	window.open(`/api/method/${method}?${params.toString()}`, "_blank");
}

function show_status_alerts(frm) {
	const params = new URLSearchParams(window.location.search);
	const oauthStatus = params.get("oauth_status");
	const oauthError = params.get("oauth_error");

	if (oauthStatus === "connected") {
		frappe.show_alert({ message: __("Google Drive connected successfully."), indicator: "green" });
		params.delete("oauth_status");
		params.delete("oauth_error");
		update_history(params);
	}

	if (oauthError) {
		frappe.msgprint({
			title: __("Google Drive Connection Failed"),
			message: decodeURIComponent(oauthError),
			indicator: "red",
		});
		params.delete("oauth_status");
		params.delete("oauth_error");
		update_history(params);
	}
}

function update_history(params) {
	const nextQuery = params.toString();
	const nextUrl = nextQuery ? `${window.location.pathname}?${nextQuery}` : window.location.pathname;
	window.history.replaceState({}, "", nextUrl);
}
