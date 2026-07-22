# Drive Bucket

Drive Bucket is a Frappe / ERPNext app for routing ERPNext attachments to Google Drive with user-based ownership, fallback drive logic, quota awareness, and admin-managed sharing.

It is designed for teams that want to:

- connect multiple Google Drive accounts
- route uploads to the correct user's drive
- fall back to a default drive when a user drive is unavailable or full
- import files from Google Drive into ERPNext attachments
- manage Google Drive access from inside ERPNext

## Features

- Google OAuth2 connection flow using ERPNext `Google Settings`
- one `Cloud Storage Account` record per connected Google account
- automatic folder management:
  - `erpnext_backup_private`
  - `erpnext_backup_public`
- automatic file upload on new ERPNext `File` save
- drive routing rules:
  - linked user's drive first
  - default fallback drive if user drive is unavailable or quota-limited
- Google Drive quota sync
- custom Drive Bucket control center page at `/app/cloud-backup`
- direct Google Drive import into ERPNext attachments
- Google Drive permission management from the ERPNext `File` form

## App Details

- App Name: `drive_bucket`
- Module: `Drive Bucket`
- Publisher: `Savan Patel`
- Email: `savan.p.solufy@gmail.com`
- License: `mit`
- Branch: `develop`

## Requirements

- Frappe / ERPNext bench
- Google Cloud project
- Google OAuth client credentials
- Google Drive API enabled

## Installation

Install the app with Bench:

```bash
cd /path/to/frappe-bench
bench get-app https://github.com/<your-org-or-user>/drive_bucket.git --branch develop
bench --site <your-site> install-app drive_bucket
bench --site <your-site> migrate
```

## Google Cloud Setup

### 1. Create or open a Google Cloud project

Google Cloud Console:

- https://console.cloud.google.com/

### 2. Enable Google Drive API

Enable Google Drive API here:

- https://console.cloud.google.com/apis/library/drive.googleapis.com

### 3. Create an OAuth 2.0 Client ID

Open OAuth client settings here:

- https://console.cloud.google.com/apis/credentials

Create:

- Credential Type: `OAuth client ID`
- Application Type: `Web application`

### 4. Add Authorized Redirect URI

Add this exact redirect URI to your OAuth client:

```text
https://<your-public-domain>/api/method/drive_bucket.cloud_backup.api.google_auth.oauth_callback
```

Example:

```text
https://example.ngrok-free.app/api/method/drive_bucket.cloud_backup.api.google_auth.oauth_callback
```

### 5. Configure OAuth consent screen

Open consent screen settings:

- https://console.cloud.google.com/auth/branding
- https://console.cloud.google.com/auth/audience

Make sure:

- your app branding is configured
- test users are added if the app is still in testing mode
- the connected Google accounts are allowed to use the app

## ERPNext Setup

### 1. Set public site URL

If you are using a public URL or ngrok:

```bash
bench --site <your-site> set-config host_name https://<your-public-domain>
```

### 2. Configure Google Settings

In ERPNext:

- open `Google Settings`
- enable Google integration
- set your `Client ID`
- set your `Client Secret`

Drive Bucket reuses this single shared Google OAuth app for all connected accounts.

## First-Time Setup Flow

### 1. Open the Drive Bucket control center

Desk route:

```text
/app/cloud-backup
```

### 2. Connect Google Drive

Use the `Connect Google Drive` button.

This creates a `Cloud Storage Account` automatically.

### 3. Set a default fallback drive

Use the `Make Default` action on one connected account.

This default drive is used when:

- no user-linked drive is available
- a linked drive is full
- a file is saved by a user with no eligible connected drive

### 4. Verify folder creation

Each connected drive should receive:

- `erpnext_backup_private`
- `erpnext_backup_public`

## Routing Logic

When a new ERPNext file is saved:

1. Drive Bucket checks the uploading user's linked drive
2. If that drive is connected and not quota-limited, the file goes there
3. If the user's drive is unavailable or full, the file goes to the default fallback drive
4. If no default fallback is configured, upload routing may not complete for unmatched users

### Quota Handling

Each `Cloud Storage Account` supports:

- `reserve_space_gb`
- `fallback_priority`
- `allow_fallback`
- `auto_sync_uploads`

If used space reaches the effective threshold:

```text
total_quota - reserve_space_gb
```

