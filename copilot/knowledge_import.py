"""Choose a named knowledge base without exposing storage directories."""

import tkinter as tk
from tkinter import ttk

from .knowledge_pack import document_title, import_title, summary_title


def choose_base_name(app):
    t = app._tr
    window = tk.Toplevel(app.window)
    window.title(t("Новая база"))
    window.transient(app.window)
    window.attributes("-topmost", app.top.get())
    window.configure(bg=app.window.cget("bg"))
    window.resizable(False, False)
    body = tk.Frame(window, bg=window.cget("bg"), padx=16, pady=14)
    body.pack(fill="both", expand=True)
    app._label(body, t("Название базы"), size=14, bold=True).pack(anchor="w")
    name = tk.StringVar()
    entry = ttk.Entry(body, name="base_name", textvariable=name, width=42, style="Copilot.TEntry")
    entry.pack(fill="x", pady=(8, 6))
    app._label(body, t("Например: проект, продукт или команда. Выжимки добавишь после создания."),
               size=9, wrap=380).pack(anchor="w")
    feedback = tk.StringVar()
    app._label(body, var=feedback, size=9, wrap=380).pack(fill="x", pady=(10, 8))
    buttons = tk.Frame(body, bg=body.cget("bg"))
    buttons.pack(fill="x")
    result = None
    existing = {summary_title(root).casefold() for root in app.bases.values()}

    def update(*_):
        title = " ".join(name.get().split())
        error = ("Введи название базы — до 100 символов." if not title or len(title) > 100
                 else "Такая база уже есть. Выбери её в списке." if title.casefold() in existing else "")
        feedback.set(t(error) if error else "")
        create.state(["disabled"] if error else ["!disabled"])

    def submit(_event=None):
        nonlocal result
        if create.instate(["!disabled"]):
            result = " ".join(name.get().split())
            window.destroy()
        return "break"

    app._button(buttons, t("Отмена"), window.destroy).pack(side="right")
    create = app._button(buttons, t("Создать базу"), submit, primary=True)
    create.pack(side="right", padx=(0, 8))
    name.trace_add("write", update)
    window.bind("<Return>", submit)
    window.bind("<Escape>", lambda _: window.destroy())
    update()
    window.update_idletasks()
    window.geometry(f"+{app.window.winfo_rootx() + 20}+{app.window.winfo_rooty() + 65}")
    window.grab_set()
    entry.focus_set()
    window.wait_window()
    return result


def choose_import_destination(app, source):
    t = app._tr
    window = tk.Toplevel(app.window)
    window.title(t("Добавить файл в базу"))
    window.transient(app.window)
    window.attributes("-topmost", app.top.get())
    window.configure(bg=app.window.cget("bg"))
    window.resizable(False, False)
    body = tk.Frame(window, bg=window.cget("bg"), padx=16, pady=14)
    body.pack(fill="both", expand=True)
    app._label(body, t("Добавить файл в базу"), size=14, bold=True).pack(anchor="w")
    app._label(body, source.name, size=9, wrap=390).pack(anchor="w", pady=(4, 12))
    create = t("Новая база…")
    while create in app.bases:
        create += "…"
    options = [*app.bases, create]
    chosen = next((label for label, root in app.bases.items() if root == app.project), create)
    destination = tk.StringVar(value=chosen)

    def default_name(title):
        return " ".join(title.split())[:100].strip() or source.name[:100]

    def suggested_title():
        try:
            return default_name(import_title(app.bases.get(destination.get()), source))
        except (OSError, ValueError):
            return default_name(document_title(source))

    last_suggested = suggested_title()
    document_name = tk.StringVar(value=last_suggested)
    target_fields = tk.Frame(body, bg=body.cget("bg"))
    target_fields.pack(fill="x")
    picker = None
    if app.bases:
        app._label(target_fields, t("Добавить в базу"), size=10, bold=True).pack(anchor="w", pady=(0, 4))
        picker = ttk.Combobox(target_fields, name="base", textvariable=destination, values=options,
                              state="readonly", style="Copilot.TCombobox", width=42)
        picker.pack(fill="x")
    name_row = tk.Frame(target_fields, bg=body.cget("bg"))
    app._label(name_row, t("Название базы"), size=10, bold=True).pack(anchor="w", pady=(6, 4))
    name = tk.StringVar(value=default_name(document_title(source)))
    entry = ttk.Entry(name_row, name="name", textvariable=name, style="Copilot.TEntry", width=42)
    entry.pack(fill="x")

    details = tk.Frame(body, bg=body.cget("bg"))
    details.pack(fill="x", pady=(8, 0))
    name_details = tk.Frame(details, bg=body.cget("bg"))
    app._label(name_details, t("Название выжимки"), size=9).pack(anchor="w", pady=(0, 4))
    document_entry = ttk.Entry(name_details, name="document_name", textvariable=document_name,
                               style="Copilot.TEntry", width=42)
    document_entry.pack(fill="x")

    def show_document_name():
        edit_name.pack_forget()
        name_details.pack(fill="x")
        document_entry.focus_set()
        document_entry.selection_range(0, "end")

    edit_name = app._button(details, t("Изменить название выжимки…"), show_document_name)
    edit_name.pack(anchor="w")
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
        if not title or len(title) > 100:
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
            name_row.pack(fill="x")
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
    focus = entry if chosen == create else picker
    focus.focus_set()
    window.wait_window()
    return result
