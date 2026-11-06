import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copilot.configuration import load_settings, save_settings
from copilot.whisper_install import _Source, _run_worker, install_whisper, whisper_installed


class WhisperInstallationTests(unittest.TestCase):
    def test_snapshot_status_checks_weights_and_required_files(self):
        files = {"config.json": b"config", "model.bin": b"weights", "tokenizer.json": b"tokens"}
        source = _Source("publisher/model", "example", {name: len(data) for name, data in files.items()})
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.dict("copilot.whisper_install._SOURCES", {"tiny": source}),
            patch("copilot.whisper_install._package_installed", return_value=True),
        ):
            folder = Path(temp) / "whisper/models--publisher--model/snapshots/example"
            folder.mkdir(parents=True)
            for name, data in files.items():
                (folder / name).write_bytes(data)
            self.assertTrue(whisper_installed(temp, "tiny"))
            (folder / "model.bin").write_bytes(b"part")
            self.assertFalse(whisper_installed(temp, "tiny"))
            (folder / "model.bin").write_bytes(files["model.bin"])
            (folder / "tokenizer.json").write_bytes(b"part")
            self.assertFalse(whisper_installed(temp, "tiny"))

    def test_cancel_during_download_skips_verification(self):
        progress = []
        with (
            patch("copilot.whisper_install._package_installed", return_value=True),
            patch("copilot.whisper_install.whisper_cache_path", return_value=None),
            patch("copilot.whisper_install._run_worker", return_value=False),
        ):
            self.assertFalse(install_whisper(".", "tiny", lambda *event: progress.append(event)))
        self.assertEqual([stage for stage, *_ in progress], ["download"])

    def test_worker_reports_bytes_and_cancels_an_active_process(self):
        progress = []
        result = _run_worker(
            ["-c", "import time; print('CALL_COPILOT_WHISPER_BYTES 12', flush=True); time.sleep(30)"],
            lambda: bool(progress), progress.append,
        )
        self.assertIs(result, False)
        self.assertEqual(progress, [12])

    def test_whisper_selection_is_separate_from_external_speech_model(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "settings.local.json"
            save_settings({"stt_engine": "openai_local", "stt_model": "remote-model"}, path)
            self.assertEqual(load_settings(path)["whisper_model"], "large-v3")
            save_settings({"stt_engine": "whisper", "whisper_model": "tiny"}, path)
            settings = load_settings(path)
            self.assertEqual(settings["whisper_model"], "tiny")
            self.assertEqual(settings["stt_model"], "remote-model")
