import io
import json
import tempfile
import threading
import unittest
import wave
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError

from copilot.configuration import load_settings, save_settings
from copilot.speech import RATE, create_asr


class SpeechProviderTest(unittest.TestCase):
    def test_configured_local_provider_posts_wav_and_optional_vocabulary(self):
        requests = []

        class SpeechServer(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                headers = f"Content-Type: {self.headers['Content-Type']}\r\n\r\n".encode("ascii")
                parts = BytesParser(policy=policy.default).parsebytes(headers + body)
                requests.append((self.path, {
                    part.get_param("name", header="content-disposition"): part.get_payload(decode=True)
                    for part in parts.iter_parts()
                }))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({"text": "  Hola, AtlasToken.  "}).encode())

            def log_message(self, *_args):
                pass

        with tempfile.TemporaryDirectory() as tmp, ThreadingHTTPServer(("127.0.0.1", 0), SpeechServer) as server:
            settings_file = Path(tmp) / "settings.json"
            save_settings({"stt_engine": "openai_local", "stt_url": f"http://127.0.0.1:{server.server_port}",
                           "stt_model": "speech-fixture", "llm_provider": "ollama"}, settings_file)
            settings = load_settings(settings_file)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                asr = create_asr(tmp, settings["stt_engine"], url=settings["stt_url"], model=settings["stt_model"])
                self.assertEqual(asr(b""), "")
                pcm = b"\x01\x02" * 320
                self.assertEqual(asr(pcm, "AtlasToken, código"), "Hola, AtlasToken.")
                self.assertEqual(asr(pcm), "Hola, AtlasToken.")
            finally:
                server.shutdown()
            self.assertEqual(settings["llm_provider"], "ollama")
            self.assertEqual([path for path, _ in requests], ["/v1/audio/transcriptions"] * 2)
            _, fields = requests[0]
            self.assertEqual(fields["model"], b"speech-fixture")
            self.assertEqual(fields["response_format"], b"json")
            self.assertEqual(fields["prompt"].decode("utf-8"), "AtlasToken, código")
            self.assertNotIn("prompt", requests[1][1])
            with wave.open(io.BytesIO(fields["file"]), "rb") as wav:
                self.assertEqual((wav.getnchannels(), wav.getsampwidth(), wav.getframerate()), (1, 2, RATE))
                self.assertEqual(wav.readframes(wav.getnframes()), pcm)

    def test_transcription_is_not_sent_to_redirect_target(self):
        requests = []

        class Redirect(BaseHTTPRequestHandler):
            def do_POST(self):
                requests.append(self.path)
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(303)
                self.send_header("Location", "/do-not-send-audio")
                self.end_headers()

            def do_GET(self):
                requests.append(self.path)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"text": "Redirect followed."}')

            def log_message(self, *_args):
                pass

        with ThreadingHTTPServer(("127.0.0.1", 0), Redirect) as server:
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                asr = create_asr(".", "openai_local", url=f"http://127.0.0.1:{server.server_port}/v1",
                                 model="speech-fixture")
                with self.assertRaises(HTTPError) as error:
                    asr(b"\0\0")
                self.assertEqual(error.exception.code, 303)
            finally:
                server.shutdown()
        self.assertEqual(requests, ["/v1/audio/transcriptions"])
        with self.assertRaises(ValueError):
            create_asr(".", "openai_local", url="https://example.com/v1", model="speech-fixture")
