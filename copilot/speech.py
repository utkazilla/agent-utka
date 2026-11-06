import io
import json
import os
import threading
import time
import wave
from collections import deque
from contextlib import contextmanager, ExitStack
from pathlib import Path
from sysconfig import get_path
from urllib.request import Request
from uuid import uuid4

from .brains import local_api_opener, local_api_url
from .whisper_install import DEFAULT_WHISPER_MODEL, install_whisper, whisper_cache_path


RATE = 16000
FRAME_MS = 20
FRAME_BYTES = RATE * FRAME_MS // 1000 * 2
QWEN_ASR_BUNDLE = "sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25"
QWEN_ASR_CUDA_BUNDLE = "qwen3-asr-0.6b-hf"
ASR_ENGINES = {
    "qwen": "Qwen3-ASR 0.6B",
    "whisper": "Faster Whisper",
    "openai_local": "OpenAI-совместимый · локальный",
}


class Endpointer:
    """Feed 20 ms of 16 kHz, mono signed PCM, with a speech flag."""
    def __init__(self, pause_ms=420, max_wait_ms=5000, *, replay_turn=True):
        self.end_frames = max(5, pause_ms // FRAME_MS)
        self.max_frames = max(50, max_wait_ms // FRAME_MS)
        self.replay_turn = replay_turn
        self.history = deque(maxlen=8)
        self.frames = None
        self.turn = None
        self.checkpointed = False
        self.voiced = self.quiet = self.run = self.age = 0

    def feed(self, pcm, voice):
        if self.frames is None:
            self.history.append(pcm)
            self.run = self.run + 1 if voice else 0
            if self.run >= 3:
                self.frames = deque(self.history, maxlen=2100)
                # A checkpoint is for a preview; retain up to 20 s for the final question.
                if self.replay_turn:
                    self.turn = deque(self.history, maxlen=20_000 // FRAME_MS)
                self.checkpointed = False
                self.history.clear()
                self.voiced, self.quiet = self.run, 0
                self.age = self.run
                return "start", None
            return None
        self.frames.append(pcm)
        if self.turn is not None:
            self.turn.append(pcm)
        self.age += 1
        self.voiced += int(voice)
        self.quiet = 0 if voice else self.quiet + 1
        if self.quiet >= self.end_frames:
            clip = b"".join(self.turn if self.replay_turn else self.frames)
            enough = self.voiced >= (1 if self.checkpointed else 9)
            self.frames = self.turn = None
            self.run = 0
            return ("end", clip) if enough else ("empty", None)
        if voice and self.age >= self.max_frames:
            clip = b"".join(self.frames)
            if self.replay_turn:
                self.frames = deque(list(self.frames)[-7:], maxlen=2100)
            else:
                self.frames.clear()
                self.voiced = 0
                self.checkpointed = True
            self.age = 0
            return "checkpoint", clip
        return None


def pcm_frames(source, stop):
    pending = bytearray()
    for pcm in source:
        if stop.is_set():
            return
        pending.extend(pcm)
        while len(pending) >= FRAME_BYTES:
            yield bytes(pending[:FRAME_BYTES])
            del pending[:FRAME_BYTES]


def detect(source, stop, pause_ms=420, max_wait_ms=5000, *, replay_turn=True):
    import webrtcvad
    vad = webrtcvad.Vad(2)
    end = Endpointer(pause_ms, max_wait_ms, replay_turn=replay_turn)
    for frame in pcm_frames(source, stop):
        event = end.feed(frame, vad.is_speech(frame, RATE))
        if event:
            yield event


def _resample_chunks(chunks, rate, channels):
    import av
    import numpy as np
    resampler = av.AudioResampler(format="s16", layout="mono", rate=RATE)
    for raw in chunks:
        data = np.frombuffer(raw, dtype=np.int16).reshape((-1, channels))
        mono = (data[:, 0] if channels == 1 else
                data.mean(axis=1).astype(np.int16))
        frame = av.AudioFrame.from_ndarray(mono.reshape(1, -1), format="s16", layout="mono")
        frame.sample_rate = rate
        for out in resampler.resample(frame):
            yield out.to_ndarray().tobytes()


def default_endpoint_id():
    """Read the current Windows multimedia render endpoint, outside PortAudio's cached list."""
    import ctypes as c
    import uuid
    if os.name != "nt":
        return None
    guid = c.c_byte * 16
    clsid = guid.from_buffer_copy(uuid.UUID("BCDE0395-E52F-467C-8E3D-C4579291692E").bytes_le)
    iid = guid.from_buffer_copy(uuid.UUID("A95664D2-9614-4F35-A746-DE8DB63617E6").bytes_le)
    ole = c.windll.ole32
    initialized = ole.CoInitializeEx(None, 0)
    if initialized < 0 and initialized != -2147417850:  # An existing STA is also usable.
        return None

    def method(obj, index, result, *args):
        vtable = c.cast(obj, c.POINTER(c.POINTER(c.c_void_p))).contents
        return c.WINFUNCTYPE(result, c.c_void_p, *args)(vtable[index])

    enumerator, device, name = c.c_void_p(), c.c_void_p(), c.c_void_p()
    try:
        if ole.CoCreateInstance(c.byref(clsid), None, 1, c.byref(iid), c.byref(enumerator)) < 0:
            return None
        endpoint = method(enumerator, 4, c.c_long, c.c_int, c.c_int, c.POINTER(c.c_void_p))
        if endpoint(enumerator, 0, 1, c.byref(device)) < 0:
            return None
        get_id = method(device, 5, c.c_long, c.POINTER(c.c_void_p))
        return c.wstring_at(name) if get_id(device, c.byref(name)) >= 0 else None
    finally:
        if name:
            ole.CoTaskMemFree(name)
        for obj in (device, enumerator):
            if obj:
                method(obj, 2, c.c_ulong)(obj)
        if initialized >= 0:
            ole.CoUninitialize()


def loopback(stop, on_device=lambda name: None):
    import pyaudiowpatch as pa
    endpoint = default_endpoint_id()
    with pa.PyAudio() as api:
        device = api.get_default_wasapi_loopback()
        rate = int(device["defaultSampleRate"])
        channels = int(device["maxInputChannels"])
        count = max(1, rate // 50)
        with api.open(format=pa.paInt16, channels=channels, rate=rate, input=True,
                      input_device_index=device["index"], frames_per_buffer=count) as stream:
            on_device(device["name"])

            def raw():
                check_at = time.monotonic() + 1.5
                while not stop.is_set():
                    if time.monotonic() >= check_at:
                        if default_endpoint_id() != endpoint:
                            raise OSError("Устройство вывода Windows изменилось")
                        check_at = time.monotonic() + 1.5
                    yield stream.read(count, exception_on_overflow=False)

            yield from _resample_chunks(raw(), rate, channels)


class QwenASR:
    name = ASR_ENGINES["qwen"]

    def __init__(self, runtime, on_status=lambda msg: None):
        self.runtime, self.on_status = Path(runtime), on_status
        self.processor = None
        cuda = self.runtime / QWEN_ASR_CUDA_BUNDLE
        if (cuda / "model.safetensors").is_file():
            try:
                import torch

                if torch.cuda.is_available() and torch.cuda.is_bf16_supported():
                    from transformers import AutoModelForMultimodalLM, AutoProcessor

                    on_status(f"Загрузка {self.name} · CUDA…")
                    processor = AutoProcessor.from_pretrained(cuda, local_files_only=True)
                    self.model = AutoModelForMultimodalLM.from_pretrained(
                        cuda, local_files_only=True, dtype=torch.bfloat16,
                        attn_implementation="sdpa",
                    ).to("cuda").eval()
                    self.processor, self.torch = processor, torch
                    self.device = "cuda"
                    on_status(f"{self.name} · CUDA")
                    return
            except (ImportError, OSError, RuntimeError, ValueError):
                on_status("Qwen ASR на GPU недоступен. Загружаю Qwen ASR на CPU…")
        self._load_cpu()

    def _load_cpu(self):
        import sherpa_onnx

        folder = self.runtime / QWEN_ASR_BUNDLE
        conv, encoder, decoder, tokenizer = (folder / name for name in (
            "conv_frontend.onnx", "encoder.int8.onnx", "decoder.int8.onnx", "tokenizer",
        ))
        if not all(path.is_file() for path in (
                conv, encoder, decoder, tokenizer / "vocab.json", tokenizer / "merges.txt")):
            raise FileNotFoundError("Не найдены файлы Qwen ASR. Запусти Setup Agent Utka.ps1.")
        self.on_status(f"Загрузка {self.name} INT8 · CPU…")
        self.model = sherpa_onnx.OfflineRecognizer.from_qwen3_asr(
            str(conv), str(encoder), str(decoder), str(tokenizer),
            num_threads=min(os.cpu_count() or 4, 4),
        )
        self.device = "cpu"
        self.on_status(f"{self.name} INT8 · CPU")

    def __call__(self, pcm, glossary=""):
        import numpy as np

        if not pcm:
            return ""
        audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
        if self.processor is not None:
            try:
                return self._decode_cuda(audio, glossary)
            except self.torch.OutOfMemoryError:
                self.processor = self.model = None
                self.torch.cuda.empty_cache()
                self._load_cpu()

        stream = self.model.create_stream()
        if glossary:
            stream.set_option("hotwords", glossary)
        stream.accept_waveform(RATE, audio)
        self.model.decode_stream(stream)
        return stream.result.text.strip()

    def unload(self):
        self.model = None
        if self.processor is not None:
            self.torch.cuda.empty_cache()

    def _decode_cuda(self, audio, glossary):
        messages = [{"role": "user", "content": [{"type": "audio", "audio": audio}]}]
        if glossary:
            messages.insert(0, {"role": "system", "content": f"Vocabulary: {glossary}"})
        with self.torch.inference_mode():
            inputs = self.processor.apply_chat_template(
                messages, tokenize=True, add_generation_prompt=True, return_dict=True,
            ).to(self.model.device, self.model.dtype)
            output = self.model.generate(**inputs, max_new_tokens=128, do_sample=False)
            parsed = self.processor.decode(output[:, inputs["input_ids"].shape[1]:],
                                           return_format="parsed")[0]
        return parsed["transcription"].strip() if parsed["language"] else ""


class FasterWhisperASR:
    def __init__(self, runtime, on_status=lambda msg: None, *, download=False, variant=DEFAULT_WHISPER_MODEL,
                 device="auto"):
        runtime = Path(runtime)
        self.name = f"{ASR_ENGINES['whisper']} {variant}"
        self.on_status = on_status
        self.preferred_device = device
        self.dll_dirs = [runtime / "vc", *(Path(get_path("purelib")) / "nvidia").glob("*/bin")]
        on_status(f"Проверяю модель {self.name}…")
        if download:
            install_whisper(runtime, variant, device=device)
        folder = whisper_cache_path(runtime, variant)
        if folder is None:
            raise FileNotFoundError(f"Модель {self.name} не скачана. Выбери её в настройках.")
        try:
            with self._native_libraries():
                from ctranslate2 import get_cuda_device_count
                from faster_whisper import WhisperModel
                from faster_whisper.vad import get_vad_model

                get_vad_model()
        except (ImportError, OSError, RuntimeError) as error:
            raise RuntimeError(
                "Faster Whisper недоступен. Установи faster-whisper и Microsoft Visual C++ Runtime."
            ) from error

        self.folder, self.model_class = folder, WhisperModel
        with self._native_libraries():
            try:
                if device != "cpu" and get_cuda_device_count():
                    if os.name == "nt":
                        from ctypes import WinDLL

                        # CTranslate2 resolves cuBLAS by filename on its first inference.
                        self.cuda_libraries = [
                            WinDLL(str((directory / name).resolve()))
                            for name in ("cublasLt64_12.dll", "cublas64_12.dll")
                            for directory in self.dll_dirs if (directory / name).is_file()
                        ]
                    self._load("cuda")
                    return
                if device == "cuda":
                    raise RuntimeError("Faster Whisper не видит доступный GPU NVIDIA.")
            except (OSError, RuntimeError, ValueError):
                if device == "cuda":
                    raise
                on_status("Faster Whisper на GPU недоступен. Загружаю модель на CPU…")
            self._load("cpu")

    @contextmanager
    def _native_libraries(self):
        with ExitStack() as stack:
            if os.name == "nt":
                for folder in self.dll_dirs:
                    if folder.is_dir():
                        stack.enter_context(os.add_dll_directory(str(folder.resolve())))
            yield

    def _load(self, device):
        self.on_status(f"Загрузка {self.name} · {device.upper()}…")
        self.model = self.model_class(str(self.folder), device=device,
                                      compute_type="int8_float16" if device == "cuda" else "int8",
                                      cpu_threads=min(os.cpu_count() or 4, 4), local_files_only=True)
        self.device = device
        self.on_status(f"{self.name} · {device.upper()}")

    def __call__(self, pcm, glossary=""):
        import numpy as np

        if not pcm:
            return ""
        audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
        with self._native_libraries():
            try:
                return self._decode(audio, glossary)
            except (OSError, RuntimeError):
                if self.device != "cuda" or self.preferred_device == "cuda":
                    raise
            self.model = None
            self.on_status("Faster Whisper на GPU недоступен. Загружаю модель на CPU…")
            self._load("cpu")
            return self._decode(audio, glossary)

    def unload(self):
        self.model.model.unload_model()

    def _decode(self, audio, glossary):
        segments, _ = self.model.transcribe(
            audio, beam_size=1, temperature=0, vad_filter=True, condition_on_previous_text=False,
            hotwords=glossary or None,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()


class LocalAudioTranscriptions:
    """Send a voice segment to a local OpenAI-compatible transcription endpoint."""

    device = "local_http"

    def __init__(self, url, model):
        self.url = local_api_url(url) + "/audio/transcriptions"
        if not isinstance(model, str) or not model.strip():
            raise ValueError("Укажи имя модели распознавания.")
        self.name = model.strip()
        self.opener = local_api_opener()

    def __call__(self, pcm, glossary=""):
        if not pcm:
            return ""
        audio = io.BytesIO()
        with wave.open(audio, "wb") as wav:
            wav.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
            wav.writeframes(pcm)

        boundary = uuid4().hex
        fields = {"model": self.name, "response_format": "json"}
        if glossary:
            fields["prompt"] = glossary
        parts = [
            (f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
             f'{value}\r\n').encode("utf-8")
            for name, value in fields.items()
        ]
        parts.extend((
            (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="segment.wav"\r\n'
             "Content-Type: audio/wav\r\n\r\n").encode("ascii"),
            audio.getvalue(),
            f"\r\n--{boundary}--\r\n".encode("ascii"),
        ))
        request = Request(self.url, data=b"".join(parts), headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        })
        max_response = 1_048_576
        with self.opener.open(request, timeout=20) as response:
            data = response.read(max_response + 1)
        try:
            if len(data) > max_response:
                raise ValueError
            text = json.loads(data)["text"]
            if not isinstance(text, str):
                raise ValueError
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Сервер распознавания не вернул текст в ожидаемом формате.") from error
        return text.strip()


class SpeechSession:
    def __init__(self, factory, listening):
        self.factory, self.listening = factory, listening
        self.model = None
        self.lock = threading.Lock()

    def _load(self):
        if self.model is None:
            self.model = self.factory()
        return self.model

    def warm(self):
        with self.lock:
            if self.listening():
                self._load()

    def loaded(self):
        model = self.model
        return (model.name, model.device) if model is not None else None

    def __call__(self, pcm, glossary=""):
        with self.lock:
            if self.listening():
                return self._load()(pcm, glossary)
        return ""

    def unload(self):
        with self.lock:
            model, self.model = self.model, None
            if model is not None and hasattr(model, "unload"):
                model.unload()


def create_asr(runtime, engine="qwen", on_status=lambda msg: None, *, url="", model="", download=False,
               whisper_model=DEFAULT_WHISPER_MODEL, whisper_device="auto"):
    if engine == "qwen":
        return QwenASR(runtime, on_status)
    if engine == "whisper":
        return FasterWhisperASR(runtime, on_status, download=download, variant=whisper_model,
                                device=whisper_device)
    if engine == "openai_local":
        return LocalAudioTranscriptions(url, model)
    raise ValueError(f"Неизвестный движок распознавания {engine!r}.")
