"""Local answer diagnostics without questions, snippets, or model output."""

import json
import logging
from contextvars import ContextVar
from hashlib import sha256


REQUEST_ID = ContextVar("answer_request_id", default=None)
LOG = logging.getLogger("call_copilot.answer")


def event(stage, **fields):
    request_id = REQUEST_ID.get()
    if request_id is not None:
        LOG.info("%s", json.dumps({"request_id": request_id, "stage": stage, **fields},
                                 separators=(",", ":")))


def span(source):
    return {"file_id": sha256(str(source.path).encode("utf-8")).hexdigest()[:20],
            "start": source.line, "end": source.line + max(0, len(source.text.splitlines()) - 1),
            "chars": len(source.text)}
