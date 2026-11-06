import tempfile
import unittest
from pathlib import Path

from copilot.knowledge import Source
from copilot.suggest import Card, validate_options


class HistoryTest(unittest.TestCase):
    def test_saved_cards_reopen_in_order_with_original_sources_and_project_scope(self):
        from copilot.history import History
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            file = root / "history.sqlite"
            card = Card((("Use the token.", [1]),), (Source(root / "auth.md", 12, "source"),),
                        "Варианты ответа")
            with History(file, limit=3) as history:
                history.add(root / "a", "Old question", card)
                history.add(root / "a", "Question 1", card)
                history.add(root / "b", "Other project", card)
                history.add(root / "a", "Question 2", card)
            with History(file) as history:
                entries = history.recent(root / "a")
                self.assertEqual([e.text for e in entries], ["Question 1", "Question 2"])
                self.assertEqual(entries[0].card, card)
                self.assertEqual([e.text for e in history.recent(root / "b")], ["Other project"])

    def test_three_distinct_sourced_options_are_accepted(self):
        data = {"options": [{"text": f"Choice {number}", "sources": [1]} for number in range(4)]}
        self.assertEqual(len(validate_options(data, 1)), 3)

    def test_sourced_placeholders_are_not_presented_as_replies(self):
        data = {"options": [{"text": "Short answer here.", "sources": [1]},
                            {"text": "Click Sources.", "sources": [1]}]}
        self.assertEqual(validate_options(data, 1), [("Click Sources.", [1])])
