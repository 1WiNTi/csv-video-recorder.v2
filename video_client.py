"""Client functions for the video web service (Test Task 2)."""
import os

import requests

UPLOAD_TIMEOUT = 300  # seconds; videos can be large
LOOKUP_TIMEOUT = 30


def UploadVideo(server_url: str, video_path: str, company_name: str) -> str:
    """Uploads a video file to the server and returns its URL."""
    url = server_url.rstrip("/") + "/upload"
    with open(video_path, "rb") as fileobj:
        resp = requests.post(
            url,
            files={"file": (os.path.basename(video_path), fileobj)},
            data={"company_name": company_name},
            timeout=UPLOAD_TIMEOUT,
        )
    resp.raise_for_status()
    return resp.json()["video_url"]


def GetVideoURL(server_url: str, company_name: str) -> str:
    """Returns the video URL for the given company name."""
    url = server_url.rstrip("/") + "/get_video_url"
    resp = requests.get(
        url, params={"company_name": company_name}, timeout=LOOKUP_TIMEOUT
    )
    resp.raise_for_status()  # 404 for an unknown company raises HTTPError
    return resp.json()["video_url"]
