import json
import math
import os
import re
import sqlite3
import subprocess
import time
from contextlib import closing
from dataclasses import dataclass
from fnmatch import fnmatchcase
from functools import lru_cache
from itertools import chain
from pathlib import Path

from .knowledge_pack import MAX_DOCUMENT_BYTES, PACK_FILENAMES, imported_documents, parse_pack


REGISTRY = Path.home() / ".codex" / ".codex-global-state.json"
INDEX_VERSION = 5
SKIP = {".git", ".svn", ".codex", ".agents", ".aws", ".ssh", ".idea", ".vscode", ".venv",
        ".runtime", "node_modules", "__pycache__", "dist", "build", "target", "vendor",
        "obj", "bin", "coverage", "call copilot", "logs", "secrets", "credentials"}
TEXT = {".md", ".rst", ".txt", ".adoc", ".py", ".js", ".jsx", ".ts", ".tsx", ".cs",
        ".java", ".kt", ".kts", ".go", ".rs", ".swift", ".sql", ".yaml", ".yml", ".json",
        ".toml", ".ini", ".properties", ".gradle", ".xml", ".html", ".css", ".sh", ".ps1",
        ".rb", ".cpp", ".c", ".h", ".hpp", ".vue", ".svelte", ".tf", ".http", ".proto"}
PRIVATE_PATH = re.compile(r"(^|[._-])(secrets?|credentials?|passwords?|tokens?|private.?key|auth.?cache|diagnostic|dump)([._-]|$)", re.I)
PRIVATE_BODY = re.compile(
    r"-----BEGIN (?:[\w ]+ )?PRIVATE KEY-----|"
    r"""(?im:^[ \t-]*["']?(?:[\w.-]*[_.-])?(?:api[_-]?key|password|client[_-]?secret|access[_-]?token|private[_-]?key)["']?\s*[:=]\s*\S)|"""
    r"\b(?:ghp_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16})\b"
)
STOP = set("and the why what which with from about when where this that there would should could please how are was were does did have can will you your can about есть почему зачем как что кто где когда если это эта этой или для при про ещё так такой какой такая нам нужно можно надо нас у его её они оно он она еще ли чем такой какие работает просто происходит".split())


@dataclass(frozen=True)
class Project:
    name: str
    root: Path


@dataclass(frozen=True)
class Source:
    path: Path
    line: int
    text: str


def discover_projects(registry=REGISTRY, extra=()):
    items = []
    try:
        local = json.loads(Path(registry).read_text(encoding="utf-8-sig")).get("local-projects", {})
        for project in local.values():
            if isinstance(project, dict):
                items.extend((project.get("name"), p) for p in project.get("rootPaths", [])
                             if isinstance(p, str))
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    items.extend((None, p) for p in extra)
    result = {}
    for name, path in items:
        try:
            root = Path(path).expanduser().resolve()
            if root.is_dir() and root != Path.home().resolve() and root.parent != root:
                result.setdefault(root, Project(str(name or root.name), root))
        except (OSError, ValueError):
            pass
    return sorted(result.values(), key=lambda p: (p.name.casefold(), str(p.root).casefold()))


def _directory_allowed(path):
    name = path.name.casefold()
    return ((not name.startswith(".") or name == ".copilot-knowledge")
            and name not in SKIP and not PRIVATE_PATH.search(name)
            and not path.is_symlink() and not path.is_junction())


def _file_allowed(path, root):
    name = path.name.casefold()
    if (name.startswith(".") or name.endswith((".min.js", ".lock.json", "-lock.json"))
            or name in {"package-lock.json", "composer.lock", "pnpm-lock.yaml", "search-aliases.json"}
            or PRIVATE_PATH.search(name)
            or (path.suffix.lower() not in TEXT and name not in {"readme", "dockerfile", "makefile"})):
        return False
    return (not path.is_symlink() and path.is_file() and path.resolve().is_relative_to(root)
            and all(_directory_allowed(d) for d in path.parents if d != root and d.is_relative_to(root)))


