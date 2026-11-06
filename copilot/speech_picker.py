import queue
import threading
import tkinter as tk
from tkinter import ttk

from .i18n import translate
from .model_picker import COPY as MODEL_COPY
from .qwen_install import QWEN_DOWNLOAD_BYTES, install_qwen, qwen_installed
from .whisper_install import WHISPER_MODELS, install_whisper, whisper_installed


COPY = {
    **MODEL_COPY,
    "Модели распознавания": ("Speech recognition models", "Modelos de reconocimiento de voz"),
    "Размер загрузки": ("Download size", "Tamaño de descarga"),
    "Примерно {size:.0f} МБ": ("About {size:.0f} MB", "Unos {size:.0f} MB"),
    "Примерно {size:.1f} ГБ": ("About {size:.1f} GB", "Unos {size:.1f} GB"),
    "Проверяю установленные модели…": ("Checking installed models…", "Comprobando los modelos instalados…"),
    "Доступна для скачивания": ("Available to download", "Disponible para descargar"),
    "Выбери модель распознавания.": ("Choose a speech recognition model.", "Elige un modelo de reconocimiento de voz."),
    "Qwen скачивает пакет INT8 для CPU. Если CUDA уже настроена, приложение использует её автоматически.": (
        "Qwen downloads the INT8 CPU package. The app uses CUDA automatically if it is already configured.",
        "Qwen descarga el paquete INT8 para CPU. La aplicación usa CUDA si ya está configurada.",
    ),
    "Многоязычный вариант Faster Whisper. Меньшие варианты обычно быстрее. Точность зависит от речи и языка.": (
        "A multilingual Faster Whisper variant. Smaller variants are usually faster. Accuracy depends on the speech and language.",
        "Variante multilingüe de Faster Whisper. Los tamaños menores suelen ser más rápidos. La precisión depende del habla y el idioma.",
    ),
    "Устанавливаю Faster Whisper…": ("Installing Faster Whisper…", "Instalando Faster Whisper…"),
    "Скачиваю файлы модели…": ("Downloading model files…", "Descargando los archivos del modelo…"),
    "Скачиваю файлы модели · {percent}%": ("Downloading model files · {percent}%", "Descargando los archivos del modelo · {percent}%"),
    "Проверяю файлы модели…": ("Checking model files…", "Verificando los archivos del modelo…"),
    "Не удалось проверить установленные модели. {detail}": (
        "Couldn't check installed models. {detail}", "No se pudieron comprobar los modelos instalados. {detail}",
    ),
    "Не удалось установить модель. {detail}": (
        "Couldn't install the model. {detail}", "No se pudo instalar el modelo. {detail}",
    ),
    "Модель {name} выбрана. Перезапусти Agent Utka для применения.": (
        "{name} selected. Restart Agent Utka to use it.",
        "Se seleccionó {name}. Reinicia Agent Utka para usarlo.",
    ),
}


def show_speech_picker(app, parent, *, runtime, use_model, vram, selected="qwen"):
    return SpeechPicker(app, parent, runtime, use_model, vram, selected).window


