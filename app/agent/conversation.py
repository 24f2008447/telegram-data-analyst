"""
Very small in-memory conversation store, keyed by Telegram chat_id.
Each chat gets its own independent message history.

A message is treated as "the final question to answer" if it contains an
explicit instruction to reply with a JSON object (this is how the grader's
messages are formatted: "Reply with ONLY this JSON object ...").
Everything before it in the same chat is kept as context for multi-turn tasks.

Note on the fallback heuristic: an earlier version matched a bare
`{"key": ...}`-shaped substring *anywhere* in the message as a fallback
trigger. That is too eager - a mid-conversation context message that happens
to hand over inline JSON-ish data (plausible for real datasets) would be
mistaken for the final question and cut the multi-turn sequence short before
the real question ever arrived. The fallback below is scoped to only look at
the *tail* of the message and requires the message to actually end on a
closing `}` - i.e. it looks like "...respond with {template}" rather than
"here's some data: {...} now here's more text after it".
"""
import re
import time
from collections import defaultdict
from typing import List, Dict

_HISTORY: Dict[int, List[dict]] = defaultdict(list)

_FINAL_MESSAGE_PATTERN = re.compile(r'\{\s*"[A-Za-z_]+"\s*:', re.IGNORECASE)
_REPLY_INSTRUCTION_PATTERN = re.compile(r'reply\s+with\s+only', re.IGNORECASE)

# How far from the end of the message the fallback JSON-template check looks.
_TAIL_WINDOW = 300


def add_message(chat_id: int, text: str) -> None:
    _HISTORY[chat_id].append({"text": text, "ts": time.time()})


def get_history(chat_id: int) -> List[str]:
    return [m["text"] for m in _HISTORY[chat_id]]


def is_final_question(text: str) -> bool:
    """Heuristic: does this message specify the exact JSON reply shape (i.e. it's
    the question we should actually answer now)? Different questions may use
    different key names (e.g. "answer", "values", "state"), so we don't hardcode
    one - we look for the near-universal "reply with only ..." instruction first.

    Fallback (only used when that phrase is absent): the message ends with a
    JSON-object-shaped template, e.g. '...respond with {"answer": ...}'. This is
    intentionally narrower than "contains JSON anywhere" so that a context
    message that merely hands over inline JSON-ish data mid-conversation isn't
    mistaken for the final question.
    """
    if _REPLY_INSTRUCTION_PATTERN.search(text):
        return True

    stripped = text.strip()
    if stripped.endswith("}") and _FINAL_MESSAGE_PATTERN.search(stripped[-_TAIL_WINDOW:]):
        return True

    return False


def clear(chat_id: int) -> None:
    _HISTORY.pop(chat_id, None)


def build_context_blob(chat_id: int) -> str:
    """Join full history into one block for the planner, most recent last."""
    history = get_history(chat_id)
    numbered = [f"[message {i+1}]\n{msg}" for i, msg in enumerate(history)]
    return "\n\n".join(numbered)