def _repo_files(repo, *paths):
    try:
        run = subprocess.run(["git", "-C", str(repo), "ls-files", "-z", "--cached", "--others",
                              "--exclude-standard", "--", *paths], capture_output=True, check=True, timeout=6,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return (repo / os.fsdecode(p) for p in run.stdout.split(b"\0") if p)
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError(f"Не удалось прочитать файлы Git: {repo.name}") from error


def project_pack(root):
    """Select the first eligible root pack for the speech glossary."""
    root = Path(root).resolve()
    try:
        files = [root / name for name in PACK_FILENAMES if _file_allowed(root / name, root)]
        if files and (root / ".git").exists():
            visible = set(_repo_files(root, *(file.name for file in files)))
            files = [file for file in files if file in visible]
        return next(iter(files), None)
    except (OSError, RuntimeError, ValueError):
        pass
    return None


def _files(root):
    for current, dirs, files in os.walk(root, followlinks=False):
        directory = Path(current)
        if (directory / ".git").exists():
            paths = _repo_files(directory)
            dirs.clear()
            yield from paths
            continue
        dirs[:] = [d for d in dirs if _directory_allowed(directory / d)]
        yield from (directory / name for name in files)


@lru_cache(maxsize=8192)
def _stem(word):
    try:
        import Stemmer
        kind = "russian" if re.fullmatch(r"[а-я]+", word) else "english"
        return _stemmer(kind).stemWord(word)
    except ImportError:
        return word


@lru_cache(maxsize=2)
def _stemmer(kind):
    import Stemmer
    return Stemmer.Stemmer(kind)


def _terms(text, *, query=False):
    split = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    words = re.findall(r"[^\W_]+", (text + " " + split).lower().replace("ё", "е"))
    out = []
    for word in words:
        if len(word) >= 2 and (not query or word not in STOP):
            stem = _stem(word)
            if len(stem) >= 2:
                out.append(stem)
    return out


def _chunks(text, *, compact=False):
    lines = text.splitlines()
    cursor = 0
    line_limit, char_limit, overlap = (10, 760, 2) if compact else (22, 1150, 3)
    while cursor < len(lines):
        while cursor < len(lines) and not lines[cursor].strip():
            cursor += 1
        end = cursor
        chars = 0
        while end < len(lines) and end - cursor < line_limit and chars < char_limit:
            if compact and end > cursor and lines[end].startswith(("# ", "## ", "### ", "#### ")):
                break
            chars += len(lines[end]) + 1
            end += 1
        chunk = "\n".join(lines[cursor:end])[:1600]
        if chunk.strip():
            yield cursor + 1, chunk
        if end >= len(lines):
            break
        cursor = (end if compact and lines[end].startswith(("# ", "## ", "### ", "#### "))
                  else max(cursor + 1, end - overlap))


@lru_cache(maxsize=16)
def _load_aliases(file, modified):
    try:
        data = json.loads(file.read_text(encoding="utf-8-sig"))
        return tuple((re.compile(pattern, re.I), spec if isinstance(spec, dict) else {"terms": spec})
                     for pattern, spec in data.items() if isinstance(spec, (str, dict)))
    except (OSError, ValueError, TypeError, re.error, AttributeError):
        return ()


def _search_profile(root, query):
    file = root / ".copilot-knowledge" / "search-aliases.json"
    try:
        aliases = _load_aliases(file, file.stat().st_mtime_ns)
    except OSError:
        return [], []
    matching = [spec for pattern, spec in aliases if pattern.search(query)]
    return ([spec["terms"] for spec in matching if isinstance(spec.get("terms"), str)],
            [mask.casefold() for spec in matching for mask in spec.get("files", ())
             if isinstance(mask, str)])


def search_aliases(root, query):
    return _search_profile(root, query)[0]


@lru_cache(maxsize=2048)
def _term_set(text):
    return frozenset(_terms(text))


def _ranking(rows, terms, aliases, exact_names, preferred, limit):
    candidates = []
    term_set = set(terms)
    for name, line, body, bm25 in rows:
        words = _term_set(body)
        title = _term_set(name)
        local = max((len(term_set.intersection(_term_set(part)))
                     for part in body.splitlines() if part.strip()), default=0)
        candidates.append((name, line, body, bm25, words, title, local))
    freq = {t: sum(t in w or t in p for _, _, _, _, w, p, _ in candidates)
            for t in [*terms, *aliases]}
    weight = {t: math.log1p(len(candidates) / (1 + n)) for t, n in freq.items()}
    total = max(1, sum(weight[t] for t in terms))

    def score(row):
        name, _, _, bm25, words, title, local = row
        hit = sum(weight[t] * (1 if t in words else .55) for t in terms if t in words or t in title)
        alias = sum(weight[t] * (.55 if t in words else 1) for t in aliases if t in words or t in title)
        rel = name.replace("\\", "/").lower()
        penalty = .11 if rel.startswith(("snapshots/", "_archives/")) or "-history-" in rel else 0
        if "/src/test/" in rel:
            penalty += .04
        file = Path(name)
        named = .52 if file.stem.casefold() in exact_names else 0
        if preferred and any(fnmatchcase(file.name.casefold(), mask) for mask in preferred):
            named += .23
        return (.65 * hit / total + .23 * (-bm25 / best) + .16 * local / len(terms)
                + min(.34, .067 * alias) + named - penalty)

    if not candidates:
        return []
    best = max(1, -candidates[0][3])
    out, per_file, taken = [], {}, []
    for name, line, body, _, words, _, _ in sorted(candidates, key=score, reverse=True):
        if per_file.get(name, 0) >= 3:
            continue
        if any(len(words & seen) >= .72 * len(words | seen) for seen in taken):
            continue
        per_file[name] = per_file.get(name, 0) + 1
        out.append((name, line, body))
        taken.append(words)
        if len(out) >= limit:
            break
    return out


class Knowledge:
    def __init__(self, path, *, retriever=None):
        self.path = Path(path)
        self.retriever = retriever
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db, db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS files (
                  project TEXT, path TEXT, mtime INTEGER, bytes INTEGER, indexed INTEGER,
                  PRIMARY KEY(project, path));
                CREATE VIRTUAL TABLE IF NOT EXISTS passages USING fts5(
                  project UNINDEXED, path UNINDEXED, line UNINDEXED, body UNINDEXED,
                  terms, tokenize='unicode61');
                CREATE TABLE IF NOT EXISTS info (project TEXT PRIMARY KEY, refreshed REAL);
                CREATE TABLE IF NOT EXISTS index_version (project TEXT PRIMARY KEY, version INTEGER);
            """)

    def _connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def refresh(self, root):
        root = Path(root).resolve()
        if not root.is_dir():
            return self.status(root)
        project = str(root)
        with closing(self._connect()) as db:
            old_version = db.execute("SELECT version FROM index_version WHERE project=?", (project,)).fetchone()
            cached = {p: (m, b) for p, m, b in db.execute(
                "SELECT path, mtime, bytes FROM files WHERE project=?", (project,))}
            seen, edits = set(), []
            imported = set(imported_documents(root))
            root_packs = {root / name for name in PACK_FILENAMES}
            for file in chain(_files(root), sorted(imported)):
                try:
                    if not _file_allowed(file, root):
                        continue
                    name = str(file.relative_to(root))
                    if name in seen:
                        continue
                    seen.add(name)
                    info = file.stat()
                    signature = (info.st_mtime_ns, info.st_size)
                    if old_version == (INDEX_VERSION,) and cached.get(name) == signature:
                        continue
                    body = (file.read_text(encoding="utf-8-sig", errors="strict")
                            if 0 < info.st_size <= MAX_DOCUMENT_BYTES else "")
                    if "\x00" in body or PRIVATE_BODY.search(body):
                        body = ""
                    if file in imported or file in root_packs:
                        body, _ = parse_pack(body)
                    compact = file.suffix.casefold() in {".md", ".txt", ".adoc", ".rst"}
                    chunks = [(project, name, line, c, " ".join(_terms(name + " " + c)))
                              for line, c in _chunks(body, compact=compact)]
                    edits.append((name, signature, chunks))
                except (OSError, ValueError, UnicodeError):
                    # Temporarily inaccessible files keep their prior snapshot.
                    continue
            with db:
                rebuild = old_version != (INDEX_VERSION,)
                if rebuild:
                    db.execute("DELETE FROM passages WHERE project=?", (project,))
                    db.execute("DELETE FROM files WHERE project=?", (project,))
                else:
                    for name in cached.keys() - seen:
                        db.execute("DELETE FROM passages WHERE project=? AND path=?", (project, name))
                        db.execute("DELETE FROM files WHERE project=? AND path=?", (project, name))
                for name, (mtime, size), chunks in edits:
                    if not rebuild and name in cached:
                        db.execute("DELETE FROM passages WHERE project=? AND path=?", (project, name))
                    db.executemany("INSERT INTO passages VALUES (?,?,?,?,?)", chunks)
                    db.execute("INSERT OR REPLACE INTO files VALUES (?,?,?,?,?)",
                               (project, name, mtime, size, int(bool(chunks))))
                db.execute("INSERT OR REPLACE INTO info VALUES (?,?)", (project, time.time()))
                db.execute("INSERT OR REPLACE INTO index_version VALUES (?,?)", (project, INDEX_VERSION))
        return self.status(root)

    def status(self, root):
        project = str(Path(root).resolve())
        with closing(self._connect()) as db:
            count = db.execute("SELECT count(*) FROM files WHERE project=? AND indexed=1",
                               (project,)).fetchone()[0]
            stamp = db.execute("SELECT refreshed FROM info WHERE project=?", (project,)).fetchone()
        return count, stamp[0] if stamp else None

    def index_files(self, root):
        with closing(self._connect()) as db:
            return [row[0] for row in db.execute(
                "SELECT path FROM files WHERE project=? AND indexed=1 ORDER BY path COLLATE NOCASE",
                (str(Path(root).resolve()),))]

    def index_passages(self, root, name):
        root = Path(root).resolve()
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT line, body FROM passages WHERE project=? AND path=? ORDER BY CAST(line AS INTEGER)",
                (str(root), name))
            return [Source(root / name, int(line), body) for line, body in rows]

    def search(self, root, query, limit=4):
        root = Path(root).resolve()
        if self.retriever is not None:
            references = self.retriever.references(root, query, limit)
            return self._referenced_sources(root, references, limit)
        terms = list(dict.fromkeys(_terms(query, query=True)))[:24]
        if not terms:
            return []
        expansions, preferred = _search_profile(root, query)
        expansion = " ".join(expansions)
        aliases = [t for t in dict.fromkeys(_terms(expansion, query=True))
                   if t not in terms][:32]
        exact_names = {w.casefold() for w in expansion.split()
                       if re.fullmatch(r"[A-Za-z][A-Za-z0-9-]{9,}", w)}
        expr = " OR ".join(f'"{t}"' for t in [*terms, *aliases])
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT path,line,body,bm25(passages) FROM passages WHERE passages MATCH ? AND project=? "
                "ORDER BY bm25(passages) LIMIT ?", (expr, str(root), max(80, limit * 14))).fetchall()
            if preferred or exact_names:
                masks = [*preferred, *(name + ".*" for name in exact_names)]
                sql = ("SELECT path,line,body,bm25(passages) FROM passages "
                       "WHERE passages MATCH ? AND project=? AND (" +
                       " OR ".join("lower(path) LIKE ?" for _ in masks) +
                       ") ORDER BY bm25(passages) LIMIT 48")
                scope = ["%" + mask.replace("*", "%").replace("?", "_") for mask in masks]
                scoped = db.execute(sql, (expr, str(root), *scope)).fetchall()
                rows = list(dict.fromkeys([*rows, *scoped]))
            ranked = _ranking(rows, terms, aliases, exact_names, preferred, limit)
        return [Source(root / name, int(line), body) for name, line, body in ranked]

    def _referenced_sources(self, root, references, limit):
        references = [(str(Path(path)), line) for path, line in references]
        if not references:
            return []
        names = list(dict.fromkeys(name for name, _ in references))
        placeholders = ",".join("?" for _ in names)
        passages = {name: [] for name in names}
        with closing(self._connect()) as db:
            for name, start, body in db.execute(
                    f"SELECT path,line,body FROM passages WHERE project=? AND path IN ({placeholders}) "
                    "ORDER BY line DESC", (str(root), *names)):
                passages[name].append((int(start), body))
        sources = []
        for name, line in references:
            for start, body in passages[name]:
                if start <= line < start + body.count("\n") + 1:
                    source = Source(root / name, start, body)
                    if source not in sources:
                        sources.append(source)
                    break
            if len(sources) >= limit:
                break
        return sources
