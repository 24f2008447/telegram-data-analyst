"""
Lightweight, no-API-key web search used ONLY as a fallback for locating a
public dataset URL when the planner/LLM doesn't already know a direct link.
Scrapes DuckDuckGo's HTML endpoint (no auth, no rate-limit key needed) -
good enough for finding a CSV/XLSX/data-page link, not meant as a general
search product.
"""
import re
import requests
from bs4 import BeautifulSoup

_HEADERS = {"User-Agent": "Mozilla/5.0 (data-analyst-bot; +https://github.com)"}


def search(query: str, max_results: int = 8) -> list:
    """Return a list of result URLs for `query`, best-effort. Never raises -
    returns [] on any failure so callers can fall back gracefully."""
    try:
        resp = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers=_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    urls = []
    for a in soup.select("a.result__a"):
        href = a.get("href", "")
        # DuckDuckGo's html endpoint sometimes wraps the real URL in a redirect param
        match = re.search(r"uddg=([^&]+)", href)
        if match:
            from urllib.parse import unquote
            href = unquote(match.group(1))
        if href.startswith("http"):
            urls.append(href)
        if len(urls) >= max_results:
            break
    return urls


def rank_dataset_like(urls: list) -> list:
    """Sort candidate URLs so likely-direct-data links (csv/xlsx/json/zip)
    come first, then government/stats domains, then everything else."""
    def score(u: str) -> int:
        lower = u.lower()
        if lower.endswith((".csv", ".xlsx", ".xls", ".json", ".zip")):
            return 0
        if any(d in lower for d in ["mospi.gov.in", "data.gov.in", ".gov", "worldbank.org", "data.gov"]):
            return 1
        return 2
    return sorted(urls, key=score)
