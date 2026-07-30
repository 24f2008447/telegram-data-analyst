import pandas as pd
import pytest

from app.analysis import dataframe_engine, sql_engine, parser


@pytest.fixture
def sample_df():
    return pd.DataFrame({
        "state": ["A", "B", "C"],
        "literacy": [85.5, 92.3, 78.1],
    })


def test_basic_stat_mean(sample_df):
    assert dataframe_engine.basic_stat(sample_df, "literacy", "mean") == pytest.approx((85.5 + 92.3 + 78.1) / 3)


def test_row_with_extreme_max(sample_df):
    row = dataframe_engine.row_with_extreme(sample_df, "literacy", mode="max")
    assert row["state"] == "B"


def test_row_with_extreme_min(sample_df):
    row = dataframe_engine.row_with_extreme(sample_df, "literacy", mode="min")
    assert row["state"] == "C"


def test_group_by_agg():
    df = pd.DataFrame({"grp": ["x", "x", "y"], "val": [1, 2, 3]})
    out = dataframe_engine.group_by_agg(df, "grp", "val", "sum")
    assert out.set_index("grp").loc["x", "val"] == 3
    assert out.set_index("grp").loc["y", "val"] == 3


def test_sql_engine_basic(sample_df):
    result = sql_engine.run_query(sample_df, 'SELECT state FROM data ORDER BY literacy DESC LIMIT 1')
    assert result.iloc[0]["state"] == "B"


def test_extract_inline_table_csv():
    text = "Here is the data:\nname,score\nAlice,90\nBob,80\n"
    df = parser.extract_inline_table(text)
    assert list(df.columns) == ["name", "score"]
    assert len(df) == 2


def test_extract_inline_table_markdown():
    text = """
    | name | score |
    | --- | --- |
    | Alice | 90 |
    | Bob | 80 |
    """
    df = parser.extract_inline_table(text)
    assert "name" in df.columns
    assert len(df) == 2


def test_missing_values():
    df = pd.DataFrame({"a": [1, None, 3], "b": [None, None, 1]})
    result = dataframe_engine.missing_values(df)
    assert result["a"] == 1
    assert result["b"] == 2


def test_percentage():
    assert dataframe_engine.percentage(25, 200) == 12.5
    assert dataframe_engine.percentage(1, 0) is None
