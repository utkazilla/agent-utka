"""Install the pinned Qwen3-ASR CPU bundle used by Agent Utka."""

import hashlib
import tarfile
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen

from .speech import QWEN_ASR_BUNDLE


QWEN_DOWNLOAD_BYTES = 878_702_423
_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    f"{QWEN_ASR_BUNDLE}.tar.bz2"
)
_SHA256 = "393f8a14e2f5fb96746aaab342997a40641001fbd5bf9592a080a8329178ee96"
_FILES = {
    "conv_frontend.onnx": 44_148_281,
    "encoder.int8.onnx": 182_491_662,
    "decoder.int8.onnx": 755_914_231,
    "tokenizer/merges.txt": 1_671_853,
    "tokenizer/tokenizer_config.json": 12_487,
    "tokenizer/vocab.json": 2_776_833,
}
_BLOCK = 1 << 20


class _Cancelled(Exception):
    pass


def _check_cancelled(cancelled):
    if cancelled():
        raise _Cancelled


def _link(path):
    return path.is_symlink() or path.is_junction()


def _matches(path, length):
    return not _link(path) and path.is_file() and path.stat().st_size == length


def qwen_installed(runtime):
    """Report whether the bundled CPU files are present."""
    bundle = Path(runtime) / QWEN_ASR_BUNDLE
    try:
        return (
            not _link(bundle)
            and not _link(bundle / "tokenizer")
            and all(_matches(bundle / name, length) for name, length in _FILES.items())
        )
    except OSError:
        return False


def _download(archive, on_progress, cancelled):
    digest = hashlib.sha256()
    received = 0
    request = Request(_URL, headers={"User-Agent": "Agent-Utka"})
    on_progress("download", received, QWEN_DOWNLOAD_BYTES)
    _check_cancelled(cancelled)
    with urlopen(request, timeout=20) as source, archive.open("xb") as output:
        while True:
            _check_cancelled(cancelled)
            block = source.read(_BLOCK)
            if not block:
                break
            received += len(block)
            if received > QWEN_DOWNLOAD_BYTES:
                raise OSError("Unexpected Qwen ASR download size.")
            digest.update(block)
            output.write(block)
            on_progress("download", received, QWEN_DOWNLOAD_BYTES)
    _check_cancelled(cancelled)
    if received != QWEN_DOWNLOAD_BYTES or digest.hexdigest() != _SHA256:
        raise OSError("Qwen ASR archive checksum did not match.")


def _unpack(archive, staged, on_progress, cancelled):
    prefix = f"{QWEN_ASR_BUNDLE}/"
    extracted = set()
    written = 0
    total = sum(_FILES.values())
    on_progress("verify", written, total)
    try:
        with tarfile.open(archive, "r|bz2") as package:
            for entry in package:
                _check_cancelled(cancelled)
                name = entry.name.removeprefix("./")
                if not name.startswith(prefix) or (relative := name[len(prefix):]) not in _FILES:
                    continue
                if relative in extracted or not entry.isfile() or entry.size != _FILES[relative]:
                    raise OSError(f"Unexpected file in Qwen ASR archive: {relative}")
                destination = staged / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                with package.extractfile(entry) as source, destination.open("xb") as output:
                    while True:
                        _check_cancelled(cancelled)
                        block = source.read(_BLOCK)
                        if not block:
                            break
                        output.write(block)
                        written += len(block)
                        on_progress("verify", written, total)
                if destination.stat().st_size != _FILES[relative]:
                    raise OSError(f"Incomplete file in Qwen ASR archive: {relative}")
                extracted.add(relative)
    except (tarfile.TarError, EOFError) as error:
        raise OSError("Could not unpack the Qwen ASR archive.") from error
    _check_cancelled(cancelled)
    if extracted != set(_FILES):
        raise OSError("Qwen ASR archive is missing required files.")


def _publish(staged, bundle):
    if not bundle.exists() and not _link(bundle):
        try:
            staged.rename(bundle)
            return
        except FileExistsError:
            pass  # Another installer created the bundle first.
    for folder in (bundle, bundle / "tokenizer"):
        if _link(folder) or (folder.exists() and not folder.is_dir()):
            raise OSError("The Qwen ASR destination is not a regular directory.")
    for relative in _FILES:
        path = bundle / relative
        if _link(path) or (path.exists() and not path.is_file()):
            raise OSError(f"Unexpected file at the Qwen ASR destination: {relative}")
    for relative, length in _FILES.items():
        path = bundle / relative
        if not _matches(path, length):
            path.parent.mkdir(parents=True, exist_ok=True)
            (staged / relative).replace(path)


def install_qwen(runtime, on_progress=lambda *_: None, cancelled=lambda: False):
    """Install CPU files after verifying the entire archive, or return False on cancellation."""
    runtime = Path(runtime)
    if cancelled():
        return False
    if qwen_installed(runtime):
        return True
    runtime.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="qwen-install-", dir=runtime) as temporary:
            work = Path(temporary)
            archive, staged = work / "model.tar.bz2", work / "bundle"
            _download(archive, on_progress, cancelled)
            _unpack(archive, staged, on_progress, cancelled)
            _check_cancelled(cancelled)
            _publish(staged, runtime / QWEN_ASR_BUNDLE)
        return True
    except _Cancelled:
        return False
