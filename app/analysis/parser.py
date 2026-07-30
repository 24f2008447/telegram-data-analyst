"""
Universal loader: turns a local file (csv/excel/json/html) OR inline text
found in a chat message into a pandas DataFrame.
"""
import io
import re
import pandas as pd


class ParseError(RuntimeError):
    pass


def load_file(path: str, fmt: str) -> pd.DataFrame:
    try:
        if fmt == "csv":
            return pd.read_csv(path)
        if fmt == "excel":
            return pd.read_excel(path)
        if fmt == "json":
            return pd.read_json(path)
        if fmt == "html":
            tables = pd.read_html(path)
            if not tables:
                raise ParseError("No tables found in HTML page")
            # heuristic: return the largest table (most likely the real data)
            return max(tables, key=lambda df: df.shape[0] * df.shape[1])
    except Exception as e:
        raise ParseError(f"Failed to parse {fmt} file at {path}: {e}")
    raise ParseError(f"Unsupported format: {fmt}")


def _largest_delimited_block(text: str, delimiter: str) -> str:
    """Find the longest run of consecutive lines that all split into the same
    number (>1) of fields on `delimiter`, and return that block."""
    lines = text.splitlines()
    best_start, best_len, best_fields = 0, 0, 0
    i = 0
    while i < len(lines):
        fields = len(lines[i].split(delimiter))
        if fields > 1:
            j = i
            while j < len(lines) and len(lines[j].split(delimiter)) == fields:
                j += 1
            block_len = j - i
            if block_len > best_len:
                best_start, best_len, best_fields = i, block_len, fields
            i = j
        else:
            i += 1
    if best_len < 2:
        return ""
    return "\n".join(lines[best_start:best_start + best_len])


def extract_inline_table(text: str) -> pd.DataFrame:
    """Best-effort extraction of an inline CSV/TSV/markdown table embedded in a
    chat message into a DataFrame. Scans for the largest contiguous block of
    consistently-delimited lines rather than assuming the whole message is a table."""
    # Try a fenced code block first
    fence_match = re.search(r"```(?:csv|tsv)?\n(.*?)```", text, re.DOTALL)
    search_space = fence_match.group(1) if fence_match else text

    # Markdown-style table (| a | b |)
    md_lines = [l for l in search_space.splitlines() if l.strip().startswith("|")]
    if len(md_lines) >= 2:
        rows = [
            [c.strip() for c in line.strip().strip("|").split("|")]
            for line in md_lines
            if not re.match(r"^\s*:?-+:?\s*(\|\s*:?-+:?\s*)*$", line.strip().strip("|"))
        ]
        if len(rows) >= 2:
            return pd.DataFrame(rows[1:], columns=rows[0])

    # Comma-separated block
    csv_block = _largest_delimited_block(search_space, ",")
    if csv_block:
        try:
            df = pd.read_csv(io.StringIO(csv_block))
            if df.shape[1] > 1:
                return df
        except Exception:
            pass

    # Tab-separated block
    tsv_block = _largest_delimited_block(search_space, "\t")
    if tsv_block:
        try:
            df = pd.read_csv(io.StringIO(tsv_block), sep="\t")
            if df.shape[1] > 1:
                return df
        except Exception:
            pass

    # Whitespace-separated fallback over the whole search space
    try:
        df = pd.read_csv(io.StringIO(search_space), sep=r"\s+", engine="python")
        if df.shape[1] > 1:
            return df
    except Exception:
        pass

    raise ParseError("Could not extract a tabular structure from the message text")
