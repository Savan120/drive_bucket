frappe.listview_settings["Cloud Storage Account"] = {
	onload(listview) {
		hide_manual_create(listview);
		listview.page.add_inner_button(__("Connect Google Drive"), async () => {
			const { message } = await frappe.call({
				method: "drive_bucket.cloud_backup.api.google_auth.get_connect_url",
			});

			if (!message?.url) {
				frappe.throw(__("Could not generate the Google connect URL."));
			}

			window.location.href = message.url;
		});
	},
	refresh(listview) {
		hide_manual_create(listview);
	},
};

function hide_manual_create(listview) {
	listview.can_create = false;
	listview.page.clear_primary_action();
	listview.page.set_primary_action(__("Connect Google Drive"), async () => {
		const { message } = await frappe.call({
			method: "drive_bucket.cloud_backup.api.google_auth.get_connect_url",
		});

		if (!message?.url) {
			frappe.throw(__("Could not generate the Google connect URL."));
		}

		window.location.href = message.url;
	});

	setTimeout(() => {
		$(".btn-new-doc").hide();
		$(".list-empty-state button").hide();
	}, 0);
}
