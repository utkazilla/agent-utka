"""Install pinned Qwen3-ASR CPU bundles."""

import hashlib
import tarfile
import tempfile
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .speech import DEFAULT_QWEN_MODEL, QWEN_ASR_BUNDLE, QWEN_ASR_MODELS, QWEN_LARGE_MODEL


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
# The 1.7B ONNX export linked by sherpa-onnx. Only these six files are needed.
_LARGE_REPO = "https://modelscope.cn/api/v1/models/zengshuishui/Qwen3-ASR-onnx/repo"
_LARGE_REVISION = "cb045ad80b8970c9d411d463e5b78991a566596c"
_LARGE_FILES = {
    "conv_frontend.onnx": (48_080_441, "fa894a4ba53da6a4238f2a6ca0b09362e505d39cecbd646051b033e2e8d7e2fb"),
    "encoder.int8.onnx": (314_222_162, "436fbd910a0c8914851e5ac1354e807be9f283d08a5da728adaa609731c41469"),
    "decoder.int8.onnx": (2_037_458_645, "c43c853fa6e97d08365cb8a5502b360b595cd43c00dc60e4d8ca7cc18cad460b"),
    "tokenizer/merges.txt": (1_671_853, "8831e4f1a044471340f7c0a83d7bd71306a5b867e95fd870f74d0c5308a904d5"),
    "tokenizer/tokenizer_config.json": (12_487, "4942d005604266809309cabc9f4e9cb89ce855d59b14681fdc0e1cc62ea26c4c"),
    "tokenizer/vocab.json": (2_776_833, "ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910"),
}
QWEN_DOWNLOAD_SIZES = {
    DEFAULT_QWEN_MODEL: QWEN_DOWNLOAD_BYTES,
    QWEN_LARGE_MODEL: sum(size for size, _digest in _LARGE_FILES.values()),
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


def _files(variant):
    return _FILES if variant == DEFAULT_QWEN_MODEL else {name: size for name, (size, _) in _LARGE_FILES.items()}


def qwen_installed(runtime, variant=DEFAULT_QWEN_MODEL):
    """Report whether the chosen CPU model files are present."""
    bundle = Path(runtime) / QWEN_ASR_MODELS[variant][1]
    try:
        return (
            not _link(bundle)
            and not _link(bundle / "tokenizer")
            and all(_matches(bundle / name, length) for name, length in _files(variant).items())
        )
    except OSError:
        return False


def _download(archive, on_progress, cancelled):
    _download_file(_URL, archive, QWEN_DOWNLOAD_BYTES, _SHA256, on_progress, cancelled)


def _download_file(url, destination, size, checksum, progress, cancelled):
    digest = hashlib.sha256()
    received = 0
    request = Request(url, headers={"User-Agent": "Agent-Utka"})
    progress("download", received, size)
    _check_cancelled(cancelled)
    with urlopen(request, timeout=60) as source, destination.open("xb") as output:
        while True:
            _check_cancelled(cancelled)
            block = source.read(_BLOCK)
            if not block:
                break
            received += len(block)
            if received > size:
                raise OSError("Unexpected Qwen ASR download size.")
            digest.update(block)
            output.write(block)
            progress("download", received, size)
    _check_cancelled(cancelled)
    if received != size or digest.hexdigest() != checksum:
        raise OSError(f"Qwen ASR checksum did not match for {destination.name}.")


def _download_large(staged, on_progress, cancelled):
    completed = 0
    total = sum(size for size, _digest in _LARGE_FILES.values())

    def progress(stage, received, _size):
        on_progress(stage, completed + received, total)

    for name, (size, checksum) in _LARGE_FILES.items():
        remote = name if name.startswith("tokenizer/") else f"model_1.7B/{name}"
        query = urlencode({"Revision": _LARGE_REVISION, "FilePath": remote})
        destination = staged / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        _download_file(f"{_LARGE_REPO}?{query}", destination, size, checksum, progress, cancelled)
        completed += size


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


def _publish(staged, bundle, files):
    if not bundle.exists() and not _link(bundle):
        try:
            staged.rename(bundle)
            return
        except FileExistsError:
            pass  # Another installer created the bundle first.
    for folder in (bundle, bundle / "tokenizer"):
        if _link(folder) or (folder.exists() and not folder.is_dir()):
            raise OSError("The Qwen ASR destination is not a regular directory.")
    for relative in files:
        path = bundle / relative
        if _link(path) or (path.exists() and not path.is_file()):
            raise OSError(f"Unexpected file at the Qwen ASR destination: {relative}")
    for relative, length in files.items():
        path = bundle / relative
        if not _matches(path, length):
            path.parent.mkdir(parents=True, exist_ok=True)
            (staged / relative).replace(path)


def install_qwen(runtime, on_progress=lambda *_: None, cancelled=lambda: False, *, variant=DEFAULT_QWEN_MODEL):
    """Install and verify the selected CPU model, or return False on cancellation."""
    runtime = Path(runtime)
    if cancelled():
        return False
    if qwen_installed(runtime, variant):
        return True
    runtime.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="qwen-install-", dir=runtime) as temporary:
            work = Path(temporary)
            staged = work / "bundle"
            if variant == DEFAULT_QWEN_MODEL:
                archive = work / "model.tar.bz2"
                _download(archive, on_progress, cancelled)
                _unpack(archive, staged, on_progress, cancelled)
            else:
                _download_large(staged, on_progress, cancelled)
            _check_cancelled(cancelled)
            _publish(staged, runtime / QWEN_ASR_MODELS[variant][1], _files(variant))
        return True
    except _Cancelled:
        return False
