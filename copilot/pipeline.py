import re
import threading
import time
from collections import deque

from .asr_glossary import project_asr_glossary
from .retrieval import SearchUnavailable


class Latest:
    """An epoch invalidates pending and running work."""
    def __init__(self, *, fifo=False):
        self._condition = threading.Condition()
        self._epoch = 0
        self._pending = deque()
        self._fifo = fifo
        self._closed = False

    def begin(self):
        with self._condition:
            self._epoch += 1
            self._pending.clear()
            return self._epoch

    def is_current(self, epoch):
        with self._condition:
            return not self._closed and epoch == self._epoch

    def epoch(self):
        with self._condition:
            return self._epoch

    def submit(self, epoch, item):
        with self._condition:
            if self._closed or epoch != self._epoch:
                return False
            if not self._fifo:
                self._pending.clear()
            self._pending.append((epoch, item))
            self._condition.notify()
            return True

    def take(self, timeout=None):
        with self._condition:
            self._condition.wait_for(lambda: self._pending or self._closed, timeout)
            return self._pending.popleft() if self._pending else None

    def close(self):
        with self._condition:
            self._closed = True
            self._pending.clear()
            self._condition.notify_all()


FOLLOWUP = re.compile(
    r"^(?:а\s+)?(?:если\s+(?:он[аи]?|это|там|они|его|её)\b|"
    r"(?:как|где|почему|зачем)\s+(?:это|он[аи]?|оно|они|его|её|там)\b|"
    r"а\s+(?:дальше|потом|теперь)\s*[?.!]*$)|"
    r"^(?:(?:and\s+)?(?:what|how)\s+if\s+(?:it|they|that)\b|"
    r"(?:why|how|where)\s+(?:does|did|is|can)\s+(?:it|that|they)\b)", re.I)


def followup_context(text, history):
    return list(history[-2:]) if FOLLOWUP.search(text.strip()) else []


class Pipeline:
    def __init__(self, transcribe, suggest, on_event, *, manual=False):
        self.manual = manual
        self.asr = Latest(fifo=manual)
        self.cards = Latest()
        self.on_event = on_event
        self.transcribe = transcribe
        self.suggest = suggest
        self.stopping = threading.Event()
        self.guard = threading.Lock()
        self.history = []
        for worker in (self._speech, self._advice):
            threading.Thread(target=worker, daemon=True).start()

    def begin(self, *, reset_history=False, clear=True):
        with self.guard:
            token = self.asr.begin()
            self.cards.begin()
            if reset_history:
                self.history.clear()
        if clear:
            self.on_event(token, "clear", None)
        return token

    def hearing(self):
        self._event(self.asr.epoch(), "hearing", None)

    def accept_audio(self, kind, pcm, root, glossary=""):
        if kind == "start":
            self.hearing()
        elif kind in ("checkpoint", "end"):
            token = self.asr.epoch() if self.manual else self.begin(clear=False)
            self.finish(token, pcm, root, glossary)
        elif kind == "empty":
            self._event(self.asr.epoch(), "idle", None)

    def finish(self, token, pcm, root, glossary=""):
        self.asr.submit(token, (pcm, root, glossary, time.perf_counter()))

    def ask(self, text, root):
        text = text.strip()
        if not self.manual or not text or root is None:
            return False
        return self.cards.submit(self.cards.begin(), (text, [], root, time.perf_counter()))

    def cancel_answer(self):
        self.cards.begin()

    def current(self, token, kind=None):
        queue = self.cards if self.manual and kind in ("card", "answer_error", "search_error") else self.asr
        return queue.is_current(token)

    def _event(self, token, kind, payload):
        if self.current(token, kind):
            self.on_event(token, kind, payload)

    def _speech(self):
        while not self.stopping.is_set():
            item = self.asr.take()
            if item is None:
                continue
            token, (pcm, root, glossary, ended) = item
            try:
                self._event(token, "asr", None)
                profile = project_asr_glossary(root)
                text = profile.normalize(self.transcribe(pcm, profile.hotwords(glossary)))
                with self.guard:
                    if not self.current(token):
                        continue
                    if not text.strip() or (not self.manual and len(text.strip()) < 3):
                        self._event(token, "idle", None)
                        continue
                    if self.manual:
                        self._event(token, "transcript", text)
                        continue
                    context = followup_context(text, self.history)
                    self.history = (context + [text])[-2:]
                    self._event(token, "transcript", text)
                    self.cards.submit(token, (text, context, root, ended))
            except Exception as error:
                self._event(token, "error", f"Распознавание: {error}")

    def _advice(self):
        while not self.stopping.is_set():
            item = self.cards.take()
            if item is None:
                continue
            token, (text, context, root, ended) = item
            try:
                def preview(card):
                    self._event(token, "preview", (text, card, time.perf_counter() - ended))

                card = self.suggest(text, context, root, lambda: not self.cards.is_current(token),
                                    None if self.manual else preview)
                self._event(token, "card", (text, card, time.perf_counter() - ended))
            except SearchUnavailable:
                self._event(token, "search_error" if self.manual else "error",
                            "Локальный API поиска недоступен. Проверь адрес в настройках.")
            except Exception as error:
                self._event(token, "answer_error" if self.manual else "error", f"Подсказка: {error}")

    def close(self):
        self.stopping.set()
        self.asr.close()
        self.cards.close()
