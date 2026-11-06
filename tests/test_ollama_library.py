import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from copilot.brains import create_brain, local_ollama_url
from copilot.ollama_library import validate_ollama_model


class OllamaHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        response = {
            "/api/status": {"cloud": {"disabled": self.server.cloud_disabled}},
            "/api/tags": {"models": [
                {"name": "a-local:4b", "size": 1000,
                 "details": {"quantization_level": "Q4_K_M", "parameter_size": "4B"}},
                {"name": "cloud-alias:latest", "remote_host": "https://ollama.com"},
            ]},
            "/api/ps": {"models": self.server.running},
        }[self.path]
        self.reply(response)

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.requests.append((self.path, data))
        if self.path == "/api/pull":
            self.reply({"status": "pulling layer", "completed": 10, "total": 100}, {"status": "success"})
        elif self.path == "/api/chat":
            self.reply({"message": {"content": "{}"}, "done": True})
        elif self.path == "/api/generate":
            self.server.running = [item for item in self.server.running if item["name"] != data["model"]]
            self.reply({"done": True, "done_reason": "unload"})

    def reply(self, *events):
        self.send_response(200)
        self.end_headers()
        for event in events:
            self.wfile.write((json.dumps(event) + "\n").encode())


class OllamaLibraryTest(unittest.TestCase):
    def setUp(self):
        server = self.server = ThreadingHTTPServer(("127.0.0.1", 0), OllamaHandler)
        server.cloud_disabled = True
        server.requests = []
        server.running = [{"name": "a-local:4b", "size": 1500, "size_vram": 700}]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        runtime = tempfile.TemporaryDirectory()
        self.addCleanup(runtime.cleanup)
        self.address = f"http://127.0.0.1:{server.server_port}"
        self.brain = create_brain(runtime.name, {
            "llm_provider": "ollama_local", "ollama_model": "a-local:4b", "ollama_url": self.address,
        })
        self.addCleanup(self.brain.close)

    def test_installed_metadata_running_vram_and_download_use_chosen_daemon(self):
        self.assertEqual(local_ollama_url(self.address + "/v1"), self.address)
        self.assertEqual(self.brain.models(), ["a-local:4b"])
        model, = self.brain.model_details()
        self.assertEqual((model.name, model.size, model.quantization), ("a-local:4b", 1000, "Q4_K_M"))
        running, = self.brain.running_models()
        self.assertEqual((running.size, running.size_vram), (1500, 700))
        progress = []
        self.assertTrue(self.brain.pull("some-user/some-model:8b",
                                       lambda *event: progress.append(event)))
        self.assertEqual(progress, [("pulling layer", 10, 100), ("success", None, None)])
        self.assertEqual(self.server.requests, [
            ("/api/pull", {"model": "some-user/some-model:8b", "stream": True}),
        ])

    def test_cloud_enabled_server_refuses_to_send_prompt_or_download(self):
        self.server.cloud_disabled = False
        with self.assertRaisesRegex(RuntimeError, "OLLAMA_NO_CLOUD"):
            self.brain.generate({"messages": [{"role": "user", "content": "local text"}]}, lambda: False)
        with self.assertRaisesRegex(RuntimeError, "OLLAMA_NO_CLOUD"):
            self.brain.pull("a-local:4b")
        self.assertEqual(self.server.requests, [])

    def test_unload_releases_only_the_requested_model_and_keeps_files_installed(self):
        self.server.running.append({"name": "other:latest", "size_vram": 300})
        self.brain.unload_model("a-local:4b")
        self.assertEqual([model.name for model in self.brain.running_models()], ["other:latest"])
        self.assertEqual(self.brain.models(), ["a-local:4b"])
        self.assertEqual(self.server.requests, [
            ("/api/generate", {"model": "a-local:4b", "stream": False, "keep_alive": 0}),
        ])

    def test_invalid_model_and_cancel_never_download(self):
        self.assertEqual(validate_ollama_model(" registry.ollama.ai/library/_model:8b "),
                         "registry.ollama.ai/library/_model:8b")
        for model in ("name:cloud", "name:8b-cloud", "name:8b:cloud",
                      "https://example.com/name", "../outside:latest", "name\nnext",
                      "registry.ollama.ai/name", "example.com/user/name"):
            with self.subTest(model=model), self.assertRaises(ValueError):
                validate_ollama_model(model)
        self.assertFalse(self.brain.pull("a-local:4b", cancelled=lambda: True))
        self.assertEqual(self.server.requests, [])

    def test_pull_can_stop_after_the_first_progress_event(self):
        progress = []
        self.assertFalse(self.brain.pull("a-local:4b", lambda *event: progress.append(event),
                                         cancelled=lambda: bool(progress)))
        self.assertEqual(progress, [("pulling layer", 10, 100)])


if __name__ == "__main__":
    unittest.main()
