import time
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings


def _slow_handle_incoming_message(chat_id, text):
    time.sleep(2)  # simulate a slow LLM/download pipeline
    return '{"answer": {"ok": true}, "log_url": "https://example.com/log.jsonl"}'


@pytest.mark.asyncio
async def test_webhook_acks_fast_even_when_processing_is_slow():
    update = {
        "message": {
            "chat": {"id": 123},
            "text": 'Reply with ONLY {"answer": {"ok": true}, "log_url": "..."}',
        }
    }
    transport = httpx.ASGITransport(app=app)
    with patch("app.main.handle_incoming_message", side_effect=_slow_handle_incoming_message), \
         patch("app.main.bot", None):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            start = time.monotonic()
            resp = await client.post(f"/webhook/{settings.telegram_webhook_secret}", json=update)
            elapsed = time.monotonic() - start

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    # The webhook must return well before the simulated 2s processing time -
    # it should ack immediately and process in the background, on the same
    # persistent event loop a real deployed server would use.
    assert elapsed < 1.0


def test_webhook_rejects_wrong_secret():
    client = TestClient(app)
    resp = client.post("/webhook/wrong-secret", json={"message": {"chat": {"id": 1}, "text": "hi"}})
    assert resp.status_code == 403