the account is treated as full for routing purposes.

## Cloud Storage Account Fields

Key fields on `Cloud Storage Account`:

- `account_email`
- `linked_user`
- `is_default_upload`
- `allow_fallback`
- `auto_sync_uploads`
- `fallback_priority`
- `reserve_space_gb`
- `connection_status`
- `private_folder_id`
- `public_folder_id`
- `used_space`
- `total_quota`
- `last_synced`

## File Upload Behavior

New ERPNext `File` records are uploaded automatically after save.

Drive Bucket stores extra metadata on `File`:

- `drive_bucket_google_account`
- `drive_bucket_google_file_id`
- `drive_bucket_google_file_link`
- `drive_bucket_drive_status`
- `drive_bucket_last_shared_at`

These fields are used for:

- share management
- Drive link opening
- audit visibility

## Manage Google Drive Access From ERPNext

For newly uploaded files with stored Drive metadata, open the `File` record and use:

- `Open in Google Drive`
- `View Drive Access`
- `Grant Drive Access`

You can grant:

- `reader`
- `commenter`
- `writer`

to:

- an ERPNext `User`
- or any Google email address

Note:

- older files uploaded before Drive metadata support may not have a stored Google file ID
- those files may need re-upload or a metadata backfill tool before access can be managed from ERPNext

## Import From Google Drive

The control center supports direct Google Drive import.

From `/app/cloud-backup`:

1. choose a connected account
2. search Google Drive files
3. click `Attach to Document`
4. choose:
   - target DocType
   - target document name
   - optional target field
   - private/public

This creates a normal ERPNext `File` attachment.

## Recommended Admin Policy

For a client-ready setup:

- connect one primary drive per active ERPNext user
- configure exactly one default fallback drive
- keep shared fallback drives separate from personal drives
- review any `Guest`-linked drive accounts and convert them to a real owner if needed
- keep `reserve_space_gb` above zero so fallback occurs before Google rejects uploads

## Testing Checklist

After setup, test the following:

### OAuth

- `Connect Google Drive` opens Google consent screen
- callback returns to ERPNext successfully

### Folder creation

- private backup folder exists
- public backup folder exists

### Quota sync

- `used_space` is visible
- `total_quota` is visible
- `last_synced` updates

### Upload routing

- upload a file as a user with a linked drive
- confirm it lands in that user's Google Drive
- mark another account as default fallback
- confirm fallback works when the user has no eligible drive

### Access management

- upload a new private file
- open the `File` record
- use `Grant Drive Access`
- confirm the recipient gets access in Google Drive

### Drive import

- import a file from Google Drive into ERPNext
- verify the attachment appears on the target document

## Troubleshooting

### `redirect_uri_mismatch`

Your Google OAuth client redirect URI does not exactly match the ERPNext callback URL.

Check:

- `host_name` in site config
- Authorized Redirect URI in Google Cloud

### `Google Drive API has not been used in project`

Enable Google Drive API:

- https://console.cloud.google.com/apis/library/drive.googleapis.com

### `Not permitted` on connect button

Usually caused by:

- wrong HTTP method on endpoint
- permissions issue
- stale cache after code changes

Run:

```bash
bench --site <your-site> clear-cache
bench --site <your-site> migrate
```

### Connected account appears but folders or quota are missing

Run:

- `Sync Quota`
- `Ensure Backup Folders`

and confirm the connected Google account still has valid consent.

### File uploads but share management is missing

This usually means the file was uploaded before Drive metadata fields were added.

Re-upload the file or build a metadata backfill tool.

## Bench Commands

Useful commands:

```bash
bench --site <your-site> migrate
bench --site <your-site> clear-cache
bench --site <your-site> list-apps
bench --site <your-site> execute drive_bucket.cloud_backup.api.control_center.get_console_data
```

## Current Desk Routes

- Drive control center: `/app/cloud-backup`
- Accounts list: `/app/cloud-storage-account`

## Development Notes

This app currently includes:

- Google OAuth connection flow
- quota sync
- automatic upload routing
- fallback drive logic
- Drive import
- Drive access grant flow

Possible next enhancements:

- backfill tool for older uploaded files
- richer share management with revoke/update access
- per-user preferred drive selection
- folder browser UI instead of search-only import
- upload routing audit trail per file

## License

mit
