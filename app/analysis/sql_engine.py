"""
Runs arbitrary SQL against an in-memory DuckDB, with a pandas DataFrame
registered as a table called `data`. Used when the operation the planner
describes is more naturally expressed as a query (joins, pivots, complex
group-bys) than as a chain of pandas calls.
"""
import duckdb
import pandas as pd


def run_query(df: pd.DataFrame, sql: str) -> pd.DataFrame:
    """Run `sql` against `df`, which is registered as table name `data`."""
    con = duckdb.connect()
    con.register("data", df)
    try:
        result = con.execute(sql).fetchdf()
    finally:
        con.close()
    return result


def run_multi_table_query(tables: dict, sql: str) -> pd.DataFrame:
    """tables: {table_name: DataFrame}. Useful for join/merge questions."""
    con = duckdb.connect()
    for name, tdf in tables.items():
        con.register(name, tdf)
    try:
        result = con.execute(sql).fetchdf()
    finally:
        con.close()
    return result
