from app.utils.llm_client import chat_json
from app.agent.prompts import PLANNER_SYSTEM_PROMPT


def plan(conversation_blob: str) -> dict:
    """Ask the LLM to produce a structured plan for answering the last message
    in `conversation_blob`. Returns the parsed plan dict."""
    plan_dict = chat_json(PLANNER_SYSTEM_PROMPT, conversation_blob)

    # sane defaults in case the model omits a field
    plan_dict.setdefault("needs_external_data", False)
    plan_dict.setdefault("dataset_hint", None)
    plan_dict.setdefault("dataset_url", None)
    plan_dict.setdefault("dataset_urls", [])
    plan_dict.setdefault("data_format_guess", "inline")
    plan_dict.setdefault("operation", "")
    plan_dict.setdefault("output_schema", {})
    plan_dict.setdefault("notes", "")
    return plan_dict
