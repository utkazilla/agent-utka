import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from .knowledge import Source
from .suggest import Card


@dataclass(frozen=True)
class Entry:
    id: int
    captured_at: float
    text: str
    card: Card


class History:
    def __init__(self, path, limit=200):
        self.db = sqlite3.connect(path, timeout=2)
        self.limit = limit
        with self.db:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS turns (
                    id INTEGER PRIMARY KEY, project TEXT NOT NULL, captured_at REAL NOT NULL,
                    transcript TEXT NOT NULL, card TEXT NOT NULL
                )
            """)

    @staticmethod
    def _project(root):
        if isinstance(root, tuple):
            return "*"
        return str(root.resolve()) if root else ""

    def add(self, root, text, card):
        now = time.time()
        payload = json.dumps({
            "label": card.label, "options": card.options,
            "sources": [[str(source.path), source.line, source.text] for source in card.sources],
        }, ensure_ascii=False)
        with self.db:
            row = self.db.execute(
                "INSERT INTO turns(project,captured_at,transcript,card) VALUES(?,?,?,?)",
                (self._project(root), now, text, payload))
            self.db.execute("DELETE FROM turns WHERE id IN (SELECT id FROM turns "
                            "ORDER BY id DESC LIMIT -1 OFFSET ?)", (self.limit,))
        return Entry(row.lastrowid, now, text, card)

    def recent(self, root):
        rows = self.db.execute(
            "SELECT id,captured_at,transcript,card FROM turns WHERE project=? "
            "ORDER BY id DESC LIMIT ?", (self._project(root), self.limit)).fetchall()
        entries = []
        for entry_id, captured, text, raw in reversed(rows):
            data = json.loads(raw)
            card = Card(tuple((option, ids) for option, ids in data["options"]),
                        tuple(Source(Path(path), line, body) for path, line, body in data["sources"]),
                        data["label"])
            entries.append(Entry(entry_id, captured, text, card))
        return entries

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
