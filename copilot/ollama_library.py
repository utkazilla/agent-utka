import json
import os
import re
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


CONTEXT_SIZE = 6144
_MODEL_PART = r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,79}"
_NAMESPACE = r"[A-Za-z0-9_][A-Za-z0-9_-]{0,79}"
_MODEL_NAME = re.compile(
    rf"(?:(?:registry\.ollama\.ai/)?(?P<namespace>{_NAMESPACE})/)?"
    rf"(?P<name>{_MODEL_PART})(?::(?P<tag>{_MODEL_PART}))?",
    re.ASCII,
)


def validate_ollama_model(model):
    name = model.strip()
    match = _MODEL_NAME.fullmatch(name)
    if not match:
        raise ValueError("Введи тег Ollama, например qwen3.5:4b.")
    tag = (match["tag"] or "").lower()
    if tag == "cloud" or tag.endswith("-cloud"):
        raise ValueError("Выбери локальную модель Ollama вместо облачной.")
    return name


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def local_api_opener():
    return build_opener(ProxyHandler({}), _NoRedirect())


def _byte_count(value):
    return value if type(value) is int and value >= 0 else None


@dataclass(frozen=True)
class OllamaModel:
    name: str
    size: int | None
    quantization: str
    size_vram: int | None


def _open(host, path, payload=None, timeout=3):
    request = Request("http://" + host + path,
                      data=json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None,
                      headers={"Content-Type": "application/json"})
    return local_api_opener().open(request, timeout=timeout)


def _json_request(host, path, payload=None, timeout=3):
    with _open(host, path, payload, timeout) as response:
        return json.load(response)


class LocalOllama:
    def __init__(self, runtime, model, *, external_host=None):
        if external_host and not re.fullmatch(r"(?:127\.0\.0\.1|\[::1\])(?::[0-9]{1,5})?", external_host):
            raise ValueError("Укажи локальный адрес Ollama, например http://127.0.0.1:11434.")
        self.runtime = Path(runtime)
        self.model = model
        self.external_host = external_host
        self.process = None
        self.host = None
        self.lock = threading.Lock()
        self.closed = threading.Event()

    def start(self):
        if self.closed.is_set():
            raise RuntimeError("Локальный сервер уже закрыт.")
        if self.external_host:
            try:
                status = _json_request(self.external_host, "/api/status")
            except HTTPError as error:
                if error.code not in (404, 405):
                    raise
                status = {}
            cloud = status.get("cloud") if isinstance(status, dict) else None
            if not isinstance(cloud, dict) or cloud.get("disabled") is not True:
                raise RuntimeError("Обнови Ollama и отключи облако через OLLAMA_NO_CLOUD=1.")
            return self.external_host
        with self.lock:
            if self.closed.is_set():
                raise RuntimeError("Локальный сервер уже закрыт.")
            if self.process and self.process.poll() is None and self.host:
                return self.host
            exe = self.runtime / "ollama" / "ollama.exe"
            if not exe.is_file():
                raise FileNotFoundError("Локальный Ollama отсутствует. Запусти Setup Agent Utka.ps1.")
            with socket.socket() as port:
                port.bind(("127.0.0.1", 0))
                host = f"127.0.0.1:{port.getsockname()[1]}"
            env = dict(os.environ, OLLAMA_HOST=host,
                       OLLAMA_MODELS=str(self.runtime / "ollama-models"),
                       OLLAMA_NO_CLOUD="1", OLLAMA_NUM_PARALLEL="1", OLLAMA_FLASH_ATTENTION="1")
            with (self.runtime / "ollama-app.log").open("ab") as log:
                self.process = subprocess.Popen(
                    [str(exe), "serve"], env=env, stdout=log, stderr=log,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            for _ in range(50):
                if self.closed.is_set() or self.process.poll() is not None:
                    break
                try:
                    _json_request(host, "/api/version", timeout=1)
                    if self.process.poll() is None:
                        self.host = host
                        return host
                except OSError:
                    self.closed.wait(.2)
            if self.process.poll() is None:
                self.process.terminate()
            self.host = None
            raise RuntimeError("Ollama не запустился. См. .runtime/ollama-app.log.")

    def warm(self):
        name = validate_ollama_model(self.model)
        host = self.start()
        _json_request(host, "/api/chat", {"model": name, "stream": False, "think": False,
                      "messages": [{"role": "user", "content": "Say OK."}],
                      "keep_alive": "30m", "options": {"num_ctx": CONTEXT_SIZE, "num_predict": 4}},
                      timeout=85)

    def _list(self, endpoint):
        response = _json_request(self.start(), endpoint)
        if not isinstance(response, dict) or not isinstance(response.get("models"), list):
            raise ValueError("Сервер не вернул список моделей в ожидаемом формате.")
        models = []
        for item in response["models"]:
            if not isinstance(item, dict) or item.get("remote_host") or item.get("remote_model"):
                continue
            try:
                name = validate_ollama_model(item.get("name") or item.get("model") or "")
            except (ValueError, AttributeError):
                continue
            details = item.get("details")
            if not isinstance(details, dict):
                details = {}
            models.append(OllamaModel(name, _byte_count(item.get("size")),
                                      details.get("quantization_level") or "",
                                      _byte_count(item.get("size_vram"))))
        return sorted(models, key=lambda model: model.name.casefold())

    def models(self):
        return [model.name for model in self.model_details()]

    def model_details(self):
        return self._list("/api/tags")

    def running_models(self):
        return self._list("/api/ps")

    def unload_model(self, model):
        name = validate_ollama_model(model)
        _json_request(self.start(), "/api/generate",
                      {"model": name, "stream": False, "keep_alive": 0}, timeout=10)

    def pull(self, model, on_progress=lambda status, completed, total: None, cancelled=lambda: False):
        name = validate_ollama_model(model)

        def stopped():
            return self.closed.is_set() or cancelled()

        if stopped():
            return False
        host = self.start()
        if stopped():
            return False
        try:
            with _open(host, "/api/pull", {"model": name, "stream": True}, timeout=30) as response:
                for line in response:
                    if stopped():
                        return False
                    event = json.loads(line)
                    if "error" in event:
                        raise RuntimeError(event["error"])
                    status = event.get("status")
                    if not isinstance(status, str):
                        continue
                    on_progress(status, _byte_count(event.get("completed")), _byte_count(event.get("total")))
                    if status == "success":
                        return True
        except OSError:
            if not stopped():
                raise
        if stopped():
            return False
        raise RuntimeError("Загрузка модели Ollama завершилась без подтверждения.")

    def close(self):
        self.closed.set()
        with self.lock:
            if self.process and self.process.poll() is None:
                self.process.terminate()

    def generate(self, payload, cancelled, on_prefix=None):
        if cancelled():
            return {}
        host = self.start()
        request = {**payload, "model": validate_ollama_model(payload.get("model", self.model))}
        pieces = []
        deadline = time.monotonic() + 15
        with _open(host, "/api/chat", request, timeout=14) as response:
            for line in response:
                if cancelled():
                    return {}
                if time.monotonic() >= deadline:
                    raise TimeoutError("Локальная генерация превысила 15 секунд")
                event = json.loads(line)
                if "error" in event:
                    raise RuntimeError(event["error"])
                pieces.append(event.get("message", {}).get("content", ""))
                if on_prefix and on_prefix("".join(pieces)):
                    on_prefix = None
                if event.get("done"):
                    break
        return json.loads("".join(pieces))
