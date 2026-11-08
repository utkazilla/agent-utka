import tempfile
import unittest
from pathlib import Path

from copilot.knowledge import Knowledge
from copilot.knowledge_pack import import_summary
from copilot.suggest import Advisor


class DefinitionsTest(unittest.TestCase):
    class QuoteModel:
        model = "test"

        def generate(self, payload, cancelled):
            return {"quotes": [1]}

    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.folder = Path(scratch.name)
        self.index = Knowledge(self.folder / "index.sqlite", documents_only=True)
        self.advisor = Advisor(self.index, self.QuoteModel(), requested=True)

    def add(self, name, text, target=None):
        path = self.folder / (name + ".md")
        path.write_text(text, encoding="utf-8")
        base = import_summary(self.folder / "library", path, name=name if target is None else None, target=target)
        self.index.refresh(base)
        return base

    def test_plain_definition_beats_matching_code_and_keeps_its_citation(self):
        base = self.add("Maple", "# Maple\n\n```java\npublic class LDTClient {}\n```\n" * 30)
        self.add("terms", "# Reference\n\n## Utka glossary\n\n- **LDT** — Maple's delivery tracker.\n", target=base)
        for question in ("что такое LDT?", "What is LDT?", "¿Qué es LDT?"):
            with self.subTest(question=question):
                card = self.advisor(question, [], base)
                self.assertIn("Maple's delivery tracker.", card.options[0][0])
                self.assertEqual(len(card.sources), 1)
                self.assertEqual((card.sources[0].path.name, card.sources[0].line), ("terms.md", 5))

    def test_code_mentions_do_not_become_a_definition(self):
        base = self.add("Maple", "# Maple\n\n```markdown\n## Utka glossary\n"
                               "- **LDT** — fictitious example, not a project fact.\n```\n"
                               "\nLDTClient: see the migration notes.")
        card = self.advisor("что такое LDT?", [], base)
        self.assertEqual(card.label, "Нет ответа в базе")
        self.assertFalse(card.sources)

    def test_existing_definition_heading_still_works(self):
        base = self.add("Maple", "# Maple\n\n## Что такое LDT?\n\n"
                               "**LDT — трекер доставки.** Он показывает статус отправления.\n")
        card = self.advisor("что такое ldt ?", [], base)
        self.assertIn("трекер доставки", card.options[0][0])
        self.assertEqual(card.sources[0].line, 5)

    def test_reimport_replaces_definition_and_base_scope_is_preserved(self):
        first = self.add("Maple", "# Maple\n\n## Utka glossary\n- **LDT** — First definition.\n")
        second = self.add("Orchid", "# Orchid\n\n## Utka glossary\n- **LDT** — Different meaning.\n")
        self.add("Maple", "# Maple\n\n## Utka glossary\n- **LDT** — Revised definition.\n", target=first)
        one = self.advisor("What is LDT?", [], first)
        self.assertIn("Revised definition.", one.options[0][0])
        self.assertNotIn("Different meaning.", one.options[0][0])
        combined = self.advisor("What is LDT?", [], (first, second))
        self.assertEqual(len(combined.options), 2)
        self.assertEqual({s.path.name for s in combined.sources}, {"Maple.md", "Orchid.md"})
        self.assertNotIn("First definition.", " ".join(text for text, _ in combined.options))
