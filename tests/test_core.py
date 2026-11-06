import json
import queue
import tempfile
import threading
import unittest
from pathlib import Path


class KnowledgeTest(unittest.TestCase):
    def test_broken_git_metadata_does_not_index_untracked_private_files(self):
        from copilot.knowledge import Knowledge
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo = base / "repo"
            repo.mkdir()
            (repo / "doc.md").write_text("PreservedAuth architecture.", encoding="utf-8")
            index = Knowledge(base / "index.sqlite")
            index.refresh(repo)
            (repo / ".git").mkdir()
            (repo / ".gitignore").write_text("private-notes.md\n", encoding="utf-8")
            (repo / "private-notes.md").write_text("UntrackedHiddenProject", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                index.refresh(repo)
            self.assertFalse(index.search(repo, "UntrackedHiddenProject"))
            self.assertTrue(index.search(repo, "PreservedAuth"))

    def test_codex_registry_returns_local_roots_only(self):
        from copilot.knowledge import discover_projects
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a").mkdir()
            state = root / "state.json"
            state.write_text(json.dumps({
                "local-projects": {"one": {"name": "Atlas", "rootPaths": [str(root / "a")]}},
                "thread-workspace-root-hints": {"other": str(root)}
            }), encoding="utf-8")
            self.assertEqual([(x.name, x.root) for x in discover_projects(state)],
                             [("Atlas", (root / "a").resolve())])

    def test_refresh_updates_deletes_and_scopes_sources(self):
        from copilot.knowledge import Knowledge
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            a, b = base / "a", base / "b"
            a.mkdir()
            b.mkdir()
            doc = a / "auth.md"
            doc.write_text("AtlasAuth refresh policy uses single flight.", encoding="utf-8")
            (b / "auth.md").write_text("AtlasAuth refresh policy uses rotating locks.", encoding="utf-8")
            (a / ".env").write_text("AtlasAuth api_key=outside-source", encoding="utf-8")
            (a / "settings.yaml").write_text("AtlasAuth\napi_key: do-not-index-this-key\n", encoding="utf-8")
            index = Knowledge(base / "index.sqlite")
            index.refresh(a)
            index.refresh(b)
            found = index.search(a, "Atlas Auth refresh policy")
            self.assertTrue(any("single flight" in s.text for s in found))
            self.assertTrue(all(s.path == doc for s in found))
            doc.write_text("AtlasAuth refresh policy now uses token rotation.", encoding="utf-8")
            index.refresh(a)
            self.assertIn("token rotation", index.search(a, "AtlasAuth refresh")[0].text)
            doc.unlink()
            index.refresh(a)
            self.assertEqual(index.search(a, "AtlasAuth"), [])
            self.assertTrue(index.search(b, "AtlasAuth"))


class SpeechTest(unittest.TestCase):
    def test_transcript_chunks_cover_long_speech_once(self):
        from copilot.speech import Endpointer
        gate = Endpointer(pause_ms=420, max_wait_ms=5000, replay_turn=False)
        speech = [i.to_bytes(2, "little") * 320 for i in range(1, 551)]
        silence = bytes(640)
        events = [event for frame in speech if (event := gate.feed(frame, True))]
        events.extend(event for _ in range(21) if (event := gate.feed(silence, False)))
        self.assertEqual([kind for kind, _ in events], ["start", "checkpoint", "checkpoint", "end"])
        self.assertEqual(b"".join(pcm for _, pcm in events[1:]), b"".join(speech) + silence * 21)

    def test_pause_keeps_the_start_of_a_question_after_a_checkpoint(self):
        from copilot.speech import Endpointer
        gate = Endpointer(pause_ms=420, max_wait_ms=5000)
        first = b"\x01\x00" * 320
        rest = b"\x02\x00" * 320
        frames = [first] * 8 + [rest] * 244
        events = [event for frame in frames if (event := gate.feed(frame, True))]
        self.assertEqual([e[0] for e in events], ["start", "checkpoint"])
        silence = bytes(len(first))
        final = [event for _ in range(21) if (event := gate.feed(silence, False))]
        self.assertEqual([e[0] for e in final], ["end"])
        self.assertTrue(final[0][1].startswith(first * 8))

    def test_continuous_speech_emits_a_checkpoint_without_a_pause(self):
        from copilot.speech import Endpointer
        gate = Endpointer(pause_ms=420, max_wait_ms=5000)
        frame = b"\x01\x00" * 320
        events = [event for _ in range(550) if (event := gate.feed(frame, True))]
        self.assertEqual([e[0] for e in events], ["start", "checkpoint", "checkpoint"])
        self.assertTrue(all(len(e[1]) <= 180000 for e in events[1:]))
        silence = bytes(len(frame))
        tail = [event for _ in range(30) if (event := gate.feed(silence, False))]
        self.assertEqual([e[0] for e in tail], ["end"])

    def test_endpoint_requires_voice_and_trailing_silence(self):
        from copilot.speech import Endpointer
        gate = Endpointer(pause_ms=420)
        frame = b"\x01\x00" * 320
        silence = bytes(len(frame))
        self.assertFalse(any(gate.feed(silence, False) for _ in range(30)))
        speech_events = [gate.feed(frame, True) for _ in range(24)]
        self.assertEqual(sum(e is not None and e[0] == "start" for e in speech_events), 1)
        self.assertFalse(any(gate.feed(silence, False) for _ in range(20)))
        event = gate.feed(silence, False)
        self.assertEqual(event[0], "end")
        self.assertIn(frame, event[1])
        self.assertFalse(any(gate.feed(silence, False) for _ in range(30)))


class TopicTest(unittest.TestCase):
    def test_project_speech_glossary_canonicalizes_only_supported_mentions(self):
        from copilot.pipeline import Pipeline

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            glossary = root / ".copilot-knowledge" / ".asr-glossary.json"
            glossary.parent.mkdir()
            glossary.write_text(json.dumps({
                "terms": ["JSM", "ОКЭД"],
                "hotwords": ["JSM"],
                "aliases": [
                    {"term": "JSM", "heard": ["дж е с м", "джсм"]},
                    {"term": "ОКЭД", "heard": ["окет"], "context": r"программ\w*"},
                ],
            }), encoding="utf-8")
            results = queue.Queue()
            prompts = []

            def transcribe(pcm, hotwords):
                prompts.append(hotwords)
                return pcm.decode()

            def record(_token, kind, data):
                if kind in ("transcript", "error"):
                    results.put(data)

            engine = Pipeline(transcribe, None, record, manual=True)
            try:
                cases = [
                    (root, "В Дж.Е.С.М. проверили окет по программе.", "В JSM проверили ОКЭД по программе."),
                    (root, "Купили пакет, а окет и GSM-модем обсудили отдельно.",
                     "Купили пакет, а окет и GSM-модем обсудили отдельно."),
                    (root, "Thank you, смотри джсмокет.", "Thank you, смотри джсмокет."),
                    (root / "other", "В ДжСМ проверили окет по программе.", "В ДжСМ проверили окет по программе."),
                ]
                for project, raw, expected in cases:
                    engine.accept_audio("end", raw.encode(), project, "Kafka")
                    self.assertEqual(results.get(timeout=2), expected)
                self.assertEqual(prompts, ["Kafka, JSM"] * 3 + ["Kafka"])

                glossary.write_text("invalid json", encoding="utf-8")
                engine.accept_audio("end", "ДжСМ".encode(), root, "Kafka")
                self.assertEqual(results.get(timeout=2), "ДжСМ")
                self.assertEqual(prompts[-1], "Kafka")
            finally:
                engine.close()

    def test_manual_request_is_independent_of_queued_speech(self):
        from copilot.pipeline import Pipeline
        observed = queue.Queue()
        asr_started, release_asr = threading.Event(), threading.Event()
        answer_started, release_answer = threading.Event(), threading.Event()
        calls = []
        root = Path("project")

        def transcribe(pcm, glossary):
            if pcm == b"first paragraph":
                asr_started.set()
                release_asr.wait(2)
            return pcm.decode()

        def generate(text, context, selected_root, cancelled, preview):
            calls.append((text, context, selected_root, preview))
            answer_started.set()
            release_answer.wait(2)
            return None if cancelled() else "grounded answer"

        def next_event(kind):
            while True:
                token, event, data = observed.get(timeout=2)
                if event == kind:
                    self.assertTrue(engine.current(token, event))
                    return data

        engine = Pipeline(transcribe, generate, lambda *e: observed.put(e), manual=True)
        try:
            engine.accept_audio("end", b"first paragraph", root)
            self.assertTrue(asr_started.wait(1))
            engine.accept_audio("end", b"second paragraph", root)
            engine.accept_audio("end", b"OK", root)
            release_asr.set()
            self.assertEqual(next_event("transcript"), "first paragraph")
            self.assertEqual(next_event("transcript"), "second paragraph")
            self.assertEqual(next_event("transcript"), "OK")
            self.assertEqual(calls, [])
            self.assertFalse(engine.ask("  ", root))
            self.assertTrue(engine.ask("second paragraph", root))
            self.assertTrue(answer_started.wait(1))
            engine.accept_audio("end", b"third paragraph", root)
            self.assertEqual(next_event("transcript"), "third paragraph")
            release_answer.set()
            self.assertEqual(next_event("card")[:2], ("second paragraph", "grounded answer"))
            self.assertEqual(calls, [("second paragraph", [], root, None)])
        finally:
            release_asr.set()
            release_answer.set()
            engine.close()

    def test_resumed_speech_does_not_cancel_the_last_recognized_turn(self):
        from copilot.pipeline import Pipeline
        observed = queue.Queue()
        started, release = threading.Event(), threading.Event()

        def generate(text, context, root, cancelled, preview):
            started.set()
            release.wait(2)
            return None if cancelled() else "useful note"

        engine = Pipeline(lambda pcm, glossary: pcm.decode(), generate,
                          lambda token, kind, data: observed.put((token, kind, data)))
        try:
            turn = engine.begin()
            engine.finish(turn, b"first question", None)
            self.assertTrue(started.wait(1))
            engine.hearing()
            release.set()
            while True:
                token, kind, data = observed.get(timeout=2)
                if kind == "card":
                    self.assertEqual((token, data[1]), (turn, "useful note"))
                    break
        finally:
            release.set()
            engine.close()

    def test_inflight_generation_cannot_replace_new_topic(self):
        from copilot.pipeline import Pipeline
        observed = queue.Queue()
        started, release = threading.Event(), threading.Event()

        def generate(text, context, root, cancelled, preview):
            if text == "authorization":
                started.set()
                release.wait(2)
                self.assertTrue(cancelled())
                preview("stale preview")
            return text

        engine = Pipeline(lambda pcm, glossary: pcm.decode(), generate,
                          lambda token, kind, data: observed.put((token, kind, data)))
        try:
            old = engine.begin()
            engine.finish(old, b"authorization", None)
            self.assertTrue(started.wait(1))
            new = engine.begin()
            engine.finish(new, b"database pool", None)
            release.set()
            while True:
                token, kind, data = observed.get(timeout=2)
                if kind == "preview":
                    self.assertEqual(token, new)
                if kind == "card":
                    self.assertEqual(token, new)
                    self.assertEqual(data[1], "database pool")
                    break
        finally:
            release.set()
            engine.close()

    def test_new_turn_invalidates_old_card_and_newest_work_wins(self):
        from copilot.pipeline import Latest
        state = Latest()
        first = state.begin()
        self.assertTrue(state.submit(first, "authentication"))
        second = state.begin()
        self.assertFalse(state.is_current(first))
        self.assertFalse(state.submit(first, "outdated"))
        self.assertTrue(state.submit(second, "database pool"))
        self.assertEqual(state.take(timeout=.01), (second, "database pool"))
        self.assertIsNone(state.take(timeout=.01))

    def test_only_explicit_followups_carry_context_forward(self):
        from copilot.pipeline import followup_context
        past = ["Как обновляется токен доступа?"]
        self.assertEqual(followup_context("А если он истёк?", past), past)
        self.assertEqual(followup_context("Почему зависла база данных?", past), [])
        self.assertEqual(followup_context("А теперь про пул базы данных.", past), [])


class SuggestTest(unittest.TestCase):
    def test_manual_answer_uses_only_verified_source_text(self):
        from copilot.knowledge import Source
        from copilot.suggest import Advisor

        root = Path.cwd()
        source = Source(root / "contract.md", 30, "Состояния заявки\nПри отмене вернётся CANCELLED.\nЧерновик сохраняется.")

        class Index:
            def search(self, root, query, limit):
                return [source]

        class Model:
            model = "test"

            def __init__(self, responses):
                self.responses = iter(responses)
                self.calls = []

            def generate(self, payload, cancelled):
                self.calls.append(payload)
                return next(self.responses)

        def ask(*responses, question="Какой статус при отмене?"):
            model = Model(responses)
            return Advisor(Index(), model, requested=True)(question, [], root), model

        span = {"source": 1, "first": 31, "last": 31}
        candidate = {"evidence": [span], "short": "Заявка удаляется без следа."}
        card, model = ask(candidate, {"scope_matches": True, "keep": [1]})
        evidence = "При отмене вернётся CANCELLED."
        self.assertEqual(card.options, ((evidence, [1]),))
        self.assertEqual(card.sources, (Source(source.path, 31, evidence),))
        self.assertIn(evidence, model.calls[1]["messages"][1]["content"])
        self.assertNotIn("удаляется", model.calls[1]["messages"][1]["content"])

        for response in ({"scope_matches": True, "keep": []},
                         {"scope_matches": True, "keep": [True]},
                         {"scope_matches": True, "keep": [2]},
                         {"scope_matches": True, "keep": [1, 1]},
                         {"scope_matches": False, "keep": [1]}):
            with self.subTest(response=response):
                card, _ = ask(candidate, response)
                self.assertFalse(card.sources)
                self.assertEqual(card.label, "Нет ответа в базе")

        for invalid in ({**span, "source": 2}, {**span, "first": 29},
                        {**span, "last": 33}, {**span, "source": True}):
            with self.subTest(span=invalid):
                card, model = ask({"evidence": [invalid]})
                self.assertFalse(card.sources)
                self.assertEqual(len(model.calls), 1)
        card, model = ask(candidate, question="Какой статус при отмене по контракту 2039 года?")
        self.assertFalse(card.sources)
        self.assertEqual(len(model.calls), 1)

    def test_preview_waits_for_complete_text_and_valid_citations(self):
        from copilot.suggest import _preview_options
        self.assertEqual(_preview_options('{"short":"Ответ","sources":[1', 2), [])
        self.assertEqual(_preview_options('{"short":"Ответ","sources":[9],', 2), [])
        self.assertEqual(
            _preview_options('{"short":"Ответ со скобками [1]","sources":[2],"spoken":"', 2),
            [("Ответ со скобками [1]", [2])],
        )

    def test_narration_with_no_project_sources_still_has_a_visible_note(self):
        from copilot.suggest import Advisor

        class NoSuggestion:
            model = "test"
            def generate(self, payload, cancelled):
                return {"options": [], "clarification": ""}

        text = "This tutorial explains why the cache is useful."
        card = Advisor(None, NoSuggestion())(text, [], None)
        self.assertTrue(card.options)
        self.assertEqual(card.options[0][0], text)
        self.assertFalse(card.sources)

    def test_rejects_unknown_source_ids(self):
        from copilot.suggest import validate_options
        data = {"options": [
            {"text": "Fake project fact.", "sources": [99]},
            {"text": "Real project fact.", "sources": [1]},
        ]}
        self.assertEqual(validate_options(data, 1), [("Real project fact.", [1])])