class SpeechPicker:
    def __init__(self, app, parent, runtime, use_model, vram, selected):
        self.language, self.runtime, self.use_model = app.ui_language, runtime, use_model
        self.window = w = tk.Toplevel(parent)
        w.title(self.t("Модели распознавания"))
        w.transient(parent)
        w.attributes("-topmost", app.top.get())
        bg = parent.cget("bg")
        w.configure(bg=bg)
        width = min(710, w.winfo_screenwidth() - 60)
        height = min(460, w.winfo_screenheight() - 96)
        w.minsize(min(565, width), min(380, height))
        w.geometry(f"{width}x{height}")
        self.models = {
            "qwen": ("qwen", "0.6b-int8", "Qwen3-ASR 0.6B", "INT8 · CPU", QWEN_DOWNLOAD_BYTES),
            **{variant: ("whisper", variant, "Faster Whisper", variant, size)
               for variant, size in WHISPER_MODELS.items()},
        }
        self.saved_key = selected if selected in self.models else "qwen"
        self.installed = None
        self.stop = None
        self.after_id = None
        self.events = queue.SimpleQueue()
        self.feedback = tk.StringVar(w, self.t("Проверяю установленные модели…"))
        self.details = tk.StringVar(w)
        frame = tk.Frame(w, bg=bg, padx=14, pady=12)
        frame.pack(fill="both", expand=True)
        bottom = tk.Frame(frame, bg=bg)
        bottom.pack(side="bottom", fill="x")
        app._label(frame, self.t("Модели распознавания"), size=15, bold=True, bg=bg).pack(fill="x")
        app._label(frame, var=vram, color="#b1bbb2", size=9, bg=bg, wrap=505).pack(fill="x", pady=(2, 6))
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
        table_frame = tk.Frame(frame, bg=bg)
        table_frame.pack(fill="both", expand=True)
        columns = (("model", "Модель", 145), ("variant", "Вариант", 115),
                   ("size", "Размер загрузки", 130), ("status", "Состояние", 145))
        self.table = ttk.Treeview(table_frame, columns=[key for key, *_ in columns], show="headings",
                                  selectmode="browse", style="SpeechPicker.Treeview")
        for key, text, width in columns:
            self.table.heading(key, text=self.t(text))
            self.table.column(key, width=width, minwidth=80)
        bar = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview, style="Copilot.Vertical.TScrollbar")
        self.table.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.table.pack(side="left", fill="both", expand=True)
        for key, (_engine, _variant, name, label, size) in self.models.items():
            size_label = self.t("Примерно {size:.1f} ГБ", size=size / 10**9) if size >= 10**9 else self.t(
                "Примерно {size:.0f} МБ", size=size / 10**6)
            status = self.t("Выбрана") if key == self.saved_key else "…"
            self.table.insert("", "end", iid=key, values=(name, label, size_label, status))
        self.table.selection_set(self.saved_key)
        self.table.see(self.selected())
        self.table.bind("<<TreeviewSelect>>", self.update_action)
        self.update_action()
        w.bind("<Destroy>", self.cleanup)
        w.bind("<Escape>", lambda _: w.destroy())
        w.grab_set()
        self.table.focus_set()
        self.run(self.check_installed, self.installed_checked)

    def t(self, source, **values):
        return translate(self.language, COPY, source, **values)

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
        installed = {"qwen"} if qwen_installed(self.runtime) else set()
        installed.update(variant for variant in WHISPER_MODELS if whisper_installed(self.runtime, variant))
        return installed

    def installed_checked(self, installed, error):
        self.installed = installed if error is None else set()
        if error is None:
            self.feedback.set(self.t("Выбери модель распознавания."))
        else:
            self.feedback.set(self.t("Не удалось проверить установленные модели. {detail}", detail=str(error)))
        for key in self.models:
            self.mark_status(key)
        self.update_action()

    def mark_status(self, key):
        status = "Выбрана" if key == self.saved_key else "Установлена" if key in self.installed else "Доступна для скачивания"
        self.table.set(key, "status", self.t(status))

    def selected(self):
        return next(iter(self.table.selection()), None)

    def update_action(self, _event=None):
        key = self.selected()
        installed = self.installed is not None and key in self.installed
        self.action.configure(text=self.t("Выбрать" if installed else "Скачать и выбрать"))
        self.action.state(["!disabled"] if key and self.installed is not None and self.stop is None else ["disabled"])
        self.cancel.state(["!disabled"] if self.stop and not self.stop.is_set() else ["disabled"])
        if key:
            self.details.set(self.t(
                "Qwen скачивает пакет INT8 для CPU. Если CUDA уже настроена, приложение использует её автоматически."
                if key == "qwen" else
                "Многоязычный вариант Faster Whisper. Меньшие варианты обычно быстрее. Точность зависит от речи и языка."))

    def choose(self):
        key = self.selected()
        if not key or self.installed is None or self.stop is not None:
            return
        engine, variant, *_ = self.models[key]
        if key in self.installed:
            self.apply(key)
            return
        stop = self.stop = threading.Event()
        self.feedback.set(self.t("Скачиваю файлы модели…"))
        self.update_action()

        def progress(stage, completed, total):
            self.events.put(("progress", stage, (completed, total)))

        def install():
            if engine == "qwen":
                return install_qwen(self.runtime, progress, stop.is_set)
            return install_whisper(self.runtime, variant, progress, stop.is_set)

        def finish(complete, error):
            self.stop = None
            if stop.is_set() or (error is None and not complete):
                self.feedback.set(self.t("Загрузка отменена."))
            elif error is not None:
                self.feedback.set(self.t("Не удалось установить модель. {detail}", detail=str(error)))
            else:
                self.installed.add(key)
                self.mark_status(key)
                self.apply(key)
            self.update_action()

        self.run(install, finish)

    def apply(self, key):
        engine, variant, name, *_ = self.models[key]
        try:
            self.use_model(engine, variant)
        except (OSError, ValueError) as error:
            self.feedback.set(self.t("Не удалось сохранить выбор. {detail}", detail=str(error)))
            return
        previous, self.saved_key = self.saved_key, key
        self.mark_status(previous)
        self.mark_status(key)
        name = f"{name} · {variant}" if engine == "whisper" else name
        self.feedback.set(self.t("Модель {name} выбрана. Перезапусти Agent Utka для применения.", name=name))

    def update_progress(self, stage, completed, total):
        if stage == "dependencies":
            message = self.t("Устанавливаю Faster Whisper…")
        elif stage == "verify":
            message = self.t("Проверяю файлы модели…")
        elif completed is not None and total:
            message = self.t("Скачиваю файлы модели · {percent}%",
                             percent=min(100, round(100 * completed / total)))
        else:
            message = self.t("Скачиваю файлы модели…")
        self.feedback.set(message)

    def cancel_download(self):
        if self.stop:
            self.stop.set()
            self.feedback.set(self.t("Отменяю загрузку…"))
            self.update_action()

    def cleanup(self, event):
        if event.widget is self.window:
            if self.stop:
                self.stop.set()
            if self.after_id is not None:
                self.window.after_cancel(self.after_id)
