import queue
import threading
import tkinter as tk
from tkinter import ttk

from .i18n import translate
from .model_picker import COPY as MODEL_COPY
from .qwen_install import QWEN_CUDA_DOWNLOAD_SIZES, QWEN_DOWNLOAD_SIZES, install_qwen, qwen_installed
from .speech import DEFAULT_QWEN_MODEL, QWEN_ASR_MODELS, QWEN_LARGE_MODEL
from .whisper_install import WHISPER_DEVICES, WHISPER_MODELS, install_whisper, whisper_cuda_installed, whisper_installed


COPY = {
    **MODEL_COPY,
    "Модели распознавания": ("Speech recognition models", "Modelos de reconocimiento de voz"),
    "Размер загрузки": ("Download size", "Tamaño de descarga"),
    "Языки": ("Languages", "Idiomas"),
    "Только английский": ("English only", "Solo inglés"),
    "Многоязычная": ("Multilingual", "Multilingüe"),
    "Примерно {size:.0f} МБ": ("About {size:.0f} MB", "Unos {size:.0f} MB"),
    "Примерно {size:.1f} ГБ": ("About {size:.1f} GB", "Unos {size:.1f} GB"),
    "Проверяю установленные модели…": ("Checking installed models…", "Comprobando los modelos instalados…"),
    "Выбери модель распознавания.": ("Choose a speech recognition model.", "Elige un modelo de reconocimiento de voz."),
    "Установленных моделей пока нет. Скачай модель из каталога.": (
        "No models installed yet. Download one from the catalog.",
        "Todavía no hay modelos instalados. Descarga uno del catálogo.",
    ),
    "Qwen BF16 работает на NVIDIA GPU. При первой установке также скачиваются библиотеки PyTorch CUDA.": (
        "Qwen BF16 runs on an NVIDIA GPU. The first setup also downloads PyTorch CUDA libraries.",
        "Qwen BF16 usa la GPU NVIDIA. La primera instalación también descarga las bibliotecas PyTorch CUDA.",
    ),
    "Устанавливаю PyTorch CUDA для Qwen…": (
        "Installing PyTorch CUDA for Qwen…", "Instalando PyTorch CUDA para Qwen…",
    ),
    "Устанавливаю Transformers для Qwen…": (
        "Installing Transformers for Qwen…", "Instalando Transformers para Qwen…",
    ),
    "{stage} · загрузка файла {percent}%": (
        "{stage} · file download {percent}%", "{stage} · descarga del archivo {percent}%",
    ),
    "{stage} · {percent}%": ("{stage} · {percent}%", "{stage} · {percent}%"),
    "Qwen3-ASR 1.7B INT8 работает на CPU и требует больше оперативной памяти, чем 0.6B.": (
        "Qwen3-ASR 1.7B INT8 runs on CPU and uses more system memory than 0.6B.",
        "Qwen3-ASR 1.7B INT8 usa la CPU y requiere más memoria RAM que 0.6B.",
    ),
    "Устанавливаю Faster Whisper…": ("Installing Faster Whisper…", "Instalando Faster Whisper…"),
    "Установить CUDA и выбрать": ("Install CUDA and select", "Instalar CUDA y seleccionar"),
    "Устанавливаю cuBLAS и cuDNN для CUDA 12…": (
        "Installing cuBLAS and cuDNN for CUDA 12…", "Instalando cuBLAS y cuDNN para CUDA 12…",
    ),
    "NVIDIA GPU · при первом выборе загрузится около 1,3 ГБ библиотек.": (
        "NVIDIA GPU downloads about 1.3 GB of libraries the first time.",
        "NVIDIA GPU descarga unos 1,3 GB de bibliotecas la primera vez.",
    ),
    "Для режима GPU нужен доступный драйвер NVIDIA.": (
        "GPU mode requires a working NVIDIA driver.", "El modo GPU requiere un controlador NVIDIA operativo.",
    ),
    "Не удалось установить библиотеки NVIDIA. Проверь интернет и повтори.": (
        "Couldn't install the NVIDIA libraries. Check your connection and try again.",
        "No se pudieron instalar las bibliotecas NVIDIA. Comprueba la conexión e inténtalo de nuevo.",
    ),
    "Faster Whisper не прошёл проверку CUDA. Проверь драйвер NVIDIA и свободную VRAM.": (
        "Faster Whisper failed its CUDA check. Check the NVIDIA driver and free VRAM.",
        "Faster Whisper no pasó la prueba de CUDA. Comprueba el controlador NVIDIA y la VRAM libre.",
    ),
    "Скачиваю файлы модели…": ("Downloading model files…", "Descargando los archivos del modelo…"),
    "Проверяю файлы модели…": ("Checking model files…", "Verificando los archivos del modelo…"),
    "Не удалось проверить установленные модели. {detail}": (
        "Couldn't check installed models. {detail}", "No se pudieron comprobar los modelos instalados. {detail}",
    ),
    "Не удалось установить модель. {detail}": (
        "Couldn't install the model. {detail}", "No se pudo instalar el modelo. {detail}",
    ),
}


