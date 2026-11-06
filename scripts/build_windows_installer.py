"""Stage a self-contained Windows app, optionally compile and test its installer."""

import argparse
import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from build_source_release import PUBLIC_FILES, ROOT, public_file


PYTHON_DLL = f"python{sys.version_info.major}{sys.version_info.minor}.dll"
PYTHON_FILES = ("python.exe", "pythonw.exe", PYTHON_DLL, "python3.dll", "LICENSE.txt",
                "vcruntime140.dll", "vcruntime140_1.dll")
MODEL_EXTENSIONS = {".gguf", ".ggml", ".onnx", ".ort", ".safetensors", ".pt", ".pth",
                    ".ckpt", ".tflite", ".h5", ".bin", ".npy", ".npz"}
PRIVATE_PARTS = {".git", ".runtime", ".venv", ".copilot-knowledge", "settings.local.json"}
PIP_VERSION = "26.3"


def check_payload(directory):
    for path in directory.rglob("*"):
        relative = path.relative_to(directory)
        if path.is_symlink() or path.is_junction() or any(part.lower() in PRIVATE_PARTS for part in relative.parts):
            raise ValueError(f"Unexpected path in the installer: {relative}")
        if path.is_file() and (path.suffix.lower() in MODEL_EXTENSIONS or path.name.startswith("sha256-")):
            raise ValueError(f"Model or binary data file in the installer: {relative}")


def stage(payload, vc_redist, wheelhouse):
    for name in (*PUBLIC_FILES, "LICENSE"):
        if name.startswith(("assets/", "copilot/", "docs/examples/")) or name in {
            "README.md", "LICENSE", "settings.example.json",
        }:
            source = public_file(name)
            target = payload / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    python = payload / "python"
    python.mkdir()
    base = Path(sys.base_prefix)
    for name in PYTHON_FILES:
        shutil.copyfile(base / name, python / name)
    for name in ("msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "msvcp140_atomic_wait.dll",
                 "msvcp140_codecvt_ids.dll", "concrt140.dll", "vcruntime140.dll", "vcruntime140_1.dll"):
        shutil.copyfile(vc_redist / name, python / name)
    shutil.copytree(base / "DLLs", python / "DLLs", ignore=shutil.ignore_patterns("*.lib", "*.pdb", "_test*"))
    (python / "Lib").mkdir()
    stdlib = sys.stdlib_module_names - {"idlelib", "ensurepip", "test"}
    for path in (base / "Lib").iterdir():
        if path.stem not in stdlib:
            continue
        target = python / "Lib" / path.name
        if path.is_dir():
            shutil.copytree(path, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "test", "tests"))
        elif path.suffix == ".py":
            shutil.copyfile(path, target)
    for name in ("tcl8", "tcl8.6", "tk8.6"):
        shutil.copytree(base / "tcl" / name, python / "tcl" / name)

    # Install wheels into an empty target, keeping only importable packages and their licenses.
    # Entry point wrappers from pip can contain the absolute path of the build interpreter.
    with tempfile.TemporaryDirectory(prefix="utka-wheels-") as folder:
        packages = Path(folder)
        source = ["--no-index", "--find-links", str(wheelhouse)] if wheelhouse else [
            "--index-url", "https://pypi.org/simple",
        ]
        subprocess.run([
            sys.executable, "-E", "-s", "-m", "pip", "--isolated", "--disable-pip-version-check", "install",
            "--no-compile", "--only-binary=:all:", "--target", str(packages), *source,
            "-r", str(ROOT / "requirements.txt"), f"pip=={PIP_VERSION}",
        ], check=True, env={**os.environ, "PIP_CONFIG_FILE": os.devnull})
        site = python / "Lib" / "site-packages"
        site.mkdir()
        for path in packages.iterdir():
            if path.name.lower() in {"bin", "scripts", "__pycache__"}:
                continue
            if path.is_dir():
                shutil.copytree(path, site / path.name, ignore=shutil.ignore_patterns(
                    "__pycache__", "*.pyc", "test", "tests",
                ))
            else:
                shutil.copyfile(path, site / path.name)
    (python / "agent-utka-runtime").touch()
    check_payload(payload)


