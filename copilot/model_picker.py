import queue
import threading
import tkinter as tk
from tkinter import ttk

from .catalog import CatalogError, model_variants, search_models
from .i18n import translate


COPY = {
    "Модели Ollama": ("Ollama models", "Modelos de Ollama"),
    "Каталог": ("Catalog", "Catálogo"),
    "Установленные": ("Installed", "Instalados"),
    "Название модели": ("Model name", "Nombre del modelo"),
    "Поиск": ("Search", "Buscar"),
    "Модель": ("Model", "Modelo"),
    "Вариант": ("Variant", "Variante"),
    "Размер на диске": ("File size", "Tamaño en disco"),
    "Квантование": ("Quantization", "Cuantización"),
    "Установлена": ("Installed", "Instalado"),
    "Состояние": ("Status", "Estado"),
    "Размер файлов указан для диска. Свободная VRAM показана отдельно.": (
        "File sizes are for disk storage. Free VRAM is shown separately.",
        "Los tamaños corresponden al disco. La VRAM libre se muestra por separado.",
    ),
    "Обновить": ("Refresh", "Actualizar"),
    "Загружаю каталог…": ("Loading the catalog…", "Cargando el catálogo…"),
    "Модели не найдены. Попробуй другое название.": (
        "No models found. Try another name.", "No se encontraron modelos. Prueba con otro nombre.",
    ),
    "Не удалось загрузить каталог. Нажми «Поиск», чтобы повторить.": (
        "Couldn't load the catalog. Select Search to try again.",
        "No se pudo cargar el catálogo. Pulsa Buscar para volver a intentarlo.",
    ),
    "Загружаю варианты…": ("Loading variants…", "Cargando las variantes…"),
    "У модели нет доступных локальных вариантов.": (
        "This model has no available local variants.", "Este modelo no tiene variantes locales disponibles.",
    ),
    "Не удалось загрузить варианты.": ("Couldn't load the variants.", "No se pudieron cargar las variantes."),
    "Получаю список установленных моделей…": (
        "Loading installed models…", "Cargando los modelos instalados…",
    ),
    "У этого сервера пока нет установленных моделей.": (
        "This server has no installed models yet.", "Este servidor aún no tiene modelos instalados.",
    ),
    "Не удалось получить список. {detail}": (
        "Couldn't load the list. {detail}", "No se pudo cargar la lista. {detail}",
    ),
    "Выбрать": ("Select", "Seleccionar"),
    "Скачать и выбрать": ("Download and select", "Descargar y seleccionar"),
    "Отменить загрузку": ("Cancel download", "Cancelar descarga"),
    "Закрыть": ("Close", "Cerrar"),
    "Выбери модель и размер.": ("Choose a model and size.", "Elige un modelo y un tamaño."),
    "Скачиваю {name}…": ("Downloading {name}…", "Descargando {name}…"),
    "Скачиваю {name} · текущий слой {percent}%": (
        "Downloading {name} · current layer {percent}%", "Descargando {name} · capa actual {percent}%",
    ),
    "Отменяю загрузку…": ("Cancelling download…", "Cancelando la descarga…"),
    "Загрузка отменена.": ("Download cancelled.", "Descarga cancelada."),
    "Не удалось скачать {name}. {detail}": ("Couldn't download {name}. {detail}", "No se pudo descargar {name}. {detail}"),
    "Не удалось сохранить выбор. {detail}": ("Couldn't save the selection. {detail}", "No se pudo guardar la selección. {detail}"),
    "Выбрана {name}. Перезапусти Agent Utka, чтобы использовать её для ответов.": (
        "{name} selected. Restart Agent Utka to use it for answers.",
        "Se seleccionó {name}. Reinicia Agent Utka para usarlo en las respuestas.",
    ),
}


def show_model_picker(app, parent, *, load_installed, download, use_model, vram):
    return ModelPicker(app, parent, load_installed, download, use_model, vram).window


