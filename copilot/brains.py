import json
import threading
from urllib.parse import urlsplit
from urllib.request import Request

from .ollama_library import LocalOllama, local_api_opener


BRAIN_PROVIDERS = {
    "ollama": "Ollama · встроенный",
    "ollama_local": "Ollama · установленный",
    "openai_local": "OpenAI-совместимый · локальный",
}


def local_api_url(url):
    parsed = urlsplit(url.strip())
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1"}
            or parsed.username is not None or parsed.password is not None or parsed.query
            or parsed.fragment or parsed.path.rstrip("/") not in {"", "/v1"}):
        raise ValueError("Укажи локальный адрес вида http://127.0.0.1:1234/v1.")
    host = "[::1]" if parsed.hostname == "::1" else "127.0.0.1"
    port = f":{parsed.port}" if parsed.port is not None else ""
    return f"http://{host}{port}/v1"


def local_ollama_url(url):
    try:
        return local_api_url(url).removesuffix("/v1")
    except ValueError as error:
        raise ValueError("Укажи локальный адрес Ollama, например http://127.0.0.1:11434.") from error


class LocalChatCompletions:
    def __init__(self, url, model):
        self.url = local_api_url(url)
        self.model = model
        self.closed = threading.Event()
        self.opener = local_api_opener()

    def _request(self, endpoint, payload=None):
        if self.closed.is_set():
            raise RuntimeError("Соединение с локальной моделью закрыто.")
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        req = Request(self.url + endpoint, data=data, headers={"Content-Type": "application/json"})
        with self.opener.open(req, timeout=15 if payload is not None else 3) as response:
            return json.load(response)

    def models(self):
        response = self._request("/models")
        if not isinstance(response, dict) or not isinstance(response.get("data"), list):
            raise ValueError("Сервер не вернул список моделей в ожидаемом формате.")
        return sorted(model["id"] for model in response["data"]
                      if isinstance(model, dict) and isinstance(model.get("id"), str))

    def warm(self):
        if self.model not in self.models():
            raise ValueError("Модель не найдена на локальном сервере.")

    def generate(self, payload, cancelled, on_prefix=None):
        if cancelled():
            return {}
        result = self._request("/chat/completions", {
            "model": self.model,
            "messages": payload["messages"],
            "temperature": 0,
            "max_tokens": payload["options"]["num_predict"],
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "copilot_answer", "schema": payload["format"]},
            },
        })
        if cancelled():
            return {}
        try:
            return json.loads(result["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as error:
            raise ValueError("Сервер не вернул ответ в ожидаемом формате.") from error

    def close(self):
        self.closed.set()


def create_brain(runtime, settings):
    provider = settings.get("llm_provider", "ollama")
    if provider == "openai_local":
        return LocalChatCompletions(settings["llm_url"], settings["llm_model"])
    if provider == "ollama_local":
        address = local_ollama_url(settings.get("ollama_url", "http://127.0.0.1:11434"))
        return LocalOllama(runtime, settings.get("ollama_model") or settings.get("ollama", "qwen3.5:4b"),
                           external_host=urlsplit(address).netloc)
    return LocalOllama(runtime, settings["ollama"])
