"""Install known multilingual Faster Whisper models into the app's local cache."""

import argparse
import io
import os
import subprocess
import sys
import threading
from contextlib import ExitStack
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from queue import Empty, SimpleQueue


DEFAULT_WHISPER_MODEL = "large-v3"
_PACKAGE = "faster-whisper"
_VERSION = "1.2.1"
_PROGRESS = "CALL_COPILOT_WHISPER_BYTES "


@dataclass(frozen=True)
class _Source:
    repo: str
    revision: str
    files: dict[str, int]


_SMALL_FILES = {"tokenizer.json": 2203239, "vocabulary.txt": 459861}
_LARGE_FILES = {"preprocessor_config.json": 340, "vocabulary.json": 1068114}
# The repository names come from Faster Whisper 1.2.1's model map. The revisions
# and sizes are from the corresponding published Hugging Face file metadata.
_SOURCES = {
    "tiny": _Source("Systran/faster-whisper-tiny", "d90ca5fe260221311c53c58e660288d3deb8d356",
                    {"config.json": 2249, "model.bin": 75538270, **_SMALL_FILES}),
    "base": _Source("Systran/faster-whisper-base", "ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66",
                    {"config.json": 2309, "model.bin": 145217532, **_SMALL_FILES}),
    "small": _Source("Systran/faster-whisper-small", "536b0662742c02347bc0e980a01041f333bce120",
                     {"config.json": 2370, "model.bin": 483546902, **_SMALL_FILES}),
    "medium": _Source("Systran/faster-whisper-medium", "08e178d48790749d25932bbc082711ddcfdfbc4f",
                      {"config.json": 2257, "model.bin": 1527906378, **_SMALL_FILES}),
    "large-v3-turbo": _Source(
        "mobiuslabsgmbh/faster-whisper-large-v3-turbo", "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf",
        {"config.json": 2263, "model.bin": 1617884929, "tokenizer.json": 2710337, **_LARGE_FILES},
    ),
    "large-v3": _Source("Systran/faster-whisper-large-v3", "edaa852ec7e145841d8ffdb056a99866b5f0a478",
                        {"config.json": 2394, "model.bin": 3087284237, "tokenizer.json": 2480617, **_LARGE_FILES}),
}
WHISPER_MODELS = {name: sum(source.files.values()) for name, source in _SOURCES.items()}


def _source(variant):
    try:
        return _SOURCES[variant]
    except (KeyError, TypeError) as error:
        raise ValueError(f"Unsupported Faster Whisper model: {variant!r}.") from error


def whisper_cache_path(runtime, variant):
    """Return the complete pinned snapshot in the standard Hugging Face cache."""
    source = _source(variant)
    repo = "models--" + source.repo.replace("/", "--")
    folder = Path(runtime) / "whisper" / repo / "snapshots" / source.revision
    try:
        if all((folder / name).stat().st_size == size for name, size in source.files.items()):
            return folder
    except OSError:
        pass
    return None


def _package_installed():
    try:
        return version(_PACKAGE) == _VERSION
    except PackageNotFoundError:
        return False


def whisper_installed(runtime, variant):
    return _package_installed() and whisper_cache_path(runtime, variant) is not None


def _run_worker(args, cancelled, progress=None):
    executable = Path(sys.executable)
    # The Windows launcher uses pythonw. The worker needs a stdout pipe.
    if executable.name.lower() == "pythonw.exe":
        executable = executable.with_name("python.exe")
    if cancelled():
        return False
    with subprocess.Popen(
        [str(executable), "-X", "utf8", *args],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        env={**os.environ, "HF_HUB_DISABLE_XET": "1"},
    ) as process:
        events = SimpleQueue()

        def read_output():
            try:
                for line in process.stdout:
                    payload = line.removeprefix(_PROGRESS).strip()
                    if line.startswith(_PROGRESS) and payload.isascii() and payload.isdigit():
                        events.put(int(payload))
            finally:
                events.put(None)

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        try:
            while not cancelled():
                try:
                    transferred = events.get(timeout=0.1)
                except Empty:
                    continue
                if transferred is None:
                    while not cancelled():
                        try:
                            return process.wait(timeout=0.1)
                        except subprocess.TimeoutExpired:
                            continue
                    break
                if progress is not None:
                    progress(transferred)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            reader.join(timeout=1)
        return False


def install_whisper(runtime, variant, on_progress=lambda *_: None, cancelled=lambda: False):
    """Prepare the selected model. Return False when the caller cancels."""
    source = _source(variant)
    if cancelled():
        return False
    if not _package_installed():
        if sys.prefix == sys.base_prefix:
            raise RuntimeError("Run Setup Agent Utka.ps1 to create the app's Python environment.")
        on_progress("dependencies", None, None)
        code = _run_worker(
            ["-m", "pip", "--disable-pip-version-check", "install", "--only-binary=:all:", f"{_PACKAGE}=={_VERSION}"],
            cancelled,
        )
        if code is False or cancelled():
            return False
        if code or not _package_installed():
            raise RuntimeError("Could not install Faster Whisper. Check your connection and run Setup Agent Utka.ps1 if needed.")
    if whisper_cache_path(runtime, variant) is None:
        total = sum(source.files.values())
        on_progress("download", 0, total)
        code = _run_worker(
            ["-m", "copilot.whisper_install", variant, str(Path(runtime).resolve())],
            cancelled,
            lambda completed: on_progress("download", min(completed, total), total),
        )
        if code is False or cancelled():
            return False
        if code:
            raise RuntimeError("Could not download the Faster Whisper model from Hugging Face.")
    on_progress("verify", None, None)
    if whisper_cache_path(runtime, variant) is None:
        raise RuntimeError("The Faster Whisper download is incomplete.")
    code = _run_worker(
        ["-m", "copilot.whisper_install", variant, str(Path(runtime).resolve()), "--verify"],
        cancelled,
    )
    if code is False or cancelled():
        return False
    if code:
        raise RuntimeError("Faster Whisper could not start. Check the Microsoft Visual C++ Runtime (x64).")
    return True


def _download(runtime, variant):
    from huggingface_hub import hf_hub_download
    from tqdm.std import tqdm

    source = _source(variant)
    completed = 0

    def emit(value):
        print(f"{_PROGRESS}{value}", flush=True)

    class TransferProgress(tqdm):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs, file=io.StringIO())
            emit(completed + self.n)

        def update(self, n=1):
            super().update(n)
            emit(completed + self.n)

    for name, size in source.files.items():
        path = hf_hub_download(
            source.repo, name, revision=source.revision, cache_dir=Path(runtime) / "whisper",
            endpoint="https://huggingface.co", token=False, tqdm_class=TransferProgress,
        )
        if Path(path).stat().st_size != size:
            raise RuntimeError(f"Unexpected size of Faster Whisper file {name}.")
        completed += size
        emit(completed)


def _verify(runtime):
    with ExitStack() as stack:
        dlls = runtime / "vc"
        if os.name == "nt" and dlls.is_dir():
            stack.enter_context(os.add_dll_directory(str(dlls)))
        from faster_whisper.vad import get_vad_model

        get_vad_model()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("variant", choices=WHISPER_MODELS)
    parser.add_argument("runtime", type=Path)
    parser.add_argument("--verify", action="store_true")
    arguments = parser.parse_args()
    if arguments.verify:
        _verify(arguments.runtime)
    else:
        _download(arguments.runtime, arguments.variant)
