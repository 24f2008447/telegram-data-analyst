import json
from unittest.mock import patch

from app.webhook import handle_incoming_message
from app.agent import conversation


INLINE_QUESTION = (
    "Here is the data:\n"
    "name,score\nAlice,90\nBob,80\nCarol,95\n"
    'Who has the highest score? Reply with ONLY this JSON object and nothing else: '
    '{"answer": {"name": "<name>"}, "log_url": "<public wget-able URL to your agent\'s JSONL log>"}'
)


def _fake_plan(*args, **kwargs):
    return {
        "needs_external_data": False,
        "dataset_hint": None,
        "dataset_url": None,
        "data_format_guess": "inline",
        "operation": "find the name with the highest score",
        "output_schema": {"name": "<name>"},
        "notes": "",
    }


def _fake_sql_writer(system_prompt, user_content, temperature=0.0):
    return {"sql": 'SELECT name FROM data ORDER BY score DESC LIMIT 1'}


def _fake_formatter(system_prompt, user_content, temperature=0.0):
    # Matches the real FORMATTER_SYSTEM_PROMPT's required wrapper shape.
    return {"answer_value": {"name": "Carol"}}


@patch("app.webhook.uploader.upload", return_value="https://example.com/fake_log.jsonl")
@patch("app.agent.formatter.chat_json", side_effect=_fake_formatter)
@patch("app.agent.executor.chat_json", side_effect=_fake_sql_writer)
@patch("app.agent.planner.chat_json", side_effect=_fake_plan)
def test_full_pipeline_inline_data(mock_plan, mock_sql, mock_fmt, mock_upload):
    chat_id = 555
    conversation.clear(chat_id)
    reply = handle_incoming_message(chat_id, INLINE_QUESTION)
    assert reply is not None
    parsed = json.loads(reply)
    assert set(parsed.keys()) == {"answer", "log_url"}
    assert parsed["answer"] == {"name": "Carol"}
    assert parsed["log_url"] == "https://example.com/fake_log.jsonl"


SCALAR_QUESTION = (
    "Here is the data:\n"
    "name,score\nAlice,90\nBob,80\nCarol,95\n"
    'What is the highest score? Reply with ONLY this JSON object and nothing else: '
    '{"answer": <number>, "log_url": "<public wget-able URL to your agent\'s JSONL log>"}'
)


def _fake_scalar_formatter(system_prompt, user_content, temperature=0.0):
    return {"answer_value": 95}


@patch("app.webhook.uploader.upload", return_value="https://example.com/fake_log.jsonl")
@patch("app.agent.formatter.chat_json", side_effect=_fake_scalar_formatter)
@patch("app.agent.executor.chat_json", side_effect=_fake_sql_writer)
@patch("app.agent.planner.chat_json", side_effect=_fake_plan)
def test_full_pipeline_bare_scalar_answer(mock_plan, mock_sql, mock_fmt, mock_upload):
    # Regression test: before the answer_value wrapper fix, a question whose
    # "answer" is a bare number/string/array (not a nested object) could not
    # round-trip through response_format=json_object correctly.
    chat_id = 557
    conversation.clear(chat_id)
    reply = handle_incoming_message(chat_id, SCALAR_QUESTION)
    assert reply is not None
    parsed = json.loads(reply)
    assert parsed["answer"] == 95
    assert isinstance(parsed["answer"], int)
    conversation.clear(chat_id)


def test_non_final_message_returns_no_reply():
    chat_id = 556
    conversation.clear(chat_id)
    reply = handle_incoming_message(chat_id, "just some context, not a final question")
    assert reply is None
    conversation.clear(chat_id)
