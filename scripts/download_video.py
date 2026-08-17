#!/usr/bin/env python3
"""Video downloader for the VidGrab GitHub Actions backend.

Reads VIDEO_URL / REQUEST_ID / CALLBACK_URL / CALLBACK_SECRET from the
environment, downloads the best <=1080p mp4 with yt-dlp, uploads it to a
free file host (catbox -> 0x0.st -> tmpfiles.org), then POSTs the result
back to the app's webhook.

Manual runs without REQUEST_ID just print the result to the logs.
"""

import json
import os
import subprocess
import sys
import urllib.request

URL = os.environ.get("VIDEO_URL", "")
PLATFORM = os.environ.get("PLATFORM", "")
REQUEST_ID = os.environ.get("REQUEST_ID", "")
CALLBACK_URL = os.environ.get("CALLBACK_URL", "")
CALLBACK_SECRET = os.environ.get("CALLBACK_SECRET", "")

# Prefer <=1080p mp4 with audio; falls back to best <=1080p
FORMAT = (
    "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/"
    "b[height<=1080][ext=mp4]/"
    "b[height<=1080]/"
    "b"
)


def send_callback(payload: dict) -> None:
    if not CALLBACK_URL or not REQUEST_ID:
        return
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        CALLBACK_URL,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-callback-secret": CALLBACK_SECRET or "",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"callback sent: {resp.status}", file=sys.stderr)
    except Exception as exc:
        print(f"callback failed: {exc}", file=sys.stderr)


def curl_upload(args: list[str], timeout: int) -> str:
    proc = subprocess.run(
        ["curl", "-s", "--max-time", str(timeout), *args],
        capture_output=True,
        text=True,
    )
    link = (proc.stdout or "").strip()
    if link.startswith("http://") or link.startswith("https://"):
        return link
    print(f"upload attempt failed: {proc.stderr or proc.stdout}", file=sys.stderr)
    return ""


def upload_file(filepath: str) -> str:
    size = os.path.getsize(filepath)
    # 1) catbox.moe — up to 200 MB, links persist
    if size <= 200 * 1024 * 1024:
        link = curl_upload(
            [
                "-F", "reqtype=fileupload",
                "-F", f"fileToUpload=@{filepath}",
                "https://catbox.moe/user/api.php",
            ],
            600,
        )
        if link:
            return link
    # 2) 0x0.st — up to 512 MB
    if size <= 512 * 1024 * 1024:
        link = curl_upload(["-F", f"file=@{filepath}", "https://0x0.st"], 900)
        if link:
            return link
    # 3) tmpfiles.org — up to 1 GB, expires after 72 h
    link = curl_upload(
        ["-F", f"file=@{filepath}", "-F", "expires=72h", "https://tmpfiles.org/api/v1/upload"],
        1200,
    )
    if link:
        return link
    return ""


def main() -> None:
    if not URL:
        print("VIDEO_URL is required", file=sys.stderr)
        send_callback(
            {"requestId": REQUEST_ID, "status": "failed", "error": "Video URL eksik."}
        )
        sys.exit(1)

    print(f"downloading: {URL} ({PLATFORM})", file=sys.stderr)
    proc = subprocess.run(
        [
            "yt-dlp",
            "--no-playlist",
            "-f", FORMAT,
            "--merge-output-format", "mp4",
            "--no-progress",
            "--print", "%(title)s|%(thumbnail)s",
            "-o", "video.%(ext)s",
            URL,
        ],
        capture_output=True,
        text=True,
        timeout=1800,
    )

    if proc.returncode != 0:
        err = (proc.stderr or "").strip()[-600:] or "yt-dlp failed"
        print(f"yt-dlp error: {err}", file=sys.stderr)
        send_callback({"requestId": REQUEST_ID, "status": "failed", "error": err})
        sys.exit(1)

    title = ""
    thumbnail = ""
    first_line = (proc.stdout or "").strip().splitlines()
    if first_line:
        parts = first_line[0].split("|", 1)
        title = parts[0]
        if len(parts) > 1:
            thumbnail = parts[1]

    filepath = next(
        (f for f in os.listdir(".") if f.startswith("video.")),
        None,
    )
    if not filepath:
        send_callback(
            {"requestId": REQUEST_ID, "status": "failed", "error": "İndirilen dosya bulunamadı."}
        )
        sys.exit(1)

    print(f"uploading {filepath} ...", file=sys.stderr)
    link = upload_file(filepath)
    if not link:
        send_callback(
            {
                "requestId": REQUEST_ID,
                "status": "failed",
                "error": "Dosya paylaşım servisine yüklenemedi (boyut limiti aşılmış olabilir).",
            }
        )
        sys.exit(1)

    result = {
        "requestId": REQUEST_ID,
        "status": "completed",
        "downloadUrl": link,
        "title": title,
        "thumbnail": thumbnail,
    }
    print(json.dumps(result, ensure_ascii=False))
    send_callback(result)


if __name__ == "__main__":
    main()
