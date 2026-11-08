import argparse
import logging
import os
import queue
import sqlite3
import threading
import time
import tkinter as tk
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .brains import create_brain
from .configuration import BASE, RUNTIME, UI_LANGUAGES, index_path, load_settings, save_settings
from .history import Entry, History
from .i18n import LANGUAGES, OVERLAY_COPY, flag_images, translate, translate_diagnostic
from .knowledge import Knowledge, Source, discover_projects, scope_roots, source_location
from .knowledge_import import choose_base_name, choose_import_destination
from .knowledge_pack import create_named_base, import_summary
from .knowledge_window import show_knowledge_window
from .pipeline import Pipeline
from .retrieval import create_retriever
from .settings_window import show_settings
from .speech import SpeechSession, create_asr, detect, loopback
from .suggest import MAX_OPTIONS, Advisor, Card


BG, SURFACE, BORDER = "#181b19", "#222622", "#383f39"
INK, MUTED, ACCENT = "#f3f5f1", "#b1bbb2", "#a9c9b6"
ACTION, ACTION_HOVER = "#a9c9b6", "#c1dccb"
WIDTH = 474
LOG = logging.getLogger("call_copilot")


class Overlay:
    def __init__(self, window, settings, *, demo=False):
        self.window, self.settings = window, settings
        self.ui_language = settings.get("ui_language", "ru")
        self._copy_widgets = []
        self._copy_vars = {}
        self.ui = queue.SimpleQueue()
        self.project = None
        self.projects = {}
        self.bases = {}
        self.base_items = []
        self.last_card = None
        self.last_utterance = ""
        self.indexed_count = None
        self.import_target = None
        self.source_window = None
        self.history_window = None
        self.settings_window = None
        self.knowledge_window = None
        self.entries = []
        self.review_id = None
        self.folded = False
        self.history = History(":memory:" if demo else RUNTIME / "history.sqlite")
        self.live = threading.Event()
        self.closed = threading.Event()
        self.scan = threading.Event()
        self.index_generation = object()
        self.capture_lock = threading.Lock()
        self.capture_reset = threading.Event()
        self.llm_done = False
        self.pipeline = None
        self.speech_session = None
        self.speech_unloading = threading.Event()
        self.device_name = ""
        self.llm_status = ""
        self.llm = create_brain(RUNTIME, settings)
        self.index = None if demo else self._create_index(settings)
        self.status = self._copy_var("Подготовка локальных моделей…")
        self.project_label = tk.StringVar()
        self.index_status = self._copy_var("")
        self.listen_label = self._copy_var("Пауза")
        self.answer_status = self._copy_var("")
        self.selection_status = self._copy_var("Речь появится в расшифровке")
        self.top = tk.BooleanVar(value=True)
        self._build()
        self._load_history()
        self.drain_id = self.window.after(55, self._drain)
        if demo:
            return
        self.live.set()
        self._projects(self._known_projects())
        self.speech_session = SpeechSession(self._speech_factory(settings, self.capture_reset), self.live.is_set)
        self.pipeline = Pipeline(self.speech_session, Advisor(self.index, self.llm, requested=True),
                                 lambda *event: self.ui.put(("turn", event)), manual=True, documents_only=True)
        brain, reset = self.llm, self.capture_reset
        for job in (self._index_loop, lambda: self._warm_llm(brain),
                    lambda: self._warm_asr(reset), self._capture):
            threading.Thread(target=job, daemon=True).start()

    def apply_settings(self, updates):
        settings = {**self.settings, **updates}
        changed = {key for key in updates if self.settings.get(key) != settings[key]}
        speech_keys = {
            "qwen": {"qwen_model", "qwen_device"},
            "whisper": {"whisper_model", "whisper_device"},
            "openai_local": {"stt_url", "stt_model"},
        }
        answer_keys = {
            "ollama": {"ollama"},
            "ollama_local": {"ollama_url", "ollama_model"},
            "openai_local": {"llm_url", "llm_model"},
        }
        speech_changed = changed & ({"stt_engine", "pause_ms"} | speech_keys[settings["stt_engine"]])
        answer_changed = changed & ({"llm_provider"} | answer_keys[settings["llm_provider"]])
        index_changed = changed & {"rag_directory", "rag_provider", "rag_url"}
        index = self._create_index(settings) if index_changed else self.index
        brain = create_brain(RUNTIME, settings) if answer_changed else self.llm
        save_settings(updates)
        with self.capture_lock:
            self.settings = settings
            if speech_changed and self.speech_session is not None:
                self.capture_reset.set()
                self.capture_reset = reset = threading.Event()
                self.speech_session.reconfigure(self._speech_factory(settings, reset))
                self.pipeline.cancel_speech()
        if index_changed:
            self.index = index
            self.index_generation = object()
            self.indexed_count = None
            self._set_copy(self.index_status, "Индекс обновляется…")
            self.scan.set()
        if (answer_changed or index_changed) and self.pipeline is not None:
            self.pipeline.set_advisor(Advisor(index, brain, requested=True))
            self._set_copy(self.answer_status, "")
        if answer_changed:
            old_brain, self.llm = self.llm, brain
            self.llm_done = False
            self.llm_status = ""
            threading.Thread(target=self._warm_llm, args=(brain, old_brain), daemon=True).start()
        if speech_changed and self.speech_session is not None:
            if self.live.is_set():
                self._set_copy(self.status, "Подготовка локальных моделей…")
            threading.Thread(target=self._warm_asr, args=(reset,), daemon=True).start()

    @staticmethod
    def _create_index(settings):
        return Knowledge(index_path(settings, documents_only=True),
                         retriever=create_retriever(settings), documents_only=True)

    def _tr(self, source, **values):
        for name in ("error", "warning"):
            if name in values:
                values[name] = self._detail(values[name])
        return translate(self.ui_language, OVERLAY_COPY, source, **values)

    def _detail(self, message):
        return translate_diagnostic(self.ui_language, message)

    def _copy_var(self, source):
        var = tk.StringVar(master=self.window)
        self._set_copy(var, source)
        return var

    def _set_copy(self, var, source, **values):
        self._copy_vars[str(var)] = (var, source, values)
        var.set(self._tr(source, **values))

    def _localize(self, widget, source):
        self._copy_widgets.append((widget, source))
        widget.configure(text=self._tr(source))
        return widget

    def _set_ui_language(self, code):
        if code not in UI_LANGUAGES or code == self.ui_language:
            return
        try:
            save_settings({"ui_language": code})
        except OSError as error:
            messagebox.showerror(self._tr("Не удалось сохранить язык"), str(error), parent=self.window)
            return
        self.ui_language = self.settings["ui_language"] = code
        self.language_button.configure(text=code.upper(), image=self.flags[code])
        for widget, source in self._copy_widgets:
            widget.configure(text=self._tr(source))
        for var, source, values in self._copy_vars.values():
            var.set(self._tr(source, **values))
        if self.project is None:
            self.project_label.set(self._tr("База не выбрана"))
        if self.base_items:
            self._projects(self.base_items)
        self._update_overlay_controls()
        self._render_selection()
        if self.history_window:
            self.history_window.title(self._tr("История · Agent Utka"))
            self.history_heading.configure(text=self._tr("История подсказок"))
        if self.source_window:
            self._render_sources()
        if self.settings_window:
            self.settings_window.event_generate("<<UILanguageChanged>>")

    def _label(self, parent, text="", *, var=None, color=INK, size=10, bold=False, bg=BG,
               wrap=WIDTH - 48, localized=False):
        widget = tk.Label(parent, text=text, textvariable=var, fg=color, bg=bg, anchor="w",
                          justify="left", wraplength=wrap,
                          font=("Segoe UI", size, "bold" if bold else "normal"))
        return self._localize(widget, text) if localized else widget

    def _build(self):
        w = self.window
        w.title("Agent Utka")
        w.configure(bg=BG)
        w.resizable(True, True)
        w.attributes("-topmost", True)
        w.protocol("WM_DELETE_WINDOW", self.close)
        w.geometry(f"+{max(10, w.winfo_screenwidth() - WIDTH - 34)}+64")
        w.bind("<Escape>", lambda _e: self._toggle())
        w.bind("<Control-Return>", self._ask_selection)
        w.bind("<Control-Left>", lambda e: None if isinstance(e.widget, tk.Text) else self._navigate(-1))
        w.bind("<Control-Right>", lambda e: None if isinstance(e.widget, tk.Text) else self._navigate(1))
        w.bind("<Control-End>", lambda e: None if isinstance(e.widget, tk.Text) else self._go_live())
        style = ttk.Style(w)
        style.theme_use("clam")
        style.configure("Copilot.TButton", background=SURFACE, foreground=INK,
                        bordercolor=BORDER, padding=(9, 5), relief="flat", font=("Segoe UI", 9))
        style.map("Copilot.TButton", background=[("active", BORDER)],
                  foreground=[("disabled", "#8391a3")], bordercolor=[("focus", ACCENT)])
        style.configure("CopilotPrimary.TButton", background=ACTION, foreground="#142019",
                        bordercolor=ACTION, padding=(12, 6), font=("Segoe UI", 9, "bold"))
        style.map("CopilotPrimary.TButton",
                  background=[("disabled", SURFACE), ("active", ACTION_HOVER)],
                  foreground=[("disabled", "#8391a3")], bordercolor=[("disabled", BORDER),
                                                                    ("focus", INK)])
        style.configure("Copilot.Vertical.TScrollbar", background=BORDER, troughcolor=SURFACE,
                        bordercolor=SURFACE, arrowcolor=MUTED, lightcolor=BORDER,
                        darkcolor=BORDER, width=11)
        style.configure("Copilot.TCombobox", foreground=INK, background=SURFACE,
                        fieldbackground=SURFACE, arrowcolor=INK, bordercolor=BORDER,
                        padding=3)
        style.map("Copilot.TCombobox", fieldbackground=[("readonly", SURFACE)],
                  foreground=[("readonly", INK)])
        style.configure("Copilot.TEntry", fieldbackground=SURFACE, foreground=INK, insertcolor=INK,
                        bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, padding=5)
        style.map("Copilot.TEntry", bordercolor=[("focus", ACCENT)])
        style.configure("Copilot.TMenubutton", background=SURFACE, foreground=INK,
                        bordercolor=BORDER, arrowcolor=MUTED, padding=(6, 5), font=("Segoe UI", 9))
        style.map("Copilot.TMenubutton", background=[("active", BORDER)],
                  bordercolor=[("focus", ACCENT)])
        w.option_add("*TCombobox*Listbox.background", SURFACE)
        w.option_add("*TCombobox*Listbox.foreground", INK)
        w.option_add("*TCombobox*Listbox.selectBackground", BORDER)
        panel = tk.Frame(w, bg=BG, padx=16, pady=12)
        panel.pack(fill="both", expand=True)
        header = tk.Frame(panel, bg=BG)
        header.pack(fill="x")
        try:
            mascot = tk.PhotoImage(master=w, file=str(BASE / "assets" / "utka.png"))
        except tk.TclError:
            mascot = None
        title_offset = 0
        if mascot:
            longest_side = max(mascot.width(), mascot.height())
            self.mascot_icon = mascot.subsample(max(1, (longest_side + 47) // 48))
            self.mascot_header = mascot.subsample(max(1, (longest_side + 27) // 28))
            w.iconphoto(True, self.mascot_icon)
            tk.Label(header, image=self.mascot_header, bg=BG, borderwidth=0,
                     padx=0, pady=0).pack(side="left", padx=(0, 6))
            title_offset = self.mascot_header.width() + 6
        self._label(header, "Agent Utka", size=16, bold=True).pack(side="left")
        self.fold_button = self._button(header, "Свернуть", self._fold)
        self.fold_button.pack(side="right")
        self._button(header, "", self._toggle, textvariable=self.listen_label).pack(side="right", padx=3)
        self.flags = flag_images(w)
        self.language_button = ttk.Menubutton(header, text=self.ui_language.upper(),
                                             image=self.flags[self.ui_language], compound="left",
                                             style="Copilot.TMenubutton")
        self.language_button.pack(side="right")
        self.language_menu = tk.Menu(self.language_button, tearoff=False)
        for code, name in LANGUAGES.items():
            self.language_menu.add_command(label=name, image=self.flags[code], compound="left",
                                           command=lambda lang=code: self._set_ui_language(lang))
        self.language_button.configure(menu=self.language_menu)
        self._label(panel, "ИИ-помощник для звонков", color=MUTED, size=9,
                    localized=True).pack(fill="x", padx=(title_offset, 0), pady=(1, 0))
        state = tk.Frame(panel, bg=BG)
        state.pack(fill="x", pady=(4, 0))
        self.status_dot = self._label(state, "●", color=MUTED, size=9)
        self.status_dot.pack(side="left", padx=(0, 5), anchor="n")
        status = self._label(state, var=self.status, color=MUTED, size=9, wrap=WIDTH - 68)
        status.configure(height=2, anchor="nw")
        status.pack(side="left", fill="x")
        self.compact_hint = self._label(panel, var=self.answer_status, color=ACCENT, size=9)
        self.compact_hint.configure(height=1)

        self.body = tk.Frame(panel, bg=BG)
        self.body.pack(fill="both", expand=True, pady=(8, 0))
        base = tk.Frame(self.body, bg=BG)
        base.pack(fill="x", pady=(0, 8))
        tk.Frame(base, bg=BORDER, height=1).pack(fill="x", pady=(0, 8))
        base_header = tk.Frame(base, bg=BG)
        base_header.pack(fill="x", pady=(0, 6))
        self.base_heading = self._label(base_header, "БАЗА ЗНАНИЙ", color=MUTED, size=8, bold=True,
                                       localized=True)
        self.base_heading.pack(side="left")
        self.base_name = self._label(base_header, var=self.project_label, size=10, bold=True, wrap=315)
        self.choose = ttk.Combobox(base_header, textvariable=self.project_label, state="readonly",
                                   style="Copilot.TCombobox", width=20)
        self.choose.bind("<<ComboboxSelected>>", self._select)
        self.new_base_button = self._button(base_header, "Новая база", self._new_knowledge_base, localized=True)
        self._button(base_header, "Настройки", lambda: show_settings(self), localized=True).pack(side="right")
        self.new_base_button.pack(side="right", padx=(0, 6))
        row = tk.Frame(base, bg=BG)
        row.pack(fill="x")
        self.import_button = self._button(row, "Импорт файла…", self._import_knowledge,
                                          primary=True, localized=True)
        self.import_button.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.copy_prompt_button = self._button(row, "Скопировать промпт", self._copy_knowledge_prompt,
                                              localized=True)
        self.copy_prompt_button.pack(side="left", fill="x", expand=True)
        self.browse_button = self._button(row, "Открыть базу", self._browse_knowledge, localized=True)
        self.first_import_hint = self._label(
            base, "Добавь файл .md или .txt. Если файла нет, скопируй промпт в чат проекта в Codex или Claude Code.",
            color=MUTED, size=9, localized=True)
        self.first_import_hint.pack(fill="x", pady=(6, 0))
        state_row = tk.Frame(base, bg=BG)
        self.base_status_row = state_row
        state_row.pack(fill="x", pady=(4, 0))
        self.pin_button = self._button(state_row, "", self._pin)
        self.pin_button.pack(side="right")
        index_status = self._label(state_row, var=self.index_status, color=MUTED, size=8, wrap=302)
        index_status.configure(height=2, anchor="w")
        index_status.pack(side="left", fill="x", expand=True)
        self.card_frame = tk.Frame(self.body, bg=BG)
        heard = tk.Frame(self.card_frame, bg=SURFACE, padx=10, pady=6,
                         highlightbackground=BORDER, highlightthickness=1)
        heard.pack(fill="both", expand=True)
        transcript_header = tk.Frame(heard, bg=SURFACE)
        transcript_header.pack(fill="x")
        self._label(transcript_header, "Расшифровка", color=INK, size=11, bold=True,
                    bg=SURFACE, localized=True).pack(side="left")
        self._button(transcript_header, "К концу", lambda: self.transcript.see("end"),
                     localized=True).pack(side="right")
        transcript_box = tk.Frame(heard, bg=SURFACE)
        transcript_box.pack(fill="both", expand=True, pady=(4, 0))
        self.transcript = tk.Text(transcript_box, width=45, height=5, wrap="word", bg=SURFACE, fg=INK,
                                  relief="flat", padx=1, pady=3, borderwidth=0, highlightthickness=0,
                                  font=("Segoe UI", 10), state="disabled", exportselection=False,
                                  cursor="xterm", selectbackground="#3e6052", selectforeground="#ffffff",
                                  inactiveselectbackground="#3e6052")
        self.transcript.pack(fill="both", expand=True)
        self._text_scrollbar(self.transcript)
        self.transcript_empty = self._label(transcript_box, "Здесь появится речь, которую воспроизводит Windows.",
                                            color=MUTED, size=10, bg=SURFACE, localized=True)
        self.transcript_empty.place(x=1, y=6)
        action = tk.Frame(heard, bg=SURFACE)
        action.pack(fill="x", pady=(6, 0))
        self.ask_button = self._button(action, "Дай ответ", self._ask_selection, primary=True, localized=True)
        self.ask_button.pack(side="left", padx=(0, 8))
        self.ask_button.configure(state="disabled")
        self.transcript.bind("<<Selection>>", self._selection_changed)
        self._label(action, var=self.selection_status, color=MUTED, size=9, bg=SURFACE, wrap=280).pack(
            side="left", fill="x", expand=True)

        composer = tk.Frame(self.card_frame, bg=BG)
        composer.pack(fill="x", pady=(8, 0))
        self._label(composer, "Свой вопрос · Ctrl+Enter", color=MUTED, size=9,
                    localized=True).pack(anchor="w", pady=(0, 4))
        input_row = tk.Frame(composer, bg=BG)
        input_row.pack(fill="x")
        self.typed_question = tk.Text(input_row, width=1, height=2, wrap="word",
                                      bg=SURFACE, fg=INK, insertbackground=INK, font=("Segoe UI", 10),
                                      relief="flat", padx=6, pady=5, borderwidth=0,
                                      highlightthickness=1, highlightbackground=BORDER,
                                      highlightcolor=ACCENT, undo=True, exportselection=False,
                                      selectbackground="#3e6052", selectforeground="#ffffff")
        self.typed_ask_button = self._button(input_row, "Спросить", self._ask_typed,
                                            primary=True, localized=True)
        self.typed_ask_button.pack(side="right", padx=(8, 0))
        self.typed_ask_button.state(["disabled"])
        self.typed_question.pack(side="left", fill="x", expand=True)
        self.typed_question.bind("<<Modified>>", self._typed_changed)
        self.typed_question.bind("<Control-Return>", self._ask_typed)
        self.typed_ask_button.bind("<Control-Return>", self._ask_typed)
        self.typed_question.bind("<Tab>", lambda _: self._question_focus(False))
        self.typed_question.bind("<Shift-Tab>", lambda _: self._question_focus(True))

        response = tk.Frame(self.card_frame, bg=SURFACE, padx=10, pady=6,
                            highlightbackground=BORDER, highlightthickness=1)
        response.pack(fill="both", expand=True, pady=(8, 0))
        response_header = tk.Frame(response, bg=SURFACE)
        response_header.pack(fill="x")
        self.heading = self._label(response_header, "Ответ", size=11, bold=True, bg=SURFACE)
        self.heading.pack(side="left")
        self.details = self._button(response_header, "Источники", self._show_sources)
        self.details.pack(side="right")
        self.answer_subject = self._label(response, color=MUTED, size=9, bg=SURFACE)
        self.answer_subject.configure(height=1)
        self.answer_subject.pack(fill="x", pady=(2, 0))
        self.answer_area = tk.Frame(response, bg=SURFACE, height=92)
        self.answer_area.pack(fill="both", expand=True, pady=(3, 0))
        self.answer_area.pack_propagate(False)
        self.answer_empty = self._label(self.answer_area, "Выдели реплику или напиши свой вопрос.",
                                        color=MUTED, size=10, bg=SURFACE, localized=True)
        self._label(response, var=self.answer_status, color=ACCENT, size=8,
                    bg=SURFACE).pack(fill="x")
        self.options = []
        for index in range(MAX_OPTIONS):
            option = tk.Frame(self.answer_area, bg=SURFACE)
            answer = tk.Text(option, width=1, height=1, wrap="word", bg=SURFACE, fg=INK,
                             relief="flat", padx=1, pady=0, borderwidth=0, highlightthickness=0,
                             font=("Segoe UI", 10), state="disabled")
            answer.pack(side="left", fill="both", expand=True)
            self._text_scrollbar(answer)
            self.options.append((option, answer))
        self.card_frame.pack(fill="both", expand=True)

        footer = tk.Frame(self.body, bg=BG)
        footer.pack(fill="x", pady=(10, 0))
        self.prev_button = self._button(footer, "‹", lambda: self._navigate(-1), width=3)
        self.prev_button.pack(side="left")
        self.next_button = self._button(footer, "›", lambda: self._navigate(1), width=3)
        self.next_button.pack(side="left", padx=(4, 8))
        self.position = self._label(footer, color=MUTED, size=9)
        self.position.pack(side="left")
        self.live_button = self._button(footer, "К последней", self._go_live, localized=True)
        self.live_button.pack(side="right")
        self.history_button = self._button(footer, "История", self._show_history, localized=True)
        self.history_button.pack(side="right", padx=5)
        self._update_overlay_controls()
        self._render_selection()
        w.update_idletasks()
        self.expanded_min_height = panel.winfo_reqheight()
        w.minsize(WIDTH, self.expanded_min_height)
        w.geometry(f"{WIDTH}x{self.expanded_min_height}")

    def _button(self, parent, text, command, *, primary=False, localized=False, **kwargs):
        style = "CopilotPrimary.TButton" if primary else "Copilot.TButton"
        widget = ttk.Button(parent, text=text, command=command, style=style, **kwargs)
        return self._localize(widget, text) if localized else widget

    @staticmethod
    def _text_scrollbar(widget):
        scroll = ttk.Scrollbar(widget.master, command=widget.yview, style="Copilot.Vertical.TScrollbar")

        def update(first, last):
            scroll.set(first, last)
            if float(first) == 0 and float(last) == 1:
                scroll.pack_forget()
            elif not scroll.winfo_manager():
                scroll.pack(side="right", fill="y", before=widget)

        widget.configure(yscrollcommand=update)

    def _fold(self):
        self.folded = not self.folded
        w = self.window
        if self.folded:
            self._close_sources()
            self._close_history()
            self.restore_maximized = w.state() == "zoomed"
            if self.restore_maximized:
                w.state("normal")
                w.update_idletasks()
            self.expanded_height = w.winfo_height()
            self.body.pack_forget()
            self.compact_hint.pack(fill="x", pady=(3, 0))
            w.update_idletasks()
            compact_height = self.body.master.winfo_reqheight()
            w.minsize(WIDTH, compact_height)
            w.geometry(f"{w.winfo_width()}x{compact_height}")
            w.resizable(True, False)
        else:
            self.compact_hint.pack_forget()
            self.body.pack(fill="both", expand=True, pady=(8, 0))
            w.resizable(True, True)
            w.minsize(WIDTH, self.expanded_min_height)
            w.geometry(f"{w.winfo_width()}x{self.expanded_height}")
            if self.restore_maximized:
                w.state("zoomed")
        self._update_overlay_controls()

    def _update_overlay_controls(self):
        self.fold_button.configure(text=self._tr("Развернуть" if self.folded else "Свернуть"))
        self.pin_button.configure(text=self._tr("Поверх · вкл." if self.top.get() else "Поверх · выкл."))

    def _pin(self):
        self.top.set(not self.top.get())
        self.window.attributes("-topmost", self.top.get())
        self._update_overlay_controls()

    def _toggle(self):
        if self.speech_unloading.is_set():
            return
        if self.live.is_set():
            self.live.clear()
            self._set_copy(self.listen_label, "Слушать")
            self.status_dot.configure(fg=MUTED)
            self._set_copy(self.status, "Пауза · звук не обрабатывается")
        else:
            self.live.set()
            self._set_copy(self.listen_label, "Пауза")
            self._set_copy(self.status, "Подключение к звуку Windows…")

    def _known_projects(self):
        return discover_projects(extra=self.settings["extra_roots"], documents_only=True,
                                 managed=RUNTIME / "knowledge")

    def _projects(self, projects):
        self.base_items = list(projects)
        counts = {}
        for p in self.base_items:
            counts[p.name] = counts.get(p.name, 0) + 1
        seen = {}
        self.bases = {}
        all_label = self._tr("Все базы")
        for p in self.base_items:
            seen[p.name] = seen.get(p.name, 0) + 1
            label = (p.name if counts[p.name] == 1 and p.name != all_label
                     else f"{p.name} · {seen[p.name]}")
            while label == all_label or label in self.bases:
                seen[p.name] += 1
                label = f"{p.name} · {seen[p.name]}"
            self.bases[label] = p.root
        self.projects = ({all_label: tuple(self.bases.values()), **self.bases} if self.bases else {})
        self.choose["values"] = list(self.projects)
        self.base_heading.pack_forget()
        self.base_name.pack_forget()
        self.choose.pack_forget()
        if len(self.projects) > 1:
            self.choose.pack(side="left", fill="x", expand=True, padx=(0, 6))
        elif self.projects:
            self.base_name.pack(side="left", fill="x", expand=True, padx=(0, 6))
        else:
            self.base_heading.pack(side="left")
        current = next((n for n, p in self.projects.items() if p == self.project), None)
        if current is None:
            current = next((n for n, p in self.projects.items()
                            if ("*" if isinstance(p, tuple) else str(p)) == self.settings["project"]),
                           next(iter(self.bases), ""))
        self.project_label.set(current or self._tr("База не выбрана"))
        if self.projects.get(current) != self.project:
            self._select()
        self._update_knowledge_entry()

    def _update_knowledge_entry(self):
        if self.project is None:
            self.browse_button.pack_forget()
        elif not self.browse_button.winfo_manager():
            self.browse_button.pack(side="left", padx=(6, 0))
        if self.project is None or self.indexed_count == 0:
            if not self.first_import_hint.winfo_manager():
                self.first_import_hint.pack(fill="x", pady=(6, 0), before=self.base_status_row)
        else:
            self.first_import_hint.pack_forget()

    def _select(self, _event=None):
        selected = self.projects.get(self.project_label.get())
        if _event is not None and selected is not None:
            try:
                value = "*" if isinstance(selected, tuple) else str(selected)
                save_settings({"project": value})
                self.settings["project"] = value
            except OSError as error:
                messagebox.showerror(self._tr("Не удалось сохранить выбор"), str(error), parent=self.window)
        self.project = selected
        if self.knowledge_window is not None and self.knowledge_window.winfo_exists():
            self.knowledge_window.destroy()
        self.knowledge_window = None
        self.indexed_count = None
        if self.pipeline:
            self.pipeline.cancel_answer()
        self._close_sources()
        self._set_copy(self.answer_status, "")
        self._load_history()
        self._set_copy(self.index_status, "Подготавливаю базу…")
        self._update_knowledge_entry()
        self._selection_changed()
        self.scan.set()

    def _copy_knowledge_prompt(self):
        try:
            suffix = {"ru": ".ru", "es": ".es"}.get(self.ui_language, "")
            prompt = (BASE / "docs" / f"knowledge-pack-prompt{suffix}.md").read_text(encoding="utf-8")
            self.window.clipboard_clear()
            self.window.clipboard_append(prompt)
        except (OSError, tk.TclError) as error:
            messagebox.showerror(self._tr("Не удалось скопировать промпт"), str(error), parent=self.window)
            return False
        self._set_copy(self.index_status, "Промпт скопирован. Вставь его в Codex или Claude Code, затем импортируй выжимку.")
        return True

    def _new_knowledge_base(self):
        name = choose_base_name(self)
        if name is None:
            return
        try:
            root = create_named_base(RUNTIME, name)
            save_settings({"project": str(root)})
        except (OSError, ValueError) as error:
            messagebox.showerror(self._tr("Не удалось создать базу"), self._detail(error), parent=self.window)
            return
        self.settings["project"] = str(root)
        self.project = None
        self.index_generation = object()
        self._projects(self._known_projects())
        self._set_copy(self.index_status, "База создана. Скопируй промпт или импортируй готовую выжимку.")

    def _browse_knowledge(self):
        if self.project is None or self.index is None:
            self._set_copy(self.index_status, "Создай или выбери базу на главном экране.")
            return
        if self.knowledge_window is not None and self.knowledge_window.winfo_exists():
            self.knowledge_window.lift()
        else:
            self.knowledge_window = show_knowledge_window(self, self.window, self.index, self.project)

    def _import_knowledge(self):
        if self.import_button.instate(["disabled"]):
            return
        path = filedialog.askopenfilename(
            parent=self.window, title=self._tr("Выбери готовую выжимку"),
            filetypes=[(self._tr("Документы Markdown и текст"), "*.md *.txt")])
        if not path:
            return
        destination = choose_import_destination(self, Path(path))
        if destination is None:
            return
        target, name, document_name = destination
        self.import_button.state(["disabled"])
        self.copy_prompt_button.state(["disabled"])
        self.new_base_button.state(["disabled"])
        self.import_target = self.project
        self._set_copy(self.index_status, "Импортирую выжимку…")

        def work():
            try:
                root = import_summary(RUNTIME, path, target=target, name=name, document_name=document_name)
                self.ui.put(("import_done", (root, "")))
            except (OSError, ValueError) as error:
                self.ui.put(("import_done", (None, str(error))))

        threading.Thread(target=work, daemon=True).start()

    def _index_loop(self):
        while not self.closed.is_set():
            self.scan.clear()
            index = self.index
            generation = self.index_generation
            scope = self.project
            extra = tuple(self.settings["extra_roots"])
            projects = self._known_projects()
            self.ui.put(("projects", (generation, extra, projects)))
            for p in sorted(projects, key=lambda item: item.root not in scope_roots(scope)):
                if self.closed.is_set():
                    return
                if index is not self.index:
                    break
                try:
                    count, stamp = index.refresh(p.root)
                    self.ui.put(("index", (generation, index, p.root, count, stamp)))
                except Exception as error:
                    self.ui.put(("index_error", (generation, index, p.root, str(error))))
            if isinstance(scope, tuple) and index is self.index:
                try:
                    count, stamp = index.status(scope)
                    self.ui.put(("index", (generation, index, scope, count, stamp)))
                except Exception as error:
                    self.ui.put(("index_error", (generation, index, scope, str(error))))
            self.scan.wait(12)

    def _warm_llm(self, brain, old_brain=None):
        try:
            if old_brain is not None:
                old_brain.close()
            if self.closed.is_set() or brain is not self.llm:
                return
            brain.warm()
            self.ui.put(("llm", (brain, "")))
        except Exception as error:
            LOG.warning("answer_model_unavailable %s", error)
            self.ui.put(("llm", (brain, " · модель ответов недоступна")))

    def _speech_factory(self, settings, reset):
        return lambda: create_asr(
            RUNTIME, settings["stt_engine"],
            lambda msg: self.ui.put(("status", (reset, "{error}", {"error": msg}))),
            url=settings["stt_url"], model=settings["stt_model"],
            whisper_model=settings["whisper_model"], whisper_device=settings["whisper_device"],
            qwen_model=settings["qwen_model"], qwen_device=settings["qwen_device"],
        )

    def _warm_asr(self, reset):
        try:
            if reset.is_set() or self.closed.is_set():
                return
            self.speech_session.warm()
            if loaded := self.speech_session.loaded():
                LOG.info("asr_ready model=%s device=%s", *loaded)
        except Exception as error:
            self.ui.put(("status", (reset, "Распознавание не запустилось: {error}", {"error": str(error)})))

    def unload_speech(self):
        speech = self.speech_session
        if self.settings["stt_engine"] == "openai_local" or speech is None or not speech.loaded():
            return
        if self.speech_unloading.is_set():
            return
        if self.live.is_set():
            self._toggle()
        if self.pipeline is not None:
            self.pipeline.cancel_speech()
        self.speech_unloading.set()

        def work():
            try:
                speech.unload()
            except (OSError, RuntimeError, ValueError) as error:
                LOG.warning("speech_unload_failed %s", error)
            finally:
                self.speech_unloading.clear()

        threading.Thread(target=work, daemon=True).start()

    def _capture(self):
        while not self.closed.is_set():
            if not self.live.wait(.35) or self.closed.is_set():
                continue
            with self.capture_lock:
                reset = self.capture_reset
                settings = self.settings
            stop = _CaptureStop(self.closed, self.live, reset)
            try:
                source = loopback(stop, lambda name: self.ui.put(("device", (reset, name))))
                prefetch = settings["stt_engine"] == "qwen" and settings["qwen_device"] == "cuda"
                for kind, pcm in detect(source, stop, settings["pause_ms"],
                                        max_wait_ms=15000, replay_turn=False, prefetch=prefetch):
                    with self.capture_lock:
                        if stop.is_set():
                            break
                        self.pipeline.accept_audio(kind, pcm, self.project, self.settings["glossary"])
            except Exception as error:
                if not stop.is_set():
                    self.ui.put(("status", (reset, "Звук недоступен · переподключение: {error}",
                                            {"error": str(error)})))
                    reset.wait(.8)

    def _close_sources(self):
        if self.source_window:
            self.source_window.destroy()
            self.source_window = None

    def _load_history(self):
        try:
            self.entries = self.history.recent(self.project)
        except (sqlite3.Error, ValueError, KeyError):
            self.entries = []
            LOG.warning("history_load_failed")
        self.review_id = None
        self._render_selection()
        self._refresh_history_window()

    def _save_card(self, text, card):
        try:
            entry = self.history.add(self.project, text, card)
        except sqlite3.Error:
            entry = Entry(-time.time_ns(), time.time(), text, card)
            LOG.warning("history_write_failed")
        self.entries.append(entry)
        self.entries = self.entries[-self.history.limit:]
        if self.review_id is not None and all(item.id != self.review_id for item in self.entries):
            self.review_id = self.entries[0].id
        self._render_selection()
        self._refresh_history_window()

    def _review_index(self):
        return next((i for i, entry in enumerate(self.entries) if entry.id == self.review_id),
                    len(self.entries) - 1)

    def _navigate(self, step):
        index = self._review_index() + step
        if 0 <= index < len(self.entries):
            self.review_id = self.entries[index].id
            self._render_selection()
            self._refresh_history_window()
        return "break"

    def _go_live(self):
        self.review_id = None
        self._render_selection()
        self._refresh_history_window()
        return "break"

    def _render_selection(self):
        count = len(self.entries)
        index = self._review_index()
        if self.review_id is not None:
            new = count - index - 1
            label = self._tr("{index} из {count}", index=index + 1, count=count)
            if new:
                label += self._tr(" · новых {count}", count=new)
        else:
            label = self._tr("Ответов · {count}", count=count)
        self.position.configure(text=label)
        self.prev_button.configure(state="normal" if index > 0 else "disabled")
        self.next_button.configure(state="normal" if 0 <= index < count - 1 else "disabled")
        self.live_button.configure(state="normal" if self.review_id is not None else "disabled")
        self.history_button.configure(state="normal" if count else "disabled")
        if index >= 0:
            entry = self.entries[index]
            self.show_card(entry.text, entry.card)
        else:
            self.show_card("", None)

    def _show_history(self):
        if self.history_window:
            self.history_window.lift()
            return
        popup = self.history_window = tk.Toplevel(self.window)
        popup.title(self._tr("История · Agent Utka"))
        popup.geometry("510x360")
        popup.configure(bg=BG)
        popup.attributes("-topmost", self.top.get())
        self.history_heading = self._label(popup, self._tr("История подсказок"), size=13, bold=True)
        self.history_heading.pack(fill="x", padx=12, pady=9)
        frame = tk.Frame(popup, bg=BG)
        frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.history_list = tk.Listbox(frame, bg=SURFACE, fg=INK, selectbackground=BORDER,
                                      selectforeground=INK, borderwidth=0, highlightthickness=0,
                                      font=("Segoe UI", 10), activestyle="none", exportselection=False)
        scroll = ttk.Scrollbar(frame, command=self.history_list.yview)
        scroll.pack(side="right", fill="y")
        self.history_list.configure(yscrollcommand=scroll.set)
        self.history_list.pack(side="left", fill="both", expand=True)
        self.history_list.bind("<<ListboxSelect>>", self._pick_history)
        self._refresh_history_window()
        popup.protocol("WM_DELETE_WINDOW", self._close_history)

    def _close_history(self):
        if self.history_window:
            self.history_window.destroy()
            self.history_window = None

    def _refresh_history_window(self):
        if self.history_window is None:
            return
        listing = self.history_list
        listing.delete(0, "end")
        for entry in reversed(self.entries):
            stamp = time.strftime("%d.%m %H:%M", time.localtime(entry.captured_at))
            preview = " ".join(entry.text.split())
            listing.insert("end", f"{stamp}    {preview[:68]}" + ("…" if len(preview) > 68 else ""))
        if self.review_id is not None:
            row = len(self.entries) - 1 - self._review_index()
            listing.selection_set(row)
            listing.see(row)

    def _pick_history(self, _event=None):
        selected = self.history_list.curselection()
        if selected:
            self.review_id = self.entries[-1 - selected[0]].id
            self._render_selection()

    def _append_transcript(self, text):
        text = text.strip()
        if not text:
            return
        self.last_utterance = text
        self.transcript_empty.place_forget()
        widget = self.transcript
        follow = widget.yview()[1] >= .999 and not widget.tag_ranges("sel")
        separator = "\n\n" if widget.index("end-1c") != "1.0" else ""
        widget.configure(state="normal")
        widget.insert("end-1c", separator + text)
        widget.configure(state="disabled")
        if follow:
            widget.see("end")
        self._selection_changed()

    def _selected_text(self):
        selected = self.transcript.tag_ranges("sel")
        return self.transcript.get(*selected).strip() if len(selected) == 2 else ""

    def _selection_changed(self, _event=None):
        text = self._selected_text()
        self.ask_button.configure(state="normal" if text or self.last_utterance else "disabled")
        if text:
            self._set_copy(self.selection_status, "Выделено · {count} симв. · Ctrl+Enter", count=len(text))
        elif self.last_utterance:
            self._set_copy(self.selection_status, "Последняя реплика · Ctrl+Enter")
        else:
            self._set_copy(self.selection_status, "Речь появится в расшифровке")

    def _ask_selection(self, _event=None):
        text = self._selected_text() or self.last_utterance
        return self._request_answer(text, "Дождись реплики в расшифровке.")

    def _typed_changed(self, _event=None):
        self.typed_ask_button.state(
            ["!disabled"] if self.typed_question.get("1.0", "end-1c").strip() else ["disabled"])
        self.typed_question.edit_modified(False)

    def _question_focus(self, previous):
        target = self.typed_question.tk_focusPrev() if previous else self.typed_question.tk_focusNext()
        target.focus_set()
        return "break"

    def _ask_typed(self, _event=None):
        return self._request_answer(self.typed_question.get("1.0", "end-1c").strip(),
                                    "Напиши вопрос в поле.")

    def _request_answer(self, text, empty_message):
        if not text:
            self._set_copy(self.answer_status, empty_message)
        elif self.project is None:
            self._set_copy(self.answer_status, "Импортируй выжимку, чтобы получать ответы.")
        elif self.import_target == self.project or (self.index is not None and self.indexed_count is None):
            self._set_copy(self.answer_status, "База ещё готовится. Попробуй после обновления.")
        elif self.indexed_count == 0:
            self._set_copy(self.answer_status, "Импортируй выжимку, чтобы получать ответы.")
        elif self.index is not None and not self.llm_done:
            self._set_copy(self.answer_status, "Прогрев локальной модели подсказок…")
        elif self.pipeline and self.pipeline.ask(text, self.project):
            self.review_id = None
            self._set_copy(self.answer_status, "Ищу ответ во всех базах…" if isinstance(self.project, tuple)
                           else "Ищу ответ в базе проекта…")
        else:
            self._set_copy(self.answer_status, "Подготовка локальных моделей…")
        return "break"

    @staticmethod
    def _set_text(widget, text):
        if widget.get("1.0", "end-1c") != text:
            widget.configure(state="normal")
            widget.delete("1.0", "end")
            widget.insert("1.0", text)
            widget.configure(state="disabled")
            widget.yview_moveto(0)

    def show_card(self, text, card):
        if self.last_card is not card:
            self._close_sources()
        self.last_card = card
        self.heading.configure(text=self._tr(card.label if card else "Ответ"))
        subject = " ".join(text.split())
        self.answer_subject.configure(text=subject[:60] + ("…" if len(subject) > 60 else ""))
        self.answer_empty.pack_forget()
        visible = 0
        for index, (frame, answer) in enumerate(self.options):
            if card is None or index >= len(card.options):
                frame.pack_forget()
                continue
            option, ids = card.options[index]
            if not ids and card.label.startswith("Услышано") and option == text.strip():
                frame.pack_forget()
                continue
            suffix = "  [" + ", ".join(map(str, ids)) + "]" if ids else ""
            prefix = f"{index + 1}. " if len(card.options) > 1 else ""
            if card.label in ("Нет ответа в базе", "Ошибка ответа") and not ids:
                option = self._tr(option)
            self._set_text(answer, prefix + option + suffix)
            frame.pack(fill="both", expand=True)
            visible += 1
        if not visible:
            self.answer_empty.pack(fill="both", expand=True, anchor="nw")
        source_count = len(card.sources) if card else 0
        self.details.configure(text=self._tr("Источники · {count}", count=source_count)
                               if source_count else self._tr("Источники"),
                               state="normal" if source_count else "disabled")

    def _show_sources(self):
        if not self.last_card or not self.last_card.sources:
            return
        if self.source_window:
            self.source_window.lift()
            return
        popup = self.source_window = tk.Toplevel(self.window)
        popup.configure(bg=BG)
        popup.transient(self.window)
        popup.attributes("-topmost", self.top.get())
        popup.geometry("620x350")
        self.source_heading = self._label(popup, size=14, bold=True)
        self.source_heading.pack(fill="x", padx=14, pady=(10, 2))
        self.source_subtitle = self._label(popup, color=MUTED, size=9)
        self.source_subtitle.pack(fill="x", padx=14, pady=(0, 8))
        panel = tk.Frame(popup, bg=SURFACE)
        panel.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        text = self.source_text = tk.Text(panel, wrap="word", bg=SURFACE, fg=INK, padx=12, pady=10,
                                          font=("Segoe UI", 10), relief="flat", borderwidth=0)
        text.tag_configure("path", foreground=ACCENT, font=("Segoe UI", 10, "bold"))
        text.pack(fill="both", expand=True)
        self._text_scrollbar(text)
        self._render_sources()

        def close(_event=None):
            self._close_sources()
            return "break"

        popup.protocol("WM_DELETE_WINDOW", close)
        popup.bind("<Escape>", close)

    def _render_sources(self):
        self.source_window.title(self._tr("Источники · Agent Utka"))
        self.source_heading.configure(text=self._tr("Источники ответа"))
        self.source_subtitle.configure(text=self._tr("Фрагменты, на которых основан ответ."))
        text = self.source_text
        position = text.yview()[0]
        text.configure(state="normal")
        text.delete("1.0", "end")
        used = {i for _, ids in self.last_card.options for i in ids}
        for i, source in enumerate(self.last_card.sources, 1):
            if not used or i in used:
                location = self._tr("строка {line}", line=source.line)
                path = source_location(self.project, source.path)
                text.insert("end", f"[{i}] {path} · {location}\n", "path")
                text.insert("end", f"{source.text}\n\n")
        text.configure(state="disabled")
        text.yview_moveto(position)

    def _drain(self):
        self.drain_id = None
        try:
            while True:
                kind, data = self.ui.get_nowait()
                if kind == "projects":
                    generation, extra, projects = data
                    if generation is self.index_generation and extra == tuple(self.settings["extra_roots"]):
                        self._projects(projects)
                elif (kind == "index" and data[0] is self.index_generation and data[1] is self.index
                      and data[2] == self.project != self.import_target):
                    _, _, _, count, _ = data
                    self.indexed_count = count
                    self._update_knowledge_entry()
                    if count:
                        self._set_copy(self.index_status, "Готово · напиши вопрос или выдели реплику в расшифровке.")
                    else:
                        self._set_copy(self.index_status, "Импортируй выжимку, чтобы получать ответы.")
                elif (kind == "index_error" and data[0] is self.index_generation and data[1] is self.index
                      and data[2] == self.project != self.import_target):
                    self._set_copy(self.index_status, "Ошибка обновления: {error}", error=data[3])
                elif kind == "import_done":
                    root, error = data
                    self.import_target = None
                    self.import_button.state(["!disabled"])
                    self.copy_prompt_button.state(["!disabled"])
                    self.new_base_button.state(["!disabled"])
                    self.scan.set()
                    if error:
                        self._set_copy(self.index_status, "Импорт не завершён. Проверь файл и повтори.")
                        messagebox.showerror(self._tr("Импорт базы знаний"), self._detail(error), parent=self.window)
                    else:
                        self.index_generation = object()
                        try:
                            save_settings({"project": str(root)})
                        except OSError as error:
                            messagebox.showerror(self._tr("Не удалось сохранить выбор"), str(error), parent=self.window)
                        self.settings["project"] = str(root)
                        self.project = None
                        self._projects(self._known_projects())
                elif kind == "status" and data[0] is self.capture_reset and self.live.is_set():
                    _, source, values = data
                    self._set_copy(self.status, source, **values)
                elif kind == "llm" and data[0] is self.llm:
                    self.llm_status = data[1]
                    self.llm_done = True
                elif kind == "device" and data[0] is self.capture_reset and self.live.is_set():
                    self.device_name = data[1]
                    self.status_dot.configure(fg=ACCENT)
                    self._set_copy(self.status, "Слушаю · {device}{warning}",
                                   device=self.device_name, warning=self.llm_status)
                elif kind == "turn" and self.pipeline.current(data[0], data[1]):
                    self._turn(data[1], data[2])
        except queue.Empty:
            pass
        if not self.closed.is_set():
            self.drain_id = self.window.after(55, self._drain)

    def _turn(self, event, data):
        if event == "transcript":
            self._append_transcript(data)
        elif event == "card":
            text, card, elapsed = data
            self._save_card(text, card)
            if self.review_id is None and not self.folded:
                LOG.info("card_displayed options=%s sources=%s processing_seconds=%.2f",
                         len(card.options), len(card.sources), elapsed)
            if card.sources:
                self._set_copy(self.answer_status, "Готово · {elapsed:.1f} с", elapsed=elapsed)
            else:
                self._set_copy(self.answer_status, card.label)
            return
        elif event == "answer_error":
            LOG.warning("manual_answer_failed")
            self._set_copy(self.answer_status, "Не удалось получить ответ из базы")
            return
        elif event == "search_error":
            LOG.warning("local_search_unavailable")
            self._set_copy(self.answer_status, data)
            return
        if not self.live.is_set():
            return
        if event == "hearing":
            LOG.info("speech_detected")
            self.status_dot.configure(fg=ACCENT)
            self._set_copy(self.status, "Слышу речь…")
        elif event == "asr":
            self.status_dot.configure(fg=ACCENT)
            self._set_copy(self.status, "Распознаю реплику…")
        elif event == "error":
            LOG.warning("processing_failed")
            self.status_dot.configure(fg="#ff9d9e")
            self._set_copy(self.status, "{error}", error=data)
        elif event in ("transcript", "idle"):
            self.status_dot.configure(fg=ACCENT)
            self._set_copy(self.status, "Слушаю · {device}{warning}",
                           device=self.device_name, warning=self.llm_status)

    def close(self):
        self.closed.set()
        self.live.clear()
        self.scan.set()
        if self.drain_id is not None:
            self.window.after_cancel(self.drain_id)
            self.drain_id = None
        if self.pipeline:
            self.pipeline.close()
        self.history.close()
        self.llm.close()
        self.window.destroy()


class _CaptureStop:
    def __init__(self, closed, live, reset):
        self.closed, self.live, self.reset = closed, live, reset

    def is_set(self):
        return self.closed.is_set() or self.reset.is_set() or not self.live.is_set()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui-test", action="store_true")
    ap.add_argument("--launch-check", action="store_true")
    ap.add_argument("--installed", action="store_true")
    args = ap.parse_args()
    RUNTIME.mkdir(exist_ok=True)
    if not args.ui_test:
        handler = RotatingFileHandler(RUNTIME / "assistant.log", maxBytes=200000,
                                      backupCount=1, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        LOG.addHandler(handler)
        LOG.setLevel(logging.INFO)
        LOG.info("started")
    window = tk.Tk()
    if os.name == "nt":
        icon = BASE / "assets" / "utka.ico"
        if icon.is_file():
            window.iconbitmap(default=str(icon))
    settings = load_settings()
    if args.installed and not (args.ui_test or args.launch_check):
        from .bootstrap import setup_window

        if not setup_window(window, settings):
            window.destroy()
            return
    if args.ui_test:
        settings["ui_language"] = "ru"
    app = Overlay(window, settings, demo=args.ui_test)
    if args.ui_test:
        app.live.set()
        app._set_copy(app.status, "Слушаю · {device}{warning}", device="Demo audio", warning="")
        calls = []

        class ManualRequest:
            def ask(self, text, root):
                calls.append((text, root))
                return True

            def close(self):
                pass

        app.pipeline = ManualRequest()
        app.project = BASE

        def layout():
            window.update()
            return window.winfo_geometry(), app.history_button.winfo_rooty()

        expanded_layout = layout()
        question = "Как обновляется токен?"
        assert app.ask_button.instate(["disabled"])
        app.ask_button.invoke()
        assert not calls
        app._turn("transcript", question)
        window.update()
        fragment = question[4:15]
        x1, y1, _, _ = app.transcript.bbox("1.4")
        x2, y2, _, _ = app.transcript.bbox("1.15")
        app.transcript.event_generate("<ButtonPress-1>", x=x1 + 1, y=y1 + 3)
        app.transcript.event_generate("<B1-Motion>", x=x2 + 1, y=y2 + 3)
        app.transcript.event_generate("<ButtonRelease-1>", x=x2 + 1, y=y2 + 3)
        window.update()
        assert app.ask_button.instate(["!disabled"])
        assert app.selection_status.get() == f"Выделено · {len(fragment)} симв. · Ctrl+Enter"
        app._turn("transcript", "Вторая реплика")
        assert layout() == expanded_layout, "Transcript moved the expanded overlay"
        assert app.transcript.get("1.0", "end-1c") == question + "\n\nВторая реплика"
        assert app.transcript.get("sel.first", "sel.last") == fragment
        assert not app.entries and not calls
        app._toggle()
        app.ask_button.focus_force()
        window.update()
        app.ask_button.invoke()
        assert calls == [(fragment, BASE)]
        assert app.last_card is None
        card = Card(
            (("Токен обновляется через локальный шлюз.", [1]),
             ("Обновление токена выполняет локальный шлюз.", [1]),
             ("За обновление токена отвечает локальный шлюз.", [1])),
            (Source(BASE / "docs" / "demo.md", 1, "Токен обновляется через локальный шлюз."),),
            "Варианты ответа")
        app._turn("card", (fragment, card, .9))
        assert layout() == expanded_layout, "Full suggestions moved the expanded overlay"
        assert app.card_frame.winfo_ismapped()
        assert window.winfo_width() < 580
        assert all(frame.winfo_ismapped() for frame, _ in app.options)
        assert app.details.cget("text") == "Источники · 1"
        app._toggle()
        app._show_sources()
        source_window = app.source_window
        shown = app.source_text.get("1.0", "end")
        assert "docs/demo.md" in shown and str(BASE) not in shown
        for event, value in (("hearing", None), ("asr", None), ("transcript", "Новая реплика")):
            app._turn(event, value)
            assert layout() == expanded_layout, f"{event} moved the expanded overlay"
            assert app.last_card == card and app.source_window is source_window
        assert app.transcript.get("sel.first", "sel.last") == fragment
        assert app.transcript.get("1.0", "end-1c") == question + "\n\nВторая реплика\n\nНовая реплика"
        assert len(app.entries) == 1 and len(calls) == 1
        app.transcript.tag_remove("sel", "1.0", "end")
        window.update()
        assert app.ask_button.instate(["!disabled"])
        assert app.selection_status.get() == "Последняя реплика · Ctrl+Enter"
        app.transcript.focus_force()
        window.update()
        app.transcript.event_generate("<Control-Return>")
        window.update()
        assert calls == [(fragment, BASE), ("Новая реплика", BASE)]
        app._turn("card", ("Вторая реплика", card, .9))
        app._navigate(-1)
        app._turn("card", ("Третья реплика", card, .9))
        assert app.answer_subject.cget("text") == fragment
        assert app.position.cget("text") == "1 из 3 · новых 2"
        app._show_sources()
        window.update()
        assert app.source_window is not None and app.source_window.winfo_ismapped()
        app._show_history()
        assert app.history_list.size() == 3
        app.history_list.selection_clear(0, "end")
        app.history_list.selection_set(1)
        app._pick_history()
        assert app.answer_subject.cget("text") == "Вторая реплика"
        app._go_live()
        assert app.answer_subject.cget("text") == "Третья реплика"
        compact_width = window.winfo_width()
        compact_height = window.winfo_height()
        transcript_size = app.transcript.winfo_width(), app.transcript.winfo_height()
        answer_size = app.options[0][1].winfo_width(), app.options[0][1].winfo_height()
        assert all(window.resizable()), "The normal window must allow user resizing"
        max_width, max_height = window.maxsize()
        large_size = (min(compact_width + 250, max_width), min(compact_height + 160, max_height))
        window.geometry(f"{large_size[0]}x{large_size[1]}+10+10")
        resized_layout = layout()
        assert (window.winfo_width(), window.winfo_height()) == large_size, (
            window.winfo_geometry(), large_size, window.maxsize())
        assert app.transcript.winfo_width() > transcript_size[0]
        assert app.transcript.winfo_height() >= transcript_size[1]
        if large_size[1] > compact_height:
            assert app.transcript.winfo_height() > transcript_size[1]
        assert app.options[0][1].winfo_width() > answer_size[0]
        assert app.options[0][1].winfo_height() >= answer_size[1]
        if large_size[1] > compact_height:
            assert app.options[0][1].winfo_height() > answer_size[1]
        app._turn("transcript", "Реплика в большом окне")
        assert layout() == resized_layout
        app._fold()
        window.update()
        assert not app.card_frame.winfo_ismapped()
        assert window.winfo_height() < compact_height
        app._fold()
        window.update()
        assert app.card_frame.winfo_ismapped()
        assert layout() == resized_layout
        if os.name == "nt":
            window.state("zoomed")
            layout()
            assert window.state() == "zoomed"
            assert window.winfo_width() >= large_size[0]
            app._fold()
            window.update()
            assert window.state() == "normal" and not app.card_frame.winfo_ismapped()
            app._fold()
            window.update()
            assert window.state() == "zoomed" and app.card_frame.winfo_ismapped()
        from .knowledge import Project
        app.pipeline = None
        first, second = BASE / "first-demo-base", BASE / "second-demo-base"
        app._projects([Project("Все базы", first), Project("Все базы · 1", second)])
        assert len(app.bases) == 2
        assert set(app.projects["Все базы"]) == {first, second}
        app.pipeline = ManualRequest()
        app.project = (first, second)
        app.typed_question.insert("1.0", "  Какой срок хранения?\nИ кто его меняет?  ")
        window.update()
        assert app.typed_ask_button.instate(["!disabled"])
        app.transcript.tag_add("sel", "1.0", "1.3")
        selected = app._selected_text()
        app._turn("transcript", "Новая речь во время ввода")
        app.typed_question.focus_force()
        window.update()
        app.typed_question.event_generate("<Control-Return>")
        window.update()
        assert calls[-1] == ("Какой срок хранения?\nИ кто его меняет?", (first, second))
        assert app._selected_text() == selected
        assert app.typed_question.get("1.0", "end-1c").strip() == calls[-1][0]
        app._turn("card", (calls[-1][0], card, .8))
        assert app.entries[-1].text == calls[-1][0]
        app.project = first
        app.typed_ask_button.invoke()
        assert calls[-1][1] == first
        app.typed_question.delete("1.0", "end")
        app.typed_question.insert("1.0", "  \n ")
        window.update()
        assert app.typed_ask_button.instate(["disabled"])
        count = len(calls)
        app.typed_question.event_generate("<Control-Return>")
        window.update()
        assert len(calls) == count, "Blank typed input must not send the selected transcript"
        app.transcript.configure(state="normal")
        app.transcript.delete("1.0", "end")
        app.transcript.configure(state="disabled")
        app.last_utterance = ""
        app.live.clear()
        app.typed_question.delete("1.0", "end")
        app.typed_question.insert("1.0", "How does Orbit work?")
        window.update()
        app.typed_question.event_generate("<Tab>")
        window.update()
        assert window.focus_get() == app.typed_ask_button
        app.typed_ask_button.invoke()
        assert calls[-1] == ("How does Orbit work?", first), "Typed questions must work without speech"
        count = len(calls)
        app.project = None
        app.typed_ask_button.invoke()
        assert len(calls) == count
        assert app.typed_question.get("1.0", "end-1c") == "How does Orbit work?"
        app.close()
        print("Overlay resizes and maximizes, appends paragraphs and preserves selection and layout")
    else:
        if args.launch_check:
            until = time.monotonic() + 100
            try:
                while time.monotonic() < until:
                    window.update()
                    if (app.device_name and app.pipeline and app.live.is_set()
                            and app.llm_done and not app.llm_status):
                        count, stamp = app.index.status(app.project) if app.project else (0, None)
                        if app.project is None or stamp is not None:
                            assert app.pipeline.manual
                            print(f"Windows overlay listening in manual mode · {count} indexed files")
                            return
                    time.sleep(.05)
                raise RuntimeError(f"Startup timed out: {app.status.get()}{app.llm_status}")
            finally:
                app.close()
        window.mainloop()


if __name__ == "__main__":
    main()
