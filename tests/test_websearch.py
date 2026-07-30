from unittest.mock import patch, MagicMock

from app.analysis import websearch


def test_search_parses_duckduckgo_html():
    fake_html = """
    <div class="result">
      <a class="result__a" href="https://example.com/data.csv">Data CSV</a>
    </div>
    <div class="result">
      <a class="result__a" href="https://example.com/page.html">Some page</a>
    </div>
    """
    fake_resp = MagicMock()
    fake_resp.text = fake_html
    fake_resp.raise_for_status = lambda: None

    with patch("app.analysis.websearch.requests.post", return_value=fake_resp):
        results = websearch.search("some dataset")
        assert "https://example.com/data.csv" in results
        assert "https://example.com/page.html" in results


def test_search_returns_empty_on_network_error():
    import requests
    with patch("app.analysis.websearch.requests.post", side_effect=requests.RequestException("boom")):
        assert websearch.search("anything") == []


def test_rank_dataset_like_prioritizes_direct_files():
    urls = [
        "https://example.com/about",
        "https://data.gov.in/dataset",
        "https://example.com/raw/file.csv",
    ]
    ranked = websearch.rank_dataset_like(urls)
    assert ranked[0] == "https://example.com/raw/file.csv"
    assert ranked[1] == "https://data.gov.in/dataset"
