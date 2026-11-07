"""Choose a named knowledge base without exposing storage directories."""

import tkinter as tk
from tkinter import ttk

from .knowledge_pack import document_title, summary_title


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
    app._label(body, t("Добавить в базу"), size=14, bold=True).pack(anchor="w")
    app._label(body, source.name, size=9, wrap=400).pack(anchor="w", pady=(4, 14))
    create = t("Новая база…")
    options = [*app.bases, create]
    chosen = next((label for label, root in app.bases.items() if root == app.project), create)
    destination = tk.StringVar(value=chosen)
    picker = ttk.Combobox(body, name="base", textvariable=destination, values=options,
                          state="readonly", style="Copilot.TCombobox", width=46)
    picker.pack(fill="x")
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
        result = ((None, " ".join(name.get().split())) if destination.get() == create
                  else (app.bases[destination.get()], None))
        window.destroy()
        return "break"

    app._button(buttons, t("Отмена"), window.destroy).pack(side="right")
    confirm = app._button(buttons, t("Импортировать"), submit, primary=True)
    confirm.pack(side="right", padx=(0, 8))

    def update(*_):
        if destination.get() == create:
            name_row.pack(fill="x", after=picker)
        else:
            name_row.pack_forget()
        ready, message = valid()
        confirm.state(["!disabled"] if ready else ["disabled"])
        feedback.set(message or t("В одну базу можно добавить несколько выжимок."))

    destination.trace_add("write", update)
    name.trace_add("write", update)
    window.bind("<Escape>", lambda _: window.destroy())
    window.bind("<Return>", submit)
    window.protocol("WM_DELETE_WINDOW", window.destroy)
    update()
    window.update_idletasks()
    window.geometry(f"+{app.window.winfo_rootx() + 20}+{app.window.winfo_rooty() + 65}")
    window.grab_set()
    (entry if chosen == create else picker).focus_set()
    if chosen == create:
        entry.selection_range(0, "end")
    window.wait_window()
    return result
