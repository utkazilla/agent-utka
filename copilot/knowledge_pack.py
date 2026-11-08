"""Import local knowledge documents without sending files to an AI service."""

import json
import hashlib
import os
import re
import tempfile
from pathlib import Path


# Legacy automatic raw-code scans remain bounded; explicitly imported documents are complete.
MAX_DOCUMENT_BYTES = 180_000
PACK_FILENAME = "utka-cue-knowledge.md"
PACK_FILENAMES = (PACK_FILENAME, "utka-knowledge.md", "call-copilot-knowledge.md")
PACK_FENCE = "```utka-cue-asr"
_PACK_FENCES = {PACK_FENCE, "```utka-asr", "```call-copilot-asr"}
_TEXT_SUFFIXES = {".md", ".txt"}
_CONTEXT = re.compile(r"(?:\w+(?:\\w\*)?)(?:[ -]\w+(?:\\w\*)?)*")


def _validate_glossary(data):
    def words(values, limit=None):
        return (isinstance(values, list) and (limit is None or len(values) <= limit)
                and all(isinstance(value, str) and len(value) > 0
                        and value == value.strip() and "\n" not in value and "\r" not in value
                        for value in values))

    if not isinstance(data, dict) or not words(data.get("terms")):
        raise ValueError("В словаре нужны terms с точными написаниями.")
    terms = set(data["terms"])
    hints = data.get("hotwords", data["terms"][:10])
    if not words(hints, 20) or not set(hints) <= terms:
        raise ValueError("hotwords должен содержать до 20 терминов из terms.")
    rules = data.get("aliases", [])
    if not isinstance(rules, list):
        raise ValueError("aliases должен содержать список правил произношения.")
    for rule in rules:
        if (not isinstance(rule, dict) or not isinstance(rule.get("term"), str)
                or rule["term"] not in terms or not words(rule.get("heard"), 16)
                or not rule["heard"] or any(not value.strip(" .-") for value in rule["heard"])):
            raise ValueError("Каждое правило aliases должно содержать term из terms и список heard.")
        if "context" in rule:
            context = rule["context"]
            if not isinstance(context, str) or len(context) > 240:
                raise ValueError("context должен содержать короткие соседние слова или фразы.")
            if context.startswith(r"\b") and context.endswith(r"\b"):
                context = context[2:-2]
            if context.startswith("(?:") and context.endswith(")"):
                context = context[3:-1]
            if not all(_CONTEXT.fullmatch(part) for part in context.split("|")):
                raise ValueError(r"context допускает слова, фразы, |, \b и окончание \w*.")
    return {**data, "hotwords": hints}


_GLOSSARY_HEADING = re.compile(r"^(#{1,6})\s+Utka glossary\s*#*\s*$", re.I)
_HEADING = re.compile(r"^(#{1,6})\s+")
_DEFINITION_ROW = re.compile(r"^\s*[-*]\s+\*\*([^*\r\n]{1,80})\*\*\s+[—–-]\s+(\S.+)\s*$")
_DEFINITION_QUESTION = re.compile(
    r"^\s*¿?(?:что\s+такое|что\s+значит|what\s+(?:is|are)(?:\s+(?:a|an|the))?|"
    r"qu[eé]\s+es|qu[eé]\s+significa)\s+(?P<term>[\w.`+#-]+(?:\s+[\w.`+#-]+){0,4})\s*[?!.]*\s*$",
    re.I,
)


def term_key(term):
    return " ".join(term.strip().strip("`").casefold().split())


def definition_term(question):
    match = _DEFINITION_QUESTION.fullmatch(question)
    if not match:
        return None
    return term_key(match["term"].rstrip(".")) or None


def glossary_definitions(text):
    """Yield exact lines from glossary entries or an explicit definition heading."""
    level = None
    fence = None
    pending = None
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if fence:
            if len(line) >= len(fence) and set(line) == {fence[0]}:
                fence = None
            continue
        if match := re.match(r"^(`{3,}|~{3,})", line):
            fence = match[1]
            pending = None
            continue
        if match := _GLOSSARY_HEADING.fullmatch(line):
            level = len(match[1])
            pending = None
            continue
        if match := _HEADING.match(line):
            pending = definition_term(re.sub(r"\s+#+$", "", line[match.end():]))
            if level is not None and len(match[1]) <= level:
                level = None
            continue
        if pending is not None and line:
            if len(raw) <= 1200 and not re.match(r"^(?:[-*+] |\d+[.)] |[>|<`])", line):
                yield pending, number, raw
            pending = None
        if level is not None and (match := _DEFINITION_ROW.fullmatch(raw)) and len(raw) <= 1200:
            if key := term_key(match[1]):
                yield key, number, raw


