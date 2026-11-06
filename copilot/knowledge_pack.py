"""Import local knowledge documents without sending files to an AI service."""

import json
import os
import re
import tempfile
from pathlib import Path


MAX_DOCUMENT_BYTES = 180_000
PACK_FILENAME = "utka-cue-knowledge.md"
PACK_FILENAMES = (PACK_FILENAME, "utka-knowledge.md", "call-copilot-knowledge.md")
PACK_FENCE = "```utka-cue-asr"
_PACK_FENCES = {PACK_FENCE, "```utka-asr", "```call-copilot-asr"}
_TEXT_SUFFIXES = {".md", ".txt"}
_CONTEXT = re.compile(r"(?:\w+(?:\\w\*)?)(?:[ -]\w+(?:\\w\*)?)*")


def _validate_glossary(data):
    def words(values, limit):
        return (isinstance(values, list) and len(values) <= limit
                and all(isinstance(value, str) and 0 < len(value) <= 120
                        and value == value.strip() and "\n" not in value and "\r" not in value
                        for value in values))

    if not isinstance(data, dict) or not words(data.get("terms"), 200):
        raise ValueError("В словаре нужны terms с точными написаниями.")
    terms = set(data["terms"])
    hints = data.get("hotwords", data["terms"][:10])
    if not words(hints, 20) or not set(hints) <= terms:
        raise ValueError("hotwords должен содержать до 20 терминов из terms.")
    rules = data.get("aliases", [])
    if not isinstance(rules, list) or len(rules) > 200:
        raise ValueError("aliases должен содержать до 200 правил произношения.")
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


def imported_documents(root):
    try:
        folder = _import_folder(Path(root))
        return tuple(sorted((path for path in folder.iterdir()
                             if not path.name.startswith(".") and path.suffix.lower() in _TEXT_SUFFIXES
                             and path.is_file() and not path.is_symlink() and not path.is_junction()),
                            key=lambda path: path.name.casefold()))
    except (OSError, ValueError):
        return ()


def import_documents(workspace, files):
    """Validate the batch, then publish each file by atomic replacement."""
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
            content = stream.read(MAX_DOCUMENT_BYTES + 1)
        if not 0 < len(content) <= MAX_DOCUMENT_BYTES:
            raise ValueError(f"{name}: размер документа должен быть от 1 до {MAX_DOCUMENT_BYTES} байт.")
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
