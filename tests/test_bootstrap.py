import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from zipfile import ZipFile

from copilot.bootstrap import SetupCancelled, _unpack_ollama, download_answer_model, prepare_runtime, setup_needed
from copilot.configuration import DEFAULTS


class FirstRunTests(unittest.TestCase):
    def test_picker_installs_missing_ollama_before_pulling_and_can_retry(self):
        brain = Mock(external_host=None, runtime=Path("runtime"))
        brain.pull.return_value = True
        progress, cancelled = Mock(), Mock(return_value=False)
        with patch("copilot.bootstrap._download_ollama", side_effect=SetupCancelled):
            self.assertFalse(download_answer_model(brain, "qwen3.5:4b", progress, cancelled))
            brain.pull.assert_not_called()
        with patch("copilot.bootstrap._download_ollama") as install:
            def pull(name, report, stop):
                install.assert_called_once_with(brain.runtime, progress, cancelled)
                self.assertEqual((name, report, stop), ("qwen3.5:4b", progress, cancelled))
                return True
            brain.pull.side_effect = pull
            self.assertTrue(download_answer_model(brain, "qwen3.5:4b", progress, cancelled))

    def test_picker_uses_configured_external_ollama_without_installing_portable_server(self):
        brain = Mock(external_host="127.0.0.1:11434")
        brain.pull.return_value = True
        with patch("copilot.bootstrap._download_ollama") as install:
            self.assertTrue(download_answer_model(brain, "qwen3.5:4b", Mock(), lambda: False))
            install.assert_not_called()
            brain.pull.assert_called_once()

    def test_first_run_prepares_defaults_and_can_be_skipped_for_external_engines(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            self.assertTrue(setup_needed(runtime, DEFAULTS))
            self.assertFalse(setup_needed(runtime, {
                **DEFAULTS, "stt_engine": "openai_local", "llm_provider": "ollama_local",
            }))
            brain = Mock()
            brain.models.return_value = []
            brain.pull.return_value = True

            def install_ollama(runtime, *_):
                (runtime / "ollama").mkdir()
                (runtime / "ollama" / "ollama.exe").touch()

            with (
                patch("copilot.bootstrap.qwen_installed", return_value=False),
                patch("copilot.bootstrap.install_qwen", return_value=True) as qwen,
                patch("copilot.bootstrap._download_ollama", side_effect=install_ollama),
                patch("copilot.bootstrap.create_brain", return_value=brain),
            ):
                self.assertTrue(prepare_runtime(runtime, DEFAULTS, Mock(), lambda: False))
                qwen.assert_called_once()
                self.assertEqual(brain.pull.call_args.args[0], DEFAULTS["ollama"])
                brain.close.assert_called_once()
            with patch("copilot.bootstrap.qwen_installed", return_value=True):
                self.assertFalse(setup_needed(runtime, DEFAULTS))

    def test_cancel_keeps_setup_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            with patch("copilot.bootstrap.install_qwen", return_value=False):
                self.assertFalse(prepare_runtime(runtime, DEFAULTS, Mock(), lambda: False))
            self.assertFalse((runtime / "installer-setup.complete").exists())
            self.assertTrue(setup_needed(runtime, DEFAULTS))

    def test_ollama_extraction_rejects_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "ollama.zip"
            with ZipFile(archive, "w") as package:
                package.writestr("../escape.exe", b"not a real executable")
            with self.assertRaisesRegex(OSError, "unsafe path"):
                _unpack_ollama(archive, root / "target", lambda: False)
            self.assertFalse((root / "escape.exe").exists())
