from app.agent import conversation


def test_independent_chat_histories():
    conversation.clear(1)
    conversation.clear(2)
    conversation.add_message(1, "hello from chat 1")
    conversation.add_message(2, "hello from chat 2")
    assert conversation.get_history(1) == ["hello from chat 1"]
    assert conversation.get_history(2) == ["hello from chat 2"]
    conversation.clear(1)
    conversation.clear(2)


def test_is_final_question_detects_answer_shape():
    final = 'Which state? Reply with ONLY this JSON: {"answer": {"state": "..."}, "log_url": "..."}'
    not_final = "Here is some context data: 1,2,3,4"
    assert conversation.is_final_question(final) is True
    assert conversation.is_final_question(not_final) is False


def test_is_final_question_handles_non_answer_key_names():
    # Some questions use a different key than "answer" - the detector must not
    # hardcode one specific key name.
    final = 'Forecast for these inputs: [1,2,3]. Reply with ONLY {"values": [<numbers>]}.'
    assert conversation.is_final_question(final) is True


def test_is_final_question_ignores_inline_json_data_mid_message():
    # Regression test: earlier heuristic matched any {"key": ...} pattern
    # anywhere in the text, so a context message that merely hands over
    # inline JSON-shaped data (plausible for real datasets) was wrongly
    # treated as the final question, cutting multi-turn sequences short.
    context_with_json_data = (
        'Here is the dataset: {"state": "Assam", "rate": 4.2} '
        "Use this in the next step."
    )
    assert conversation.is_final_question(context_with_json_data) is False


def test_is_final_question_fallback_still_catches_trailing_template():
    # If a question doesn't literally say "reply with only" but still ends
    # the message with an embedded JSON template, the fallback should catch it.
    trailing_template = 'What is the total? Respond with {"answer": 0}'
    assert conversation.is_final_question(trailing_template) is True


def test_multi_turn_accumulates_context():
    chat_id = 99
    conversation.clear(chat_id)
    conversation.add_message(chat_id, "Here is some data: [1,2,3]")
    conversation.add_message(chat_id, "Now add 10 to each")
    conversation.add_message(
        chat_id,
        'Sum the result. Reply with ONLY this JSON: {"answer": {"sum": 0}, "log_url": "..."}',
    )
    blob = conversation.build_context_blob(chat_id)
    assert "[1,2,3]" in blob
    assert "add 10" in blob
    assert "Sum the result" in blob
    conversation.clear(chat_id)
