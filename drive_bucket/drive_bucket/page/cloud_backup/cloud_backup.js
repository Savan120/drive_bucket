frappe.pages["cloud-backup"].on_page_load = function (wrapper) {
	new DriveBucketConsole(wrapper);
};

class DriveBucketConsole {
	constructor(wrapper) {
		this.wrapper = $(wrapper);
		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: __("Drive Bucket"),
			single_column: true,
		});
		this.state = { accounts: [], summary: null, importedFiles: [], selectedAccount: null };
		this.injectStyles();
		this.buildLayout();
		this.bindActions();
		this.load();
	}

	injectStyles() {
		if (document.getElementById("drive-bucket-console-styles")) return;

		const style = document.createElement("style");
		style.id = "drive-bucket-console-styles";
		style.textContent = `
			.drive-bucket-console {
				--db-shell: radial-gradient(circle at top left, #f2f4e8 0%, #eef1e6 30%, #f8f7f1 100%);
				--db-card: rgba(255, 255, 255, 0.96);
				--db-card-strong: #ffffff;
				--db-border: #d6dcc7;
				--db-border-strong: #c0caab;
				--db-shadow: 0 20px 50px rgba(37, 51, 17, 0.08);
				--db-text: #16200f;
				--db-muted: #607054;
				--db-olive: #31411f;
				--db-moss: #718a3f;
				--db-gold: #bf9440;
				--db-red: #c45845;
				--db-blue: #3a6fa8;
				--db-surface: #f8faef;
				--db-success-soft: #eef6e3;
				--db-warning-soft: #fff5df;
				--db-danger-soft: #fdebe7;
				background: var(--db-shell);
				border-radius: 30px;
				padding: 20px;
				min-height: calc(100vh - 180px);
			}
			.drive-bucket-console * { box-sizing: border-box; }
			.db-topbar {
				display: flex;
				align-items: center;
				justify-content: space-between;
				gap: 16px;
				margin-bottom: 14px;
			}
			.db-topbar-copy h1 {
				margin: 0;
				font-size: 28px;
				line-height: 1.05;
				letter-spacing: -0.03em;
				color: var(--db-text);
				font-weight: 800;
			}
			.db-topbar-copy p {
				margin: 6px 0 0;
				color: var(--db-muted);
				font-size: 13px;
			}
			.db-topbar-actions {
				display: flex;
				align-items: center;
				gap: 10px;
				flex-wrap: wrap;
			}
			.db-hero {
				background:
					radial-gradient(circle at top right, rgba(221, 191, 122, 0.24), transparent 30%),
					linear-gradient(135deg, #243116 0%, #31411f 42%, #4c642c 100%);
				border-radius: 28px;
				color: #fbfbf5;
				padding: 28px;
				display: grid;
				grid-template-columns: minmax(0, 1.15fr) minmax(320px, 0.85fr);
				gap: 20px;
				box-shadow: 0 26px 54px rgba(33, 41, 21, 0.16);
			}
			.db-hero h2 {
				margin: 0;
				font-size: 38px;
				line-height: 1.02;
				letter-spacing: -0.03em;
				font-weight: 800;
				color: #fbfbf5;
			}
			.db-hero p {
				margin: 12px 0 0;
				max-width: 700px;
				color: rgba(251, 251, 245, 0.82);
				font-size: 15px;
				line-height: 1.55;
			}
			.db-chip-row,
			.db-stat-grid,
			.db-shell-grid,
			.db-insight-grid,
			.db-policy-list,
			.db-account-grid,
			.db-import-list {
				display: grid;
				gap: 12px;
			}
			.db-chip-row {
				grid-template-columns: repeat(3, minmax(0, 1fr));
				margin-top: 18px;
			}
			.db-chip {
				background: rgba(255, 255, 255, 0.1);
				border: 1px solid rgba(255, 255, 255, 0.16);
				border-radius: 18px;
				padding: 14px 16px;
				backdrop-filter: blur(6px);
			}
			.db-chip-label {
				font-size: 11px;
				letter-spacing: 0.08em;
				text-transform: uppercase;
				color: rgba(247, 245, 238, 0.7);
			}
			.db-chip-value {
				margin-top: 6px;
				font-size: 26px;
				font-weight: 700;
				color: #ffffff;
			}
			.db-hero-panel {
				background: rgba(10, 16, 7, 0.16);
				border: 1px solid rgba(255, 255, 255, 0.12);
				border-radius: 24px;
				padding: 20px;
				backdrop-filter: blur(8px);
				display: flex;
				flex-direction: column;
				justify-content: space-between;
			}
			.db-hero-panel h3,
			.db-section-head h3,
			.db-card-title {
				margin: 0;
				font-weight: 700;
				letter-spacing: -0.02em;
			}
			.db-hero-panel p {
				margin: 10px 0 0;
				font-size: 13px;
				color: rgba(251, 251, 245, 0.8);
			}
			.db-alert {
				border-radius: 18px;
				padding: 14px 16px;
				font-size: 13px;
				line-height: 1.45;
				border: 1px solid transparent;
			}
			.db-alert.warning {
				background: rgba(255, 245, 223, 0.16);
				border-color: rgba(255, 245, 223, 0.24);
				color: #fff5df;
			}
			.db-alert.success {
				background: rgba(238, 246, 227, 0.16);
				border-color: rgba(238, 246, 227, 0.22);
				color: #eef6e3;
			}
			.db-shell-grid {
				grid-template-columns: minmax(0, 1.35fr) minmax(360px, 0.95fr);
				margin-top: 20px;
			}
			.db-card {
				background: var(--db-card);
				border: 1px solid var(--db-border);
				border-radius: 26px;
				padding: 20px;
				box-shadow: var(--db-shadow);
				color: var(--db-text);
			}
			.db-section-head {
				display: flex;
				align-items: center;
				justify-content: space-between;
				gap: 12px;
				margin-bottom: 14px;
			}
			.db-section-head p,
			.db-card-subtitle {
				margin: 4px 0 0;
				font-size: 12px;
				color: var(--db-muted);
			}
			.db-account-grid {
				grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
			}
			.db-account-card {
				border: 1px solid var(--db-border);
				border-radius: 22px;
				background: var(--db-card-strong);
				padding: 16px;
				display: flex;
				flex-direction: column;
				gap: 14px;
				position: relative;
				overflow: hidden;
			}
			.db-account-card.is-default {
				border-color: rgba(191, 148, 64, 0.72);
				box-shadow: inset 0 0 0 1px rgba(191, 148, 64, 0.22);
			}
			.db-account-card.is-default::after {
				content: "Default Fallback";
				position: absolute;
				top: 14px;
				right: -38px;
				background: #31411f;
				color: #fff;
				font-size: 10px;
				font-weight: 700;
				padding: 6px 38px;
				transform: rotate(36deg);
				letter-spacing: 0.08em;
			}
			.db-account-row,
			.db-account-meta,
			.db-log-row {
				display: flex;
				align-items: center;
				justify-content: space-between;
				gap: 12px;
			}
			.db-pill {
				display: inline-flex;
				align-items: center;
				padding: 6px 10px;
				border-radius: 999px;
				font-size: 11px;
				font-weight: 700;
			}
			.db-pill.green { background: #e8f4e2; color: #476523; }
			.db-pill.red { background: #fde8e4; color: #a63f30; }
			.db-pill.gold { background: #fff3dc; color: #9b6a14; }
			.db-pill.blue { background: #eaf3ff; color: #356ea9; }
			.db-pill.slate { background: #f1f4ea; color: #5f6c52; }
			.db-meter {
				height: 10px;
				background: #edf1e4;
				border-radius: 999px;
				overflow: hidden;
			}
			.db-meter > span {
				display: block;
				height: 100%;
				border-radius: inherit;
				background: linear-gradient(90deg, #5d6f35 0%, #c49a45 100%);
			}
			.db-action-row {
				display: flex;
				flex-wrap: wrap;
				gap: 10px;
			}
			.db-btn {
				border: 0;
				border-radius: 14px;
				padding: 10px 14px;
				font-weight: 700;
				font-size: 12px;
				cursor: pointer;
				transition: transform 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
			}
			.db-btn:hover { transform: translateY(-1px); }
			.db-btn.primary { background: #27321a; color: #f7f5ee; }
			.db-btn.secondary { background: #edf1e4; color: #33411d; }
			.db-btn.ghost { background: transparent; border: 1px solid var(--db-border); color: var(--db-text); }
			.db-btn.wide { width: 100%; justify-content: center; }
			.db-policy-list {
				margin-top: 14px;
			}
			.db-policy {
				border-radius: 18px;
				background: #f7f8f2;
				border: 1px solid var(--db-border);
				padding: 14px;
				font-size: 13px;
				color: var(--db-muted);
			}
			.db-log-list,
			.db-import-list {
				display: flex;
				flex-direction: column;
				gap: 10px;
			}
			.db-log-item,
			.db-import-item {
				border-radius: 16px;
				border: 1px solid var(--db-border);
				background: #fbfbf8;
				padding: 12px 14px;
			}
			.db-log-item strong,
			.db-import-item strong {
				display: block;
				color: var(--db-text);
			}
			.db-empty {
				border: 1px dashed var(--db-border);
				background: rgba(255, 255, 255, 0.58);
				border-radius: 18px;
				padding: 24px;
				text-align: center;
				color: var(--db-muted);
			}
			.db-search-row {
				display: grid;
				grid-template-columns: minmax(180px, 220px) 1fr auto;
				gap: 10px;
				margin-top: 14px;
			}
			.db-search-row input,
			.db-search-row select {
				border: 1px solid var(--db-border);
				background: #fff;
				border-radius: 14px;
				padding: 10px 12px;
				font-size: 13px;
			}
			.db-side-stack {
				display: flex;
				flex-direction: column;
				gap: 14px;
			}
			.db-insight-grid {
				grid-template-columns: repeat(2, minmax(0, 1fr));
			}
			.db-insight {
				background: var(--db-surface);
				border: 1px solid var(--db-border);
				border-radius: 18px;
				padding: 14px;
			}
			.db-insight strong {
				display: block;
				font-size: 22px;
				line-height: 1;
				color: var(--db-text);
				margin-bottom: 6px;
			}
			.db-insight span {
				font-size: 12px;
				color: var(--db-muted);
			}
			.db-step-list {
				display: flex;
				flex-direction: column;
				gap: 10px;
			}
			.db-step {
				display: grid;
				grid-template-columns: 34px 1fr;
				gap: 12px;
				align-items: start;
				padding: 12px 14px;
				border-radius: 18px;
				border: 1px solid var(--db-border);
				background: #fbfbf7;
			}
			.db-step-no {
				width: 34px;
				height: 34px;
				border-radius: 50%;
				background: #31411f;
				color: #fff;
				display: flex;
				align-items: center;
				justify-content: center;
				font-size: 12px;
				font-weight: 700;
			}
			.db-step strong {
				display: block;
				color: var(--db-text);
				font-size: 13px;
				margin-bottom: 2px;
			}
			.db-step p {
				margin: 0;
				font-size: 12px;
				color: var(--db-muted);
				line-height: 1.45;
			}
			@media (max-width: 1100px) {
				.db-hero,
				.db-shell-grid { grid-template-columns: 1fr; }
			}
			@media (max-width: 760px) {
				.db-chip-row,
				.db-account-grid,
				.db-insight-grid { grid-template-columns: 1fr; }
				.drive-bucket-console { padding: 12px; }
				.db-hero { padding: 18px; }
				.db-topbar { flex-direction: column; align-items: flex-start; }
				.db-search-row { grid-template-columns: 1fr; }
			}
		`;
		document.head.appendChild(style);
	}

	buildLayout() {
		this.page.body.addClass("no-border");
		this.$root = $(`
			<div class="drive-bucket-console">
				<div class="db-topbar">
					<div class="db-topbar-copy">
						<h1>Drive Bucket Control Center</h1>
						<p>One place to route uploads, protect fallback storage, and attach files from Google Drive without confusing users.</p>
					</div>
					<div class="db-topbar-actions">
						<button class="db-btn primary js-connect-drive">${__("Connect Google Drive")}</button>
						<button class="db-btn secondary js-refresh-console">${__("Refresh Console")}</button>
					</div>
				</div>
				<section class="db-hero">
					<div>
						<h2>Make upload routing obvious, safe, and client-ready.</h2>
						<p>Choose a default fallback drive, see which accounts are close to full, and give your team a clean path for both automatic uploads and direct Drive attachments.</p>
						<div class="db-chip-row js-summary"></div>
					</div>
					<div class="db-hero-panel">
						<div>
							<h3>Routing Intelligence</h3>
							<p class="js-routing-copy">Loading current drive routing policy...</p>
						</div>
						<div class="db-alert warning js-setup-alert">Checking setup quality...</div>
					</div>
				</section>
				<div class="db-shell-grid">
					<section class="db-card">
						<div class="db-section-head">
							<div>
								<h3>Managed Drives</h3>
								<p>Each card shows who owns the drive, whether it can be used as fallback, and the latest upload activity.</p>
							</div>
						</div>
						<div class="db-account-grid js-account-grid"></div>
					</section>
					<div class="db-side-stack">
						<section class="db-card">
							<div class="db-section-head">
								<div>
									<h3>Next Best Setup</h3>
									<p>Simple guidance for admins so the module is easy to explain to clients.</p>
								</div>
							</div>
							<div class="db-step-list js-step-list"></div>
						</section>
						<section class="db-card">
							<div class="db-section-head">
								<div>
									<h3>Import From Google Drive</h3>
									<p>Search one connected drive and attach the selected file directly into ERPNext.</p>
								</div>
							</div>
							<div class="db-search-row">
								<select class="js-account-selector"></select>
								<input type="text" class="js-search-query" placeholder="Search Google Drive files by name" />
								<button class="db-btn primary js-search-drive">${__("Search")}</button>
							</div>
							<div class="db-import-list js-import-list" style="margin-top:14px;"></div>
						</section>
						<section class="db-card">
							<div class="db-section-head">
								<div>
									<h3>Routing Snapshot</h3>
									<p>A quick client-facing explanation of how your upload policy behaves.</p>
								</div>
							</div>
							<div class="db-insight-grid js-insight-grid"></div>
							<div class="db-policy-list js-policy-list"></div>
						</section>
					</div>
				</div>
			</div>
		`);
		this.$root.appendTo(this.page.body);
	}

	bindActions() {
		this.$root.on("click", ".js-connect-drive", () => this.connectDrive());
		this.$root.on("click", ".js-refresh-console", () => this.load());
		this.$root.on("click", ".js-set-default", (event) => this.setDefault($(event.currentTarget).data("account")));
		this.$root.on("click", ".js-open-account", (event) => frappe.set_route("Form", "Cloud Storage Account", $(event.currentTarget).data("account")));
		this.$root.on("click", ".js-sync-account", (event) => this.syncAccount($(event.currentTarget).data("account")));
		this.$root.on("click", ".js-search-drive", () => this.searchDriveFiles());
		this.$root.on("click", ".js-import-drive-file", (event) => this.promptImport($(event.currentTarget).data("account"), $(event.currentTarget).data("file-id")));
	}

	async load() {
		const { message } = await frappe.call({
			method: "drive_bucket.cloud_backup.api.control_center.get_console_data",
		});
		this.state = message || { accounts: [], summary: {}, policies: [] };
		this.state.selectedAccount = this.state.accounts[0]?.name || null;
		this.render();
	}

	render() {
		this.renderSummary();
		this.renderSetupAlert();
		this.renderAccounts();
		this.renderPolicies();
		this.renderSteps();
		this.renderInsights();
		this.renderAccountSelector();
	}

	renderSummary() {
		const summary = this.state.summary || {};
		const chips = [
			{ label: "Connected Drives", value: summary.connected_accounts || 0 },
			{ label: "Used / Quota", value: `${summary.total_used_space_gb || 0} / ${summary.total_quota_gb || 0} GB` },
			{ label: "Fallback Default", value: summary.default_account || "Not set" },
		];
		this.$root.find(".js-summary").html(chips.map((chip) => `
			<div class="db-chip">
				<div class="db-chip-label">${frappe.utils.escape_html(chip.label)}</div>
				<div class="db-chip-value">${frappe.utils.escape_html(String(chip.value))}</div>
			</div>
		`).join(""));

		const routingText = summary.default_account
			? `User-linked drives are preferred first. If a user's drive is full or unavailable, uploads fall back to ${summary.default_account}.`
			: "No system-wide default drive is set yet. User-linked drives will be used when available.";
		this.$root.find(".js-routing-copy").text(routingText);
	}

	renderSetupAlert() {
		const summary = this.state.summary || {};
		const guestAccounts = (this.state.accounts || []).filter((account) => account.linked_user === "Guest");
		let cssClass = "warning";
		let message = "Pick one default fallback drive so uploads still succeed when a user's drive is missing or full.";

		if (summary.default_account) {
			cssClass = "success";
			message = `Default fallback drive is set to ${summary.default_account}. New uploads will still prefer each user's linked drive first.`;
		}

		if (guestAccounts.length) {
			cssClass = "warning";
			message = `${message} Also review ${guestAccounts.length} drive account(s) linked to Guest and assign them to a real ERPNext user if they are not shared fallback drives.`;
		}

		const $alert = this.$root.find(".js-setup-alert");
		$alert.removeClass("warning success").addClass(cssClass).text(message);
	}

	renderAccounts() {
		const $grid = this.$root.find(".js-account-grid");
		if (!this.state.accounts.length) {
			$grid.html(`<div class="db-empty">No Google Drive accounts are connected yet.</div>`);
			return;
		}

		$grid.html(this.state.accounts.map((account) => {
			const percent = Math.min(account.usage_percent || 0, 100);
			const statusClass = account.connection_status === "Connected" ? "green" : "red";
			const fullBadge = account.is_full ? `<span class="db-pill red">Quota Full</span>` : `<span class="db-pill blue">Free ${account.free_space_gb} GB</span>`;
			const ownerBadge = account.linked_user === "Guest"
				? `<span class="db-pill red">Shared / Guest</span>`
				: `<span class="db-pill slate">${frappe.utils.escape_html(account.linked_user || "No user selected")}</span>`;
			return `
				<article class="db-account-card ${account.is_default_upload ? "is-default" : ""}">
					<div class="db-account-row">
						<div>
							<div class="db-card-title">${frappe.utils.escape_html(account.account_email)}</div>
							<div class="db-card-subtitle">Reserve ${account.reserve_space_gb} GB before fallback triggers</div>
						</div>
						<span class="db-pill ${statusClass}">${frappe.utils.escape_html(account.connection_status || "Unknown")}</span>
					</div>
					<div class="db-account-meta">
						<span class="db-pill gold">${account.is_default_upload ? "Default Fallback Drive" : "Primary User Drive"}</span>
						${ownerBadge}
						${fullBadge}
					</div>
					<div>
						<div class="db-account-meta">
							<strong>${account.used_space} GB</strong>
							<span>${account.total_quota} GB</span>
						</div>
						<div class="db-meter" style="margin-top:8px;"><span style="width:${percent}%;"></span></div>
					</div>
					<div class="db-card-subtitle">
						Fallback: ${account.allow_fallback ? "Allowed" : "Blocked"} | Auto Sync: ${account.auto_sync_uploads ? "On" : "Off"} | Priority: ${account.fallback_priority}
					</div>
					${account.status_note ? `<div class="db-card-subtitle">${frappe.utils.escape_html(account.status_note)}</div>` : ""}
					<div class="db-action-row">
						<button class="db-btn secondary js-open-account" data-account="${frappe.utils.escape_html(account.name)}">${__("Open Account")}</button>
						<button class="db-btn ghost js-sync-account" data-account="${frappe.utils.escape_html(account.name)}">${__("Sync Quota")}</button>
						${account.is_default_upload ? "" : `<button class="db-btn primary js-set-default" data-account="${frappe.utils.escape_html(account.name)}">${__("Make Default")}</button>`}
					</div>
					<div class="db-log-list">
						${(account.recent_logs || []).length ? (account.recent_logs || []).map((log) => `
							<div class="db-log-item">
								<strong>${frappe.utils.escape_html(log.file_name || "Unknown file")}</strong>
								<div class="db-log-row">
									<span>${frappe.utils.escape_html(log.folder_type || "-")} | ${frappe.utils.escape_html(log.status || "-")}</span>
									<span>${frappe.datetime.str_to_user(log.timestamp)}</span>
								</div>
								${log.error_message ? `<div class="db-card-subtitle">${frappe.utils.escape_html(log.error_message)}</div>` : ""}
							</div>
						`).join("") : `<div class="db-empty">No uploads logged for this drive yet.</div>`}
					</div>
				</article>
			`;
		}).join(""));
	}

	renderPolicies() {
		this.$root.find(".js-policy-list").html((this.state.policies || []).map((policy) => `
			<div class="db-policy">${frappe.utils.escape_html(policy)}</div>
		`).join(""));
	}

	renderSteps() {
		const hasDefault = Boolean(this.state.summary?.default_account);
		const guestAccounts = (this.state.accounts || []).filter((account) => account.linked_user === "Guest").length;
		const steps = [
			{
				title: hasDefault ? "Default fallback drive is already configured" : "Choose one default fallback drive",
				copy: hasDefault
					? `Current fallback drive: ${this.state.summary.default_account}.`
					: "Select one managed drive as the system fallback so uploads never fail when a user has no eligible drive.",
			},
			{
				title: "Give each active user a primary drive",
				copy: "Each ERPNext user who uploads files should have one linked Google account so the first routing choice is always obvious.",
			},
			{
				title: guestAccounts ? "Review shared Guest-linked drives" : "Shared drives look healthy",
				copy: guestAccounts
					? `${guestAccounts} connected drive(s) are linked to Guest. Keep them only if they are truly shared fallback drives.`
					: "No Guest-linked drive needs immediate cleanup.",
			},
		];

		this.$root.find(".js-step-list").html(steps.map((step, index) => `
			<div class="db-step">
				<div class="db-step-no">${index + 1}</div>
				<div>
					<strong>${frappe.utils.escape_html(step.title)}</strong>
					<p>${frappe.utils.escape_html(step.copy)}</p>
				</div>
			</div>
		`).join(""));
	}

	renderInsights() {
		const accounts = this.state.accounts || [];
		const fullCount = accounts.filter((account) => account.is_full).length;
		const guestCount = accounts.filter((account) => account.linked_user === "Guest").length;
		const defaultAccount = this.state.summary?.default_account || "Not set";
		const insights = [
			{ value: defaultAccount, label: "Active fallback target" },
			{ value: fullCount, label: "Drives currently at fallback threshold" },
			{ value: guestCount, label: "Shared or Guest-linked drives to review" },
			{ value: accounts.filter((account) => account.auto_sync_uploads).length, label: "Drives accepting auto uploads" },
		];

		this.$root.find(".js-insight-grid").html(insights.map((insight) => `
			<div class="db-insight">
				<strong>${frappe.utils.escape_html(String(insight.value))}</strong>
				<span>${frappe.utils.escape_html(insight.label)}</span>
			</div>
		`).join(""));
	}

	renderAccountSelector() {
		this.$root.find(".js-account-selector").html((this.state.accounts || []).map((account) => `
			<option value="${frappe.utils.escape_html(account.name)}" ${this.state.selectedAccount === account.name ? "selected" : ""}>
				${frappe.utils.escape_html(account.account_email)}
			</option>
		`).join(""));
	}

	async connectDrive() {
		const { message } = await frappe.call({
			method: "drive_bucket.cloud_backup.api.google_auth.get_connect_url",
		});
		if (!message?.url) {
			frappe.throw(__("Could not generate the Google connect URL."));
		}
		window.location.href = message.url;
	}

	async setDefault(accountName) {
		await frappe.call({
			method: "drive_bucket.cloud_backup.api.control_center.set_default_upload_account",
			args: { account_name: accountName },
		});
		frappe.show_alert({ message: __("Default upload drive updated."), indicator: "green" });
		await this.load();
	}

	async syncAccount(accountName) {
		await frappe.call({
			method: "drive_bucket.cloud_backup.api.google_auth.ensure_backup_folders",
			args: { account_name: accountName },
		});
		await frappe.call({
			method: "drive_bucket.cloud_backup.api.google_auth.sync_quota",
			args: { account_name: accountName },
		});
		frappe.show_alert({ message: __("Drive quota refreshed."), indicator: "green" });
		await this.load();
	}

	async searchDriveFiles() {
		const accountName = this.$root.find(".js-account-selector").val() || this.state.accounts[0]?.name;
		if (!accountName) {
			frappe.msgprint(__("Connect at least one Google Drive account first."));
			return;
		}

		const query = this.$root.find(".js-search-query").val();
		const { message } = await frappe.call({
			method: "drive_bucket.cloud_backup.api.control_center.list_drive_files",
			args: {
				account_name: accountName,
				query,
			},
		});
		const files = message?.files || [];
		const $list = this.$root.find(".js-import-list");
		if (!files.length) {
			$list.html(`<div class="db-empty">No Google Drive files matched this search.</div>`);
			return;
		}
		$list.html(files.map((file) => `
			<div class="db-import-item">
				<strong>${frappe.utils.escape_html(file.name)}</strong>
				<div class="db-log-row">
					<span>${frappe.utils.escape_html(file.mimeType || "Unknown type")}</span>
					<span>${frappe.datetime.str_to_user(file.modifiedTime)}</span>
				</div>
				<div class="db-action-row" style="margin-top:10px;">
					<button class="db-btn primary js-import-drive-file" data-account="${frappe.utils.escape_html(accountName)}" data-file-id="${frappe.utils.escape_html(file.id)}">${__("Attach to Document")}</button>
					${file.webViewLink ? `<a class="db-btn ghost" href="${frappe.utils.escape_html(file.webViewLink)}" target="_blank" rel="noopener noreferrer">${__("Open in Drive")}</a>` : ""}
				</div>
			</div>
		`).join(""));
	}

	async promptImport(accountName, fileId) {
		frappe.prompt(
			[
				{ fieldname: "attached_to_doctype", label: __("Attach To DocType"), fieldtype: "Data", reqd: 1 },
				{ fieldname: "attached_to_name", label: __("Attach To Document"), fieldtype: "Data", reqd: 1 },
				{ fieldname: "attached_to_field", label: __("Attach To Field"), fieldtype: "Data" },
				{ fieldname: "is_private", label: __("Private File"), fieldtype: "Check", default: 1 },
			],
			async (values) => {
				await frappe.call({
					method: "drive_bucket.cloud_backup.api.control_center.import_drive_file",
					args: {
						account_name: accountName,
						drive_file_id: fileId,
						attached_to_doctype: values.attached_to_doctype,
						attached_to_name: values.attached_to_name,
						attached_to_field: values.attached_to_field,
						is_private: values.is_private,
					},
				});
				frappe.show_alert({ message: __("Google Drive file attached successfully."), indicator: "green" });
			},
			__("Attach Google Drive File"),
			__("Attach")
		);
	}
}
