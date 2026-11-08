import json
from pathlib import PurePosixPath
from urllib.parse import urlsplit
from urllib.request import Request

from .brains import local_api_opener


DEFAULT_SEARCH_URL = "http://127.0.0.1:8090/search"
RETRIEVAL_PROVIDERS = {"sqlite": "SQLite · встроенный", "ollama_hybrid": "SQLite + поиск по смыслу",
                       "http_local": "Локальный API поиска"}


def local_search_url(value):
    message = "Укажи локальный адрес поиска вида http://127.0.0.1:8090/search."
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except ValueError as error:
        raise ValueError(message) from error
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1"}
            or parsed.username is not None or parsed.password is not None or parsed.query
            or parsed.fragment or not parsed.path or parsed.path == "/"
            or any(char.isspace() for char in parsed.path)):
        raise ValueError(message)
    host = "[::1]" if parsed.hostname == "::1" else "127.0.0.1"
    return f"http://{host}{':' + str(port) if port is not None else ''}{parsed.path}"


class LocalSearch:
    def __init__(self, url):
        self.url = url
        self.opener = local_api_opener()

    def references(self, root, query, limit):
        try:
            return self._references(root, query, limit)
        except (OSError, ValueError) as error:
            raise SearchUnavailable(str(error)) from error

    def _references(self, root, query, limit):
        limit = min(max(limit, 1), 16)
        payload = json.dumps({"project": str(root), "query": query, "limit": limit}, ensure_ascii=False)
        request = Request(local_search_url(self.url), data=payload.encode("utf-8"),
                          headers={"Content-Type": "application/json", "Accept": "application/json"})
        with self.opener.open(request, timeout=4) as response:
            body = response.read(65537)
        if len(body) > 65536:
            raise ValueError("Ответ локального API поиска слишком большой.")
        result = json.loads(body)
        if not isinstance(result, dict) or not isinstance(result.get("hits"), list):
            raise ValueError("Локальный API поиска должен вернуть список hits.")
        references = []
        for hit in result["hits"][:limit * 2]:
            if not isinstance(hit, dict):
                continue
            name, line = hit.get("path"), hit.get("line")
            if (not isinstance(name, str) or not name or len(name) > 1024
                    or any(char in name for char in ("\\", ":", "\x00"))
                    or type(line) is not int or not 1 <= line <= 180000):
                continue
            path = PurePosixPath(name)
            if path.parts and not path.is_absolute() and ".." not in path.parts:
                references.append((path, line))
        return references


class SearchUnavailable(RuntimeError):
    pass


def create_retriever(settings):
    if settings.get("rag_provider") == "http_local":
        return LocalSearch(settings.get("rag_url", DEFAULT_SEARCH_URL))
    return None
