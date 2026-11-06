import queue
import sqlite3
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from .i18n import translate
from .knowledge import Source
from .retrieval import SearchUnavailable


COPY = {
    "Просмотр базы знаний": ("Knowledge browser", "Explorador de la base"),
    "Документы": ("Documents", "Documentos"),
    "Проверить поиск": ("Test retrieval", "Probar la búsqueda"),
    "Документ и фрагмент": ("Document and passage", "Documento y fragmento"),
    "Выбери документ или введи вопрос для поиска.": (
        "Choose a document or enter a question to test retrieval.",
        "Elige un documento o escribe una pregunta para probar la búsqueda.",
    ),
    "Читаю индекс…": ("Reading the index…", "Leyendo el índice…"),
    "Документов в индексе · {count}": ("Indexed documents · {count}", "Documentos indexados · {count}"),
    "Найдено фрагментов · {count}": ("Retrieved passages · {count}", "Fragmentos encontrados · {count}"),
    "Строка {line}": ("Line {line}", "Línea {line}"),
    "Фрагментов в индексе · {count}": ("Indexed passages · {count}", "Fragmentos indexados · {count}"),
    "Не удалось прочитать индекс или выполнить поиск.": (
        "Couldn't read the index or run the search.", "No se pudo leer el índice o ejecutar la búsqueda.",
    ),
    "Закрыть": ("Close", "Cerrar"),
}


def show_knowledge_window(app, parent, index, root):
    root = Path(root).resolve()
    w = tk.Toplevel(parent)
    w.transient(parent)
    w.attributes("-topmost", app.top.get())
    w.geometry(f"{min(900, w.winfo_screenwidth() - 45)}x{min(550, w.winfo_screenheight() - 85)}")
    bg = parent.cget("bg")
    w.configure(bg=bg)

    def t(key, **values):
        return translate(app.ui_language, COPY, key, **values)

    w.title(t("Просмотр базы знаний"))
    frame = tk.Frame(w, bg=bg, padx=12, pady=10)
    frame.pack(fill="both", expand=True)
    app._label(frame, t("Просмотр базы знаний"), size=14, bold=True, bg=bg).pack(fill="x")
    provider = "SQLite FTS5" if index.retriever is None else "SQLite · Local search API"
    app._label(frame, f"{root.name} · {provider}", size=9, bg=bg).pack(fill="x")
    app._label(frame, t("Выбери документ или введи вопрос для поиска."), size=9, bg=bg).pack(fill="x")
    footer = tk.Frame(frame, bg=bg)
    footer.pack(side="bottom", fill="x", pady=(8, 0))
    status = tk.StringVar(w)
    app._label(footer, var=status, size=9, bg=bg).pack(side="left", fill="x", expand=True)
    app._button(footer, t("Закрыть"), w.destroy).pack(side="right")
    controls = tk.Frame(frame, bg=bg)
    controls.pack(fill="x", pady=8)
    query = ttk.Entry(controls, style="Copilot.Settings.TEntry")
    query.pack(side="left", fill="x", expand=True)
    panes = ttk.Panedwindow(frame, orient="horizontal")
    panes.pack(fill="both", expand=True)
    sources = tk.Frame(panes, bg=bg, width=315)
    reading = tk.Frame(panes, bg=bg, width=475)
    panes.add(sources, weight=2)
    panes.add(reading, weight=3)
    style = ttk.Style(w)
    style.configure("Knowledge.Treeview", background="#222622", fieldbackground="#222622",
                    foreground="#f3f5f1", rowheight=26)
    style.map("Knowledge.Treeview", background=[("selected", "#3b5547")])
    style.configure("Knowledge.Treeview.Heading", background="#383f39", foreground="#f3f5f1")
    tree = ttk.Treeview(sources, columns=("source",), show="headings", selectmode="browse", style="Knowledge.Treeview")
    tree.heading("source", text=t("Документ и фрагмент"))
    tree.column("source", width=305)
    scroll = ttk.Scrollbar(sources, command=tree.yview, style="Copilot.Vertical.TScrollbar")
    scroll.pack(side="right", fill="y")
    tree.configure(yscrollcommand=scroll.set)
    tree.pack(side="left", fill="both", expand=True)
    preview = tk.Text(reading, state="disabled", wrap="word", font=("Consolas", 10),
                      bg="#222622", fg="#f3f5f1", padx=10, pady=8, relief="flat", width=1)
    preview.pack(side="left", fill="both", expand=True)
    app._text_scrollbar(preview)
    rows = {}
    poll_id = None

    def display(passages):
        preview.configure(state="normal")
        preview.delete("1.0", "end")
        for source in passages:
            location = source.path.relative_to(root).as_posix()
            preview.insert("end", f"{location} · {t('Строка {line}', line=source.line)}\n{source.text}\n\n")
        preview.configure(state="disabled")

    def run(work, finish):
        nonlocal poll_id
        if poll_id is not None:
            return
        status.set(t("Читаю индекс…"))
        result = queue.SimpleQueue()

        def worker():
            try:
                result.put(work())
            except (OSError, sqlite3.Error, ValueError, SearchUnavailable):
                result.put(None)

        def poll():
            nonlocal poll_id
            try:
                value = result.get_nowait()
            except queue.Empty:
                poll_id = w.after(70, poll)
                return
            poll_id = None
            if value is None:
                status.set(t("Не удалось прочитать индекс или выполнить поиск."))
            else:
                finish(value)

        threading.Thread(target=worker, daemon=True).start()
        poll_id = w.after(70, poll)

    def show_list(values, hits=False):
        tree.delete(*tree.get_children())
        rows.clear()
        display([])
        for number, value in enumerate(values, 1):
            label = (f"{number:02}  {value.path.relative_to(root).as_posix()}:{value.line}"
                     if hits else Path(value).as_posix())
            key = tree.insert("", "end", values=(label,))
            rows[key] = value
        status.set(t("Найдено фрагментов · {count}" if hits else "Документов в индексе · {count}",
                     count=len(values)))
        if hits and rows:
            tree.selection_set(next(iter(rows)))

    def documents():
        run(lambda: index.index_files(root), show_list)

    def search(_event=None):
        text = query.get().strip()
        if text:
            run(lambda: index.search(root, text, limit=8), lambda values: show_list(values, hits=True))
        else:
            documents()

    def selected(_event):
        row = rows.get(next(iter(tree.selection()), None))
        if isinstance(row, Source):
            display([row])
        elif row is not None:
            def show(passages):
                if rows.get(next(iter(tree.selection()), None)) != row:
                    selected(None)
                    return
                display(passages)
                status.set(t("Фрагментов в индексе · {count}", count=len(passages)))

            run(lambda: index.index_passages(root, row), show)

    def cleanup(event):
        if event.widget is w and poll_id is not None:
            w.after_cancel(poll_id)

    app._button(controls, t("Проверить поиск"), search, primary=True).pack(side="left", padx=6)
    app._button(controls, t("Документы"), documents).pack(side="left")
    query.bind("<Return>", search)
    tree.bind("<<TreeviewSelect>>", selected)
    w.bind("<Escape>", lambda _: w.destroy())
    w.bind("<Destroy>", cleanup)
    documents()
    return w
