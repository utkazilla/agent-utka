import json
import tempfile
from pathlib import Path

from .speech import DEFAULT_QWEN_MODEL, QWEN_ASR_MODELS


BASE = Path(__file__).resolve().parents[1]
RUNTIME = BASE / ".runtime"
LOCAL_SETTINGS = BASE / "settings.local.json"
UI_LANGUAGES = ("ru", "en", "es")
DEFAULTS = {
    "ollama": "qwen3.5:4b",
    "ollama_url": "http://127.0.0.1:11434",
    "ollama_model": "qwen3.5:4b",
    "llm_provider": "ollama",
    "llm_model": "",
    "llm_url": "http://127.0.0.1:1234/v1",
    "stt_engine": "qwen",
    "qwen_model": DEFAULT_QWEN_MODEL,
    "whisper_model": "large-v3",
    "whisper_device": "auto",
    "stt_url": "http://127.0.0.1:8000/v1",
    "stt_model": "",
    "ui_language": "ru",
    "rag_directory": "",
    "rag_provider": "sqlite",
    "rag_url": "http://127.0.0.1:8090/search",
    "pause_ms": 420,
    "extra_roots": [],
    "project": "",
    "glossary": "",
}


def _local_settings(path):
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}


def load_settings(path=LOCAL_SETTINGS):
    settings = {**DEFAULTS, **_local_settings(path)}
    if settings["ui_language"] not in UI_LANGUAGES:
        settings["ui_language"] = DEFAULTS["ui_language"]
    qwen = settings["qwen_model"]
    if not isinstance(qwen, str) or qwen not in QWEN_ASR_MODELS:
        settings["qwen_model"] = DEFAULT_QWEN_MODEL
    return settings


def save_settings(updates, path=LOCAL_SETTINGS):
    data = {**_local_settings(path), **updates}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent, prefix=".settings-", delete=False) as file:
            temporary = Path(file.name)
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def index_path(settings):
    directory = settings.get("rag_directory")
    folder = Path(directory).expanduser().resolve() if directory else RUNTIME
    name = "knowledge.sqlite" if folder == RUNTIME else "call-copilot-knowledge.sqlite"
    return folder / name
