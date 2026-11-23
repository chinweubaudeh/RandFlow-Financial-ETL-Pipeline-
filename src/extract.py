from __future__ import annotations

import io
import shutil
from pathlib import Path

from .config import EXPECTED_FILES, INPUT_DIR, RAW_DIR, drive_settings

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
GSHEET = "application/vnd.google-apps.spreadsheet"


def extract_local() -> dict[str, Path]:
    """Local mode enables end-to-end transform testing before Drive is configured."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    result: dict[str, Path] = {}
    for name in EXPECTED_FILES:
        src = INPUT_DIR / name
        if not src.is_file():
            raise FileNotFoundError(f"Missing input data: {src}")
        dest = RAW_DIR / name
        shutil.copy2(src, dest)
        result[name] = dest
    return result


def extract_drive() -> dict[str, Path]:
    """Download only expected source files; fail if any are missing/duplicated."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload

    folder_id, key_path = drive_settings()
    credentials = service_account.Credentials.from_service_account_file(
        str(key_path), scopes=[DRIVE_SCOPE]
    )
    service = build("drive", "v3", credentials=credentials, cache_discovery=False)
    found: dict[str, dict] = {}
    page_token = None
    while True:
        response = service.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            fields="nextPageToken,files(id,name,mimeType,modifiedTime,md5Checksum)",
            pageSize=1000,
            pageToken=page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        for file in response.get("files", []):
            name = file["name"]
            # A Google Sheet called "customers" can be exported as customers.csv.
            output_name = f"{name}.csv" if file["mimeType"] == GSHEET and not name.endswith(".csv") else name
            if output_name in EXPECTED_FILES:
                if output_name in found:
                    raise RuntimeError(f"Multiple Drive files resolve to {output_name}")
                found[output_name] = file
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    missing = set(EXPECTED_FILES) - set(found)
    if missing:
        raise FileNotFoundError(
            f"Missing files in Drive folder: {sorted(missing)}. "
            "Check the folder ID and share permissions."
        )

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    results: dict[str, Path] = {}
    for name in EXPECTED_FILES:
        item = found[name]
        if item["mimeType"] == GSHEET:
            request = service.files().export_media(fileId=item["id"], mimeType="text/csv")
        elif item["mimeType"] in ("text/csv", "application/vnd.ms-excel", "application/octet-stream"):
            request = service.files().get_media(fileId=item["id"])
        else:
            raise ValueError(f"Unexpected file type for {name}: {item['mimeType']}")
        final = RAW_DIR / name
        partial = RAW_DIR / f"{name}.download"
        try:
            with io.FileIO(partial, "wb") as stream:
                downloader = MediaIoBaseDownload(stream, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
            partial.replace(final)  # never expose partially downloaded CSVs
        finally:
            partial.unlink(missing_ok=True)
        results[name] = final
    return results
```