class ModelPicker:
    def __init__(self, app, parent, load_installed, download, use_model, vram):
        self.app, self.language = app, app.ui_language
        self.load_installed, self.download, self.use_model = load_installed, download, use_model
        self.window = w = tk.Toplevel(parent)
        self.bg = bg = parent.cget("bg")
        w.title(self.t("Модели Ollama"))
        w.transient(parent)
        w.attributes("-topmost", app.top.get())
        w.configure(bg=bg)
        width = min(770, w.winfo_screenwidth() - 64)
        height = min(535, w.winfo_screenheight() - 96)
        w.minsize(min(590, width), min(410, height))
        w.geometry(f"{width}x{height}")
        self.jobs = {}
        self.events = queue.SimpleQueue()
        self.after_id = None
        self.stop_download = None
        self.downloaded = set()
        self.installed_names = set()
        self.families = {}
        self.variants = {}
        self.installed_models = {}
        self.query = tk.StringVar(w)
        self.family_status = tk.StringVar(w)
        self.variant_status = tk.StringVar(w)
        self.installed_status = tk.StringVar(w)
        self.feedback = tk.StringVar(w, self.t("Выбери модель и размер."))

        layout = tk.Frame(w, bg=bg, padx=14, pady=12)
        layout.pack(fill="both", expand=True)
        controls = tk.Frame(layout, bg=bg)
        controls.pack(side="bottom", fill="x")
        app._label(layout, self.t("Модели Ollama"), size=15, bold=True, bg=bg).pack(fill="x")
        app._label(layout, var=vram, color="#b1bbb2", size=9, bg=bg, wrap=680).pack(fill="x", pady=(2, 6))
        self.tabs = ttk.Notebook(layout)
        self.tabs.pack(fill="both", expand=True)
        self.catalog_tab = tk.Frame(self.tabs, bg=bg, padx=8, pady=8)
        self.installed_tab = tk.Frame(self.tabs, bg=bg, padx=8, pady=8)
        self.tabs.add(self.catalog_tab, text=self.t("Каталог"))
        self.tabs.add(self.installed_tab, text=self.t("Установленные"))
        self.tabs.bind("<<NotebookTabChanged>>", self.update_action)
        self.build_catalog()
        self.build_installed()

        app._label(controls, self.t("Размер файлов указан для диска. Свободная VRAM показана отдельно."),
                   color="#b1bbb2", size=9, bg=bg, wrap=680).pack(fill="x", pady=(5, 2))
        app._label(controls, var=self.feedback, color="#a9c9b6", size=9, bg=bg, wrap=680).pack(fill="x")
        footer = tk.Frame(controls, bg=bg)
        footer.pack(fill="x", pady=(6, 0))
        self.action = app._button(footer, self.t("Скачать и выбрать"), self.choose, primary=True)
        self.action.pack(side="right")
        self.cancel = app._button(footer, self.t("Отменить загрузку"), self.cancel_download)
        self.cancel.pack(side="right", padx=6)
        app._button(footer, self.t("Закрыть"), w.destroy).pack(side="left")
        self.update_action()
        w.bind("<Destroy>", self.cleanup)
        w.bind("<Escape>", lambda _: w.destroy())
        w.grab_set()
        self.search()
        self.refresh_installed()

    def t(self, source, **values):
        return translate(self.language, COPY, source, **values)

    def tree(self, parent, columns):
        frame = tk.Frame(parent, bg=self.bg)
        frame.pack(fill="both", expand=True)
        style = ttk.Style(self.window)
        style.configure("Catalog.Treeview", background="#222622", fieldbackground="#222622",
                        foreground="#f3f5f1", rowheight=26)
        style.map("Catalog.Treeview", background=[("selected", "#3b5547")],
                  foreground=[("selected", "#ffffff")])
        style.configure("Catalog.Treeview.Heading", background="#383f39", foreground="#f3f5f1")
        tree = ttk.Treeview(frame, columns=[column for column, *_ in columns], show="headings",
                            selectmode="browse", style="Catalog.Treeview")
        bar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview, style="Copilot.Vertical.TScrollbar")
        tree.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)
        for column, title, width, stretch in columns:
            tree.heading(column, text=self.t(title))
            tree.column(column, width=width, minwidth=45, stretch=stretch)
        return tree

    def build_catalog(self):
        tab = self.catalog_tab
        search_row = tk.Frame(tab, bg=self.bg)
        search_row.pack(fill="x", pady=(0, 6))
        self.app._label(search_row, self.t("Название модели"), size=9, bg=self.bg).pack(side="left", padx=(0, 6))
        search_entry = ttk.Entry(search_row, textvariable=self.query, style="Copilot.Settings.TEntry")
        search_entry.pack(side="left", fill="x", expand=True)
        search_entry.bind("<Return>", lambda _: self.search())
        self.app._button(search_row, self.t("Поиск"), self.search).pack(side="right", padx=(6, 0))
        search_entry.focus_set()
        columns = tk.Frame(tab, bg=self.bg)
        family_panel = tk.Frame(columns, bg=self.bg, width=220)
        family_panel.pack(side="left", fill="both", padx=(0, 6))
        family_panel.pack_propagate(False)
        variant_panel = tk.Frame(columns, bg=self.bg)
        variant_panel.pack(side="left", fill="both", expand=True)
        self.family_table = self.tree(family_panel, [("model", "Модель", 185, True)])
        self.variant_table = self.tree(variant_panel, [("tag", "Вариант", 185, True),
                                                       ("size", "Размер на диске", 115, False),
                                                       ("status", "Состояние", 105, False)])
        self.family_table.bind("<<TreeviewSelect>>", self.select_family)
        self.variant_table.bind("<<TreeviewSelect>>", self.update_action)
        variant_row = tk.Frame(tab, bg=self.bg)
        variant_row.pack(side="bottom", fill="x")
        self.app._label(variant_row, var=self.variant_status, color="#b1bbb2", size=9,
                        bg=self.bg, wrap=530).pack(side="left", fill="x", expand=True)
        self.variant_retry = self.app._button(variant_row, self.t("Обновить"), self.select_family)
        self.app._label(tab, var=self.family_status, color="#b1bbb2", size=9, bg=self.bg,
                        wrap=540).pack(side="bottom", fill="x")
        columns.pack(fill="both", expand=True)

    def build_installed(self):
        tab = self.installed_tab
        top = tk.Frame(tab, bg=self.bg)
        top.pack(fill="x", pady=(0, 6))
        self.app._label(top, var=self.installed_status, color="#b1bbb2", size=9,
                        bg=self.bg, wrap=550).pack(side="left", fill="x", expand=True)
        self.app._button(top, self.t("Обновить"), self.refresh_installed).pack(side="right")
        self.installed_table = self.tree(tab, [("model", "Модель", 235, True),
                                               ("size", "Размер на диске", 125, False),
                                               ("quant", "Квантование", 140, False)])
        self.installed_table.bind("<<TreeviewSelect>>", self.update_action)

    @staticmethod
    def selected(table):
        return next(iter(table.selection()), None)

    @staticmethod
    def tag(name):
        return name if ":" in name else name + ":latest"

    def run(self, key, work, finish):
        token = object()
        self.jobs[key] = (token, finish)

        def worker():
            try:
                result = work()
            except (CatalogError, OSError, ValueError, RuntimeError) as error:
                self.events.put(("result", key, token, None, error))
            else:
                self.events.put(("result", key, token, result, None))

        threading.Thread(target=worker, daemon=True).start()
        self.schedule()

    def schedule(self):
        if self.jobs and self.after_id is None:
            self.after_id = self.window.after(70, self.poll)

    def poll(self):
        self.after_id = None
        while True:
            try:
                kind, key, token, value, error = self.events.get_nowait()
            except queue.Empty:
                break
            job = self.jobs.get(key)
            if job is None or job[0] is not token:
                continue
            if kind == "progress":
                self.show_progress(*value)
            else:
                del self.jobs[key]
                job[1](value, error)
        self.schedule()

    def search(self):
        query = self.query.get().strip()
        self.jobs.pop("variants", None)
        self.family_table.delete(*self.family_table.get_children())
        self.variant_table.delete(*self.variant_table.get_children())
        self.families.clear()
        self.variants.clear()
        self.family_status.set(self.t("Загружаю каталог…"))
        self.variant_status.set("")
        self.variant_retry.pack_forget()
        self.update_action()

        def finish(models, error):
            if error is not None:
                self.family_status.set(self.t("Не удалось загрузить каталог. Нажми «Поиск», чтобы повторить."))
            elif not models:
                self.family_status.set(self.t("Модели не найдены. Попробуй другое название."))
            else:
                for item in models:
                    self.families[item.name] = item
                    self.family_table.insert("", "end", iid=item.name, values=(item.name,))
                first = next(iter(self.families))
                self.family_table.selection_set(first)
                self.family_table.focus(first)

        self.run("search", lambda: search_models(query), finish)

    def select_family(self, _event=None):
        name = self.selected(self.family_table)
        if name not in self.families:
            return
        self.variant_table.delete(*self.variant_table.get_children())
        self.variants.clear()
        self.family_status.set(self.families[name].description)
        self.variant_status.set(self.t("Загружаю варианты…"))
        self.variant_retry.pack_forget()
        self.update_action()

        def finish(variants, error):
            if self.selected(self.family_table) != name:
                return
            if error is not None:
                self.variant_status.set(self.t("Не удалось загрузить варианты."))
                self.variant_retry.pack(side="right")
                return
            if not variants:
                self.variant_status.set(self.t("У модели нет доступных локальных вариантов."))
                return
            self.variant_status.set("")
            ordered = sorted(variants, key=lambda item: (item.size_bytes is None, item.size_bytes or 0))
            for item in ordered:
                if item.tag not in self.variants:
                    self.variants[item.tag] = item
                    self.variant_table.insert("", "end", iid=item.tag, values=self.variant_values(item))
            first = next(iter(self.variants))
            self.variant_table.selection_set(first)
            self.variant_table.focus(first)
            self.update_action()

        self.run("variants", lambda: model_variants(name), finish)

    def is_installed(self, name):
        return self.tag(name) in (self.installed_names | self.downloaded)

    def variant_values(self, item):
        return (item.tag, item.size or "—", self.t("Установлена") if self.is_installed(item.tag) else "")

    def refresh_installed(self):
        self.installed_status.set(self.t("Получаю список установленных моделей…"))

        def finish(items, error):
            if error is not None:
                self.installed_status.set(self.t("Не удалось получить список. {detail}", detail=str(error)))
                return
            selection = self.selected(self.installed_table)
            self.installed_names = {self.tag(item.name) for item in items}
            self.installed_table.delete(*self.installed_table.get_children())
            self.installed_models = {item.name: item for item in items}
            for item in self.installed_models.values():
                size = f"{item.size / 10**9:.2f} GB" if item.size is not None else "—"
                self.installed_table.insert("", "end", iid=item.name,
                                            values=(item.name, size, item.quantization or "—"))
            if self.installed_models:
                self.installed_status.set("")
                chosen = selection if selection in self.installed_models else next(iter(self.installed_models))
                self.installed_table.selection_set(chosen)
            else:
                self.installed_status.set(self.t("У этого сервера пока нет установленных моделей."))
            for item in self.variants.values():
                self.variant_table.item(item.tag, values=self.variant_values(item))
            self.update_action()

        self.run("installed", self.load_installed, finish)

    def current_choice(self):
        if self.tabs.select() == str(self.installed_tab):
            return self.selected(self.installed_table), True
        name = self.selected(self.variant_table)
        return name, name is not None and self.is_installed(name)

    def update_action(self, _event=None):
        name, installed = self.current_choice()
        self.action.configure(text=self.t("Выбрать" if installed else "Скачать и выбрать"))
        self.action.state(["!disabled"] if name and self.stop_download is None else ["disabled"])
        self.cancel.state(["!disabled"] if self.stop_download and not self.stop_download.is_set() else ["disabled"])

    def choose(self):
        name, installed = self.current_choice()
        if not name or self.stop_download is not None:
            return
        if installed:
            self.apply(name)
            return
        stop = self.stop_download = threading.Event()
        self.feedback.set(self.t("Скачиваю {name}…", name=name))
        self.update_action()

        def work():
            token = self.jobs["download"][0]

            def progress(_status, completed, total):
                self.events.put(("progress", "download", token, (name, completed, total), None))

            return self.download(name, progress, stop.is_set)

        def finish(downloaded, error):
            self.stop_download = None
            if error is not None:
                self.feedback.set(self.t("Не удалось скачать {name}. {detail}", name=name, detail=str(error)))
            elif not downloaded or stop.is_set():
                self.feedback.set(self.t("Загрузка отменена."))
            else:
                self.downloaded.add(self.tag(name))
                if name in self.variants:
                    self.variant_table.item(name, values=self.variant_values(self.variants[name]))
                self.apply(name)
                self.refresh_installed()
            self.update_action()

        self.run("download", work, finish)

    def apply(self, name):
        try:
            self.use_model(name)
        except (OSError, ValueError) as error:
            self.feedback.set(self.t("Не удалось сохранить выбор. {detail}", detail=str(error)))
            return
        self.feedback.set(self.t("Выбрана {name}. Перезапусти Agent Utka, чтобы использовать её для ответов.",
                                 name=name))

    def show_progress(self, name, completed, total):
        if self.stop_download and not self.stop_download.is_set() and completed is not None and total:
            percent = min(100, round(100 * completed / total))
            self.feedback.set(self.t("Скачиваю {name} · текущий слой {percent}%", name=name, percent=percent))

    def cancel_download(self):
        if self.stop_download:
            self.stop_download.set()
            self.feedback.set(self.t("Отменяю загрузку…"))
            self.update_action()

    def cleanup(self, event):
        if event.widget is self.window:
            if self.stop_download:
                self.stop_download.set()
            if self.after_id is not None:
                self.window.after_cancel(self.after_id)
