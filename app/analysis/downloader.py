"""
Downloads a dataset from a URL to local disk, guessing its type from the
URL/content-type. Supports CSV, Excel, JSON, ZIP (extracted), and raw HTML
(for pd.read_html table extraction).
"""
import os
import uuid
import zipfile
import requests

from app.config import settings

os.makedirs(settings.download_dir, exist_ok=True)


class DownloadError(RuntimeError):
    pass


def guess_format(url: str, content_type: str = "") -> str:
    lower_url = url.lower()
    if lower_url.endswith(".csv"):
        return "csv"
    if lower_url.endswith((".xlsx", ".xls")):
        return "excel"
    if lower_url.endswith(".json"):
        return "json"
    if lower_url.endswith(".zip"):
        return "zip"
    if "csv" in content_type:
        return "csv"
    if "spreadsheet" in content_type or "excel" in content_type:
        return "excel"
    if "json" in content_type:
        return "json"
    if "zip" in content_type:
        return "zip"
    return "html"  # fall back to scraping a table out of the page


def download(url: str, timeout: int = 20) -> dict:
    """Download `url`, return {"path": local_path, "format": fmt}."""
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "data-analyst-bot/1.0"})
        resp.raise_for_status()
    except requests.RequestException as e:
        raise DownloadError(f"Failed to download {url}: {e}")

    content_type = resp.headers.get("Content-Type", "")
    fmt = guess_format(url, content_type)

    run_id = uuid.uuid4().hex[:8]
    if fmt == "html":
        path = os.path.join(settings.download_dir, f"{run_id}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(resp.text)
        return {"path": path, "format": "html"}

    ext = {"csv": "csv", "excel": "xlsx", "json": "json", "zip": "zip"}[fmt]
    path = os.path.join(settings.download_dir, f"{run_id}.{ext}")
    with open(path, "wb") as f:
        f.write(resp.content)

    if fmt == "zip":
        extract_dir = os.path.join(settings.download_dir, run_id)
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(path) as zf:
            zf.extractall(extract_dir)
        # pick the first csv/xlsx/json found inside
        for root, _, files in os.walk(extract_dir):
            for name in files:
                if name.lower().endswith((".csv", ".xlsx", ".xls", ".json")):
                    inner_path = os.path.join(root, name)
                    inner_fmt = guess_format(name)
                    return {"path": inner_path, "format": inner_fmt}
        raise DownloadError("ZIP did not contain a recognizable data file")

    return {"path": path, "format": fmt}
