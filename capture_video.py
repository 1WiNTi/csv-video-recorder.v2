#!/usr/bin/env python3
"""Reads input.csv and records one video per row via qscript.CaptureVideo_Magento.

With --server, every recorded video is also uploaded to the web service and
previewed in Chromium.
"""
import argparse
import csv
import sys

import qscript


def preview_video(url, view_seconds):
    """Open the uploaded video in a visible Chromium window (Playwright sync API)."""
    from playwright.sync_api import sync_playwright  # lazy: only needed with --server

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        try:
            page = browser.new_page()
            page.goto(url)  # direct .webm URL -> Chromium's built-in media player
            if view_seconds > 0:
                page.wait_for_timeout(view_seconds * 1000)
            else:
                try:
                    input("Press Enter to close the preview... ")
                except EOFError:
                    pass  # no interactive stdin: just close
        finally:
            browser.close()


def upload_and_preview(server_url, video_path, company_name, view_seconds, index):
    """Upload one video, log its URL, preview it.

    Never raises: errors are logged so the batch loop continues.
    Returns True if the upload succeeded.
    """
    try:
        from video_client import UploadVideo  # lazy: 'requests' only needed with --server

        url = UploadVideo(server_url, video_path, company_name)
        print(f"[{index}] Uploaded: {url}")
    except Exception as exc:
        print(f"[{index}] UPLOAD FAILED: {company_name}: {exc}", file=sys.stderr)
        return False

    try:
        preview_video(url, view_seconds)
    except Exception as exc:
        print(f"[{index}] PREVIEW FAILED: {company_name}: {exc}", file=sys.stderr)
    return True


def main():
    parser = argparse.ArgumentParser(description="CSV-driven browser video recorder")
    parser.add_argument("csv_file", nargs="?", default="input.csv", help="input CSV (default: input.csv)")
    parser.add_argument("--video-dir", default="./video", help="output folder (default: ./video)")
    parser.add_argument("--headed", action="store_true", help="show the browser window")
    parser.add_argument(
        "--server",
        help="web service base URL, e.g. http://127.0.0.1:8000; "
             "if set, each recorded video is uploaded and previewed in Chromium",
    )
    parser.add_argument(
        "--view-seconds",
        type=float,
        default=5,
        help="preview time: >0 closes the browser after N seconds, "
             "0 keeps it open until Enter is pressed (default: 5)",
    )
    args = parser.parse_args()
    if args.view_seconds < 0:
        parser.error("--view-seconds must be >= 0")

    # The main script may override the global at startup.
    qscript.PATH_TO_VIDEO_FOLDER = args.video_dir
    qscript.HEADLESS = not args.headed

    failed = 0
    upload_failed = 0
    with open(args.csv_file, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";", quotechar='"')
        for i, row in enumerate(reader, start=1):
            name = row.get("Company Name", "") or ""
            print(f"[{i}] Processing: {name}")
            path = qscript.CaptureVideo_Magento(
                row.get("URL", "") or "",
                name,
                row.get("Language", "") or "",
                row.get("Country", "") or "",
                row.get("Postcode", "") or "",
                row.get("City", "") or "",
                row.get("Street", "") or "",
                row.get("HouseNo", "") or "",
            )
            if path:
                print(f"[{i}] Saved: {path}")
                if args.server:
                    if not upload_and_preview(args.server, path, name, args.view_seconds, i):
                        upload_failed += 1
            else:
                failed += 1
                print(f"[{i}] FAILED: {name}")

    if upload_failed:
        print(f"{upload_failed} upload(s) failed", file=sys.stderr)
    return 1 if (failed or upload_failed) else 0


if __name__ == "__main__":
    sys.exit(main())
