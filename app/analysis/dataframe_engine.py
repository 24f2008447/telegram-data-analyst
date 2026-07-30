"""
Common analysis operations expressed as small, safe pandas helpers.
The agent's executor calls these directly for well-understood operations
instead of asking the LLM to "do math" - real code computes real numbers.
"""
import pandas as pd


def describe_columns(df: pd.DataFrame) -> dict:
    return {
        "columns": list(df.columns),
        "dtypes": {c: str(t) for c, t in df.dtypes.items()},
        "n_rows": len(df),
        "sample": df.head(3).to_dict(orient="records"),
    }


def basic_stat(df: pd.DataFrame, column: str, stat: str):
    series = pd.to_numeric(df[column], errors="coerce").dropna()
    ops = {
        "mean": series.mean,
        "median": series.median,
        "mode": lambda: series.mode().iloc[0] if not series.mode().empty else None,
        "sum": series.sum,
        "count": series.count,
        "min": series.min,
        "max": series.max,
        "std": series.std,
    }
    if stat not in ops:
        raise ValueError(f"Unsupported stat: {stat}")
    return ops[stat]()


def row_with_extreme(df: pd.DataFrame, value_column: str, mode: str = "max") -> dict:
    """Return the full row where value_column is max/min (e.g. 'state with highest literacy')."""
    series = pd.to_numeric(df[value_column], errors="coerce")
    idx = series.idxmax() if mode == "max" else series.idxmin()
    return df.loc[idx].to_dict()


def group_by_agg(df: pd.DataFrame, group_col: str, value_col: str, agg: str) -> pd.DataFrame:
    return df.groupby(group_col)[value_col].agg(agg).reset_index()


def correlation(df: pd.DataFrame, col_a: str, col_b: str) -> float:
    a = pd.to_numeric(df[col_a], errors="coerce")
    b = pd.to_numeric(df[col_b], errors="coerce")
    return a.corr(b)


def missing_values(df: pd.DataFrame) -> dict:
    return df.isna().sum().to_dict()


def percentage(part: float, whole: float) -> float:
    return (part / whole) * 100 if whole else None


def rank(df: pd.DataFrame, value_col: str, ascending: bool = False) -> pd.DataFrame:
    out = df.copy()
    out["_rank"] = pd.to_numeric(out[value_col], errors="coerce").rank(ascending=ascending, method="min")
    return out.sort_values("_rank")
