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
  - `GOOGLE_ALLOWED_EMAILS=gluebi.d.mao@gmail.com`
  - `SECRET_KEY=<generated secret>`
  - `GOOGLE_CLIENT_ID=<Google OAuth web client id>`
  - `GOOGLE_CLIENT_SECRET=<Google OAuth web client secret>`
  - `BACKUP_ADMIN_TOKEN=<generated secret>`

Optional Google Drive backup environment:

- `GOOGLE_SERVICE_ACCOUNT_JSON=<service account JSON or base64 JSON>`
- `GOOGLE_DRIVE_BACKUP_FOLDER_ID=<shared Drive folder id>`

If your Google Cloud organization blocks service account key creation with
`iam.disableServiceAccountKeyCreation`, leave these unset for the first deploy.
The app still works with Render persistent disk storage; only the manual Drive
backup endpoint remains disabled until a keyless backup method is configured.

## Google OAuth

Create a Google OAuth Web Client and add these redirect URIs:

- `https://<render-url>/auth/google/callback`
- `http://127.0.0.1:8765/auth/google/callback`

Only emails listed in `GOOGLE_ALLOWED_EMAILS` can enter the app.

## Google Drive backup

Create a Google service account, then share the target Google Drive backup folder
with the service account email. The app uploads a zip containing:

- `data/ibs_fighter.sqlite3`
- `uploads/`
- `manifest.json` with file sizes and SHA-256 checksums

Manual backup trigger:

```bash
curl -X POST \
  -H "Authorization: Bearer $BACKUP_ADMIN_TOKEN" \
  https://<render-url>/api/admin/backups/drive
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
