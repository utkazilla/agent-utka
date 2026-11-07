"""Install pinned Qwen3-ASR CPU bundles."""

import hashlib
import tarfile
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .hardware import read_vram
from .speech import DEFAULT_QWEN_MODEL, QWEN_ASR_BUNDLE, QWEN_ASR_MODELS, QWEN_CUDA_BUNDLES, QWEN_LARGE_MODEL
from .whisper_install import _install_packages, _run_worker


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
_CUDA_COMMON_FILES = {
    "chat_template.jinja": (1_434, "f50e6b694fbf4a683206e37869990d68333fe95d285730f084c838a34b0d98c2"),
    "generation_config.json": (165, "9939fc9388b79bd70757f938b87381e817173d6a6158f5af6506c0b73e775c3c"),
    "processor_config.json": (487, "bc0b230081b44e629dd5b9045b78495615c1831b4b9f4cffe97bd37e82a6156a"),
    "tokenizer.json": (11_429_653, "fe1fad59be22a41ee293363fcf95fdedbc7c93f3b49270b1d2e18bd1399a7a05"),
    "tokenizer_config.json": (998, "945e980986de2ca7768f3326bfdbb4fbea3406f972b8ae0be233089f2b253c11"),
}
_CUDA_SOURCES = {
    DEFAULT_QWEN_MODEL: ("Qwen3-ASR-0.6B-hf", "7f1569a48a89f3e3f4dc3a5c9d28bddd903bc76c", {
        **_CUDA_COMMON_FILES,
        "config.json": (2_398, "9eecf6f1b383e343889c2e6010e632590fa57d4bc678e151c7d6a160a0dfb04a"),
        "model.safetensors": (1_564_928_088, "d3f212dd20abecd315d830bc54ae3865e56ebfc3276484e57b771288ba27fd35"),
    }),
    QWEN_LARGE_MODEL: ("Qwen3-ASR-1.7B-hf", "bcd2b5b7f32b480ab5790554cfa8347f246a14f3", {
        **_CUDA_COMMON_FILES,
        "config.json": (2_399, "117ac8e63e2af7cae3665e5a632d6eb03f5f384915519ceb6403c15ec6533f63"),
        "model.safetensors": (4_076_193_080, "2db53c7d81bd9b8cbc6a074e89be2c968a0d373fb4ee68bb1b1e14f7042dfee1"),
    }),
}
QWEN_CUDA_DOWNLOAD_SIZES = {
    variant: sum(size for size, _ in files.values()) for variant, (_, _, files) in _CUDA_SOURCES.items()
}
_TORCH = "2.11.0+cu128"
_TRANSFORMERS = "5.13.0"
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


def _bundle_installed(bundle, files):
    try:
        return (
            not _link(bundle)
            and not _link(bundle / "tokenizer")
            and all(_matches(bundle / name, length) for name, length in files.items())
        )
    except OSError:
        return False


def _has_package(package, expected):
    try:
        return version(package) == expected
    except PackageNotFoundError:
        return False


def qwen_installed(runtime, variant=DEFAULT_QWEN_MODEL, *, device="auto"):
    if device == "cuda":
        files = {name: size for name, (size, _) in _CUDA_SOURCES[variant][2].items()}
        return (_bundle_installed(Path(runtime) / QWEN_CUDA_BUNDLES[variant], files)
                and _has_package("torch", _TORCH) and _has_package("transformers", _TRANSFORMERS))
    return _bundle_installed(Path(runtime) / QWEN_ASR_MODELS[variant][1], _files(variant))


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
    def url(name):
        remote = name if name.startswith("tokenizer/") else f"model_1.7B/{name}"
        query = urlencode({"Revision": _LARGE_REVISION, "FilePath": remote})
        return f"{_LARGE_REPO}?{query}"

    _download_files(staged, _LARGE_FILES, url, on_progress, cancelled)


def _download_files(staged, files, url, on_progress, cancelled):
    completed = 0
    total = sum(size for size, _digest in files.values())

    def progress(stage, received, _size):
        on_progress(stage, completed + received, total)

    for name, (size, checksum) in files.items():
        destination = staged / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        _download_file(url(name), destination, size, checksum, progress, cancelled)
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


def install_qwen(runtime, on_progress=lambda *_: None, cancelled=lambda: False, *,
                 variant=DEFAULT_QWEN_MODEL, device="auto"):
    """Install the requested model or return False on cancellation."""
    runtime = Path(runtime)
    if cancelled():
        return False
    if device == "cuda":
        return _install_cuda(runtime, variant, on_progress, cancelled)
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


def _install_cuda(runtime, variant, on_progress, cancelled):
    if not read_vram():
        raise RuntimeError("Для режима GPU нужен доступный драйвер NVIDIA.")
    try:
        for package, pin, index, stage in (
            ("torch", _TORCH, "https://download.pytorch.org/whl/cu128", "qwen_cuda"),
            ("transformers", _TRANSFORMERS, "https://pypi.org/simple", "qwen_transformers"),
        ):
            if _has_package(package, pin):
                continue
            result = _install_packages(index, [f"{package}=={pin}"], stage, on_progress, cancelled)
            _check_cancelled(cancelled)
            if result != 0 or not _has_package(package, pin):
                raise RuntimeError(f"Could not install {package} for Qwen ASR.")

        repo, revision, source = _CUDA_SOURCES[variant]
        bundle = runtime / QWEN_CUDA_BUNDLES[variant]
        files = {name: size for name, (size, _) in source.items()}
        if not _bundle_installed(bundle, files):
            runtime.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="qwen-cuda-", dir=runtime) as temporary:
                staged = Path(temporary) / "bundle"
                base = f"https://huggingface.co/Qwen/{repo}/resolve/{revision}"
                _download_files(staged, source, lambda name: f"{base}/{name}", on_progress, cancelled)
                _check_cancelled(cancelled)
                _publish(staged, bundle, files)
        on_progress("verify", None, None)
        result = _run_worker([
            "-c", "import sys; from copilot.speech import QwenASR; "
                  "QwenASR(sys.argv[1], variant=sys.argv[2], device='cuda')",
            str(runtime.resolve()), variant,
        ], cancelled)
        _check_cancelled(cancelled)
        if result != 0:
            raise RuntimeError("Qwen ASR не прошёл проверку CUDA. Проверь драйвер NVIDIA и свободную VRAM.")
        return True
    except _Cancelled:
        return False
