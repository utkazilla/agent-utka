import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from copilot.knowledge import Knowledge
from copilot.retrieval import LocalSearch, SearchUnavailable, local_search_url


class LocalRetrievalTests(unittest.TestCase):
    def test_browse_reads_only_indexed_passages_in_the_selected_project(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            root, other = parent / "demo", parent / "other"
            root.mkdir()
            other.mkdir()
            (root / "notes.md").write_text("# Demo\nThe token lifetime is 37 minutes.", encoding="utf-8")
            (root / "credentials.md").write_text("Excluded", encoding="utf-8")
            (other / "notes.md").write_text("# Other\nA different project.", encoding="utf-8")
            knowledge = Knowledge(parent / "test.sqlite")
            knowledge.refresh(root)
            knowledge.refresh(other)
            self.assertEqual(knowledge.index_files(root), ["notes.md"])
            passage, = knowledge.index_passages(root, "notes.md")
            self.assertEqual((passage.path, passage.line), (root / "notes.md", 1))
            self.assertIn("37 minutes", passage.text)
            self.assertEqual(knowledge.index_passages(root, "../other/notes.md"), [])

    def test_ranked_references_only_return_indexed_text_in_the_selected_project(self):
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                requests.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
                data = json.dumps({} if self.path == "/invalid" else {"hits": [
                    {"path": "../other/notes.md", "line": 1},
                    {"path": "notes.md", "line": 999},
                    {"path": "notes.md", "line": 2, "text": "Fabricated evidence"},
                    {"path": "notes.md", "line": 2},
                ]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        with tempfile.TemporaryDirectory() as directory, ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
            worker = threading.Thread(target=server.serve_forever)
            worker.start()
            try:
                parent = Path(directory).resolve()
                project, other = parent / "demo", parent / "other"
                project.mkdir()
                other.mkdir()
                (project / "notes.md").write_text("# Guide\nRefresh tokens expire after two hours.", encoding="utf-8")
                (other / "notes.md").write_text("Private text from a different project.", encoding="utf-8")
                search = LocalSearch(f"http://127.0.0.1:{server.server_port}/retrieve")
                knowledge = Knowledge(parent / "test.sqlite", retriever=search)
                knowledge.refresh(project)
                knowledge.refresh(other)
                hits = knowledge.search(project, "When do refresh tokens expire?")
                self.assertEqual(len(hits), 1)
                self.assertEqual(hits[0].path, project / "notes.md")
                self.assertIn("Refresh tokens expire after two hours.", hits[0].text)
                self.assertNotIn("Fabricated evidence", hits[0].text)
                self.assertEqual(requests, [("/retrieve", {"project": str(project.resolve()),
                                                           "query": "When do refresh tokens expire?",
                                                           "limit": 4})])
                unavailable = LocalSearch(f"http://127.0.0.1:{server.server_port}/invalid")
                with self.assertRaises(SearchUnavailable):
                    unavailable.references(project, "When do refresh tokens expire?", 4)
            finally:
                server.shutdown()
                worker.join()

    def test_endpoint_requires_uncredentialed_loopback_http(self):
        for url in ("https://127.0.0.1/search", "http://example.com/search",
                    "http://user@127.0.0.1/search", "http://127.0.0.1/search?api=key"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                local_search_url(url)
        self.assertEqual(local_search_url("http://[::1]:8090/search"), "http://[::1]:8090/search")
