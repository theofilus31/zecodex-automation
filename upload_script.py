"""ZECODEX Automation: complete, working upload script (evidence for the YouTube API Services audit).

This is the same upload flow the app runs (automation/zx/youtube.py + zx/publisher.py), condensed into one file.
In the app it only runs for a video the channel owner has explicitly approved in the dashboard or via Telegram.

Flow:
  1. OAuth 2.0 (installed-app flow) for the channel owner, scopes:
       youtube.upload, youtube.readonly, yt-analytics.readonly
     The refresh token is stored locally (secrets/token.json); revocation is honoured (see privacy policy).
  2. videos.insert, resumable upload in 8 MB chunks, with title/description/tags/category,
     selfDeclaredMadeForKids=false, and either public-now or private + publishAt (scheduled premiere time).
  3. Prints the resulting video URL.

Usage:
  python upload_script.py --client-secret client_secret.json --file short.mp4 --title "..." \
      [--description "..."] [--tags "a,b,c"] [--publish-at 2026-11-21T13:00:00Z]

Requires: google-api-python-client, google-auth-oauthlib
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
TOKEN = Path("token.json")


def credentials(client_secret: str) -> Credentials:
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES) if TOKEN.exists() else None
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(client_secret, SCOPES)
        creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return creds


def upload(creds: Credentials, path: str, title: str, description: str, tags: list[str], publish_at: str | None) -> str:
    status = {"selfDeclaredMadeForKids": False, "embeddable": True}
    if publish_at:                                   # scheduled: private until publishAt, then YouTube makes it public
        status.update(privacyStatus="private", publishAt=publish_at)
    else:
        status["privacyStatus"] = "public"
    body = {
        "snippet": {"title": title[:100], "description": description[:4900], "tags": tags[:30], "categoryId": "24",
                    "defaultLanguage": "en", "defaultAudioLanguage": "en"},
        "status": status,
    }
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    media = MediaFileUpload(path, mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        progress, response = request.next_chunk()
        if progress:
            print(f"upload {progress.progress() * 100:.0f}%")
    print(json.dumps({"id": response["id"], "privacyStatus": response["status"].get("privacyStatus"),
                      "publishAt": response["status"].get("publishAt")}, indent=1))
    return response["id"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-secret", required=True)
    ap.add_argument("--file", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--description", default="#shorts")
    ap.add_argument("--tags", default="")
    ap.add_argument("--publish-at", help="RFC 3339 UTC, e.g. 2026-11-21T13:00:00Z (omit to publish now)")
    a = ap.parse_args()
    creds = credentials(a.client_secret)
    vid = upload(creds, a.file, a.title, a.description, [t.strip() for t in a.tags.split(",") if t.strip()], a.publish_at)
    print(f"https://youtube.com/shorts/{vid}")


if __name__ == "__main__":
    main()
