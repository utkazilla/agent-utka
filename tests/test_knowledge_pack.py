import json
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copilot.asr_glossary import project_asr_glossary
from copilot.knowledge import Knowledge, discover_projects, source_location
from copilot.knowledge_pack import PACK_FENCE, PACK_FILENAME, create_workspace, import_documents, import_summary, import_title


def pack(text, term, heard, *, fence=PACK_FENCE, **rule):
    glossary = {"terms": [term], "hotwords": [term],
                "aliases": [{"term": term, "heard": [heard], **rule}]}
    return f"{fence}\n{json.dumps(glossary, ensure_ascii=False)}\n```\n{text}\n"


class KnowledgePackTest(unittest.TestCase):
    def test_document_name_changes_without_renaming_source_or_losing_update_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "export.md"
            original = "# Original heading\n\nOranges grow in the northern orchard.\n"
            source.write_text(original, encoding="utf-8")
            root = import_summary(base / "runtime", source, name="Atlas", document_name="Architecture")
            index = Knowledge(base / "index.sqlite", documents_only=True)
            index.refresh(root)
            hit = index.search(root, "Oranges")[0]
            self.assertEqual(source_location(root, hit.path), "Architecture (export.md)")
            self.assertEqual(source_location((root,), hit.path), "Atlas / Architecture (export.md)")
            self.assertEqual(source.read_text(encoding="utf-8"), original)
            source.write_text("# Original heading\n\nPears grow in the east.\n", encoding="utf-8")
            import_summary(base / "runtime", source, target=root)
            self.assertEqual(index.refresh(root)[0], 1)
            self.assertFalse(index.search(root, "Oranges"))
            self.assertEqual(source_location(root, index.search(root, "Pears")[0].path),
                             "Architecture (export.md)")
            import_summary(base / "runtime", source, target=root, document_name="Decisions")
            self.assertEqual(index.refresh(root)[0], 1)
            self.assertEqual(source_location(root, hit.path), "Decisions (export.md)")
            self.assertEqual(import_title(root, source), "Decisions")

    def test_legacy_folder_uses_knowledge_title_instead_of_directory_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "Old App Name"
            source = base / "notes.md"
            source.write_text("# Atlas knowledge\n\nOranges grow here.", encoding="utf-8")
            import_documents(root, [source])
            projects = discover_projects(extra=[str(root)], documents_only=True)
            self.assertEqual([(p.name, p.root) for p in projects], [("Atlas knowledge", root)])

    def test_invalid_document_name_does_not_create_a_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "notes.md"
            source.write_text("A useful fact.", encoding="utf-8")
            for name in (" ", "x" * 101):
                with self.assertRaises(ValueError):
                    import_summary(base / "runtime", source, name="Atlas", document_name=name)
            self.assertFalse((base / "runtime/knowledge").exists())

    def test_large_import_indexes_its_end_and_preserves_a_large_glossary(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / PACK_FILENAME
            terms = [f"ProjectSymbol{i}" for i in range(260)]
            glossary = {"terms": terms, "hotwords": terms[:10],
                        "aliases": [{"term": term, "heard": [f"spoken symbol {i}"]}
                                    for i, term in enumerate(terms)]}
            text = ("# Complete project\n\nThe initial milestone is BirchLaunch.\n\n"
                    + ("Documentation for an unrelated module.\n" * 7000)
                    + "\n## Final decision\nThe release codename is SaffronHarbor.\n\n"
                    + PACK_FENCE + "\n" + json.dumps(glossary) + "\n\u0060\u0060\u0060\n")
            source.write_text(text, encoding="utf-8")
            root = import_summary(base / "runtime", source)
            index = Knowledge(base / "index.sqlite", documents_only=True)
            self.assertEqual(index.refresh(root)[0], 1)
            self.assertIn("BirchLaunch", index.search(root, "BirchLaunch")[0].text)
            hit = index.search(root, "SaffronHarbor")[0]
            self.assertIn("SaffronHarbor", hit.text)
            self.assertIn("SaffronHarbor", "\n".join(text.splitlines()[hit.line-1:hit.line+10]))
            self.assertEqual(project_asr_glossary(root, documents_only=True).normalize("spoken symbol 259"),
                             "ProjectSymbol259")

    def test_long_paragraphs_have_no_silently_dropped_tail(self):
        from copilot.knowledge import _chunks
        text = "# Decision\n" + " ".join(f"uniqueToken{i:04}" for i in range(1000)) + "\nLastFact"
        parts = list(_chunks(text, compact=True))
        indexed = " ".join(body for _, body in parts)
        for token in text.split():
            self.assertIn(token, indexed)
        self.assertTrue(all(len(body) <= 3200 for _, body in parts))
        self.assertTrue(all(line == 2 for line, body in parts if "uniqueToken" in body))

    def test_legacy_base_updates_original_after_another_document_is_added(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "notes.md"
            source.write_text("Oranges grow in the north.", encoding="utf-8")
            identity = hashlib.sha256(os.path.normcase(str(source.resolve())).encode("utf-8")).hexdigest()[:20]
            root = base / "runtime/knowledge" / identity
            import_documents(root, [source])
            other_folder = base / "other"
            other_folder.mkdir()
            other = other_folder / "notes.md"
            other.write_text("Bananas grow in the south.", encoding="utf-8")
            import_summary(base / "runtime", other, target=root)
            source.write_text("Pears grow in the east.", encoding="utf-8")
            import_summary(base / "runtime", source, target=root)
            index = Knowledge(base / "index.sqlite", documents_only=True)
            self.assertEqual(index.refresh(root)[0], 2)
            self.assertFalse(index.search(root, "Oranges"))
            self.assertIn("Pears", index.search(root, "Pears")[0].text)
            self.assertIn("Bananas", index.search(root, "Bananas")[0].text)

    def test_all_base_glossary_keeps_terms_without_conflicting_substitutions(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / PACK_FILENAME
            source.write_text(pack("Orchard guide.", "FRUIT_A", "fruit"), encoding="utf-8")
            first = import_summary(base / "runtime", source, name="Atlas")
            source.write_text(pack("Spaceship guide.", "FRUIT_B", "fruit"), encoding="utf-8")
            second = import_summary(base / "runtime", source, name="Orbit")
            glossary = project_asr_glossary((first, second), documents_only=True)
            self.assertEqual(set(glossary.hints), {"FRUIT_A", "FRUIT_B"})
            self.assertEqual(glossary.normalize("fruit"), "fruit")
            self.assertEqual(project_asr_glossary(first, documents_only=True).normalize("fruit"), "FRUIT_A")

    def test_named_base_keeps_same_named_documents_and_updates_only_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            sources = []
            for name, fact in (("one", "Oranges grow in the northern orchard."),
                               ("two", "Bananas grow in the southern orchard.")):
                folder = base / name
                folder.mkdir()
                source = folder / PACK_FILENAME
                source.write_text("# Orchard\n\n" + fact, encoding="utf-8")
                sources.append(source)
            root = import_summary(base / "runtime", sources[0], name="Fruit project")
            self.assertEqual(import_summary(base / "runtime", sources[1], target=root), root)
            projects = discover_projects(documents_only=True, managed=base / "runtime/knowledge")
            self.assertEqual([(p.name, p.root) for p in projects], [("Fruit project", root)])
            index = Knowledge(base / "index.sqlite", documents_only=True)
            self.assertEqual(index.refresh(root)[0], 2)
            self.assertIn("Oranges", index.search(root, "Oranges")[0].text)
            self.assertIn("Bananas", index.search(root, "Bananas")[0].text)
            sources[0].write_text("# Revised document\n\nPears grow in the eastern orchard.", encoding="utf-8")
            import_summary(base / "runtime", sources[0], target=root)
            self.assertEqual(index.refresh(root)[0], 2)
            self.assertFalse(index.search(root, "Oranges"))
            self.assertIn("Pears", index.search(root, "Pears")[0].text)
            self.assertIn("Bananas", index.search(root, "Bananas")[0].text)
            self.assertEqual(discover_projects(documents_only=True, managed=base / "runtime/knowledge")[0].name,
                             "Fruit project")

    def test_invalid_named_import_does_not_create_or_change_a_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "notes.md"
            source.write_text("api_key = example-secret", encoding="utf-8")
            with self.assertRaises(ValueError):
                import_summary(base / "runtime", source, name="Atlas")
            self.assertFalse((base / "runtime/knowledge").exists())

    def test_summary_import_creates_named_base_and_updates_same_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / PACK_FILENAME
            source.write_text("# Atlas\n\nThe retry delay is 5 seconds.\n", encoding="utf-8")
            runtime = base / "runtime"
            root = import_summary(runtime, source)
            projects = discover_projects(documents_only=True, managed=runtime / "knowledge")
            self.assertEqual([(p.name, p.root) for p in projects], [("Atlas", root)])
            index = Knowledge(runtime / "index.sqlite", documents_only=True)
            self.assertEqual(index.refresh(root)[0], 1)
            self.assertIn("5 seconds", index.search(root, "retry delay")[0].text)
            source.write_text("# Atlas\n\nThe retry delay is 9 seconds.\n", encoding="utf-8")
            self.assertEqual(import_summary(runtime, source), root)
            self.assertEqual(index.refresh(root)[0], 1)
            self.assertIn("9 seconds", index.search(root, "retry delay")[0].text)
            self.assertEqual(len(list((runtime / "knowledge").iterdir())), 1)

    def test_same_filename_in_different_projects_has_separate_knowledge(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runtime = base / "runtime"
            roots = []
            for name in ("Atlas", "Orbit"):
                folder = base / name
                folder.mkdir()
                source = folder / PACK_FILENAME
                source.write_text(f"# {name}\n\nThe spacecraft is {name}.", encoding="utf-8")
                roots.append(import_summary(runtime, source))
            self.assertNotEqual(*roots)
            projects = discover_projects(documents_only=True, managed=runtime / "knowledge")
            self.assertEqual([p.name for p in projects], ["Atlas", "Orbit"])
            source.write_text("api_key = example-secret", encoding="utf-8")
            with self.assertRaises(ValueError):
                import_summary(runtime, source)
            stored, = (roots[1] / ".copilot-knowledge" / "imports").iterdir()
            self.assertIn("spacecraft is Orbit", stored.read_text(encoding="utf-8"))

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
