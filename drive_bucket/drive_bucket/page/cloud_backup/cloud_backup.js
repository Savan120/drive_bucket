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
			.layout-main-section:has(.drive-bucket-console),
			.page-content:has(.drive-bucket-console),
			.page-body:has(.drive-bucket-console) {
				background:
					radial-gradient(circle at 10% 10%, rgba(111, 76, 255, 0.16), transparent 24%),
					radial-gradient(circle at 92% 14%, rgba(58, 169, 255, 0.14), transparent 22%),
					linear-gradient(180deg, #070b16 0%, #0c1120 50%, #101624 100%) !important;
			}
			.page-head:has(+ .layout-main-section .drive-bucket-console) {
				background: transparent !important;
				border-bottom-color: rgba(255, 255, 255, 0.08) !important;
			}
			.page-head .page-title .title-text,
			.page-head .breadcrumb-container,
			.page-head .breadcrumb-item a,
			.page-head .breadcrumb-item span {
				color: #eaf2ff !important;
			}
			.drive-bucket-console {
				--db-shell: radial-gradient(circle at 12% 8%, rgba(121, 82, 255, 0.34), transparent 26%),
					radial-gradient(circle at 88% 18%, rgba(83, 194, 255, 0.28), transparent 22%),
					radial-gradient(circle at 74% 82%, rgba(255, 121, 85, 0.18), transparent 20%),
					linear-gradient(145deg, #0a1023 0%, #12172b 38%, #1b1525 100%);
				--db-card: rgba(20, 23, 38, 0.58);
				--db-card-strong: rgba(28, 31, 48, 0.56);
				--db-border: rgba(255, 255, 255, 0.12);
				--db-border-strong: rgba(137, 182, 255, 0.28);
				--db-shadow: 0 24px 54px rgba(2, 6, 23, 0.42);
				--db-text: #eff4ff;
				--db-muted: rgba(226, 234, 255, 0.66);
				--db-olive: #7eb7ff;
				--db-moss: #4f8dff;
				--db-gold: #94c4ff;
				--db-red: #ff8e88;
				--db-blue: #77aaff;
				--db-surface: rgba(255, 255, 255, 0.06);
				--db-success-soft: rgba(105, 240, 174, 0.15);
				--db-warning-soft: rgba(126, 183, 255, 0.16);
				--db-danger-soft: rgba(255, 142, 136, 0.18);
				background: var(--db-shell);
				border-radius: 34px;
				padding: 22px;
				min-height: calc(100vh - 180px);
				margin-top: 10px;
				position: relative;
				overflow: hidden;
				border: 1px solid rgba(255, 255, 255, 0.09);
				box-shadow:
					inset 0 1px 0 rgba(255, 255, 255, 0.14),
					0 36px 70px rgba(4, 8, 19, 0.44);
				backdrop-filter: blur(18px);
			}
			.drive-bucket-console::before,
			.drive-bucket-console::after {
				content: "";
				position: absolute;
				border-radius: 50%;
				filter: blur(4px);
				pointer-events: none;
				opacity: 0.9;
			}
			.drive-bucket-console::before {
				width: 340px;
				height: 340px;
				top: -110px;
				right: -90px;
				background: radial-gradient(circle, rgba(82, 157, 255, 0.24) 0%, rgba(82, 157, 255, 0) 70%);
			}
			.drive-bucket-console::after {
				width: 300px;
				height: 300px;
				bottom: -120px;
				left: -80px;
				background: radial-gradient(circle, rgba(164, 101, 255, 0.18) 0%, rgba(164, 101, 255, 0) 72%);
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
				text-shadow: 0 10px 30px rgba(0, 0, 0, 0.25);
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
					linear-gradient(135deg, rgba(255, 255, 255, 0.12), rgba(255, 255, 255, 0.04)),
					radial-gradient(circle at top right, rgba(160, 120, 255, 0.24), transparent 34%),
					radial-gradient(circle at left center, rgba(74, 149, 255, 0.2), transparent 30%),
					linear-gradient(145deg, rgba(18, 23, 40, 0.84), rgba(32, 23, 40, 0.58));
				border-radius: 30px;
				color: #f8fbff;
				padding: 28px;
				display: grid;
				grid-template-columns: minmax(0, 1.15fr) minmax(320px, 0.85fr);
				gap: 20px;
				box-shadow:
					inset 0 1px 0 rgba(255, 255, 255, 0.14),
					0 20px 40px rgba(3, 8, 23, 0.26);
				position: relative;
				overflow: hidden;
				border: 1px solid rgba(255, 255, 255, 0.12);
				backdrop-filter: blur(18px);
			}
			.db-hero::before,
			.db-account-card::before,
			.db-card::before {
				content: "";
				position: absolute;
				inset: 0;
				background:
					linear-gradient(135deg, rgba(255, 255, 255, 0.08), transparent 34%),
					radial-gradient(circle at 78% 20%, rgba(146, 117, 255, 0.14), transparent 28%);
				pointer-events: none;
				opacity: 1;
				transition: none;
				filter: none;
			}
			.db-hero > *,
			.db-account-card > *,
			.db-card > * {
				position: relative;
				z-index: 1;
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
				color: rgba(241, 245, 255, 0.78);
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
				background: linear-gradient(180deg, rgba(255, 255, 255, 0.14), rgba(255, 255, 255, 0.05));
				border: 1px solid rgba(255, 255, 255, 0.14);
				border-radius: 18px;
				padding: 14px 16px;
				backdrop-filter: blur(14px);
				min-width: 0;
				box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.12);
			}
			.db-chip-label {
				font-size: 11px;
				letter-spacing: 0.08em;
				text-transform: uppercase;
				color: rgba(233, 240, 255, 0.68);
			}
			.db-chip-value {
				margin-top: 6px;
				font-size: 26px;
				font-weight: 700;
				color: #ffffff;
				overflow: hidden;
				text-overflow: ellipsis;
				white-space: nowrap;
			}
			.db-hero-panel {
				background: linear-gradient(180deg, rgba(255, 255, 255, 0.1), rgba(255, 255, 255, 0.04));
				border: 1px solid rgba(255, 255, 255, 0.12);
				border-radius: 24px;
				padding: 20px;
				backdrop-filter: blur(16px);
				display: flex;
				align-items: stretch;
				box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.14);
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
				color: rgba(233, 240, 255, 0.76);
			}
			.db-default-meta {
				margin-top: 14px;
				padding: 12px 14px;
				border-radius: 16px;
				background: linear-gradient(180deg, rgba(255, 255, 255, 0.12), rgba(255, 255, 255, 0.04));
				border: 1px solid rgba(255, 255, 255, 0.15);
				backdrop-filter: blur(14px);
				box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.12);
			}
			.db-default-meta-label {
				font-size: 11px;
				letter-spacing: 0.08em;
				text-transform: uppercase;
				color: rgba(233, 240, 255, 0.66);
			}
			.db-default-meta-value {
				margin-top: 6px;
				font-size: 16px;
				font-weight: 700;
				line-height: 1.35;
				color: #ffffff;
				word-break: break-word;
			}
			.db-shell-grid {
				grid-template-columns: 1fr;
				margin-top: 20px;
			}
			.db-card {
				background: var(--db-card);
				border: 1px solid var(--db-border);
				border-radius: 28px;
				padding: 20px;
				box-shadow: var(--db-shadow);
				color: var(--db-text);
				position: relative;
				overflow: hidden;
				backdrop-filter: blur(18px);
				box-shadow:
					inset 0 1px 0 rgba(255, 255, 255, 0.12),
					0 22px 44px rgba(4, 8, 19, 0.28);
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
			.db-section-head h3 {
				color: var(--db-text);
			}
			.db-account-grid {
				grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
			}
			.db-account-grid.is-collapsed .db-account-card:nth-child(n+6) {
				display: none;
			}
			.db-account-card {
				border: 1px solid rgba(255, 255, 255, 0.12);
				border-radius: 24px;
				background: linear-gradient(180deg, rgba(38, 41, 59, 0.5), rgba(23, 26, 40, 0.42));
				padding: 16px;
				display: flex;
				flex-direction: column;
				gap: 14px;
				position: relative;
				overflow: hidden;
				backdrop-filter: blur(16px);
				box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.1);
			}
			.db-account-card.is-default {
				border-color: rgba(131, 180, 255, 0.3);
				box-shadow:
					inset 0 0 0 1px rgba(131, 180, 255, 0.12),
					0 0 0 1px rgba(255, 255, 255, 0.04);
			}
			.db-account-row,
			.db-account-meta,
			.db-log-row {
				display: flex;
				align-items: center;
				justify-content: space-between;
				gap: 12px;
			}
			.db-account-row,
			.db-account-meta {
				flex-wrap: wrap;
			}
			.db-pill {
				display: inline-flex;
				align-items: center;
				padding: 6px 10px;
				border-radius: 999px;
				font-size: 11px;
				font-weight: 700;
			}
			.db-pill.green { background: rgba(112, 234, 170, 0.16); color: #b4ffd2; }
			.db-pill.red { background: rgba(255, 142, 136, 0.16); color: #ffc2be; }
			.db-pill.gold { background: rgba(123, 170, 255, 0.16); color: #cfe2ff; }
			.db-pill.blue { background: rgba(255, 255, 255, 0.08); color: #9cc6ff; }
			.db-pill.slate { background: rgba(255, 255, 255, 0.08); color: #dde8ff; }
			.db-pill.default-flag {
				background: linear-gradient(180deg, rgba(104, 161, 255, 0.78), rgba(42, 103, 210, 0.84));
				color: #ffffff;
				box-shadow:
					inset 0 1px 0 rgba(255, 255, 255, 0.18),
					0 10px 24px rgba(26, 115, 232, 0.18);
			}
			.db-account-title-wrap {
				min-width: 0;
				flex: 1 1 220px;
			}
			.db-card-title {
				overflow-wrap: anywhere;
				line-height: 1.2;
				color: var(--db-text);
			}
			.db-meter {
				height: 10px;
				background: rgba(255, 255, 255, 0.08);
				border-radius: 999px;
				overflow: hidden;
				box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.24);
			}
			.db-meter > span {
				display: block;
				height: 100%;
				border-radius: inherit;
				background: linear-gradient(90deg, #6db4ff 0%, #5a76ff 54%, #8f71ff 100%);
				box-shadow: 0 0 16px rgba(104, 161, 255, 0.3);
			}
			.db-action-row {
				display: flex;
				flex-wrap: wrap;
				gap: 10px;
			}
			.db-btn {
				border: 1px solid rgba(255, 255, 255, 0.12);
				border-radius: 16px;
				padding: 10px 16px;
				font-weight: 700;
				font-size: 12px;
				cursor: pointer;
				transition: transform 0.18s ease, box-shadow 0.18s ease, background 0.18s ease, border-color 0.18s ease;
				backdrop-filter: blur(14px);
				box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.12);
			}
			.db-btn:hover {
				box-shadow:
					inset 0 1px 0 rgba(255, 255, 255, 0.16),
					0 12px 24px rgba(5, 10, 24, 0.24);
			}
			.db-btn.primary {
				background: linear-gradient(180deg, rgba(103, 168, 255, 0.88), rgba(50, 111, 222, 0.9));
				color: #ffffff;
			}
			.db-btn.secondary {
				background: rgba(255, 255, 255, 0.1);
				color: #eff4ff;
			}
			.db-btn.ghost {
				background: rgba(255, 255, 255, 0.04);
				border: 1px solid rgba(255, 255, 255, 0.12);
				color: var(--db-text);
			}
			.db-btn.wide { width: 100%; justify-content: center; }
			.db-policy-list {
				margin-top: 14px;
			}
			.db-policy {
				border-radius: 18px;
				background: rgba(255, 255, 255, 0.06);
				border: 1px solid rgba(255, 255, 255, 0.1);
				padding: 14px;
				font-size: 13px;
				color: var(--db-muted);
				backdrop-filter: blur(12px);
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
				border: 1px solid rgba(255, 255, 255, 0.1);
				background: rgba(255, 255, 255, 0.05);
				padding: 12px 14px;
				backdrop-filter: blur(14px);
				box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
			}
			.db-log-item strong,
			.db-import-item strong {
				display: block;
				color: var(--db-text);
			}
			.db-log-row span,
			.db-import-item span {
				color: var(--db-muted);
			}
			.db-empty {
				border: 1px dashed rgba(255, 255, 255, 0.16);
				background: rgba(255, 255, 255, 0.05);
				border-radius: 18px;
				padding: 24px;
				text-align: center;
				color: var(--db-muted);
				backdrop-filter: blur(12px);
			}
			.db-search-row {
				display: grid;
				grid-template-columns: minmax(180px, 220px) 1fr;
				gap: 10px;
				margin-top: 14px;
			}
			.db-search-row input,
			.db-search-row select {
				border: 1px solid rgba(255, 255, 255, 0.12);
				background: rgba(255, 255, 255, 0.07);
				color: var(--db-text);
				border-radius: 16px;
				padding: 10px 12px;
				font-size: 13px;
				backdrop-filter: blur(14px);
				box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
			}
			.db-search-row input::placeholder {
				color: rgba(223, 232, 255, 0.48);
			}
			.db-search-row select option {
				background: #111827;
				color: #eff4ff;
			}
			.db-side-stack {
				display: flex;
				flex-direction: column;
				gap: 14px;
			}
			.db-collapse-toggle {
				font-size: 12px;
				font-weight: 700;
				color: #cfe2ff;
				cursor: pointer;
				background: rgba(255, 255, 255, 0.08);
				border: 1px solid rgba(255, 255, 255, 0.1);
				padding: 8px 12px;
				border-radius: 999px;
				backdrop-filter: blur(12px);
			}
			.db-collapse-toggle:hover {
				background: rgba(255, 255, 255, 0.12);
			}
			:root:not([data-theme="dark"]) .layout-main-section:has(.drive-bucket-console),
			:root:not([data-theme="dark"]) .page-content:has(.drive-bucket-console),
			:root:not([data-theme="dark"]) .page-body:has(.drive-bucket-console) {
				background:
					radial-gradient(circle at 8% 12%, rgba(132, 173, 255, 0.16), transparent 26%),
					radial-gradient(circle at 92% 16%, rgba(188, 159, 255, 0.18), transparent 22%),
					linear-gradient(180deg, #f7faff 0%, #eef4ff 52%, #f8fbff 100%) !important;
			}
			:root:not([data-theme="dark"]) .page-head:has(+ .layout-main-section .drive-bucket-console) {
				background: transparent !important;
				border-bottom-color: rgba(21, 51, 92, 0.08) !important;
			}
			:root:not([data-theme="dark"]) .page-head .page-title .title-text,
			:root:not([data-theme="dark"]) .page-head .breadcrumb-container,
			:root:not([data-theme="dark"]) .page-head .breadcrumb-item a,
			:root:not([data-theme="dark"]) .page-head .breadcrumb-item span {
				color: #1c2d4a !important;
			}
			:root:not([data-theme="dark"]) .drive-bucket-console {
				--db-shell: radial-gradient(circle at 12% 8%, rgba(114, 163, 255, 0.24), transparent 26%),
					radial-gradient(circle at 88% 18%, rgba(152, 200, 255, 0.28), transparent 24%),
					radial-gradient(circle at 74% 82%, rgba(196, 176, 255, 0.2), transparent 20%),
					linear-gradient(145deg, #f8fbff 0%, #edf4ff 40%, #f7f5ff 100%);
				--db-card: rgba(255, 255, 255, 0.72);
				--db-card-strong: rgba(255, 255, 255, 0.78);
				--db-border: rgba(108, 140, 189, 0.18);
				--db-border-strong: rgba(83, 129, 201, 0.24);
				--db-shadow: 0 24px 54px rgba(56, 88, 136, 0.12);
				--db-text: #1b2a44;
				--db-muted: rgba(71, 95, 135, 0.8);
				--db-olive: #2a66d9;
				--db-moss: #3b82f6;
				--db-gold: #5f96ff;
				--db-red: #d95f5f;
				--db-blue: #2c6ff0;
				--db-surface: rgba(255, 255, 255, 0.62);
				--db-success-soft: rgba(40, 167, 69, 0.12);
				--db-warning-soft: rgba(44, 111, 240, 0.12);
				--db-danger-soft: rgba(217, 95, 95, 0.12);
				border: 1px solid rgba(132, 166, 214, 0.16);
				box-shadow:
					inset 0 1px 0 rgba(255, 255, 255, 0.8),
					0 30px 60px rgba(74, 104, 150, 0.14);
				backdrop-filter: blur(18px);
			}
			:root:not([data-theme="dark"]) .drive-bucket-console::before {
				background: radial-gradient(circle, rgba(99, 163, 255, 0.18) 0%, rgba(82, 157, 255, 0) 70%);
			}
			:root:not([data-theme="dark"]) .drive-bucket-console::after {
				background: radial-gradient(circle, rgba(176, 124, 255, 0.12) 0%, rgba(164, 101, 255, 0) 72%);
			}
			:root:not([data-theme="dark"]) .db-topbar-copy h1,
			:root:not([data-theme="dark"]) .db-section-head h3,
			:root:not([data-theme="dark"]) .db-card-title {
				color: #1b2a44;
				text-shadow: none;
			}
			:root:not([data-theme="dark"]) .db-topbar-copy p,
			:root:not([data-theme="dark"]) .db-section-head p,
			:root:not([data-theme="dark"]) .db-card-subtitle,
			:root:not([data-theme="dark"]) .db-log-row span,
			:root:not([data-theme="dark"]) .db-import-item span {
				color: rgba(71, 95, 135, 0.8);
			}
			:root:not([data-theme="dark"]) .db-hero {
				background:
					linear-gradient(135deg, rgba(255, 255, 255, 0.62), rgba(255, 255, 255, 0.28)),
					radial-gradient(circle at top right, rgba(164, 145, 255, 0.24), transparent 34%),
					radial-gradient(circle at left center, rgba(116, 178, 255, 0.24), transparent 30%),
					linear-gradient(145deg, rgba(235, 242, 255, 0.92), rgba(228, 235, 248, 0.84));
				color: #1b2a44;
				border: 1px solid rgba(114, 151, 211, 0.18);
				box-shadow:
					inset 0 1px 0 rgba(255, 255, 255, 0.7),
					0 20px 40px rgba(82, 114, 162, 0.12);
			}
			:root:not([data-theme="dark"]) .db-hero h2,
			:root:not([data-theme="dark"]) .db-chip-value,
			:root:not([data-theme="dark"]) .db-default-meta-value {
				color: #1b2a44;
			}
			:root:not([data-theme="dark"]) .db-hero p,
			:root:not([data-theme="dark"]) .db-hero-panel p,
			:root:not([data-theme="dark"]) .db-chip-label,
			:root:not([data-theme="dark"]) .db-default-meta-label {
				color: rgba(71, 95, 135, 0.78);
			}
			:root:not([data-theme="dark"]) .db-chip,
			:root:not([data-theme="dark"]) .db-hero-panel,
			:root:not([data-theme="dark"]) .db-default-meta,
			:root:not([data-theme="dark"]) .db-card,
			:root:not([data-theme="dark"]) .db-account-card,
			:root:not([data-theme="dark"]) .db-log-item,
			:root:not([data-theme="dark"]) .db-import-item,
			:root:not([data-theme="dark"]) .db-empty,
			:root:not([data-theme="dark"]) .db-policy {
				background: linear-gradient(180deg, rgba(255, 255, 255, 0.82), rgba(245, 249, 255, 0.68));
				border-color: rgba(108, 140, 189, 0.18);
				box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.84);
			}
			:root:not([data-theme="dark"]) .db-card::before,
			:root:not([data-theme="dark"]) .db-account-card::before,
			:root:not([data-theme="dark"]) .db-hero::before {
				background:
					linear-gradient(135deg, rgba(255, 255, 255, 0.42), transparent 36%),
					radial-gradient(circle at 78% 20%, rgba(146, 117, 255, 0.08), transparent 28%);
			}
			:root:not([data-theme="dark"]) .db-pill.green { background: rgba(57, 191, 120, 0.12); color: #137a4b; }
			:root:not([data-theme="dark"]) .db-pill.red { background: rgba(217, 95, 95, 0.12); color: #a03f3f; }
			:root:not([data-theme="dark"]) .db-pill.gold { background: rgba(62, 120, 245, 0.12); color: #2d63d7; }
			:root:not([data-theme="dark"]) .db-pill.blue { background: rgba(62, 120, 245, 0.08); color: #356bdc; }
			:root:not([data-theme="dark"]) .db-pill.slate { background: rgba(114, 137, 173, 0.12); color: #5b6f95; }
			:root:not([data-theme="dark"]) .db-search-row input,
			:root:not([data-theme="dark"]) .db-search-row select,
			:root:not([data-theme="dark"]) .db-btn.secondary,
			:root:not([data-theme="dark"]) .db-btn.ghost,
			:root:not([data-theme="dark"]) .db-collapse-toggle {
				background: rgba(255, 255, 255, 0.78);
				color: #1b2a44;
				border-color: rgba(108, 140, 189, 0.18);
			}
			:root:not([data-theme="dark"]) .db-search-row input::placeholder {
				color: rgba(93, 113, 145, 0.68);
			}
			:root:not([data-theme="dark"]) .db-search-row select option {
				background: #ffffff;
				color: #1b2a44;
			}
			@media (max-width: 1100px) {
				.db-hero,
				.db-shell-grid { grid-template-columns: 1fr; }
			}
			@media (max-width: 760px) {
				.db-chip-row,
				.db-account-grid { grid-template-columns: 1fr; }
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
						<h2>Smart Google Drive control.</h2>
						<p>Connect drives, control fallback, and manage uploads from one clean screen.</p>
						<div class="db-chip-row js-summary"></div>
					</div>
					<div class="db-hero-panel">
						<div>
							<p class="js-routing-copy">Manage connected accounts and file imports from one place.</p>
							<div class="db-default-meta">
								<div class="db-default-meta-label">Default fallback drive</div>
								<div class="db-default-meta-value js-default-meta">Not configured</div>
							</div>
						</div>
					</div>
				</section>
				<div class="db-shell-grid">
					<section class="db-card">
						<div class="db-section-head">
							<div>
								<h3>Managed Drives</h3>
								<p>Ownership, quota, fallback, and recent uploads.</p>
							</div>
							<button class="db-collapse-toggle js-collapse-toggle" style="display:none;">${__("Show More")}</button>
						</div>
						<div class="db-account-grid js-account-grid"></div>
					</section>
					<section class="db-card">
						<div class="db-section-head">
							<div>
								<h3>Import From Google Drive</h3>
								<p>Search a connected drive and attach the file into ERPNext.</p>
							</div>
						</div>
						<div class="db-search-row">
							<select class="js-account-selector"></select>
							<input type="text" class="js-search-query" placeholder="Search Google Drive files by name" />
						</div>
						<div class="db-import-list js-import-list" style="margin-top:14px;"></div>
					</section>
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
		this.$root.on("click", ".js-collapse-toggle", () => this.toggleManagedDrives());
		this.$root.on("keydown", ".js-search-query", (event) => {
			if (event.key === "Enter") {
				event.preventDefault();
				this.searchDriveFiles();
			}
		});
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
		this.renderAccounts();
		this.renderAccountSelector();
	}

	renderSummary() {
		const summary = this.state.summary || {};
		const chips = [
			{ label: "Connected Drives", value: summary.connected_accounts || 0 },
			{ label: "Used / Quota", value: `${summary.total_used_space_gb || 0} / ${summary.total_quota_gb || 0} GB` },
			{ label: "Fallback Default", value: summary.default_account ? "Configured" : "Not set" },
		];
		this.$root.find(".js-summary").html(chips.map((chip) => `
			<div class="db-chip">
				<div class="db-chip-label">${frappe.utils.escape_html(chip.label)}</div>
				<div class="db-chip-value">${frappe.utils.escape_html(String(chip.value))}</div>
			</div>
		`).join(""));

		const routingText = summary.default_account
			? "Default fallback routing is active and ready for uploads."
			: "Choose a default fallback drive from Managed Drives.";
		this.$root.find(".js-routing-copy").text(routingText);
		this.$root.find(".js-default-meta").text(summary.default_account || "Not configured");
	}

	renderAccounts() {
		const $grid = this.$root.find(".js-account-grid");
		const $toggle = this.$root.find(".js-collapse-toggle");
		if (!this.state.accounts.length) {
			$grid.html(`<div class="db-empty">No Google Drive accounts are connected yet.</div>`);
			$toggle.hide();
			return;
		}

		const shouldCollapse = this.state.accounts.length > 5 && !this.state.showAllAccounts;
		$grid.toggleClass("is-collapsed", shouldCollapse);
		$toggle
			.toggle(this.state.accounts.length > 5)
			.text(this.state.showAllAccounts ? __("Show Less") : __("Show More"));

		$grid.html(this.state.accounts.map((account) => {
			const percent = Math.min(account.usage_percent || 0, 100);
			const statusClass = account.connection_status === "Connected" ? "green" : "red";
			const fullBadge = account.is_full ? `<span class="db-pill red">Quota Full</span>` : `<span class="db-pill blue">Free ${account.free_space_gb} GB</span>`;
			const ownerBadge = account.linked_user === "Guest"
				? `<span class="db-pill red">Shared / Guest</span>`
				: `<span class="db-pill slate">${frappe.utils.escape_html(account.linked_user || "No user selected")}</span>`;
			const defaultBadge = account.is_default_upload ? `<span class="db-pill default-flag">Default Fallback</span>` : "";
			return `
				<article class="db-account-card ${account.is_default_upload ? "is-default" : ""}">
					<div class="db-account-row">
						<div class="db-account-title-wrap">
							<div class="db-card-title">${frappe.utils.escape_html(account.account_email)}</div>
							<div class="db-card-subtitle">Reserve ${account.reserve_space_gb} GB before fallback triggers</div>
						</div>
						<span class="db-pill ${statusClass}">${frappe.utils.escape_html(account.connection_status || "Unknown")}</span>
					</div>
					<div class="db-account-meta">
						${defaultBadge}
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
					<div class="db-card-subtitle">Fallback: ${account.allow_fallback ? "Allowed" : "Blocked"} | Auto Sync: ${account.auto_sync_uploads ? "On" : "Off"} | Priority: ${account.fallback_priority}</div>
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
						${account.recent_log_count > 6 ? `<div class="db-card-subtitle">Showing latest 6 uploads. Open Account to review full history.</div>` : ""}
					</div>
				</article>
			`;
		}).join(""));
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

	toggleManagedDrives() {
		this.state.showAllAccounts = !this.state.showAllAccounts;
		this.renderAccounts();
	}
}
