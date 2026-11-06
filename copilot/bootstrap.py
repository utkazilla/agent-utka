"""First-run setup for the Windows installer."""

import hashlib
import queue
import stat
import tempfile
import threading
from pathlib import Path, PurePosixPath
from tkinter import ttk
from urllib.request import Request, urlopen
from zipfile import ZipFile

from .brains import create_brain
from .configuration import RUNTIME
from .qwen_install import install_qwen, qwen_installed
from .speech import DEFAULT_QWEN_MODEL
from .whisper_install import install_whisper, whisper_cuda_installed, whisper_installed


OLLAMA_URL = (
    "https://github.com/ollama/ollama/releases/download/v0.40.15/"
    "ollama-windows-amd64.zip"
)
OLLAMA_SIZE = 1_614_941_966
OLLAMA_SHA256 = "9ca74a7ab66ec86870b1eecac7df160df08dc4e3a291ab5d2d59bcf9310221c6"
BLOCK = 1024 * 1024


class SetupCancelled(Exception):
    pass


def check_cancelled(cancelled):
    if cancelled():
        raise SetupCancelled


def setup_needed(runtime, settings):
    if settings["stt_engine"] == "qwen":
        if not qwen_installed(runtime, settings.get("qwen_model", DEFAULT_QWEN_MODEL),
                              device=settings.get("qwen_device", "auto")):
            return True
    if settings["stt_engine"] == "whisper":
        if not whisper_installed(runtime, settings["whisper_model"]):
            return True
        if settings.get("whisper_device") == "cuda" and not whisper_cuda_installed():
            return True
    if settings["llm_provider"] == "ollama":
        return not all(path.is_file() for path in (
            runtime / "ollama" / "ollama.exe",
            runtime / "installer-setup.complete",
        ))
    return False


def _unpack_ollama(archive, destination, cancelled):
    with ZipFile(archive) as package:
        entries = package.infolist()
        if len(entries) > 10_000 or sum(item.file_size for item in entries) > 8 * 1024**3:
            raise OSError("The Ollama archive exceeds the expected size.")
        for entry in entries:
            check_cancelled(cancelled)
            name = PurePosixPath(entry.filename)
            if (not name.parts or name.is_absolute() or ".." in name.parts
                    or any(":" in part or "\\" in part for part in name.parts)
                    or stat.S_ISLNK(entry.external_attr >> 16)):
                raise OSError("The Ollama archive contains an unsafe path.")
            target = destination.joinpath(*name.parts)
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.open(entry) as source, target.open("xb") as output:
                while block := source.read(BLOCK):
                    check_cancelled(cancelled)
                    output.write(block)


def _download_ollama(runtime, progress, cancelled):
    target = runtime / "ollama"
    if (target / "ollama.exe").is_file():
        return
    check_cancelled(cancelled)
    with tempfile.TemporaryDirectory(prefix="ollama-setup-", dir=runtime) as directory:
        work = Path(directory)
        archive = work / "ollama.zip"
        request = Request(OLLAMA_URL, headers={"User-Agent": "Agent-Utka"})
        digest = hashlib.sha256()
        received = 0
        progress("Downloading Ollama", 0, OLLAMA_SIZE)
        with urlopen(request, timeout=30) as response, archive.open("xb") as output:
            while block := response.read(BLOCK):
                check_cancelled(cancelled)
                received += len(block)
                if received > OLLAMA_SIZE:
                    raise OSError("The Ollama download exceeds the expected size.")
                digest.update(block)
                output.write(block)
                progress("Downloading Ollama", received, OLLAMA_SIZE)
        if received != OLLAMA_SIZE or digest.hexdigest() != OLLAMA_SHA256:
            raise OSError("The Ollama archive failed its SHA-256 check.")
        progress("Extracting Ollama", None, None)
        staged = work / "ollama"
        _unpack_ollama(archive, staged, cancelled)
        if not (staged / "ollama.exe").is_file():
            raise OSError("The Ollama archive is missing ollama.exe.")
        check_cancelled(cancelled)
        if (target / "ollama.exe").is_file():
            return
        try:
            if target.is_dir() and not target.is_junction() and not target.is_symlink():
                target.rmdir()  # A previous setup may have left an empty directory.
            staged.rename(target)
        except OSError:
            if not (target / "ollama.exe").is_file():
                raise


def download_answer_model(brain, model, progress, cancelled):
    try:
        check_cancelled(cancelled)
        if brain.external_host is None:
            _download_ollama(brain.runtime, progress, cancelled)
        return brain.pull(model, progress, cancelled)
    except SetupCancelled:
        return False


