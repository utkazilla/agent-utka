"""Read the public Ollama library pages used by the in-app model picker."""

import re
from dataclasses import dataclass
from decimal import Decimal
from html.parser import HTMLParser
from http.client import HTTPException
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from .ollama_library import validate_ollama_model


_ORIGIN = "https://ollama.com"
_MAX_PAGE_BYTES = 5 * 1024 * 1024
_MAX_RESULTS = 30
_MAX_VARIANTS = 300
_LIBRARY = "/library/"
_NAME = r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,79}"
_FAMILY = re.compile(_NAME)
_LINK = re.compile(rf"{_LIBRARY}(?P<family>{_NAME})(?::(?P<tag>{_NAME}))?")
_UNSUPPORTED_TAG = re.compile(r"(?:^|[-_.])(?:cloud|mlx)(?:$|[-_.])", re.IGNORECASE)
_SIZE = re.compile(
    r"(?<![\w.])(?P<amount>\d+(?:\.\d+)?)\s*(?P<unit>[KMGT]i?B)"
    r"(?:\s*[-–—]\s*(?P<end_amount>\d+(?:\.\d+)?)\s*(?P<end_unit>[KMGT]i?B))?(?!\w)",
    re.IGNORECASE,
)
_UNITS = {**{f"{unit}B": 1000**index for index, unit in enumerate("KMGT", 1)},
          **{f"{unit}IB": 1024**index for index, unit in enumerate("KMGT", 1)}}


class CatalogError(RuntimeError):
    """The public catalog could not be reached or read."""


@dataclass(frozen=True)
class CatalogModel:
    name: str
    description: str


@dataclass(frozen=True)
class CatalogVariant:
    tag: str
    size: str
    size_bytes: int | None


@dataclass
class _LibraryLink:
    family: str
    tag: str | None
    parts: list[str]
    description: list[str]
    has_heading: bool = False


class _LibraryParser(HTMLParser):
    def __init__(self, page):
        super().__init__()
        self.links = []
        self._link = None
        self._in_description = False
        self.feed(page)
        self.close()

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href") or ""
            match = _LINK.fullmatch(href)
            if match:
                self._link = _LibraryLink(match["family"], match["tag"], [], [])
        elif self._link is not None:
            if tag in ("h2", "h3"):
                self._link.has_heading = True
            elif tag == "p":
                self._in_description = True

    def handle_data(self, data):
        if self._link is not None and (value := data.strip()):
            self._link.parts.append(value)
            if self._in_description:
                self._link.description.append(value)

    def handle_endtag(self, tag):
        if tag == "a" and self._link is not None:
            self.links.append(self._link)
            self._link = None
            self._in_description = False
        elif tag == "p":
            self._in_description = False


def _fetch(path):
    # Ollama documents endpoints for installed models, not public catalog discovery.
    request = Request(_ORIGIN + path, headers={
        "Accept": "text/html", "User-Agent": "Agent-Utka/Ollama-catalog",
    })
    try:
        with urlopen(request, timeout=8) as response:
            final = urlsplit(response.geturl())
            if final.scheme != "https" or final.hostname not in ("ollama.com", "www.ollama.com"):
                raise CatalogError("Unexpected Ollama catalog address.")
            data = response.read(_MAX_PAGE_BYTES + 1)
    except (OSError, HTTPException) as error:
        raise CatalogError("Could not connect to the Ollama catalog.") from error
    if len(data) > _MAX_PAGE_BYTES:
        raise CatalogError("The Ollama catalog page is too large.")
    return data.decode("utf-8", errors="replace")


def search_models(query=""):
    """Search the official local library for model families in catalog order."""
    params = urlencode({"q": query.strip()[:120], "c": "local", "o": "popular"})
    page = _fetch("/search?" + params)
    links = [link for link in _LibraryParser(page).links if not link.tag and link.has_heading]
    if not links and "no models found" not in page.casefold():
        raise CatalogError("Could not read model families from the Ollama catalog.")
    results = {}
    for link in links:
        labels = {part.casefold() for part in link.parts}
        description = " ".join(link.description)
        if labels & {"cloud", "embedding"}:
            continue
        if re.search(r"\b(?:text[- ]to[- ]speech|speech synthesis)\b", description, re.IGNORECASE):
            continue
        results.setdefault(link.family, CatalogModel(link.family, description[:360]))
        if len(results) >= _MAX_RESULTS:
            break
    return list(results.values())


def _format_size(amount, unit):
    unit = unit.upper()
    display_unit = unit[0] + "iB" if len(unit) == 3 else unit
    return f"{amount} {display_unit}", int(Decimal(amount) * _UNITS[unit])


def model_variants(model):
    """Return Windows-compatible local tags with advertised file sizes."""
    if not _FAMILY.fullmatch(model):
        raise CatalogError("Invalid Ollama model family.")
    links = [link for link in _LibraryParser(_fetch(f"{_LIBRARY}{model}/tags")).links
             if link.family == model and link.tag]
    if not links:
        raise CatalogError("Could not read model variants from the Ollama catalog.")
    excluded = set()
    variants = {}
    for link in links:
        tag = f"{link.family}:{link.tag}"
        labels = {part.casefold() for part in link.parts}
        text = " ".join(link.parts)
        inputs = [field for field in text.casefold().split("•") if " input" in field]
        if (_UNSUPPORTED_TAG.search(link.tag) or labels & {"cloud", "mlx"}
                or (inputs and not any("text" in field for field in inputs))):
            excluded.add(tag)
            continue
        if match := _SIZE.search(text):
            size, size_bytes = _format_size(match["amount"], match["unit"])
            if match["end_amount"]:
                end_size, end_bytes = _format_size(match["end_amount"], match["end_unit"])
                size = f"{size} - {end_size}"
                size_bytes = max(size_bytes, end_bytes)
            variants.setdefault(tag, CatalogVariant(validate_ollama_model(tag), size, size_bytes))
    if not variants and any(f"{link.family}:{link.tag}" not in excluded for link in links):
        raise CatalogError("Could not read model sizes from the Ollama catalog.")
    return [variant for tag, variant in variants.items() if tag not in excluded][:_MAX_VARIANTS]
