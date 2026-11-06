import unittest
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

from copilot.catalog import CatalogError, CatalogModel, CatalogVariant, model_variants, search_models


class CatalogTests(unittest.TestCase):
    @patch("copilot.catalog._fetch")
    def test_search_returns_local_chat_families_and_encodes_query(self, fetch):
        fetch.return_value = """
            <main id="searchresults">
              <a href="/library/chat"><h2>Chat</h2><span>tools</span><p>Chat &amp; code.</p></a>
              <a href="/library/emb"><h2>Emb</h2><span>embedding</span><p>Vectors.</p></a>
              <a href="/library/tts"><h2>TTS</h2><p>A text-to-speech family.</p></a>
              <a href="/library/remote"><h2>Remote</h2><span>cloud</span></a>
              <a href="/library/chat:4b"><h2>Not a family.</h2></a>
              <a href="https://other.example/library/other"><h2>External.</h2></a>
            </main>
        """
        self.assertEqual(search_models(" chat & code "), [CatalogModel("chat", "Chat & code.")])
        path = urlsplit(fetch.call_args.args[0])
        self.assertEqual(path.path, "/search")
        self.assertEqual(parse_qs(path.query)["q"], ["chat & code"])
        self.assertEqual(parse_qs(path.query)["c"], ["local"])

    @patch("copilot.catalog._fetch")
    def test_search_distinguishes_empty_results_and_unexpected_markup(self, fetch):
        fetch.return_value = '<main id="searchresults"><p>No models found.</p></main>'
        self.assertEqual(search_models("no such model"), [])
        fetch.return_value = "<html><p>Unexpected Ollama page</p></html>"
        with self.assertRaises(CatalogError):
            search_models()

    @patch("copilot.catalog._fetch")
    def test_variants_parse_decimal_sizes_and_exclude_cloud_and_mlx(self, fetch):
        fetch.return_value = """
            <a href="/library/chat:4b"><span>chat:4b</span> • 3.3GB - 4.0GB • Text, Image input</a>
            <a href="/library/chat:4b">chat:4b</a>
            <a href="/library/chat:1b"><span>chat:1b</span> • 645MB • Text input</a>
            <a href="/library/chat:9b-cloud">chat:9b-cloud • 9GB</a>
            <a href="/library/chat:latest"><span>cloud</span> • 9GB</a>
            <a href="/library/chat:1b-mxfp8"><span>MLX</span> • 1.0GB</a>
            <a href="/library/chat:audio">chat:audio • 1.0GB • Audio input</a>
            <a href="/library/other:1b">other:1b • 1.0GB</a>
        """
        self.assertEqual(model_variants("chat"), [
            CatalogVariant("chat:4b", "3.3 GB - 4.0 GB", 4_000_000_000),
            CatalogVariant("chat:1b", "645 MB", 645_000_000),
        ])
        fetch.assert_called_once_with("/library/chat/tags")

    @patch("copilot.catalog.urlopen", side_effect=URLError("unavailable"))
    def test_network_failure_is_a_catalog_error(self, _open):
        with self.assertRaises(CatalogError):
            search_models()
