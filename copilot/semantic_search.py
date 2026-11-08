"""Optional local semantic search over the same imported passages as SQLite."""

import hashlib
import logging
import sqlite3
import threading
from contextlib import closing

import numpy as np

from .knowledge import Knowledge, Source, scope_roots
from .ollama_library import LocalOllama, _json_request


MODEL = "qwen3-embedding:0.6b"
LOG = logging.getLogger(__name__)


def _normalized(values, count):
    vectors = np.asarray(values, dtype=np.float32)
    if vectors.ndim != 2 or vectors.shape[0] != count or not np.isfinite(vectors).all():
        raise ValueError("Invalid embedding response")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    if np.any(norms == 0):
        raise ValueError("Empty embedding")
    return vectors / norms


def fuse(lexical, semantic, limit):
    scores = {}
    for ranking in (lexical, semantic):
        for rank, source in enumerate(dict.fromkeys(ranking)):
            scores[source] = scores.get(source, 0) + 1 / (12 + rank)
    return sorted(scores, key=scores.get, reverse=True)[:limit]


class HybridKnowledge(Knowledge):
    """SQLite remains usable if embeddings are absent or the local server is busy."""

    def __init__(self, path, brain):
        super().__init__(path, documents_only=True)
        self.brain = brain
        self._snapshots = {}
        self._lock = threading.Lock()
        self._closed = threading.Event()
        self._cache = self.path.with_name(self.path.stem + "-semantic.sqlite")

    def close(self):
        self._closed.set()

    def _embed(self, host, texts, timeout):
        return _normalized(_json_request(host, "/api/embed", {
            "model": MODEL, "input": texts, "truncate": False, "keep_alive": "5m",
            "options": {"num_ctx": 2048},
        }, timeout=timeout)["embeddings"], len(texts))

    def _files(self, root):
        with closing(self._connect()) as db:
            return tuple(db.execute(
                "SELECT path,mtime,bytes FROM files WHERE project=? AND indexed=1 ORDER BY path",
                (str(root),)))

    def refresh(self, root):
        result = super().refresh(root)
        if self._closed.is_set() or not result[0] or not isinstance(self.brain, LocalOllama):
            return result
        root, = scope_roots(root)
        try:
            host = self.brain.start()
            models = _json_request(host, "/api/tags").get("models", [])
            model = next((item for item in models if item.get("name") == MODEL
                          and not item.get("remote_model") and not item.get("remote_host")), {})
            digest = model.get("digest")
            if not digest:
                with self._lock:
                    self._snapshots.pop(root, None)
                return result
            fingerprint = (digest, self._files(root))
            with self._lock:
                previous = self._snapshots.get(root)
                if previous and previous[0] == fingerprint:
                    return result
                self._snapshots.pop(root, None)
            with closing(self._connect()) as db:
                sources = [Source(root / path, int(line), body) for path, line, body in db.execute(
                    "SELECT path,line,body FROM passages WHERE project=? ORDER BY path,line", (str(root),))]
            texts = [f"{s.path.name}\n{s.text}" for s in sources]
            keys = [hashlib.sha256(("v1\n" + digest + "\n" + t).encode()).hexdigest() for t in texts]
            by_key = dict(zip(keys, texts))
            vectors = {}
            with closing(sqlite3.connect(self._cache, timeout=10)) as db:
                db.execute("CREATE TABLE IF NOT EXISTS vectors (key TEXT PRIMARY KEY, data BLOB)")
                for key in by_key:
                    row = db.execute("SELECT data FROM vectors WHERE key=?", (key,)).fetchone()
                    if row:
                        vectors[key] = np.frombuffer(row[0], dtype=np.float32)
                pending = [key for key in by_key if key not in vectors]
                for start in range(0, len(pending), 32):
                    if self._closed.is_set():
                        return result
                    batch = pending[start:start + 32]
                    values = self._embed(host, [by_key[k] for k in batch], 45)
                    vectors.update(zip(batch, values))
                    with db:
                        db.executemany("INSERT OR REPLACE INTO vectors VALUES (?,?)",
                                       ((key, vector.tobytes()) for key, vector in zip(batch, values)))
            if sources and fingerprint[1] == self._files(root) and not self._closed.is_set():
                matrix = _normalized([vectors[k] for k in keys], len(keys))
                with self._lock:
                    self._snapshots[root] = (fingerprint, sources, matrix)
                LOG.info("semantic_index_ready passages=%s", len(sources))
        except (OSError, RuntimeError, ValueError, KeyError, sqlite3.Error) as error:
            LOG.info("semantic_index_unavailable %s", type(error).__name__)
        return result

    def search(self, scope, query, limit=4):
        roots = scope_roots(scope)
        if not roots:
            return []
        lexical = super().search(roots[0] if len(roots) == 1 else roots, query, limit=max(12, limit))
        with self._lock:
            snapshots = [self._snapshots.get(root) for root in roots]
        valid = [item for root, item in zip(roots, snapshots)
                 if item is not None and item[0][1] == self._files(root)]
        if not valid:
            return lexical[:limit]
        try:
            prompt = "Instruct: Retrieve the project passages that answer this question.\nQuery: " + query
            vector, = self._embed(self.brain.start(), [prompt], 5)
            candidates = []
            for _, sources, matrix in valid:
                scores = matrix @ vector
                candidates.extend((float(scores[i]), sources[i])
                                  for i in np.argsort(scores)[::-1][:max(12, limit)])
            semantic = [source for _, source in sorted(candidates, key=lambda item: item[0], reverse=True)
                        [:max(12, limit)]]
            return fuse(lexical, semantic, limit)
        except (OSError, RuntimeError, ValueError, KeyError):
            return lexical[:limit]