def smoke_test(directory):
    directory = directory.resolve()
    env = {**os.environ, "PATH": str(Path(os.environ["SystemRoot"]) / "System32")}
    python = [str(directory / "python" / "python.exe"), "-E", "-s", "-B"]
    subprocess.run([*python, "-c", """
import ssl, sys, tkinter as tk
from pathlib import Path
from tkinter import ttk
import av, numpy, pyaudiowpatch, sherpa_onnx, Stemmer, webrtcvad
from copilot.app import Overlay
from copilot.bootstrap import setup_needed, setup_window
from copilot.configuration import RUNTIME, load_settings

assert Path(sys.prefix).resolve() == Path.cwd() / 'python'
ssl.create_default_context()
settings = load_settings()
assert setup_needed(RUNTIME, settings)
window = tk.Tk()

def open_app(widget):
    if isinstance(widget, ttk.Button) and widget.cget('text') == 'Open app':
        widget.invoke()
        return True
    return any(open_app(child) for child in widget.winfo_children())

window.after_idle(lambda: open_app(window) or window.destroy())
assert setup_window(window, settings)
overlay = Overlay(window, settings, demo=True)
try:
    window.update()
    assert window.winfo_viewable() and overlay.transcript.winfo_ismapped()
finally:
    overlay.close()
print('The installed setup dialog and main window opened with bundled Python.')
"""], cwd=directory, env=env, check=True, timeout=60)
    subprocess.run([*python, "-m", "pip", "--version"], cwd=directory, env=env, check=True, timeout=60)


def compile_installer(iscc, version, payload, output):
    setup_name = f"Agent-Utka-Setup-v{version}-x64.exe"
    installer = output / setup_name
    subprocess.run([str(iscc), "/Qp", f"/DAppVersion={version}", f"/DPayloadDir={payload}",
                    f"/DOutputDir={output}", str(ROOT / "installer" / "agent-utka.iss")],
                   check=True, timeout=240)
    with tempfile.TemporaryDirectory(prefix="utka-install-test-") as folder:
        installed = Path(folder) / "Agent Utka"
        options = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]
        subprocess.run([str(installer), *options, "/SP-", f"/DIR={installed}"], check=True, timeout=120)
        try:
            check_payload(installed)
            smoke_test(installed)
        finally:
            subprocess.run([str(installed / "unins000.exe"), *options], check=True, timeout=120)
    with installer.open("rb") as file:
        digest = hashlib.file_digest(file, "sha256").hexdigest()
    (output / f"{setup_name}.sha256").write_text(f"{digest}  {setup_name}\n", encoding="ascii")
    print(f"Built and tested {setup_name} ({installer.stat().st_size:,} bytes).", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="Three-part version without the v prefix")
    parser.add_argument("--output", required=True, type=Path, help="New output directory")
    parser.add_argument("--vc-redist", required=True, type=Path, help="Visual Studio's x64 CRT redist directory")
    parser.add_argument("--wheelhouse", type=Path, help="Use a previously downloaded wheel directory")
    parser.add_argument("--iscc", type=Path, help="Path to Inno Setup's ISCC.exe (omit to stage and test only)")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", args.version):
        parser.error("--version must be in MAJOR.MINOR.PATCH form")
    if (sys.platform != "win32" or platform.machine().upper() != "AMD64"
            or sys.version_info[:2] not in {(3, 12), (3, 13)}):
        parser.error("building requires x64 Windows and Python 3.12 or 3.13 with Tk")
    output = args.output.resolve()
    output.mkdir(parents=True)
    payload = output / "payload"
    stage(payload, args.vc_redist, args.wheelhouse)
    if args.iscc:
        compile_installer(args.iscc, args.version, payload, output)
    else:
        smoke_test(payload)
        print("Staged and tested the Windows payload.", flush=True)


if __name__ == "__main__":
    main()
