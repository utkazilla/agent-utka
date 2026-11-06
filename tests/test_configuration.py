import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError

from copilot.asr_glossary import project_asr_glossary
from copilot.brains import LocalChatCompletions, create_brain, local_api_url
from copilot.configuration import index_path, load_settings, save_settings
from copilot.knowledge import Knowledge
from copilot.knowledge_pack import create_workspace, import_documents
from copilot.suggest import Advisor


class ConfigurationTest(unittest.TestCase):
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
                if "evidence" in data["response_format"]["json_schema"]["schema"]["properties"]:
                    sources = json.loads(data["messages"][-1]["content"])["sources"]
                    line = next(int(k) for k, v in sources[0]["lines"].items() if "47" in v)
                    result = {"evidence": [{"source": 1, "first": line, "last": line}]}
                else:
                    result = {"scope_matches": True, "keep": [1]}
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
            self.assertEqual([path for path, _ in requests[1:]], ["/v1/chat/completions"] * 2)
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
