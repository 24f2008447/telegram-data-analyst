"""
Writes one JSON object per line to logs/<run_id>.jsonl, recording every
step of processing a single question (received -> planning -> download ->
analysis -> formatting -> reply). Used both for debugging and because the
assignment grades a public copy of this log.
"""
import json
import os
import time
import uuid

from app.config import settings

os.makedirs(settings.local_log_dir, exist_ok=True)


class RunLogger:
    def __init__(self, chat_id: int = None):
        self.run_id = uuid.uuid4().hex[:12]
        self.chat_id = chat_id
        self.path = os.path.join(settings.local_log_dir, f"run_{self.run_id}.jsonl")
        self._fh = open(self.path, "a", encoding="utf-8")

    def log(self, step: str, **fields) -> None:
        entry = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "run_id": self.run_id,
            "chat_id": self.chat_id,
            "step": step,
            **fields,
        }
        self._fh.write(json.dumps(entry, default=str) + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()
