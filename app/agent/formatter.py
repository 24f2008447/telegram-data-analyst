import json

from app.utils.llm_client import chat_json
from app.agent.prompts import FORMATTER_SYSTEM_PROMPT, FALLBACK_KNOWLEDGE_SYSTEM_PROMPT


def format_answer(question_text: str, raw_result: dict, output_schema: dict = None, logger=None) -> dict:
    """Given the original question (which states the exact JSON shape) and the
    raw computed result, return the value that should go into the "answer" key."""
    user_content = (
        f"Original question:\n{question_text}\n\n"
        f"Computed raw result (from real code execution, trust these values):\n"
        f"{json.dumps(raw_result, default=str)}"
    )
    raw_response = chat_json(FORMATTER_SYSTEM_PROMPT, user_content)

    # The prompt always asks for {"answer_value": <actual answer>} so that a
    # bare number/string/array answer is still valid top-level JSON (OpenAI's
    # response_format=json_object requires an object at the top level, so the
    # model can't return a bare scalar/array directly). Unwrap it here.
    if isinstance(raw_response, dict) and "answer_value" in raw_response:
        answer_value = raw_response["answer_value"]
    else:
        # Model didn't follow the wrapper convention (older prompt, or a
        # provider that ignores json_mode) - fall back to using the raw
        # response as-is rather than failing the whole run.
        if logger:
            logger.log("formatter_missing_wrapper", raw_response=raw_response)
        answer_value = raw_response

    if logger and output_schema and isinstance(answer_value, dict) and isinstance(output_schema, dict):
        expected_keys = set(output_schema.keys())
        actual_keys = set(answer_value.keys())
        if expected_keys != actual_keys:
            logger.log("formatter_shape_mismatch", expected_keys=list(expected_keys), actual_keys=list(actual_keys))

    return answer_value


def answer_from_knowledge(question_text: str, logger=None):
    """Last-resort fallback used only when the normal pipeline (dataset
    download/search/SQL) fails entirely - e.g. a scrape-hostile source like
    data.gov.in/MOSPI blocked or returned an unusable page. Asks the LLM to
    answer directly from its own knowledge instead of giving up with a
    guaranteed-wrong `null`. Returns the answer value, or None if even this
    fails."""
    try:
        raw_response = chat_json(FALLBACK_KNOWLEDGE_SYSTEM_PROMPT, question_text)
    except Exception as e:
        if logger:
            logger.log("fallback_knowledge_failed", error=str(e))
        return None

    if isinstance(raw_response, dict) and "answer_value" in raw_response:
        answer_value = raw_response["answer_value"]
    else:
        if logger:
            logger.log("fallback_missing_wrapper", raw_response=raw_response)
        answer_value = raw_response

    if logger:
        logger.log("fallback_knowledge_answer", answer=answer_value)
    return answer_value