def show_speech_picker(app, parent, *, runtime, use_model, vram, current, unload, selected, device):
    return SpeechPicker(app, parent, runtime, use_model, vram, current, unload, selected, device).window


class SpeechPicker:
    def __init__(self, app, parent, runtime, use_model, vram, current, unload, selected, device):
        self.language, self.runtime, self.use_model = app.ui_language, runtime, use_model
        self.window = w = tk.Toplevel(parent)
        w.title(self.t("Модели распознавания"))
        w.transient(parent)
        w.attributes("-topmost", app.top.get())
        bg = parent.cget("bg")
        w.configure(bg=bg)
        width = min(790, w.winfo_screenwidth() - 60)
        height = min(545, w.winfo_screenheight() - 96)
        w.minsize(min(650, width), min(430, height))
        w.geometry(f"{width}x{height}")
        self.models = {
            **{variant: ("qwen", variant, name, "INT8 · CPU", QWEN_DOWNLOAD_SIZES[variant])
               for variant, (name, _bundle) in QWEN_ASR_MODELS.items()},
            **{f"{variant}-cuda": ("qwen", variant, name, "BF16 · NVIDIA GPU", QWEN_CUDA_DOWNLOAD_SIZES[variant])
               for variant, (name, _bundle) in QWEN_ASR_MODELS.items()},
            **{variant: ("whisper", variant, "Faster Whisper", variant, size)
               for variant, size in WHISPER_MODELS.items()},
        }
        self.saved_key = selected if selected in self.models else DEFAULT_QWEN_MODEL
        self.installed = None
        self.cuda_ready = False
        self.current = current
        self.stop = None
        self.after_id = None
        self.events = queue.SimpleQueue()
        self.query = tk.StringVar(w)
        self.saved_model = tk.StringVar(w)
        self.feedback = tk.StringVar(w, self.t("Проверяю установленные модели…"))
        self.details = tk.StringVar(w)
        frame = tk.Frame(w, bg=bg, padx=14, pady=12)
        frame.pack(fill="both", expand=True)
        bottom = tk.Frame(frame, bg=bg)
        bottom.pack(side="bottom", fill="x")
        app._label(frame, self.t("Модели распознавания"), size=15, bold=True, bg=bg).pack(fill="x")
        app._label(frame, var=self.saved_model, color="#a9c9b6", size=9, bg=bg).pack(fill="x", pady=(2, 0))
        self.update_saved_model()
        current_row = tk.Frame(frame, bg=bg)
        current_row.pack(fill="x")
        app._label(current_row, var=current, size=9, bg=bg).pack(side="left", fill="x", expand=True)
        unload_button = app._button(current_row, self.t("Выгрузить модель"), unload)
        unload_button.pack(side="right")

        def update_unload(*_args):
            session = app.speech_session
            ready = (session is not None and session.loaded() and app.settings["stt_engine"] != "openai_local"
                     and not app.speech_unloading.is_set())
            unload_button.state(["!disabled"] if ready else ["disabled"])

        self.current_trace = current.trace_add("write", update_unload)
        update_unload()
        app._label(frame, var=vram, color="#b1bbb2", size=9, bg=bg, wrap=505).pack(fill="x", pady=(2, 6))
        device_row = tk.Frame(frame, bg=bg)
        device_row.pack(fill="x", pady=(0, 5))
        app._label(device_row, "Faster Whisper", size=9, bg=bg).pack(side="left", padx=(0, 7))
        self.device = ttk.Combobox(device_row, values=list(WHISPER_DEVICES.values()), state="readonly",
                                   style="Copilot.TCombobox", width=22)
        self.device.set(WHISPER_DEVICES.get(device, "Auto"))
        self.device.pack(side="left")
        self.device.bind("<<ComboboxSelected>>", self.update_action)
        app._label(bottom, var=self.details, color="#b1bbb2", size=9, bg=bg, wrap=505).pack(fill="x", pady=(5, 2))
        app._label(bottom, var=self.feedback, color="#a9c9b6", size=9, bg=bg, wrap=505).pack(fill="x")
        actions = tk.Frame(bottom, bg=bg)
        actions.pack(fill="x", pady=(6, 0))
        app._button(actions, self.t("Закрыть"), w.destroy).pack(side="left")
        self.action = app._button(actions, self.t("Скачать и выбрать"), self.choose, primary=True)
        self.action.pack(side="right")
        self.cancel = app._button(actions, self.t("Отменить загрузку"), self.cancel_download)
        self.cancel.pack(side="right", padx=6)

        style = ttk.Style(w)
        style.configure("SpeechPicker.Treeview", background="#222622", fieldbackground="#222622",
                        foreground="#f3f5f1", rowheight=26)
        style.map("SpeechPicker.Treeview", background=[("selected", "#3b5547")],
                  foreground=[("selected", "#ffffff")])
        style.configure("SpeechPicker.Treeview.Heading", background="#383f39", foreground="#f3f5f1")
        self.tabs = ttk.Notebook(frame)
        self.tabs.pack(fill="both", expand=True)
        catalog = tk.Frame(self.tabs, bg=bg, padx=6, pady=6)
        installed = tk.Frame(self.tabs, bg=bg, padx=6, pady=6)
        self.tabs.add(catalog, text=self.t("Каталог"))
        self.tabs.add(installed, text=self.t("Установленные"))
        search_row = tk.Frame(catalog, bg=bg)
        search_row.pack(fill="x", pady=(0, 6))
        app._label(search_row, self.t("Поиск"), size=9, bg=bg).pack(side="left", padx=(0, 8))
        search = ttk.Entry(search_row, textvariable=self.query, style="Copilot.Settings.TEntry")
        search.pack(side="left", fill="x", expand=True)
        self.catalog_table = self.make_table(catalog)
        self.installed_table = self.make_table(installed)
        self.tabs.bind("<<NotebookTabChanged>>", self.update_action)
        self.query.trace_add("write", self.filter_catalog)
        self.filter_catalog()
        w.bind("<Destroy>", self.cleanup)
        w.bind("<Escape>", lambda _: w.destroy())
        w.grab_set()
        search.focus_set()
        self.run(self.check_installed, self.installed_checked)

    def t(self, source, **values):
        return translate(self.language, COPY, source, **values)

    def make_table(self, frame):
        columns = (("model", "Модель", 145), ("variant", "Вариант", 135), ("languages", "Языки", 120),
                   ("size", "Размер загрузки", 120), ("status", "Состояние", 120))
        table = ttk.Treeview(frame, columns=[key for key, *_ in columns], show="headings",
                             selectmode="browse", style="SpeechPicker.Treeview")
        for key, label, width in columns:
            table.heading(key, text=self.t(label))
            table.column(key, width=width, minwidth=70)
        bar = ttk.Scrollbar(frame, orient="vertical", command=table.yview, style="Copilot.Vertical.TScrollbar")
        table.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        table.pack(side="left", fill="both", expand=True)
        table.bind("<<TreeviewSelect>>", self.update_action)
        return table

    def model_languages(self, key):
        english = key.endswith(".en") or key.startswith("distil-")
        return self.t("Только английский" if english else "Многоязычная")

    def filter_catalog(self, *_args):
        terms = self.query.get().casefold().split()
        keys = []
        for key, (_engine, _variant, name, label, _size) in self.models.items():
            searchable = f"{name} {label} {self.model_languages(key)}".casefold()
            if all(term in searchable for term in terms):
                keys.append(key)
        self.show_models(self.catalog_table, keys)
        self.update_action()

    def show_models(self, table, keys):
        selected = next(iter(table.selection()), self.saved_key)
        table.delete(*table.get_children())
        for key in keys:
            _engine, _variant, name, label, size = self.models[key]
            size_label = (self.t("Примерно {size:.1f} ГБ", size=size / 10**9) if size >= 10**9
                          else self.t("Примерно {size:.0f} МБ", size=size / 10**6))
            table.insert("", "end", iid=key,
                         values=(name, label, self.model_languages(key), size_label, self.model_status(key)))
        if selected in keys:
            table.selection_set(selected)
            table.see(selected)

    def update_saved_model(self):
        engine, variant, name, *_ = self.models[self.saved_key]
        if engine == "whisper":
            name = f"{name} · {variant}"
        self.saved_model.set(self.t("Выбор в настройках · {name}", name=name))

    def run(self, job, finish):
        def work():
            try:
                result = job()
            except (OSError, ValueError, RuntimeError, ImportError) as error:
                self.events.put(("done", None, error))
            else:
                self.events.put(("done", result, None))

        def poll():
            self.after_id = None
            while True:
                try:
                    kind, value, extra = self.events.get_nowait()
                except queue.Empty:
                    self.after_id = self.window.after(80, poll)
                    return
                if kind == "done":
                    finish(value, extra)
                    return
                if self.stop and not self.stop.is_set():
                    self.update_progress(value, *extra)

        threading.Thread(target=work, daemon=True).start()
        self.after_id = self.window.after(80, poll)

    def check_installed(self):
        installed = {variant for variant in QWEN_ASR_MODELS if qwen_installed(self.runtime, variant)}
        installed.update(f"{variant}-cuda" for variant in QWEN_ASR_MODELS
                         if qwen_installed(self.runtime, variant, device="cuda"))
        installed.update(variant for variant in WHISPER_MODELS if whisper_installed(self.runtime, variant))
        return installed, whisper_cuda_installed()

    def installed_checked(self, installed, error):
        self.installed, self.cuda_ready = installed if error is None else (set(), False)
        if error is None:
            self.feedback.set(self.t("Выбери модель распознавания."))
        else:
            self.feedback.set(self.t("Не удалось проверить установленные модели. {detail}", detail=str(error)))
        for key in self.catalog_table.get_children():
            self.mark_status(key)
        self.show_models(self.installed_table, [key for key in self.models if key in self.installed])
        self.update_action()

    def model_status(self, key):
        if self.installed is None:
            return self.t("Выбрана") if key == self.saved_key else "…"
        disk = self.t("Установлена" if key in self.installed else "Не скачана")
        return f'{self.t("Выбрана")} · {disk}' if key == self.saved_key else disk

    def mark_status(self, key):
        for table in (self.catalog_table, self.installed_table):
            if table.exists(key):
                table.set(key, "status", self.model_status(key))

    def active_table(self):
        return self.catalog_table if self.tabs.index("current") == 0 else self.installed_table

    def update_action(self, _event=None):
        table = self.active_table()
        key = next(iter(table.selection()), None)
        installed = self.installed is not None and key in self.installed
        whisper = key is not None and self.models[key][0] == "whisper"
        self.device.state(["!disabled"] if whisper and self.stop is None else ["disabled"])
        needs_cuda = whisper and self.device.get() == WHISPER_DEVICES["cuda"] and not self.cuda_ready
        self.action.configure(text=self.t(
            ("Установить CUDA и выбрать" if needs_cuda else "Выбрать") if installed else "Скачать и выбрать"))
        self.action.state(["!disabled"] if key and self.installed is not None and self.stop is None else ["disabled"])
        self.cancel.state(["!disabled"] if self.stop and not self.stop.is_set() else ["disabled"])
        detail = "Размер файлов указан для диска. Свободная VRAM показана отдельно."
        if table is self.catalog_table and not table.get_children():
            detail = "Модели не найдены. Попробуй другое название."
        elif table is self.installed_table and self.installed == set():
            detail = "Установленных моделей пока нет. Скачай модель из каталога."
        elif key and key.endswith("-cuda"):
            detail = "Qwen BF16 работает на NVIDIA GPU. При первой установке также скачиваются библиотеки PyTorch CUDA."
        elif key == QWEN_LARGE_MODEL:
            detail = "Qwen3-ASR 1.7B INT8 работает на CPU и требует больше оперативной памяти, чем 0.6B."
        elif needs_cuda:
            detail = "NVIDIA GPU · при первом выборе загрузится около 1,3 ГБ библиотек."
        self.details.set(self.t(detail))

    def choose(self):
        key = next(iter(self.active_table().selection()), None)
        if not key or self.installed is None or self.stop is not None:
            return
        engine, variant, *_ = self.models[key]
        if engine == "qwen":
            device = "cuda" if key.endswith("-cuda") else "cpu"
        else:
            device = next((name for name, label in WHISPER_DEVICES.items() if label == self.device.get()), "auto")
        if key in self.installed and (device != "cuda" or engine == "qwen" or self.cuda_ready):
            self.apply(key, device)
            return
        stop = self.stop = threading.Event()
        self.feedback.set(self.t("Скачиваю файлы модели…"))
        self.update_action()

        def progress(stage, completed, total):
            self.events.put(("progress", stage, (completed, total)))

        def install():
            if engine == "qwen":
                return install_qwen(self.runtime, progress, stop.is_set, variant=variant, device=device)
            return install_whisper(self.runtime, variant, progress, stop.is_set, device=device)

        def finish(complete, error):
            self.stop = None
            if stop.is_set() or (error is None and not complete):
                self.feedback.set(self.t("Загрузка отменена."))
            elif error is not None:
                self.feedback.set(self.t("Не удалось установить модель. {detail}", detail=self.t(str(error))))
            else:
                self.installed.add(key)
                self.mark_status(key)
                self.show_models(self.installed_table, [item for item in self.models if item in self.installed])
                if engine == "whisper" and device == "cuda":
                    self.cuda_ready = True
                if self.apply(key, device):
                    return
            self.update_action()

        self.run(install, finish)

    def apply(self, key, device):
        engine, variant, *_ = self.models[key]
        try:
            self.use_model(engine, variant, device)
        except (OSError, ValueError) as error:
            self.feedback.set(self.t("Не удалось сохранить выбор. {detail}", detail=str(error)))
            return False
        self.window.destroy()
        return True

    def update_progress(self, stage, completed, total):
        packages = {
            "dependencies": "Устанавливаю Faster Whisper…",
            "cuda": "Устанавливаю cuBLAS и cuDNN для CUDA 12…",
            "qwen_cuda": "Устанавливаю PyTorch CUDA для Qwen…",
            "qwen_transformers": "Устанавливаю Transformers для Qwen…",
        }
        message = self.t(packages.get(stage, "Проверяю файлы модели…" if stage == "verify"
                                      else "Скачиваю файлы модели…"))
        if completed is not None and total:
            template = "{stage} · загрузка файла {percent}%" if stage in packages else "{stage} · {percent}%"
            message = self.t(template, stage=message.removesuffix("…"), percent=min(100, 100 * completed // total))
        self.feedback.set(message)

    def cancel_download(self):
        if self.stop:
            self.stop.set()
            self.feedback.set(self.t("Отменяю загрузку…"))
            self.update_action()

    def cleanup(self, event):
        if event.widget is self.window:
            self.current.trace_remove("write", self.current_trace)
            if self.stop:
                self.stop.set()
            if self.after_id is not None:
                self.window.after_cancel(self.after_id)
