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
            "docs/knowledge-pack-prompt.md",
            "docs/knowledge-pack-prompt.ru.md",
            "docs/knowledge-pack-prompt.es.md",
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
import ssl, sys, tempfile, time, tkinter as tk
from pathlib import Path
from tkinter import ttk
from unittest.mock import patch
import av, numpy, pyaudiowpatch, sherpa_onnx, Stemmer, webrtcvad
from copilot.app import Overlay
from copilot.bootstrap import setup_needed, setup_window
from copilot.configuration import RUNTIME, load_settings, save_settings
from copilot.knowledge import Knowledge
from copilot.knowledge import discover_projects, source_location
from copilot.knowledge_pack import import_summary
from copilot.knowledge_import import choose_import_destination
from copilot.settings_window import show_settings
from copilot.whisper_install import whisper_cuda_installed

assert Path(sys.prefix).resolve() == Path.cwd() / 'python'
ssl.create_default_context()
settings = load_settings()
assert setup_needed(RUNTIME, settings)
window = tk.Tk()
window.iconbitmap(default=str(Path.cwd() / "assets" / "utka.ico"))

def invoke_button(widget, text):
    if isinstance(widget, ttk.Button) and widget.cget('text') == text:
        widget.invoke()
        return True
    return any(invoke_button(child, text) for child in widget.winfo_children())

def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)

