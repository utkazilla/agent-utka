import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copilot.asr_glossary import project_asr_glossary
from copilot.knowledge import Knowledge
from copilot.knowledge_pack import PACK_FENCE, PACK_FILENAME, create_workspace, import_documents


def pack(text, term, heard, *, fence=PACK_FENCE, **rule):
    glossary = {"terms": [term], "hotwords": [term],
                "aliases": [{"term": term, "heard": [heard], **rule}]}
    return f"{fence}\n{json.dumps(glossary, ensure_ascii=False)}\n```\n{text}\n"


class KnowledgePackTest(unittest.TestCase):
    def test_project_root_pack_is_loaded_without_import_and_respects_git_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = base / "Atlas"
            root.mkdir()
            source = root / PACK_FILENAME
            source.write_text(pack("Atlas uses rotating locks.", "SYNC_JOB", "синк джоб"), encoding="utf-8")
            unrelated = root / "example.md"
            unrelated.write_text(pack("An ordinary note.", "OTHER_TERM", "пример термина"), encoding="utf-8")
            index = Knowledge(base / "index.sqlite")
            self.assertEqual(index.refresh(root)[0], 2)
            hit = index.search(root, "rotating locks")[0]
            self.assertEqual((hit.path, hit.line), (source, 4))
            self.assertEqual(index.search(root, "джоб"), [])
            self.assertEqual(project_asr_glossary(root).hints, ("SYNC_JOB",))
            self.assertEqual(project_asr_glossary(root).normalize("синк джоб"), "SYNC_JOB")

            (root / ".git").mkdir()
            with patch("copilot.knowledge._repo_files", return_value=[]) as listed:
                self.assertEqual(index.refresh(root)[0], 0)
                self.assertFalse(project_asr_glossary(root).hints)
                listed.assert_called_with(root.resolve(), PACK_FILENAME)
            with patch("copilot.knowledge._repo_files", return_value=[source]):
                self.assertEqual(index.refresh(root)[0], 1)
                self.assertEqual(project_asr_glossary(root).hints, ("SYNC_JOB",))

    def test_import_indexes_prose_and_loads_project_vocabulary(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = create_workspace(base / "Atlas")
            manual = root / ".copilot-knowledge" / ".asr-glossary.json"
            manual.write_text('{"terms":["API"],"aliases":[]}', encoding="utf-8")
            source = base / "atlas.md"
            source.write_text(pack("Atlas architecture uses rotating locks.", "SYNC_JOB", "синк джоб",
                                   context="журнал|очередь"), encoding="utf-8")
            plain = base / "plain.txt"
            plain.write_text("Atlas retries are limited to three attempts.", encoding="utf-8")
            first, second = import_documents(root, [source, plain])
            index = Knowledge(base / "index.sqlite")
            self.assertEqual(index.refresh(root)[0], 2)
            hits = index.search(root, "rotating locks")
            self.assertEqual((hits[0].path, hits[0].line), (first, 4))
            self.assertNotIn(PACK_FENCE, hits[0].text)
            self.assertEqual(index.search(root, "джоб"), [])
            self.assertEqual(index.search(root, "three attempts")[0].path, second)
            glossary = project_asr_glossary(root)
            self.assertEqual(glossary.hotwords("URL"), "URL, API, SYNC_JOB")
            self.assertEqual(glossary.normalize("журнал синк джоб"), "журнал SYNC_JOB")
            self.assertEqual(glossary.normalize("про синк джоб"), "про синк джоб")
            self.assertEqual(project_asr_glossary(base / "Other").normalize("журнал синк джоб"),
                             "журнал синк джоб")
            self.assertEqual(json.loads(manual.read_text(encoding="utf-8"))["terms"], ["API"])

            source.write_text("Atlas moved to single flight.\n", encoding="utf-8")
            self.assertEqual(import_documents(root, [source]), (first,))
            (root / ".git").mkdir()
            with patch("copilot.knowledge._repo_files", return_value=[]):
                self.assertEqual(index.refresh(root)[0], 2)
            self.assertEqual(index.search(root, "rotating locks"), [])
            self.assertEqual(project_asr_glossary(root).hotwords("URL"), "URL, API")

    def test_new_root_pack_takes_precedence_and_ignored_pack_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = base / "Atlas"
            root.mkdir()
            preferred = root / "utka-cue-knowledge.md"
            preferred.write_text(pack("Index partitions use checksums.", "PARTITION", "партишн",
                                      fence="```utka-cue-asr"), encoding="utf-8")
            interim = root / "utka-knowledge.md"
            interim.write_text(pack("Atlas exports manifests.", "MANIFEST", "манифэст",
                                      fence="```utka-asr"), encoding="utf-8")
            legacy = root / "call-copilot-knowledge.md"
            legacy.write_text(pack("Atlas uses rotating locks.", "SYNC_JOB", "синк джоб",
                                   fence="```call-copilot-asr"), encoding="utf-8")
            index = Knowledge(base / "index.sqlite")
            self.assertEqual(index.refresh(root)[0], 3)
            for query, source in (("checksums", preferred), ("manifests", interim), ("rotating locks", legacy)):
                hit = index.search(root, query)[0]
                self.assertEqual((hit.path, hit.line), (source, 4))
            self.assertEqual(index.search(root, "партишн манифэст джоб"), [])
            self.assertEqual(project_asr_glossary(root).hints, ("PARTITION",))

            (root / ".git").mkdir()
            with patch("copilot.knowledge._repo_files", return_value=[legacy, interim]):
                self.assertEqual(index.refresh(root)[0], 2)
                self.assertEqual(index.search(root, "checksums"), [])
                self.assertEqual(project_asr_glossary(root).hints, ("MANIFEST",))
            with patch("copilot.knowledge._repo_files", return_value=[legacy]):
                self.assertEqual(index.refresh(root)[0], 1)
                self.assertEqual(index.search(root, "manifests"), [])
                self.assertEqual(project_asr_glossary(root).hints, ("SYNC_JOB",))

    def test_legacy_fence_is_importable_and_counts_toward_the_glossary_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "Atlas"
            source = base / "atlas.md"
            legacy = pack("Atlas uses rotating locks.", "SYNC_JOB", "синк джоб",
                          fence="```call-copilot-asr")
            source.write_text(legacy, encoding="utf-8")
            (stored,) = import_documents(root, [source])
            self.assertEqual(project_asr_glossary(root).hints, ("SYNC_JOB",))
            for fence in ("```utka-asr", "```utka-cue-asr"):
                with self.subTest(fence=fence):
                    source.write_text(legacy + pack("Atlas uses checksums.", "CHECKSUM", "чексам",
                                                   fence=fence), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        import_documents(root, [source])
                    self.assertEqual(stored.read_text(encoding="utf-8"), legacy)

    def test_validation_preserves_existing_documents_and_rejects_unsafe_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "Atlas"
            source = base / "atlas.md"
            source.write_text("Atlas prior knowledge.", encoding="utf-8")
            (stored,) = import_documents(root, [source])
            source.write_text("Atlas revised knowledge.", encoding="utf-8")
            malformed = base / "malformed.md"
            malformed.write_text(pack("Example.", "X", "икс", context="(a+)+$"), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "context"):
                import_documents(root, [source, malformed])
            self.assertEqual(stored.read_text(encoding="utf-8"), "Atlas prior knowledge.")
            malformed.write_text("api_key = obvious-secret", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "ключи"):
                import_documents(root, [source, malformed])
            self.assertEqual(list(stored.parent.iterdir()), [stored])

    def test_ordinary_example_with_literal_pack_fence_remains_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "example.md"
            source.write_text(f"# Example\n````markdown\n{PACK_FENCE}\nExample\n```\n````\n", encoding="utf-8")
            (stored,) = import_documents(base / "Atlas", [source])
            self.assertEqual(stored.read_text(encoding="utf-8"), source.read_text(encoding="utf-8"))
            self.assertFalse(project_asr_glossary(base / "Atlas").hints)
