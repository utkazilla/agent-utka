import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import Mock, patch

from copilot.asr_glossary import project_asr_glossary
from copilot.app import Overlay
from copilot.brains import LocalChatCompletions, create_brain, local_api_url
from copilot.configuration import DEFAULTS, index_path, load_settings, save_settings
from copilot.knowledge import Knowledge, discover_projects
from copilot.knowledge_pack import create_workspace, import_documents
from copilot.suggest import Advisor


class ConfigurationTest(unittest.TestCase):
    def test_app_knowledge_uses_imports_without_reading_codex_projects_or_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            raw = base / "source"
            raw.mkdir()
            (raw / "README.md").write_text("Private original source", encoding="utf-8")
            registry = base / "codex.json"
            registry.write_text(json.dumps({"local-projects": {
                "example": {"rootPaths": [str(raw)]},
            }}), encoding="utf-8")
            root = create_workspace(base / "selected")
            (root / ".git").mkdir()
            (root / "README.md").write_text("Unimported glossary and text", encoding="utf-8")
            doc = base / "export.md"
            doc.write_text("The imported test spacecraft is named Atlas.", encoding="utf-8")
            imported, = import_documents(root, [doc])
            with patch("copilot.knowledge._repo_files", side_effect=AssertionError("Git must stay untouched")):
                workspaces = discover_projects(registry, extra=[str(root), str(raw)], documents_only=True)
                self.assertEqual([project.root for project in workspaces], [root])
                index = Knowledge(base / "documents.sqlite", documents_only=True)
                self.assertEqual(index.refresh(root)[0], 1)
                self.assertEqual(index.search(root, "test spacecraft")[0].path, imported)
                self.assertEqual(index.search(root, "unimported glossary"), [])

    def test_switch_settings_applies_to_current_pipeline_and_preserves_pause(self):
        overlay = Overlay.__new__(Overlay)
        overlay.settings = dict(DEFAULTS)
        overlay.llm, overlay.index, overlay.pipeline, overlay.speech_session = (Mock() for _ in range(4))
        overlay.live, overlay.scan = threading.Event(), threading.Event()
        overlay.capture_lock, overlay.capture_reset = threading.Lock(), threading.Event()
        overlay.closed, overlay.ui = threading.Event(), Mock()
        overlay.indexed_count = 2
        old_brain, old_capture = overlay.llm, overlay.capture_reset
        new_brain, new_index = Mock(), Mock()
        with (patch("copilot.app.save_settings") as save, patch("copilot.app.create_brain", return_value=new_brain),
              patch("copilot.app.Knowledge", return_value=new_index), patch("copilot.app.threading.Thread") as thread,
              patch.object(overlay, "_set_copy", create=True)):
            overlay.index_status = Mock()
            overlay.status = Mock()
            overlay.answer_status = Mock()
            changes = {"ollama": "new:4b", "qwen_model": "1.7b-int8", "rag_directory": "new"}
            overlay.apply_settings(changes)
            save.assert_called_once_with(changes)
            self.assertEqual(overlay.settings["qwen_model"], "1.7b-int8")
            self.assertIs(overlay.llm, new_brain)
            self.assertIs(overlay.index, new_index)
            self.assertIsNone(overlay.indexed_count)
            self.assertTrue(overlay.scan.is_set())
            self.assertTrue(old_capture.is_set())
            self.assertFalse(overlay.live.is_set())
            overlay.speech_session.reconfigure.assert_called_once()
            overlay.pipeline.cancel_speech.assert_called_once()
            advisor = overlay.pipeline.set_advisor.call_args.args[0]
            self.assertIs(advisor.index, new_index)
            self.assertIs(advisor.ollama, new_brain)
            for call in thread.call_args_list:
                call.kwargs["target"](*call.kwargs.get("args", ()))
            old_brain.close.assert_called_once()
            new_brain.warm.assert_called_once()

    def test_interface_language_persists_independently_of_speech_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            save_settings({"language": "ru", "stt_engine": "whisper"}, path)

            for locale in ("en", "es", "ru"):
                with self.subTest(locale=locale):
                    save_settings({"ui_language": locale}, path)
                    settings = load_settings(path)
                    self.assertEqual(settings.get("ui_language"), locale)
                    self.assertEqual(settings["language"], "ru")
                    self.assertEqual(settings["stt_engine"], "whisper")

    def test_legacy_and_invalid_interface_languages_use_russian(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            self.assertEqual(load_settings(path).get("ui_language"), "ru")

            for values in ({"language": "es"}, {"ui_language": "de"}, {"ui_language": ["en"]}):
                with self.subTest(values=values):
                    path.write_text(json.dumps(values), encoding="utf-8")
                    self.assertEqual(load_settings(path).get("ui_language"), "ru")

    def test_import_to_new_base_and_answer_using_configured_local_server(self):
        requests = []

        class Server(BaseHTTPRequestHandler):
            def reply(self, body):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps(body).encode())

            def do_GET(self):
                requests.append(self.path)
                self.reply({"data": [{"id": "test-model"}]})

            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append((self.path, data))
                sources = json.loads(data["messages"][-1]["content"])["sources"]
                quote = next(row["id"] for row in sources if "47" in row["quote"])
                result = {"quotes": [quote]}
                self.reply({"choices": [{"message": {"content": json.dumps(result)}}]})

            def log_message(self, *_args):
                pass

        with tempfile.TemporaryDirectory() as tmp, ThreadingHTTPServer(("127.0.0.1", 0), Server) as server:
            base = Path(tmp)
            project = create_workspace(base / "Atlas")
            source = base / "Atlas.md"
            source.write_text(
                "# Atlas authentication\n\nAtlas access token lifetime is 47 minutes.\n\n"
                '```call-copilot-asr\n{"terms":["AtlasToken"],"aliases":[{"term":"AtlasToken",'
                '"heard":["atlas token"]}]}\n```\n', encoding="utf-8")
            imported, = import_documents(project, [source])
            configuration = base / "settings.json"
            save_settings({"extra_roots": [str(project)], "stt_engine": "whisper"}, configuration)
            save_settings({"llm_provider": "openai_local", "llm_model": "test-model",
                           "llm_url": f"http://127.0.0.1:{server.server_port}",
                           "rag_directory": str(base / "index")}, configuration)
            settings = load_settings(configuration)
            self.assertEqual(settings["stt_engine"], "whisper")
            self.assertEqual(settings["extra_roots"], [str(project)])
            index = Knowledge(index_path(settings))
            self.assertEqual(index.refresh(project)[0], 1)
            self.assertTrue((base / "index" / "call-copilot-knowledge.sqlite").is_file())
            self.assertEqual(project_asr_glossary(project).normalize("atlas token"), "AtlasToken")
            self.assertTrue(all("AtlasToken" not in hit.text for hit in index.search(project, "AtlasToken")))

            threading.Thread(target=server.serve_forever, daemon=True).start()
            brain = create_brain(base, settings)
            try:
                brain.warm()
                card = Advisor(index, brain, requested=True)(
                    "What is the Atlas access token lifetime?", [], project)
            finally:
                brain.close()
                server.shutdown()
            self.assertIn("47 minutes", card.options[0][0])
            self.assertEqual(card.sources[0].path, imported)
            self.assertEqual(requests[0], "/v1/models")
            self.assertEqual([path for path, _ in requests[1:]], ["/v1/chat/completions"])
            self.assertTrue(all(request["model"] == "test-model" for _, request in requests[1:]))

    def test_local_server_disallows_external_addresses_and_redirects(self):
        for url in ("https://example.com/v1", "http://127.0.0.1@example.com/v1",
                    "http://127.0.0.1:1234/v1?next=https://example.com"):
            with self.assertRaises(ValueError):
                local_api_url(url)

        class Redirect(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(307)
                self.send_header("Location", "http://example.com/v1/models")
                self.end_headers()

            def log_message(self, *_args):
                pass

        with ThreadingHTTPServer(("127.0.0.1", 0), Redirect) as server:
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                brain = LocalChatCompletions(f"http://127.0.0.1:{server.server_port}/v1", "test")
                with self.assertRaises(HTTPError) as result:
                    brain.models()
                self.assertEqual(result.exception.code, 307)
            finally:
                server.shutdown()
