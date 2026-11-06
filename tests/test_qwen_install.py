import hashlib
import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from copilot import qwen_install as qwen
from copilot.configuration import load_settings, save_settings
from copilot.speech import create_asr


class QwenInstallTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.runtime = Path(temporary.name)
        self.bundle = self.runtime / qwen.QWEN_ASR_BUNDLE
        self.files = {
            "conv_frontend.onnx": b"model",
            "tokenizer/vocab.json": b"vocab",
        }

    def archive(self, *, replace_with_link=None):
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w:bz2") as archive:
            for path, data in {**self.files, "../outside.txt": b"not installed"}.items():
                entry = tarfile.TarInfo(f"{qwen.QWEN_ASR_BUNDLE}/{path}")
                if path == replace_with_link:
                    entry.type = tarfile.SYMTYPE
                    entry.linkname = "../../outside.txt"
                    archive.addfile(entry)
                else:
                    entry.size = len(data)
                    archive.addfile(entry, io.BytesIO(data))
        return output.getvalue()

    def install(self, archive, *, checksum=None, on_progress=lambda *_: None, cancelled=lambda: False):
        with (patch.object(qwen, "_FILES", {key: len(value) for key, value in self.files.items()}),
              patch.object(qwen, "QWEN_DOWNLOAD_BYTES", len(archive)),
              patch.object(qwen, "_SHA256", checksum or hashlib.sha256(archive).hexdigest()),
              patch.object(qwen, "urlopen", return_value=io.BytesIO(archive))):
            result = qwen.install_qwen(self.runtime, on_progress, cancelled)
            self.assertEqual(qwen.qwen_installed(self.runtime), result)
            return result

    def test_verified_download_installs_only_allowed_files_and_preserves_valid_files(self):
        self.bundle.mkdir()
        retained = self.bundle / "unrelated.txt"
        retained.write_bytes(b"preserve")
        stages = []
        self.assertTrue(self.install(self.archive(), on_progress=lambda stage, *_: stages.append(stage)))
        self.assertEqual(retained.read_bytes(), b"preserve")
        for path, value in self.files.items():
            self.assertEqual((self.bundle / path).read_bytes(), value)
        self.assertFalse((self.runtime / "outside.txt").exists())
        self.assertIn("download", stages)
        self.assertIn("verify", stages)

    def test_bad_checksum_and_symlink_never_replace_existing_weights(self):
        self.bundle.mkdir()
        original = self.bundle / "conv_frontend.onnx"
        original.write_bytes(b"old")
        for archive, checksum, message in (
            (self.archive(), "0" * 64, "checksum"),
            (self.archive(replace_with_link="tokenizer/vocab.json"), None, "Unexpected file"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(OSError, message):
                self.install(archive, checksum=checksum)
            self.assertEqual(original.read_bytes(), b"old")
            self.assertEqual(list(self.runtime.iterdir()), [self.bundle])

    def test_cancel_during_extraction_does_not_publish_bundle(self):
        stopped = False

        def progress(stage, done, _total):
            nonlocal stopped
            if stage == "verify" and done:
                stopped = True

        self.assertFalse(self.install(self.archive(), on_progress=progress, cancelled=lambda: stopped))
        self.assertEqual(list(self.runtime.iterdir()), [])

    def test_install_17b_checks_each_file_and_preserves_other_variant(self):
        files = {name: (len(data), hashlib.sha256(data).hexdigest()) for name, data in self.files.items()}
        self.bundle.mkdir()
        old = self.bundle / "keep.txt"
        old.write_text("previous bundle", encoding="utf-8")
        with patch.object(qwen, "_LARGE_FILES", files), patch.object(qwen, "urlopen") as fetch:
            fetch.side_effect = [io.BytesIO(b"x" * len(next(iter(self.files.values()))))]
            with self.assertRaisesRegex(OSError, "checksum"):
                qwen.install_qwen(self.runtime, variant="1.7b-int8")
            self.assertEqual(list(self.runtime.iterdir()), [self.bundle])

            fetch.side_effect = [io.BytesIO(data) for data in self.files.values()]
            self.assertTrue(qwen.install_qwen(self.runtime, variant="1.7b-int8"))
            self.assertTrue(qwen.qwen_installed(self.runtime, "1.7b-int8"))
            self.assertFalse(qwen.qwen_installed(self.runtime))
            self.assertEqual(old.read_text(encoding="utf-8"), "previous bundle")

    def test_recognizer_uses_the_saved_qwen_variant(self):
        settings = self.runtime / "settings.json"
        self.assertEqual(load_settings(settings)["qwen_model"], "0.6b-int8")
        save_settings({"qwen_model": "1.7b-int8"}, settings)
        with patch("copilot.speech.QwenASR._load_cpu", autospec=True) as cpu:
            recognizer = create_asr(self.runtime, qwen_model=load_settings(settings)["qwen_model"])
            self.assertEqual(recognizer.name, "Qwen3-ASR 1.7B")
            cpu.assert_called_once_with(recognizer)

    def test_recognizer_strips_only_leading_language_metadata(self):
        with patch("copilot.speech.QwenASR._load_cpu"):
            recognizer = create_asr(self.runtime, qwen_model="1.7b-int8")
        recognizer.model = Mock()
        stream = recognizer.model.create_stream.return_value
        for decoded, transcript in (
            ("language English<asr_text>What is the token lifetime?", "What is the token lifetime?"),
            ("language None<asr_text>", ""),
            ("Use the <asr_text> tag.", "Use the <asr_text> tag."),
        ):
            with self.subTest(decoded=decoded):
                stream.result.text = decoded
                self.assertEqual(recognizer(b"\0\0"), transcript)
