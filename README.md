# CSV-driven Browser Automation Video Recorder

Reads `input.csv` and records a video of automated browser actions for each row:
opens DuckDuckGo, shows a custom SVG cursor, glides to the search box, types
"Magento developer in <city>" character by character, clicks search and opens
the first result. Effects: SVG cursor, yellow highlight, click ripple, callouts.

**Stage 2** adds a small web service: every recorded video can be uploaded,
stored in a database, looked up by company name and previewed in a browser.

## Sample output

[`q.solutions.webm`](q.solutions.webm) - one video recorded by this tool.

## Setup (once)

Run these two commands one after another:

```
pip install -r requirements.txt
```

```
python -m playwright install chromium
```

## Run the recorder (stage 1)

```
python capture_video.py --headed
```

The browser window is shown while recording (recommended: DuckDuckGo more often
shows a bot check in background mode).
Videos are saved to `./video/<Company Name>.webm`; the path is printed for every row.

## Run the web service (stage 2)

Start the service in one terminal:

```
python web_service.py
```

It listens on `0.0.0.0:8000` by default. Override with the `FLASK_HOST` and
`FLASK_PORT` environment variables. On first start it creates `videos.db`
(SQLite) and the `uploads/` folder next to the script.

Then run the recorder in a second terminal with `--server`:

```
python capture_video.py --headed --server http://127.0.0.1:8000
```

After each recorded video the recorder uploads it, logs the returned URL and
opens it in Chromium (a visible window) for preview. A failed upload or
preview is logged and the batch continues with the next row.

| Option | Meaning |
| --- | --- |
| `--server URL` | Web service base URL. If omitted, nothing is uploaded and `requests` is not needed. |
| `--view-seconds N` | Preview time. `N > 0`: close the browser after N seconds (default 5). `0`: keep it open until Enter is pressed. |

### Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/upload` | UploadVideo: multipart form with `file` and `company_name`; saves the file, upserts the DB record, returns `{"company_name": ..., "video_url": ...}` |
| GET | `/get_video_url?company_name=<name>` | GetVideoURL: returns the same JSON, or 404 if the company is unknown |
| GET | `/media/<filename>` | serves an uploaded video so the URL plays in a browser |
| GET | `/videos` | lists all records (optional) |

Re-uploading the same `company_name` updates the existing record (no duplicate rows).

Examples:

```
curl -F "file=@video/ACME_GmbH.webm" -F "company_name=ACME GmbH" http://127.0.0.1:8000/upload
curl "http://127.0.0.1:8000/get_video_url?company_name=ACME%20GmbH"
```

### Database

SQLite file `videos.db`, table `videos`: `company_name` (unique), `file_path`
(absolute path on disk), `video_url`, `created_at`, `updated_at`. Only the path
and URL are stored; the video itself lives in `uploads/`. A new connection is
opened per request, WAL mode and a busy timeout are enabled so concurrent
uploads do not fail with "database is locked".

### Client functions

`video_client.py` provides:

```python
UploadVideo(server_url: str, video_path: str, company_name: str) -> str
GetVideoURL(server_url: str, company_name: str) -> str
```

## Files

- `capture_video.py` - reads the CSV (`;` delimiter, `"` qualifier) and calls the function for each row; with `--server` uploads and previews each video
- `qscript.py` - `CaptureVideo_Magento(...)`, `PATH_TO_VIDEO_FOLDER`, `ShowCallout(...)`
- `web_service.py` - Flask web service and SQLite database layer (stage 2)
- `video_client.py` - `UploadVideo` / `GetVideoURL` client functions (stage 2)
- `input.csv` - sample input
- `requirements.txt` - dependencies (Flask, Requests, Playwright)
- `sample/sample.webm` - example of the recorded video
