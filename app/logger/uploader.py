"""
Publishes a local JSONL log file to a public GitHub repo (via the GitHub
Contents API), then returns a public raw.githubusercontent.com URL that is
wget-able with no auth. This is a zero-extra-infra option -- if you'd rather
use S3/GCS/Azure Blob, swap this module's upload() implementation, the rest
of the app doesn't need to change.
"""
import base64
import requests

from app.config import settings


class UploadError(RuntimeError):
    pass


def upload(local_path: str, remote_name: str) -> str:
    if not settings.github_token or not settings.github_log_repo:
        raise UploadError("GITHUB_TOKEN / GITHUB_LOG_REPO not configured")

    with open(local_path, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode()

    api_url = f"https://api.github.com/repos/{settings.github_log_repo}/contents/logs/{remote_name}"
    headers = {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
    }
    payload = {
        "message": f"Add run log {remote_name}",
        "content": content_b64,
        "branch": settings.github_log_branch,
    }
    resp = requests.put(api_url, headers=headers, json=payload, timeout=30)
    if resp.status_code not in (200, 201):
        raise UploadError(f"GitHub upload failed: {resp.status_code} {resp.text[:300]}")

    raw_url = (
        f"https://raw.githubusercontent.com/{settings.github_log_repo}/"
        f"{settings.github_log_branch}/logs/{remote_name}"
    )
    return raw_url