def parse_pack(text):
    """Return the citation text and the optional glossary, preserving line numbers."""
    lines = text.splitlines(keepends=True)
    start = None
    glossary = None
    fence = None
    for i, line in enumerate(lines):
        value = line.strip()
        if fence:
            if len(value) >= len(fence) and set(value) == {fence[0]}:
                fence = None
            continue
        if start is not None:
            if value != "```":
                continue
            try:
                glossary = _validate_glossary(json.loads("".join(lines[start + 1:i])))
            except json.JSONDecodeError as error:
                raise ValueError(f"Неверный JSON в словаре на строке {start + error.lineno + 1}.") from error
            lines[start:i + 1] = ["\n"] * (i - start + 1)
            start = None
            continue
        if value in _PACK_FENCES:
            if glossary is not None:
                raise ValueError("В одном документе допустим один блок словаря распознавания.")
            start = i
        elif match := re.match(r"^(`{3,}|~{3,})", value):
            fence = match[1]
    if start is not None:
        raise ValueError("Блок словаря распознавания нужно закрыть тройными обратными кавычками.")
    return "".join(lines), glossary


def _import_folder(root, *, create=False):
    directory = root
    for part in (".copilot-knowledge", "imports"):
        directory = directory / part
        if directory.is_symlink() or directory.is_junction():
            raise ValueError(f"Папка импорта не может быть ссылкой: {directory}")
        if create:
            directory.mkdir(exist_ok=True)
    return directory


def create_workspace(folder):
    root = Path(folder).expanduser().resolve()
    if root.parent == root or root == Path.home().resolve():
        raise ValueError("Выбери отдельную папку проекта.")
    root.mkdir(parents=True, exist_ok=True)
    _import_folder(root, create=True)
    return root


def is_workspace(root):
    try:
        return _import_folder(root).is_dir()
    except (OSError, ValueError):
        return False


def imported_documents(root):
    try:
        folder = _import_folder(Path(root))
        return tuple(sorted((path for path in folder.iterdir()
                             if not path.name.startswith(".") and path.suffix.lower() in _TEXT_SUFFIXES
                             and path.is_file() and not path.is_symlink() and not path.is_junction()),
                            key=lambda path: path.name.casefold()))
    except (OSError, ValueError):
        return ()

def _base_metadata(root):
    path = Path(root) / ".copilot-knowledge" / "base.json"
    if any(item.is_symlink() or item.is_junction() for item in (path, path.parent)):
        raise ValueError("Описание базы не может быть ссылкой.")
    if not path.exists():
        return {}
    try:
        if path.stat().st_size > 200_000:
            raise ValueError()
        data = json.loads(path.read_text(encoding="utf-8"))
        imports = data.get("imports", {})
        titles = data.get("document_names", {})
        if (not isinstance(data.get("name"), str) or not isinstance(imports, dict)
                or any(not isinstance(k, str) or not isinstance(v, str)
                       or Path(v).name != v or v.startswith(".") or re.search(r'[<>:"/\\|?*\x00-\x1f]', v)
                       for k, v in imports.items())
                or len({v.casefold() for v in imports.values()}) != len(imports)):
            raise ValueError()
        if (not isinstance(titles, dict)
                or any(k not in imports.values() or not isinstance(v, str)
                       or not v.strip() or len(v) > 100 for k, v in titles.items())):
            raise ValueError()
        return data
    except (ValueError, AttributeError) as error:
        raise ValueError("Не удалось прочитать описание базы. Импорт отменён.") from error


def _source_identity(source):
    return hashlib.sha256(os.path.normcase(str(Path(source).expanduser().resolve())).encode("utf-8")).hexdigest()[:20]


def create_named_base(runtime, name):
    name = " ".join(name.split())
    if not name or len(name) > 100:
        raise ValueError("Введи название базы — до 100 символов.")
    library = Path(runtime) / "knowledge"
    key = hashlib.sha256(("base:" + name.casefold()).encode("utf-8")).hexdigest()[:20]
    root = library / key
    if library.is_symlink() or library.is_junction() or root.is_symlink() or root.is_junction():
        raise ValueError("Папка базы знаний не может быть ссылкой.")
    if root.exists():
        raise ValueError("Такая база уже есть. Выбери её в списке.")
    create_workspace(root)
    _save_base_metadata(root, {"name": name, "imports": {}, "document_names": {}})
    return root.resolve()


def _save_base_metadata(root, metadata):
    folder = _import_folder(create_workspace(root))
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=folder.parent,
                                         prefix=".base-", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(metadata, stream, ensure_ascii=False)
        os.replace(temporary, folder.parent / "base.json")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def import_title(root, source):
    """Preserve the user's display title when the same source is imported again."""
    if root is not None:
        metadata = _base_metadata(root)
        filename = metadata.get("imports", {}).get(_source_identity(source))
        if title := metadata.get("document_names", {}).get(filename):
            return title
    return document_title(source)


def imported_document_label(root, filename):
    try:
        title = _base_metadata(root).get("document_names", {}).get(filename)
    except (OSError, ValueError):
        title = None
    return f"{title} ({filename})" if title else filename


