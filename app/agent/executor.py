"""
Executor turns a plan into a real computed result.

Strategy: rather than trying to hardcode every possible operation
(mean/median/groupby/join/...), we let the LLM write a DuckDB SQL query
against the loaded table(s) - SQL is easy to sandbox (read-only, no side
effects) and DuckDB makes pandas-shaped data queryable directly. Real
execution then produces the real number, avoiding LLM arithmetic mistakes.

Dataset discovery is layered so a single wrong LLM guess doesn't sink the
whole answer:
  1. Try plan['dataset_url'] (or each of plan['dataset_urls']) if given.
  2. If that fails or is missing, run a free web search on dataset_hint and
     try the top ranked candidate links until one downloads and parses.
"""
from typing import Optional, List
import pandas as pd

from app.analysis import downloader, parser, sql_engine, websearch
from app.utils.llm_client import chat_json
from app.agent.prompts import EXECUTOR_SEARCH_SYSTEM_PROMPT

SQL_WRITER_PROMPT = """You write a single DuckDB SQL query to answer a data question.
You are given the table name(s), their columns/dtypes, and the operation to perform.
Return ONLY JSON: {"sql": "SELECT ..."}
Rules:
- Use exactly the table name(s) given. Only a single SELECT statement. No DDL/DML, no multiple statements.
- Quote column names with double quotes if they contain spaces.
- Prefer including ORDER BY + LIMIT 1 for "which X has highest/lowest Y" questions.
- Apply any rounding/precision/formatting instructions mentioned in the operation.
"""

MAX_CANDIDATE_DOWNLOADS = 4


class ExecutionError(RuntimeError):
    pass


def _try_load_url(url: str, logger=None, _depth: int = 0) -> Optional[pd.DataFrame]:
    try:
        dl = downloader.download(url)
        return parser.load_file(dl["path"], dl["format"])
    except Exception:
        pass

    # If it resolved to an HTML page with no usable <table> (common for
    # government open-data catalog/landing pages), crawl it one level deep
    # for an actual data-file link (e.g. the real CSV/ZIP behind a "Download"
    # button) instead of giving up immediately.
    if _depth >= 1:
        return None
    try:
        dl = downloader.download(url)
        if dl["format"] != "html":
            return None
        with open(dl["path"], "r", encoding="utf-8") as f:
            html_text = f.read()
    except Exception:
        return None

    candidate_links = downloader.extract_data_links(html_text, url)
    if logger:
        logger.log("html_page_crawled", url=url, candidate_links=candidate_links)
    for link in candidate_links:
        df = _try_load_url(link, logger=logger, _depth=_depth + 1)
        if df is not None:
            if logger:
                logger.log("dataset_loaded_from_crawled_link", url=link)
            return df
    return None


def _resolve_one_dataset(url: Optional[str], hint: str, logger=None) -> pd.DataFrame:
    # 1. Try the planner's own URL guess first, if it gave one.
    if url:
        df = _try_load_url(url, logger=logger)
        if df is not None:
            if logger:
                logger.log("dataset_loaded_from_planner_url", url=url)
            return df
        if logger:
            logger.log("planner_url_failed", url=url)

    # 2. Fall back to a free web search using the hint, try ranked candidates.
    query = hint or url or ""
    if not query:
        raise ExecutionError("No dataset URL or hint available to resolve a dataset")

    candidates = websearch.rank_dataset_like(websearch.search(query))
    if logger:
        logger.log("websearch_candidates", query=query, candidates=candidates[:MAX_CANDIDATE_DOWNLOADS])

    for candidate in candidates[:MAX_CANDIDATE_DOWNLOADS]:
        df = _try_load_url(candidate, logger=logger)
        if df is not None:
            if logger:
                logger.log("dataset_loaded_from_search", url=candidate)
            return df
        if logger:
            logger.log("candidate_failed", url=candidate)

    # 3. Last resort: web search returned nothing usable (e.g. blocked from this
    # host's IP) - ask the LLM directly for its best-guess direct download URL.
    try:
        guess = chat_json(EXECUTOR_SEARCH_SYSTEM_PROMPT, query)
        guessed_url = guess.get("url")
    except Exception as e:
        guessed_url = None
        if logger:
            logger.log("llm_url_guess_failed", error=str(e))

    if guessed_url:
        if logger:
            logger.log("llm_url_guess", query=query, url=guessed_url)
        df = _try_load_url(guessed_url, logger=logger)
        if df is not None:
            if logger:
                logger.log("dataset_loaded_from_llm_guess", url=guessed_url)
            return df
        if logger:
            logger.log("llm_guess_failed", url=guessed_url)

    raise ExecutionError(f"Could not download/parse any dataset for hint: {query!r}")


def _load_dataframes(plan: dict, conversation_blob: str, logger=None) -> dict:
    """Returns {table_name: DataFrame}."""
    if not plan.get("needs_external_data"):
        df = parser.extract_inline_table(conversation_blob)
        return {"data": df}

    urls: List[str] = plan.get("dataset_urls") or []
    if urls:
        tables = {}
        for i, url in enumerate(urls, start=1):
            tables[f"data_{i}"] = _resolve_one_dataset(url, plan.get("dataset_hint", ""), logger)
        return tables

    single_url = plan.get("dataset_url")
    hint = plan.get("dataset_hint") or plan.get("operation") or ""
    return {"data": _resolve_one_dataset(single_url, hint, logger)}


def _write_sql(tables: dict, operation: str) -> str:
    schema_lines = []
    for name, df in tables.items():
        schema_lines.append(f"Table `{name}` columns/dtypes: {dict(df.dtypes.astype(str))}")
    description = "\n".join(schema_lines) + f"\nOperation requested: {operation}"
    result = chat_json(SQL_WRITER_PROMPT, description)
    sql = result.get("sql", "").strip()
    if not sql.lower().startswith("select"):
        raise ExecutionError(f"Refusing non-SELECT SQL from planner: {sql}")
    return sql


def execute(plan: dict, conversation_blob: str, logger=None) -> dict:
    """Returns {"raw_result": ..., "sql": ..., "columns": [...]}"""
    tables = _load_dataframes(plan, conversation_blob, logger)
    if logger:
        for name, df in tables.items():
            logger.log("data_loaded", table=name, rows=len(df), columns=list(df.columns))

    operation = plan.get("operation", "")
    sql = _write_sql(tables, operation)
    if logger:
        logger.log("sql_generated", sql=sql)

    try:
        result_df = sql_engine.run_multi_table_query(tables, sql)
    except Exception as e:
        if logger:
            logger.log("sql_failed_retrying", error=str(e))
        schema_lines = [f"Table `{n}` columns/dtypes: {dict(df.dtypes.astype(str))}" for n, df in tables.items()]
        retry_desc = (
            "\n".join(schema_lines)
            + f"\nOperation requested: {operation}\n"
            + f"Previous SQL failed with error: {e}\nPrevious SQL: {sql}\nWrite a corrected query."
        )
        result = chat_json(SQL_WRITER_PROMPT, retry_desc)
        sql = result.get("sql", "").strip()
        result_df = sql_engine.run_multi_table_query(tables, sql)

    raw_result = result_df.to_dict(orient="records")
    return {"raw_result": raw_result, "sql": sql, "columns": list(result_df.columns)}