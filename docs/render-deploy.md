# Render Deployment Notes

## Render service

- Runtime: Python
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn ibs_fighter.wsgi:app --bind 0.0.0.0:$PORT`
- Persistent disk mount: `/var/data`
- Environment:
  - `IBS_FIGHTER_DATA_DIR=/var/data/data`
  - `IBS_FIGHTER_UPLOADS_DIR=/var/data/uploads`
  - `IBS_FIGHTER_COOKIE_SECURE=1`
  - `IBS_FIGHTER_SESSION_DAYS=360`
  - `IBS_FIGHTER_DEFAULT_TIMEZONE=Pacific/Guadalcanal`
  - `IBS_FIGHTER_LEGACY_TIMEZONE=Pacific/Port_Moresby`
  - `GOOGLE_ALLOWED_EMAILS=gluebi.d.mao@gmail.com`
  - `SECRET_KEY=<generated secret>`
  - `GOOGLE_CLIENT_ID=<Google OAuth web client id>`
  - `GOOGLE_CLIENT_SECRET=<Google OAuth web client secret>`
  - `BACKUP_ADMIN_TOKEN=<generated secret>`

Optional Google Drive backup environment:

- `GOOGLE_DRIVE_BACKUP_FOLDER_ID=<shared Drive folder id>`

The preferred backup flow is keyless OAuth. After deploying with the folder id,
open the app settings page and click `连接 Google Drive 备份`. The app stores the
Drive refresh token on the Render persistent disk at
`/var/data/data/google_drive_oauth_token.json` by default.

Optional service-account fallback:

- `GOOGLE_SERVICE_ACCOUNT_JSON=<service account JSON or base64 JSON>`

Only use the fallback if your Google Cloud project allows service account keys.
The OAuth flow avoids `iam.disableServiceAccountKeyCreation` entirely.

## Google OAuth

Create a Google OAuth Web Client and add these redirect URIs:

- `https://<render-url>/auth/google/callback`
- `http://127.0.0.1:8765/auth/google/callback`

Only emails listed in `GOOGLE_ALLOWED_EMAILS` can enter the app.

The Drive backup authorization reuses the same callback URI. No extra redirect
URI is needed beyond `/auth/google/callback`.

On the OAuth consent screen, add the signed-in account as a test user if the app
is still in Testing mode. The backup flow requests:

- `openid`
- `email`
- `profile`
- `https://www.googleapis.com/auth/drive.file`

## Login cookie lifetime

The app uses a signed, HttpOnly, Secure Flask session cookie. After Google login,
the session is marked permanent and defaults to `IBS_FIGHTER_SESSION_DAYS=360`.
Closing mobile Chrome should not log the user out. Clicking the app's `退出`
link still clears the session immediately by design.

## Google Drive backup

Enable the Google Drive API for the Google Cloud project that owns your OAuth
client. Then set `GOOGLE_DRIVE_BACKUP_FOLDER_ID` on Render and redeploy.

Open the app settings page and click `连接 Google Drive 备份`. The OAuth consent
screen requests Drive file access for the signed-in Google account. After that,
the same button changes to `备份到 Google Drive`.

The app uploads a zip containing:

- `data/ibs_fighter.sqlite3`
- `uploads/`
- `manifest.json` with file sizes and SHA-256 checksums

Meal photos are converted to JPEG and compressed to roughly 500KB on upload, so
future backups grow much more slowly than raw iPhone photos.

Existing uploaded JPEGs can be recompressed in place. The command keeps file
names unchanged and skips files already below the target size:

```bash
python3 scripts/recompress_uploads.py
```

On Render, the same maintenance task can be triggered with the admin token:

```bash
curl -X POST \
  -H "Authorization: Bearer $BACKUP_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false}' \
  https://<render-url>/api/admin/uploads/recompress
```

Manual backup trigger:

```bash
curl -X POST \
  -H "Authorization: Bearer $BACKUP_ADMIN_TOKEN" \
  https://<render-url>/api/admin/backups/drive
```

The logged-in app UI has a `备份到 Google Drive` button in `设置`. It calls the
same endpoint with the current Google-login session and CSRF token.

The backup is uploaded as:

```text
ibs-fighter-backup-YYYYMMDDTHHMMSSZ.zip
```

Each zip contains:

```text
data/ibs_fighter.sqlite3
uploads/
manifest.json
```

The app creates the database copy through SQLite's backup API before zipping, so
the uploaded database is a consistent snapshot instead of a raw copy of a live
SQLite file.

## Local backup import

Use the local sync script to trigger Render and extract the downloaded or synced
Drive backup to `data/render_backups/`:

```bash
python3 scripts/sync_render_backup.py
```

Required local environment:

```text
BACKUP_ADMIN_TOKEN=<Render BACKUP_ADMIN_TOKEN>
GOOGLE_DRIVE_BACKUP_FOLDER_ID=<backup folder id>
```

When the Render app uses OAuth backup, the Drive refresh token lives on Render's
persistent disk. For local analysis, click `备份到 Google Drive` online or trigger
the curl command above, let Google Drive Desktop sync the zip folder to this Mac,
then import the latest synced zip:

```bash
python3 scripts/sync_render_backup.py \
  --skip-trigger \
  --drive-sync-dir "/path/to/Google Drive/IBS Fighter Backups"
```

You can also import a specific downloaded zip:

```bash
python3 scripts/sync_render_backup.py \
  --backup-zip "/path/to/ibs-fighter-backup-YYYYMMDDTHHMMSSZ.zip"
```

After import, the script writes the latest online snapshot database path to:

```text
data/render_backups/latest_db_path.txt
```

Read it locally without overwriting the local development database:

```bash
sqlite3 "$(cat data/render_backups/latest_db_path.txt)" \
  "SELECT COUNT(*) FROM bowel_movements;"
```

## First data migration

Before uploading to Render, make a local copy of:

- `data/ibs_fighter.sqlite3`
- `uploads/`

Then place them on the Render persistent disk as:

- `/var/data/data/ibs_fighter.sqlite3`
- `/var/data/uploads/...`

After restart, compare row counts with the local baseline before continuing to
record new data online.

## Time zones

Existing records created before the time-zone migration are interpreted as
Papua New Guinea time with `IBS_FIGHTER_LEGACY_TIMEZONE=Pacific/Port_Moresby`.
New records keep the user's local browser time for display and store a converted
UTC timestamp in the database for cross-region analysis.
