import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copilot.knowledge_pack import import_summary
from copilot.ollama_library import LocalOllama
from copilot.semantic_search import MODEL, HybridKnowledge


class SemanticSearchTest(unittest.TestCase):
    def test_recovers_semantic_match_only_in_selected_bases_and_reuses_index(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            model = LocalOllama(folder, "test", external_host="127.0.0.1:11111")
            self.addCleanup(model.close)
            index = HybridKnowledge(folder / "index.sqlite", model)
            self.addCleanup(index.close)
            roots = []
            for name, body in (("moths", "Moths remain dormant during winter."),
                               ("plant", "Daisies stay dormant during winter.")):
                file = folder / (name + ".md")
                file.write_text(body, encoding="utf-8")
                roots.append(import_summary(folder / "runtime", file, name=name))
            batched = []

            def request(_host, endpoint, payload=None, timeout=3):
                if endpoint == "/api/status":
                    return {"cloud": {"disabled": True}}
                if endpoint == "/api/tags":
                    return {"models": [{"name": MODEL, "digest": "mock-digest"}]}
                self.assertEqual(endpoint, "/api/embed")
                if not payload["input"][0].startswith("Instruct:"):
                    batched.extend(payload["input"])
                return {"embeddings": [[0, 1] if "Daisies" in text else [1, 0]
                                       for text in payload["input"]]}

            with patch("copilot.semantic_search._json_request", request), patch(
                    "copilot.ollama_library._json_request", request):
                for root in roots:
                    index.refresh(root)
                index.refresh(roots[0])
                self.assertEqual(len(batched), 2)
                matches = index.search(roots[0], "How do insects hibernate?")
                self.assertEqual([s.path.name for s in matches], ["moths.md"])
                self.assertEqual({s.path.name for s in index.search(tuple(roots), "How do insects hibernate?")},
                                 {"moths.md", "plant.md"})
