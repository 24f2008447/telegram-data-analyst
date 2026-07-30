import pandas as pd
from unittest.mock import patch

from app.agent import executor


def _df(cols_vals):
    return pd.DataFrame(cols_vals)


def test_resolve_dataset_uses_planner_url_when_it_works():
    with patch("app.agent.executor._try_load_url", return_value=_df({"a": [1, 2]})) as mock_load:
        df = executor._resolve_one_dataset("https://example.com/data.csv", "some hint")
        assert df is not None
        mock_load.assert_called_once_with("https://example.com/data.csv")


def test_resolve_dataset_falls_back_to_websearch_when_url_fails():
    calls = {"n": 0}

    def fake_try_load(url):
        calls["n"] += 1
        if url == "https://good.example.com/data.csv":
            return _df({"a": [1]})
        return None

    with patch("app.agent.executor._try_load_url", side_effect=fake_try_load), \
         patch("app.agent.executor.websearch.search", return_value=[
             "https://bad.example.com/page",
             "https://good.example.com/data.csv",
         ]), \
         patch("app.agent.executor.websearch.rank_dataset_like", side_effect=lambda urls: urls):
        df = executor._resolve_one_dataset("https://broken.example.com/404", "some hint")
        assert df is not None
        assert calls["n"] >= 2  # tried the bad planner URL, then a search candidate


def test_resolve_dataset_raises_if_nothing_works():
    with patch("app.agent.executor._try_load_url", return_value=None), \
         patch("app.agent.executor.websearch.search", return_value=[]), \
         patch("app.agent.executor.websearch.rank_dataset_like", side_effect=lambda urls: urls):
        try:
            executor._resolve_one_dataset(None, "totally unfindable dataset")
            assert False, "expected ExecutionError"
        except executor.ExecutionError:
            pass


def test_load_dataframes_multi_url_join():
    plan = {
        "needs_external_data": True,
        "dataset_urls": ["https://a.example.com/x.csv", "https://b.example.com/y.csv"],
        "dataset_hint": "two datasets to join",
    }
    with patch("app.agent.executor._resolve_one_dataset", side_effect=[_df({"id": [1]}), _df({"id": [1]})]):
        tables = executor._load_dataframes(plan, "conversation blob")
        assert set(tables.keys()) == {"data_1", "data_2"}


def test_load_dataframes_inline_unaffected():
    plan = {"needs_external_data": False}
    text = "name,score\nAlice,90\nBob,80\n"
    tables = executor._load_dataframes(plan, text)
    assert list(tables.keys()) == ["data"]
    assert len(tables["data"]) == 2
