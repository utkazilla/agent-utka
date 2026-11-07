"""Choose a named knowledge base without exposing storage directories."""

import tkinter as tk
from tkinter import ttk

from .knowledge_pack import document_title, import_title, summary_title


def choose_import_destination(app, source):
    t = app._tr
    window = tk.Toplevel(app.window)
    window.title(t("Импортировать выжимку"))
    window.transient(app.window)
    window.attributes("-topmost", app.top.get())
    window.configure(bg=app.window.cget("bg"))
    window.resizable(False, False)
    body = tk.Frame(window, bg=window.cget("bg"), padx=16, pady=14)
    body.pack(fill="both", expand=True)
    app._label(body, t("Название выжимки"), size=14, bold=True).pack(anchor="w")
    create = t("Новая база…")
    options = [*app.bases, create]
    chosen = next((label for label, root in app.bases.items() if root == app.project), create)
    destination = tk.StringVar(value=chosen)
    def suggested_title():
        try:
            return import_title(app.bases.get(destination.get()), source)
        except (OSError, ValueError):
            return document_title(source)

    last_suggested = suggested_title()
    document_name = tk.StringVar(value=last_suggested)
    document_entry = ttk.Entry(body, name="document_name", textvariable=document_name,
                               style="Copilot.TEntry", width=46)
    document_entry.pack(fill="x", pady=(6, 4))
    app._label(body, t("Название видно в источниках. Исходный файл не изменится."),
               size=9, wrap=400).pack(anchor="w")
    app._label(body, t("Добавить в базу"), size=11, bold=True).pack(anchor="w", pady=(16, 6))
    destination_row = tk.Frame(body, bg=body.cget("bg"))
    destination_row.pack(fill="x")
    picker = ttk.Combobox(destination_row, name="base", textvariable=destination, values=options,
                          state="readonly", style="Copilot.TCombobox", width=46)
    app._button(destination_row, create, lambda: destination.set(create)).pack(side="right", padx=(8, 0))
    picker.pack(side="left", fill="x", expand=True)
    name_row = tk.Frame(body, bg=body.cget("bg"))
    app._label(name_row, t("Название новой базы"), size=9).pack(anchor="w", pady=(12, 4))
    name = tk.StringVar(value=document_title(source))
    entry = ttk.Entry(name_row, name="name", textvariable=name, style="Copilot.TEntry")
    entry.pack(fill="x")
    feedback = tk.StringVar()
    app._label(body, var=feedback, size=9, wrap=400).pack(fill="x", pady=(12, 14))
    buttons = tk.Frame(body, bg=body.cget("bg"))
    buttons.pack(fill="x")
    result = None

    def valid():
        document_title_value = " ".join(document_name.get().split())
        if not document_title_value or len(document_title_value) > 100:
            return False, t("Введи название выжимки — до 100 символов.")
        title = " ".join(name.get().split())
        if destination.get() != create:
            return True, ""
        if not title or len(title) > 100 or title == create:
            return False, t("Введи название базы — до 100 символов.")
        if title.casefold() in {summary_title(root).casefold() for root in app.bases.values()}:
            return False, t("Такая база уже есть. Выбери её в списке.")
        return True, ""

    def submit(_event=None):
        nonlocal result
        if not valid()[0]:
            return "break"
        target, base_title = ((None, " ".join(name.get().split())) if destination.get() == create
                              else (app.bases[destination.get()], None))
        result = (target, base_title, " ".join(document_name.get().split()))
        window.destroy()
        return "break"

    app._button(buttons, t("Отмена"), window.destroy).pack(side="right")
    confirm = app._button(buttons, t("Импортировать"), submit, primary=True)
    confirm.pack(side="right", padx=(0, 8))

    def update(*_):
        if destination.get() == create:
            name_row.pack(fill="x", after=destination_row)
        else:
            name_row.pack_forget()
        ready, message = valid()
        confirm.state(["!disabled"] if ready else ["disabled"])
        feedback.set(message or t("В одну базу можно добавить несколько выжимок."))

    def destination_changed(*_):
        nonlocal last_suggested
        suggestion = suggested_title()
        if document_name.get() == last_suggested:
            document_name.set(suggestion)
        last_suggested = suggestion
        update()

    destination.trace_add("write", destination_changed)
    name.trace_add("write", update)
    document_name.trace_add("write", update)
    window.bind("<Escape>", lambda _: window.destroy())
    window.bind("<Return>", submit)
    window.protocol("WM_DELETE_WINDOW", window.destroy)
    update()
    window.update_idletasks()
    window.geometry(f"+{app.window.winfo_rootx() + 20}+{app.window.winfo_rooty() + 65}")
    window.grab_set()
    document_entry.focus_set()
    document_entry.selection_range(0, "end")
    window.wait_window()
    return result
