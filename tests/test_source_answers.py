import json
import tempfile
import unittest
from pathlib import Path

from copilot.knowledge import Knowledge
from copilot.knowledge_pack import import_summary
from copilot.suggest import Advisor


class SourceAnswerTest(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.folder = Path(scratch.name)
        path = self.folder / "runbook.md"
        self.first = "The Nimbus handover is governed by policy Mallow."
        self.second = "Under the Mallow policy, authority belongs to the dispatch lead."
        path.write_text(
            "# Runbook\n## Nimbus handover\n" + self.first + "\n\n"
            + "\n".join(f"Procedure note {n}." for n in range(11))
            + "\nThe authorization details are recorded separately.\n"
            + "\n\n## Mallow policy\n" + self.second + "\n",
            encoding="utf-8",
        )
        self.root = import_summary(self.folder / "library", path)
        self.index = Knowledge(self.folder / "index.sqlite", documents_only=True)
        self.index.refresh(self.root)

    def test_opens_section_and_searches_for_missing_fact(self):
        calls = []
        first, second = self.first, self.second

        class Brain:
            model = "test"

            def generate(self, payload, cancelled):
                request = json.loads(payload["messages"][-1]["content"])
                calls.append(request)
                if len(calls) == 1:
                    assert any("recorded separately" in s["text"] for s in request["sources"])
                    assert not any(second in s["text"] for s in request["sources"])
                    return {"claims": [], "follow_up": ["Mallow policy"], "missing": "Who controls it?"}
                if len(calls) == 2:
                    ids = [next(s["id"] for s in request["sources"] if sentence in s["text"])
                           for sentence in (first, second)]
                    return {"claims": [{"text": "The dispatch lead controls the handover.", "sources": ids}],
                            "follow_up": [], "missing": ""}
                return {"supported": [1], "complete": True}

        card = Advisor(self.index, Brain(), requested=True)("Who controls Nimbus handover?", [], self.root)
        self.assertEqual(len(calls), 3)
        self.assertIn("dispatch lead controls", card.options[0][0])
        self.assertEqual(len(card.sources), 2)
        for source in card.sources:
            lines = source.path.read_text(encoding="utf-8-sig").splitlines()
            self.assertEqual(source.text, "\n".join(lines[source.line - 1:source.line - 1 + len(source.text.splitlines())]))

    def test_rejects_unconfirmed_claim(self):
        class Brain:
            model = "test"

            def generate(self, payload, cancelled):
                if "supported" in payload["format"]["properties"]:
                    return {"supported": [], "complete": False}
                return {"claims": [{"text": "Nimbus handover takes 60 days.", "sources": [1]}],
                        "follow_up": [], "missing": ""}

        card = Advisor(self.index, Brain(), requested=True)("How long is Nimbus handover?", [], self.root)
        self.assertEqual(card.label, "Нет ответа в базе")
        self.assertFalse(card.sources)

    def test_traces_request_without_question_or_source_text(self):
        class Brain:
            model = "test"

            def generate(self, payload, cancelled):
                if "supported" in payload["format"]["properties"]:
                    return {"supported": [], "complete": False}
                if "claims" not in payload["format"]["properties"]:
                    return {"follow_up": []}
                return {"claims": [{"text": "Private claim", "sources": [1]}],
                        "follow_up": [], "missing": ""}

        question = "Who controls Nimbus handover?"
        advisor = Advisor(self.index, Brain(), requested=True)
        with self.assertLogs("call_copilot.answer", level="INFO") as captured:
            for _ in range(2):
                advisor(question, [], self.root)
        records = [json.loads(record.getMessage()) for record in captured.records]
        ids = {record["request_id"] for record in records}
        self.assertEqual(len(ids), 2)
        for request_id in ids:
            trace = [record for record in records if record["request_id"] == request_id]
            self.assertEqual(trace[0]["stage"], "start")
            self.assertEqual(trace[-1]["outcome"], "review_rejected")
            indexed = next(record for record in trace if record["stage"] == "search")["sources"]
            draft = next(record for record in trace if record["stage"] == "draft_input")["sources"]
            review = next(record for record in trace if record["stage"] == "review_input")["sources"]
            self.assertEqual(indexed[0]["file_id"], draft[0]["file_id"])
            self.assertEqual(review, [draft[0]])
            self.assertGreaterEqual(draft[0]["end"], indexed[0]["end"])
        log = "\n".join(captured.output)
        for private in (question, self.first, "Private claim", "runbook.md", str(self.root)):
            self.assertNotIn(private, log)

    def test_refuses_to_open_outdated_index_hit(self):
        hit = self.index.search(self.root, "Nimbus")[0]
        with hit.path.open("a", encoding="utf-8") as stream:
            stream.write("\nPrivate draft not yet indexed.")
        self.assertIsNone(self.index.open_source(self.root, hit, {}))

    def test_rejected_claim_prevents_a_complete_card(self):
        class Brain:
            model = "test"

            def generate(self, payload, cancelled):
                schema = payload["format"]["properties"]
                if "supported" in schema:
                    return {"supported": [1], "complete": True}
                if "claims" not in schema:
                    return {"follow_up": []}
                return {"claims": [
                    {"text": "Mallow governs Nimbus handover.", "sources": [1]},
                    {"text": "Handover takes 60 days.", "sources": [1]},
                ], "missing": "", "follow_up": []}

        card = Advisor(self.index, Brain(), requested=True)(
            "What policy governs Nimbus handover, and how long does it take?", [], self.root)
        self.assertEqual(card.label, "Частичный ответ из базы")
        self.assertIn("Mallow", card.options[0][0])
        self.assertNotIn("60 days", card.options[0][0])

    def test_project_status_uses_observation_date_and_copies_numbers(self):
        for name, body in {
            "recent-export.md": "# Статус Nimbus на 3 ноября 2026 года\n\nЛокальная проверка прошла, 362 теста.",
            "saved-check.md": "# Статус Nimbus на 6 ноября 2026 года\n\n"
            "Локальная проверка прошла, 1 362 теста. "
            "Приёмка на стенде остаётся открытой. Для диагностики нужны логи.",
        }.items():
            file = self.folder / name
            file.write_text(body, encoding="utf-8")
            import_summary(self.folder / "library", file, target=self.root)
        self.index.refresh(self.root)

        class Brain:
            model = "test"

            def generate(self, payload, cancelled):
                request = json.loads(payload["messages"][-1]["content"])
                excerpts = request["excerpts"]
                assert all("362 теста" not in item["text"] or "1 362" in item["text"]
                           for item in excerpts)
                return {
                    "confirmed": [next(item["id"] for item in excerpts if "1 362" in item["text"])],
                    "open": [next(item["id"] for item in excerpts if "остаётся" in item["text"])],
                    "next": [next(item["id"] for item in excerpts if "нужны логи" in item["text"])],
                }

        card = Advisor(self.index, Brain(), requested=True)("Какой статус по Nimbus?", [], self.root)
        answer = card.options[0][0]
        self.assertEqual(card.label, "Ответ из базы")
        self.assertIn("1 362 теста", answer)
        self.assertIn("остаётся открытой", answer)
        self.assertIn("нужны логи", answer)

    def test_status_retry_keeps_original_subject(self):
        search = self.index.search
        queries = []

        def track(scope, query, limit):
            queries.append(query)
            return search(scope, query, limit=limit)

        self.index.search = track

        class Brain:
            model = "test"

            def generate(self, payload, cancelled):
                if "claims" in payload["format"]["properties"]:
                    return {"claims": [], "missing": "", "follow_up": ["unrelated code"]}
                return {"follow_up": []}

        Advisor(self.index, Brain(), requested=True)("Какой статус по Nimbus?", [], self.root)
        self.assertGreaterEqual(len(queries), 2)
        self.assertTrue(all("Nimbus" in query for query in queries))
