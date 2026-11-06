import hashlib
import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copilot import qwen_install as qwen


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