def prepare_runtime(runtime, settings, progress, cancelled):
    runtime.mkdir(parents=True, exist_ok=True)
    try:
        check_cancelled(cancelled)
        engine = settings["stt_engine"]
        qwen_model = settings.get("qwen_model", DEFAULT_QWEN_MODEL)
        qwen_device = settings.get("qwen_device", "auto")
        if engine == "qwen" and not qwen_installed(runtime, qwen_model, device=qwen_device):
            if not install_qwen(runtime, lambda _, done, total: progress("Preparing Qwen speech recognition", done, total),
                                cancelled, variant=qwen_model, device=qwen_device):
                return False
        elif engine == "whisper" and (not whisper_installed(runtime, settings["whisper_model"])
                                      or settings.get("whisper_device") == "cuda"):
            if not install_whisper(runtime, settings["whisper_model"],
                                   lambda stage, done, total: progress(
                                       "Installing NVIDIA CUDA libraries" if stage == "cuda" else "Preparing Faster Whisper",
                                       done, total), cancelled, device=settings.get("whisper_device", "auto")):
                return False
        check_cancelled(cancelled)
        if settings["llm_provider"] == "ollama":
            _download_ollama(runtime, progress, cancelled)
            brain = create_brain(runtime, settings)
            try:
                model = settings["ollama"]
                progress("Checking local answer model", None, None)
                if model not in brain.models() and not brain.pull(
                    model, lambda _, done, total: progress(f"Downloading {model}", done, total), cancelled
                ):
                    return False
            finally:
                brain.close()
            check_cancelled(cancelled)
            (runtime / "installer-setup.complete").touch()
        return True
    except SetupCancelled:
        return False


def setup_window(window, settings):
    """Return True when the user wants to open the app."""
    if not setup_needed(RUNTIME, settings):
        return True

    from tkinter import Toplevel

    window.withdraw()
    dialog = Toplevel(window)
    dialog.title("Set up Agent Utka")
    dialog.resizable(False, False)
    panel = ttk.Frame(dialog, padding=20)
    panel.pack(fill="both", expand=True)
    ttk.Label(panel, text="Download local AI models", font=("Segoe UI", 14, "bold")).pack(anchor="w")
    ttk.Label(
        panel, wraplength=420, justify="left",
        text="The default setup downloads about 6 GB. Keep this window open until it finishes. "
             "If you already run compatible local services, you can open the app and configure them in Settings.",
    ).pack(anchor="w", pady=(8, 14))
    label = ttk.Label(panel, wraplength=420, justify="left")
    label.pack(anchor="w", fill="x")
    bar = ttk.Progressbar(panel, length=420)
    bar.pack(fill="x", pady=(8, 14))
    buttons = ttk.Frame(panel)
    buttons.pack(fill="x")
    events = queue.SimpleQueue()
    stop = threading.Event()
    active = False
    open_app = False

    def close(open_window=False):
        nonlocal open_app
        if active:
            stop.set()
            label.configure(text="Cancelling…")
            exit_button.state(["disabled"])
            return
        open_app = open_window
        dialog.destroy()

    def start():
        nonlocal active
        active = True
        stop.clear()
        for button in (download, skip):
            button.state(["disabled"])
        exit_button.configure(text="Cancel download")
        label.configure(text="Starting setup…")
        bar.configure(value=0)

        def worker():
            try:
                result = prepare_runtime(
                    RUNTIME, settings,
                    lambda step, done, total: events.put(("progress", (step, done, total))),
                    stop.is_set,
                )
            except Exception as error:
                events.put(("error", str(error)))
            else:
                events.put(("done", result))

        threading.Thread(target=worker, daemon=True).start()
        dialog.after(100, poll)

    def poll():
        nonlocal active
        try:
            while True:
                event, value = events.get_nowait()
                if event == "progress":
                    if not stop.is_set():
                        step, done, total = value
                        label.configure(text=step)
                        bar.configure(value=min(100, 100 * done / total) if done is not None and total else 0)
                    continue
                active = False
                if event == "done" and value and not stop.is_set():
                    close(True)
                    return
                if stop.is_set():
                    label.configure(text="Download cancelled.")
                else:
                    label.configure(text=f"Setup could not finish. {value}" if event == "error"
                                    else "Setup did not finish. Try again or open the app.")
                for button in (download, skip, exit_button):
                    button.state(["!disabled"])
                exit_button.configure(text="Exit")
                return
        except queue.Empty:
            dialog.after(100, poll)

    download = ttk.Button(buttons, text="Download and start", command=start)
    download.pack(side="left")
    skip = ttk.Button(buttons, text="Open app", command=lambda: close(True))
    skip.pack(side="left", padx=6)
    exit_button = ttk.Button(buttons, text="Exit", command=close)
    exit_button.pack(side="right")
    dialog.protocol("WM_DELETE_WINDOW", close)
    dialog.grab_set()
    dialog.wait_window()
    if open_app:
        window.deiconify()
    return open_app
