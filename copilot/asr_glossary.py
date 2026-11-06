import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .knowledge import PRIVATE_BODY, project_pack
from .knowledge_pack import MAX_DOCUMENT_BYTES, imported_documents, parse_pack


@dataclass(frozen=True)
class AsrGlossary:
    hints: tuple[str, ...] = ()
    aliases: tuple[tuple[re.Pattern, str, re.Pattern | None], ...] = ()

    def hotwords(self, common):
        if not self.hints:
            return common
        return ", ".join(dict.fromkeys([*(word.strip() for word in common.split(",") if word.strip()),
                                        *self.hints]))

    def normalize(self, text):
        for pattern, term, context in self.aliases:
            def replace(match):
                if context is not None:
                    start, end = match.span()
                    nearby = match.string[max(0, start - 80):start] + " " + match.string[end:end + 80]
                    if not context.search(nearby):
                        return match[0]
                return term

            text = pattern.sub(replace, text)
        return text


EMPTY = AsrGlossary()


def _alias_pattern(heard):
    parts = re.split(r"[\s.\-]+", heard.strip(" .-"))
    body = r"[\s.\-]+".join(map(re.escape, parts))
    # A spelled abbreviation can have a dot before the next word or punctuation.
    dot = r"(?:\.(?=[!?…,;:]|\s+(?-i:[a-zа-яё])))?" if len(parts) > 1 else ""
    return rf"(?<!\w){body}(?!\w){dot}"


@lru_cache(maxsize=16)
def _read(path, modified_ns, size):
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return _compile_glossary(data)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, re.error):
        return EMPTY


def _compile_glossary(data):
    if not isinstance(data, dict) or not isinstance(data.get("terms"), list):
        return EMPTY
    terms = tuple(dict.fromkeys(term.strip() for term in data["terms"]
                                if isinstance(term, str) and term.strip()))
    aliases = []
    for rule in data.get("aliases", []):
        if not isinstance(rule["heard"], list):
            return EMPTY
        term = rule["term"]
        heard = [value for value in rule["heard"] if isinstance(value, str) and value.strip(" .-")]
        if term not in terms or not heard:
            continue
        alternatives = "|".join(map(_alias_pattern, sorted(heard, key=len, reverse=True)))
        context = re.compile(rule["context"], re.I) if "context" in rule else None
        aliases.append((re.compile(alternatives, re.I), term, context))
    for term in sorted(terms, key=len, reverse=True):
        aliases.append((re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.I), term, None))
    hints = data.get("hotwords", list(terms))
    if not isinstance(hints, list):
        return EMPTY
    return AsrGlossary(tuple(term for term in hints if term in terms), tuple(aliases))


@lru_cache(maxsize=128)
def _read_pack(path, modified_ns, size):
    if size > MAX_DOCUMENT_BYTES:
        return EMPTY
    try:
        text = path.read_text(encoding="utf-8-sig")
        if "\x00" in text or PRIVATE_BODY.search(text):
            return EMPTY
        _, glossary = parse_pack(text)
        return _compile_glossary(glossary)
    except (OSError, ValueError, re.error):
        return EMPTY


def project_asr_glossary(root):
    if not root:
        return EMPTY
    path = Path(root) / ".copilot-knowledge" / ".asr-glossary.json"
    try:
        stat = path.stat()
        local = _read(path, stat.st_mtime_ns, stat.st_size)
    except OSError:
        local = EMPTY
    pack = project_pack(root)
    documents = imported_documents(root)
    if pack is not None:
        documents = (pack, *documents)
    packs = []
    for document in documents:
        try:
            stat = document.stat()
        except OSError:
            continue
        packs.append(_read_pack(document, stat.st_mtime_ns, stat.st_size))
    if not packs:
        return local
    hints = tuple(dict.fromkeys([*local.hints, *(term for pack in packs for term in pack.hints)]))
    aliases = (*local.aliases, *(rule for pack in packs for rule in pack.aliases))
    return AsrGlossary(hints[:max(20, len(local.hints))], aliases)
