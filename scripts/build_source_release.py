"""Build the public Agent Utka archive from a fixed allowlist."""
import argparse
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_FILES = (
    ".github/workflows/windows-release.yml",
    ".gitignore",
    "README.md",
    "requirements.txt",
    "settings.example.json",
    "Setup Agent Utka.ps1",
    "Start Agent Utka.cmd",
    "assets/utka.png",
    "assets/utka.ico",
    "copilot/__init__.py",
    "copilot/app.py",
    "copilot/asr_glossary.py",
    "copilot/bootstrap.py",
    "copilot/brains.py",
    "copilot/catalog.py",
    "copilot/configuration.py",
    "copilot/hardware.py",
    "copilot/history.py",
    "copilot/i18n.py",
    "copilot/knowledge.py",
    "copilot/knowledge_pack.py",
    "copilot/model_picker.py",
    "copilot/ollama_library.py",
    "copilot/pipeline.py",
    "copilot/prepare.py",
    "copilot/qwen_install.py",
    "copilot/retrieval.py",
    "copilot/settings_window.py",
    "copilot/speech.py",
    "copilot/speech_picker.py",
    "copilot/suggest.py",
    "copilot/whisper_install.py",
    "docs/tutorial.md",
    "docs/tutorial.ru.md",
    "docs/publishing.md",
    "docs/knowledge-pack-prompt.md",
    "docs/knowledge-pack-prompt.ru.md",
    "docs/knowledge-pack-prompt.es.md",
    "docs/examples/orbit-knowledge.md",
    "docs/examples/harry-potter-demo.md",
    "docs/examples/local-search-demo.py",
    "docs/screenshots/harry-potter-answer.jpg",
    "docs/screenshots/harry-potter-selection.jpg",
    "docs/screenshots/harry-potter-source.jpg",
    "installer/agent-utka.iss",
    "scripts/build_source_release.py",
    "scripts/build_windows_installer.py",
    "tests/test_bootstrap.py",
    "tests/test_catalog.py",
    "tests/test_configuration.py",
    "tests/test_core.py",
    "tests/test_hardware.py",
    "tests/test_history.py",
    "tests/test_knowledge_pack.py",
    "tests/test_local_retrieval.py",
    "tests/test_ollama_library.py",
    "tests/test_qwen_install.py",
    "tests/test_speech_provider.py",
    "tests/test_whisper_install.py",
)
OPTIONAL_FILES = ("LICENSE", "NOTICE")


def public_file(name):
    relative = Path(name)
    path = ROOT / relative
    if any((ROOT / part).is_symlink() or (ROOT / part).is_junction()
           for part in (relative, *relative.parents)):
        raise ValueError(f"Public entry is a symlink or junction: {name}")
    if not path.is_file() or not path.resolve().is_relative_to(ROOT):
        raise ValueError(f"Public entry is missing or outside the application: {name}")
    return path


def build(output):
    names = PUBLIC_FILES + tuple(name for name in OPTIONAL_FILES
                                 if (ROOT / name).exists() or (ROOT / name).is_symlink())
    paths = [(public_file(name), name) for name in names]
    with output.open("xb") as stream:
        try:
            with ZipFile(stream, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
                for path, name in paths:
                    archive.write(path, name)
        except BaseException:
            stream.close()
            output.unlink(missing_ok=True)
            raise
    return len(paths)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New .zip file. Its parent directory must exist.")
    args = parser.parse_args()
    output = args.output.absolute()
    if output.suffix.lower() != ".zip":
        parser.error("output must end in .zip")
    try:
        count = build(output)
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print(f"Created {output} with {count} allowlisted files.")
    if not (ROOT / "LICENSE").is_file():
        print("Review copy: add a project license before publishing as open source.", file=sys.stderr)


if __name__ == "__main__":
    main()