window.after_idle(lambda: invoke_button(window, 'Open app') or window.destroy())
assert setup_window(window, settings)
overlay = Overlay(window, settings, demo=True)
try:
    window.update()
    assert window.winfo_viewable() and overlay.transcript.winfo_ismapped()
    assert not whisper_cuda_installed()
    with tempfile.TemporaryDirectory(prefix='utka-main-flow-') as folder:
        runtime = Path(folder) / 'runtime'
        configuration = Path(folder) / 'settings.json'
        overlay.settings['extra_roots'] = []
        overlay.settings['project'] = ''
        overlay._projects([])
        assert not any(isinstance(child, tk.Toplevel) for child in window.winfo_children())
        assert overlay.new_base_button.winfo_ismapped()
        window.update_idletasks()
        assert overlay.first_import_hint.winfo_ismapped()
        assert not overlay.browse_button.winfo_ismapped()
        errors = []

        def create_from_main():
            popup = next(w for w in window.winfo_children() if isinstance(w, tk.Toplevel))
            try:
                field = next(w for w in descendants(popup) if w.winfo_name() == 'base_name')
                field.insert(0, 'Voyager')
                assert invoke_button(popup, overlay._tr('Создать базу'))
            except Exception as error:
                errors.append(error)
                popup.destroy()

        with patch('copilot.app.RUNTIME', runtime), patch(
                'copilot.app.save_settings', lambda values: save_settings(values, configuration)):
            first = Path(folder) / 'first.md'
            first.write_text('# Orbit\\nThe first retry waits 5 seconds.', encoding='utf-8')

            def accept_first_import():
                popup = next(w for w in window.winfo_children() if isinstance(w, tk.Toplevel))
                try:
                    popup.update_idletasks()
                    controls = {w.winfo_name(): w for w in descendants(popup)}
                    assert 'base' not in controls
                    assert controls['name'].get() == 'Orbit'
                    assert not controls['document_name'].winfo_ismapped()
                    assert invoke_button(popup, overlay._tr('Импортировать'))
                except Exception as error:
                    errors.append(error)
                    popup.destroy()

            with patch('copilot.app.filedialog.askopenfilename', return_value=str(first)):
                window.after(100, accept_first_import)
                overlay.import_button.invoke()
            assert not errors, errors
            until = time.monotonic() + 5
            while overlay.import_button.instate(['disabled']) and time.monotonic() < until:
                window.update()
                time.sleep(.05)
            assert overlay.import_button.instate(['!disabled'])
            assert list(overlay.bases) == ['Orbit']
            assert load_settings(configuration)['project'] == str(overlay.project)
            overlay.index = Knowledge(runtime / 'test.sqlite', documents_only=True)
            assert overlay.index.refresh(overlay.project)[0] == 1
            assert '5 seconds' in overlay.index.search(overlay.project, 'first retry')[0].text
            window.after(100, create_from_main)
            overlay.new_base_button.invoke()
            assert not errors, errors
            assert set(overlay.bases) == {'Orbit', 'Voyager'}
            assert overlay.project == overlay.bases['Voyager']
            assert load_settings(configuration)['project'] == str(overlay.project)
            assert len(discover_projects(documents_only=True, managed=runtime / 'knowledge')) == 2
            window.after(100, lambda: invoke_button(window, overlay._tr('Отмена')))
            overlay.new_base_button.invoke()
            assert len(overlay.bases) == 2
            overlay.index = Knowledge(runtime / 'test.sqlite', documents_only=True)
            assert overlay.index.refresh(overlay.project)[0] == 0
            for _ in range(2):
                overlay.browse_button.invoke()
                browser = overlay.knowledge_window
                assert browser.winfo_exists()
                until = time.monotonic() + 5
                while time.monotonic() < until:
                    window.update()
                    labels = [str(w.cget('text')) for w in descendants(browser) if isinstance(w, tk.Label)]
                    if any('Import' in text or 'Импортировать' in text or 'Importar' in text for text in labels):
                        break
                    time.sleep(.05)
                else:
                    raise AssertionError('Empty base did not provide an import recovery action.')
                browser.destroy()
            overlay.knowledge_window = None
            source = Path(folder) / 'summary.md'
            source.write_text('# Voyager\\nRetry delay is 9 seconds.', encoding='utf-8')

            def name_import():
                popup = next(w for w in window.winfo_children() if isinstance(w, tk.Toplevel))
                try:
                    assert invoke_button(popup, overlay._tr('Изменить название выжимки…'))
                    field = next(w for w in descendants(popup) if w.winfo_name() == 'document_name')
                    field.delete(0, 'end')
                    field.insert(0, 'Decisions')
                    assert invoke_button(popup, overlay._tr('Импортировать'))
                except Exception as error:
                    errors.append(error)
                    popup.destroy()

            with patch('copilot.app.filedialog.askopenfilename', return_value=str(source)):
                window.after(100, name_import)
                overlay.import_button.invoke()
            assert not errors, errors
            until = time.monotonic() + 5
            while overlay.import_target is not None and time.monotonic() < until:
                window.update()
                time.sleep(.05)
            assert overlay.import_target is None
            assert overlay.index.refresh(overlay.project)[0] == 1
            hit = overlay.index.search(overlay.project, 'retry delay')[0]
            assert source_location(overlay.project, hit.path) == 'Decisions (summary.md)'
            overlay.index = None
    with tempfile.TemporaryDirectory(prefix='utka-large-import-') as folder:
        base = Path(folder)
        document = base / 'notes.md'
        document.write_text('# Atlas\\n' + ('Project background.\\n' * 12000)
                            + '\\n## Final decision\\nRelease name is SaffronHarbor.\\n', encoding='utf-8')
        atlas = import_summary(base / 'runtime', document, name='Atlas')
        document.write_text('# Orbit\\nOrbit retry delay is 9 seconds.', encoding='utf-8')
        orbit = import_summary(base / 'runtime', document, name='Orbit')
        index = Knowledge(base / 'index.sqlite', documents_only=True)
        index.refresh(atlas)
        index.refresh(orbit)
        assert 'SaffronHarbor' in index.search(atlas, 'SaffronHarbor')[0].text
        assert any(hit.path.is_relative_to(orbit) for hit in index.search((atlas, orbit), 'retry delay'))
        overlay._projects(discover_projects(documents_only=True, managed=base / 'runtime/knowledge'))
        assert len(overlay.bases) == 2
        window.after(100, lambda: next(w for w in window.winfo_children() if isinstance(w, tk.Toplevel)).destroy())
        assert choose_import_destination(overlay, document) is None
        overlay.project = atlas

        def import_dialog_test(create_new):
            errors = []
            def fill():
                popup = next(w for w in window.winfo_children() if isinstance(w, tk.Toplevel))
                try:
                    entries = {child.winfo_name(): child for child in descendants(popup)
                               if isinstance(child, ttk.Entry) and not isinstance(child, ttk.Combobox)}
                    title = entries['document_name']
                    title.delete(0, 'end')
                    confirm = next(child for child in descendants(popup)
                                   if isinstance(child, ttk.Button)
                                   and child.cget('text') == overlay._tr('Импортировать'))
                    assert confirm.instate(['disabled'])
                    title.insert(0, 'Release decisions')
                    if create_new:
                        picker = next(w for w in descendants(popup) if w.winfo_name() == 'base')
                        picker.current(len(picker['values']) - 1)
                        entries['name'].delete(0, 'end')
                        entries['name'].insert(0, 'Voyager')
                    confirm.invoke()
                except Exception as error:
                    errors.append(error)
                    popup.destroy()
            window.after(100, fill)
            choice = choose_import_destination(overlay, document)
            assert not errors, errors
            assert choice == ((None, 'Voyager', 'Release decisions') if create_new
                              else (atlas, None, 'Release decisions')), choice
        import_dialog_test(False)
        import_dialog_test(True)
    for language, suffix, label in (
        ('en', '', 'Copy prompt'),
        ('ru', '.ru', 'Копировать промпт'),
        ('es', '.es', 'Copiar prompt'),
    ):
        overlay.ui_language = language
        show_settings(overlay)
        popup = overlay.settings_window
        try:
            template = Path('docs', f'knowledge-pack-prompt{suffix}.md').read_text(encoding='utf-8')
            with patch.object(window, 'clipboard_clear'), patch.object(window, 'clipboard_append') as copy:
                assert invoke_button(popup, label), label
                copy.assert_called_once_with(template)
            if language == 'en':
                assert invoke_button(popup, 'Choose model…')
                picker = next(child for child in popup.winfo_children() if isinstance(child, tk.Toplevel))
                assert picker.title() == 'Speech recognition models'
                tabs = next(child for child in descendants(picker) if isinstance(child, ttk.Notebook))
                catalog, installed = [tabs.nametowidget(tab) for tab in tabs.tabs()]
                assert [tabs.tab(tab, 'text') for tab in (catalog, installed)] == ['Catalog', 'Installed']
                search = next(child for child in descendants(catalog) if isinstance(child, ttk.Entry))
                models = next(child for child in descendants(catalog) if isinstance(child, ttk.Treeview))
                assert len(models.get_children()) == 21
                search.insert(0, 'Qwen')
                window.update()
                assert models.get_children() == ('0.6b-int8', '1.7b-int8', '0.6b-int8-cuda', '1.7b-int8-cuda')
                assert models.set('1.7b-int8', 'model') == 'Qwen3-ASR 1.7B'
                assert models.set('1.7b-int8-cuda', 'variant') == 'BF16 · NVIDIA GPU'
                search.delete(0, 'end')
                search.insert(0, 'DISTIL')
                window.update()
                assert len(models.get_children()) == 5
                assert models.set('distil-large-v3.5', 'languages') == 'English only'
                tabs.select(installed)
                window.update()
                on_disk = next(child for child in descendants(installed) if isinstance(child, ttk.Treeview))
                assert not on_disk.get_children()
                select = next(child for child in descendants(picker)
                              if isinstance(child, ttk.Button) and child.cget('text') == 'Download and select')
                assert select.instate(['disabled'])
                picker.destroy()
        finally:
            popup.destroy()
    with tempfile.TemporaryDirectory(prefix='utka-knowledge-smoke-') as directory:
        project = Path(directory) / 'demo'
        project.mkdir()
        (project / 'notes.md').write_text('# Example: access token lifetime is 37 minutes.', encoding='utf-8')
        overlay.project = project.resolve()
        overlay.index = Knowledge(Path(directory) / 'index.sqlite')
        assert overlay.index.refresh(overlay.project)[0] == 1
        overlay.ui_language = 'en'
        show_settings(overlay)
        popup = overlay.settings_window
        assert invoke_button(popup, 'Open base')
        browser = next(child for child in popup.winfo_children() if isinstance(child, tk.Toplevel))
        assert browser.title() == 'Knowledge browser'
        tree = next(child for child in descendants(browser) if isinstance(child, ttk.Treeview))
        until = time.monotonic() + 5
        while time.monotonic() < until:
            window.update()
            if [tree.set(row, 'source') for row in tree.get_children()] == ['notes.md']:
                break
            time.sleep(.05)
        else:
            raise AssertionError('The knowledge browser did not list the synthetic document.')
        popup.destroy()
finally:
    overlay.close()
print('The setup dialog, model picker, prompt buttons and knowledge browser passed with bundled Python.')
"""], cwd=directory, env=env, check=True, timeout=60)
    subprocess.run([*python, "-m", "pip", "--version"], cwd=directory, env=env, check=True, timeout=60)
    subprocess.run([*python, "-m", "copilot.app", "--ui-test"], cwd=directory, env=env, check=True, timeout=60)


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