def import_summary(runtime, source, *, target=None, name=None, document_name=None):
    source = Path(source).expanduser().resolve()
    prepared = _prepare_documents([source])
    identity = _source_identity(source)
    library = Path(runtime) / "knowledge"
    if name is not None:
        name = " ".join(name.split())
        if not name or len(name) > 100:
            raise ValueError("Название базы должно содержать от 1 до 100 символов.")
    if document_name is not None:
        document_name = " ".join(document_name.split())
        if not document_name or len(document_name) > 100:
            raise ValueError("Название выжимки должно содержать от 1 до 100 символов.")
    if target is not None:
        root = Path(target)
        if not is_workspace(root):
            raise ValueError("Выбери существующую базу или создай новую.")
    else:
        key = hashlib.sha256(("base:" + name.casefold()).encode("utf-8")).hexdigest()[:20] if name else identity
        root = library / key
    if any(path.is_symlink() or path.is_junction() for path in (library, root)):
        raise ValueError("Папка базы знаний не может быть ссылкой.")
    metadata = _base_metadata(root)
    copies = dict(metadata.get("imports", {}))
    titles = dict(metadata.get("document_names", {}))
    documents = imported_documents(root)
    if (not metadata and len(documents) == 1 and re.fullmatch(r"[0-9a-f]{20}", root.name)
            and root.parent.resolve() == library.resolve()):
        copies[root.name] = documents[0].name
    existing = {p.name.casefold() for p in documents} | {v.casefold() for v in copies.values()}
    filename = copies.get(identity)
    if filename is None:
        filename = source.name
        number = 2
        while filename.casefold() in existing:
            filename = f"{source.stem} ({number}){source.suffix}"
            number += 1
        copies[identity] = filename
    if document_name is not None:
        titles[filename] = document_name
    title = metadata.get("name") or name or (summary_title(root) if imported_documents(root) else document_title(source))
    _save_base_metadata(root, {"name": title, "imports": copies, "document_names": titles})
    _publish_documents(root, {filename: prepared[source.name]})
    return root.resolve()


def summary_title(root):
    try:
        if title := _base_metadata(root).get("name"):
            return title
    except (OSError, ValueError):
        pass
    documents = imported_documents(root)
    return document_title(documents[0]) if documents else Path(root).name


def document_title(source):
    source = Path(source)
    try:
        with source.open(encoding="utf-8-sig") as stream:
            first = stream.read(4096).lstrip().splitlines()[0]
        if first.startswith("# "):
            title = " ".join(first[2:].strip().strip("#").strip(" *`").split())
            if title:
                return title[:100]
    except (OSError, UnicodeError, IndexError):
        pass
    return source.stem.replace("_", " ").replace("-", " ")


def import_documents(workspace, files):
    """Validate the batch, then publish each file by atomic replacement."""
    return _publish_documents(workspace, _prepare_documents(files))


def _prepare_documents(files):
    from .knowledge import PRIVATE_BODY, PRIVATE_PATH

    prepared = {}
    names = set()
    for file in map(Path, files):
        name = file.name
        if (file.suffix.lower() not in _TEXT_SUFFIXES or name.startswith(".") or file.is_reserved()
                or PRIVATE_PATH.search(name) or re.search(r'[<>:"/\\|?*\x00-\x1f]', name)):
            raise ValueError(f"Выбери документ .md или .txt с допустимым именем: {name}")
        if name.casefold() in names:
            raise ValueError(f"В одном импорте два файла с именем {name}.")
        if not file.is_file():
            raise ValueError(f"{name}: выбери существующий файл.")
        with file.open("rb") as stream:
            content = stream.read()
        if not content:
            raise ValueError(f"{name}: документ не должен быть пустым.")
        text = content.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        if "\x00" in text or PRIVATE_BODY.search(text):
            raise ValueError(f"{name}: обнаружены ключи, пароли или двоичные данные.")
        try:
            body, _ = parse_pack(text)
            if not body.strip():
                raise ValueError("Добавь текст знаний вне блока словаря.")
        except ValueError as error:
            raise ValueError(f"{name}: {error}") from error
        prepared[name] = text
        names.add(name.casefold())
    return prepared


def _publish_documents(workspace, prepared):
    if not prepared:
        return ()
    folder = _import_folder(create_workspace(workspace))
    existing = {path.name.casefold(): path for path in folder.iterdir()}
    targets = {existing.get(name.casefold(), folder / name): text for name, text in prepared.items()}
    for path in targets:
        if path.is_symlink() or path.is_junction() or (path.exists() and not path.is_file()):
            raise ValueError(f"Недопустимый путь назначения: {path}")
    imported = []
    for path, text in targets.items():
        temp = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", prefix=".import-",
                                             dir=folder, delete=False) as stream:
                temp = Path(stream.name)
                stream.write(text)
            os.replace(temp, path)
            imported.append(path)
        except OSError as error:
            raise OSError(f"Импортировано {len(imported)} из {len(prepared)}. Не удалось записать {path.name}.") from error
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)
    return tuple(imported)
