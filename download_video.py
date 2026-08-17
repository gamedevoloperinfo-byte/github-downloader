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
            "Content-Type": "application/json"
