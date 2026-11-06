import queue
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from .bootstrap import download_answer_model
from .brains import BRAIN_PROVIDERS, create_brain, local_api_url, local_ollama_url
from .configuration import BASE, RUNTIME, load_settings, save_settings
from .hardware import read_vram
from .i18n import translate
from .knowledge_window import show_knowledge_window
from .model_picker import show_model_picker
from .ollama_library import validate_ollama_model
from .retrieval import RETRIEVAL_PROVIDERS, local_search_url
from .speech import ASR_ENGINES, QWEN_ASR_MODELS
from .speech_picker import show_speech_picker
from .whisper_install import WHISPER_DEVICES


COPY = {
    "Ответы": ("Answers", "Respuestas"),
    "Выбрать модель…": ("Choose model…", "Elegir modelo…"),
    "Выбрана {model}. Перезапусти Agent Utka, чтобы использовать её для ответов.": (
        "{model} selected. Restart Agent Utka to use it for answers.",
        "Se seleccionó {model}. Reinicia Agent Utka para usarlo en las respuestas.",
    ),
    "Модель распознавания": ("Speech model", "Modelo de voz"),
    "Адрес сервера распознавания": ("Speech server address", "Dirección del servidor de voz"),
    "Укажи имя модели распознавания.": ("Enter the speech model name.", "Indica el nombre del modelo de voz."),
    "Ollama · установленный": ("Ollama · existing server", "Ollama · servidor existente"),
    "Поиск по проекту": ("Project search", "Búsqueda del proyecto"),
    "SQLite · встроенный": ("SQLite · built-in", "SQLite · integrado"),
    "Локальный API поиска": ("Local search API", "API de búsqueda local"),
    "Адрес API поиска": ("Search API address", "Dirección de la API de búsqueda"),
    "Укажи локальный адрес поиска вида http://127.0.0.1:8090/search.": (
        "Enter a local search URL like http://127.0.0.1:8090/search.",
        "Indica una dirección local como http://127.0.0.1:8090/search.",
    ),
    "Проверить VRAM": ("Refresh VRAM", "Actualizar VRAM"),
    "Выгрузить модель": ("Unload model", "Descargar de memoria"),
    "Модель сеанса · {name}": ("Session model · {name}", "Modelo de la sesión · {name}"),
    "В памяти · {name} · {device}": ("In memory · {name} · {device}", "En memoria · {name} · {device}"),
    "Распознавание выгружается…": ("Unloading speech model…", "Liberando el modelo de voz…"),
    "Модель распознавания не загружена.": ("No speech model is loaded.", "No hay un modelo de voz cargado."),
    "Моделью управляет локальный сервер.": ("The local server manages the model.", "El servidor local gestiona el modelo."),
    "Посмотреть индекс…": ("Browse knowledge…", "Explorar la base…"),
    "Выбери проект или импортируй документы, чтобы открыть индекс.": (
        "Choose a project or import documents to open the index.",
        "Elige un proyecto o importa documentos para abrir el índice.",
    ),
    "Диспетчер задач": ("Task Manager", "Administrador de tareas"),
    "Выгружаю {name} из Ollama…": ("Unloading {name} from Ollama…", "Liberando {name} de Ollama…"),
    "{name} выгружена из памяти Ollama.": ("{name} unloaded from Ollama.", "Se liberó {name} de la memoria de Ollama."),
    "{name} всё ещё в памяти. Обнови VRAM после завершения запроса.": (
        "{name} is still loaded. Refresh VRAM after the request finishes.",
        "{name} sigue cargado. Actualiza la VRAM cuando termine la solicitud.",
    ),
    "Не удалось выгрузить {name}. {detail}": ("Couldn't unload {name}. {detail}", "No se pudo liberar {name}. {detail}"),
    "Не удалось открыть Диспетчер задач. {detail}": (
        "Couldn't open Task Manager. {detail}", "No se pudo abrir el Administrador de tareas. {detail}",
    ),
    "Запрашиваю VRAM…": ("Checking VRAM…", "Consultando VRAM…"),
    "Свободно {free:.1f} из {total:.1f} ГиБ · {name}": (
        "{free:.1f} of {total:.1f} GiB free · {name}", "{free:.1f} de {total:.1f} GiB libres · {name}",
    ),
    "Ollama · {name} занимает {size:.1f} ГиБ VRAM": (
        "Ollama · {name} uses {size:.1f} GiB VRAM", "Ollama · {name} usa {size:.1f} GiB de VRAM",
    ),
    "Замер свободной VRAM недоступен. Для замера нужен NVIDIA nvidia-smi.": (
        "Free VRAM reading unavailable. Requires NVIDIA nvidia-smi.",
        "No se pudo medir la VRAM libre. Se requiere NVIDIA nvidia-smi.",
    ),
    "Обнови Ollama и отключи облако через OLLAMA_NO_CLOUD=1.": (
        "Update Ollama and disable cloud with OLLAMA_NO_CLOUD=1.",
        "Actualiza Ollama y desactiva la nube con OLLAMA_NO_CLOUD=1.",
    ),
    "Введи тег Ollama, например qwen3.5:4b.": (
        "Enter an Ollama tag such as qwen3.5:4b.", "Indica una etiqueta de Ollama, por ejemplo qwen3.5:4b.",
    ),
    "Выбери локальную модель Ollama вместо облачной.": (
        "Choose a local Ollama model.", "Elige un modelo local de Ollama.",
    ),
    "Укажи локальный адрес Ollama, например http://127.0.0.1:11434.": (
        "Enter a local Ollama address such as http://127.0.0.1:11434.",
        "Indica una dirección local de Ollama, por ejemplo http://127.0.0.1:11434.",
    ),
    "Не удалось прочитать размер модели из каталога Ollama.": (
        "Couldn't read the model size from the Ollama library.",
        "No se pudo leer el tamaño del modelo en el catálogo de Ollama.",
    ),
    "Загрузка модели Ollama завершилась без подтверждения.": (
        "Ollama didn't confirm that the model finished downloading.",
        "Ollama no confirmó que terminara la descarga del modelo.",
    ),
    "Настройки Agent Utka": ("Agent Utka Settings", "Ajustes de Agent Utka"),
    "Настройки": ("Settings", "Ajustes"),
    "Распознавание, ответы и поиск по документам": (
        "Speech recognition, answers, and document search",
        "Reconocimiento de voz, respuestas y búsqueda en documentos",
    ),
    "Изменения применятся после перезапуска приложения.": (
        "Changes take effect when you restart the app.",
        "Los cambios se aplican al reiniciar la aplicación.",
    ),
    "Распознавание речи": ("Speech recognition", "Reconocimiento de voz"),
    "Источник распознавания": ("Speech provider", "Proveedor de voz"),
    "Встроенные модели": ("Built-in models", "Modelos integrados"),
    "Сервер ответов": ("Answer provider", "Proveedor de respuestas"),
    "Ollama · встроенный": ("Ollama · built-in", "Ollama · integrado"),
    "OpenAI-совместимый · локальный": ("OpenAI-compatible · local", "Compatible con OpenAI · local"),
    "Адрес локального сервера": ("Local server address", "Dirección del servidor local"),
    "Модель ответов": ("Answer model", "Modelo de respuestas"),
    "База знаний": ("Knowledge base", "Base de conocimientos"),
    "Папка индекса SQLite": ("SQLite index folder", "Carpeta del índice SQLite"),
    "Выбрать…": ("Choose…", "Elegir…"),
    "Пустое поле использует папку .runtime приложения.": (
        "Leave blank to use the app’s .runtime folder.",
        "Deja el campo vacío para usar la carpeta .runtime de la aplicación.",
    ),
    "Получаю список моделей…": ("Loading models…", "Cargando modelos…"),
    "Список недоступен. {detail}": ("Could not load models. {detail}", "No se pudieron cargar los modelos. {detail}"),
    "Доступно моделей · {count}": ("Models available · {count}", "Modelos disponibles · {count}"),
    "На сервере пока нет моделей.": ("The server has no models yet.", "El servidor aún no tiene modelos."),
    "Список": ("List models", "Listar modelos"),
    "Укажи имя модели ответов.": ("Enter a name for the answer model.", "Indica el nombre del modelo de respuestas."),
    "Выбери существующую папку для индекса.": (
        "Choose an existing folder for the index.", "Elige una carpeta existente para el índice.",
    ),
    "Укажи локальный адрес вида http://127.0.0.1:1234/v1.": (
        "Enter a local address like http://127.0.0.1:1234/v1.",
        "Indica una dirección local como http://127.0.0.1:1234/v1.",
    ),
    "Не удалось проверить адрес. {detail}": ("Could not check the address. {detail}", "No se pudo comprobar la dirección. {detail}"),
    "Не удалось сохранить настройки. {detail}": ("Could not save settings. {detail}", "No se pudieron guardar los ajustes. {detail}"),
    "Соединение с локальной моделью закрыто.": (
        "The connection to the local model is closed.", "La conexión con el modelo local está cerrada.",
    ),
    "Локальный сервер уже закрыт.": ("The local server has closed.", "El servidor local se ha cerrado."),
    "Сервер не вернул список моделей в ожидаемом формате.": (
        "The server returned an unexpected format for the model list.",
        "El servidor devolvió un formato inesperado para la lista de modelos.",
    ),
    "Скачай модель ответов в настройках, чтобы установить встроенный Ollama.": (
        "Download an answer model in Settings to install built-in Ollama.",
        "Descarga un modelo de respuestas en Ajustes para instalar Ollama integrado.",
    ),
    "Ollama не запустился. См. .runtime/ollama-app.log.": (
        "Ollama did not start. See .runtime/ollama-app.log.", "Ollama no se inició. Consulta .runtime/ollama-app.log.",
    ),
    "Сохранено. Настройки применятся при следующем запуске.": (
        "Saved. These settings take effect the next time you start the app.",
        "Guardado. Los ajustes se aplican la próxima vez que abras la aplicación.",
    ),
    "Не удалось скопировать промпт. {detail}": ("Could not copy the prompt. {detail}", "No se pudo copiar el prompt. {detail}"),
    "Промпт скопирован. Вставь его в чат агента в папке проекта.": (
        "Prompt copied. Paste it into an agent chat in your project folder.",
        "Prompt copiado. Pégalo en un chat del agente en la carpeta de tu proyecto.",
    ),
    "Документ проекта из Codex или Claude Code": (
        "Project document from Codex or Claude Code", "Documento del proyecto de Codex o Claude Code",
    ),
    "Копировать промпт": ("Copy prompt", "Copiar prompt"),
    "Закрыть": ("Close", "Cerrar"),
    "Сохранить": ("Save", "Guardar"),
}


def show_settings(app):
    if app.settings_window is not None:
        app.settings_window.lift()
        return

    background = app.window.cget("bg")
    surface, border = "#222622", "#383f39"
    muted, accent, error_color = "#b1bbb2", "#a9c9b6", "#ffb5ba"
    popup = app.settings_window = tk.Toplevel(app.window)
    popup.transient(app.window)
    popup.attributes("-topmost", app.top.get())
    popup.configure(bg=background)
    popup.resizable(True, True)
    popup.minsize(560, 1)
    settings = load_settings()
    style = ttk.Style(popup)
    style.configure("Copilot.Settings.TEntry", fieldbackground=background, foreground="#f3f5f1",
                    bordercolor=border, padding=(7, 4))
    style.map("Copilot.Settings.TEntry", bordercolor=[("focus", accent)])
    shell = tk.Frame(popup, bg=background, padx=18, pady=16)
    shell.pack(fill="both", expand=True)
    footer = tk.Frame(shell, bg=background)
    footer.pack(side="bottom", fill="x")
    body = tk.Frame(shell, bg=background)
    body.pack(fill="both", expand=True)
    canvas = tk.Canvas(body, bg=background, highlightthickness=0, width=1, height=1)
    scroll = ttk.Scrollbar(body, command=canvas.yview, style="Copilot.Vertical.TScrollbar")
    scroll.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    canvas.configure(yscrollcommand=scroll.set)
    form = tk.Frame(canvas, bg=background)
    form_window = canvas.create_window((0, 0), window=form, anchor="nw")
    form.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox(form_window)))
    canvas.bind("<Configure>", lambda event: canvas.itemconfigure(form_window, width=event.width))

    def scroll_settings(event):
        if event.delta:
            direction = -1 if event.delta > 0 else 1
            canvas.yview_scroll(direction * max(1, abs(event.delta) // 120), "units")
        return "break"

    def reveal_focused_field(event):
        widget = event.widget
        if not str(widget).startswith(str(form) + "."):
            return
        start = widget.winfo_rooty() - form.winfo_rooty()
        end = start + widget.winfo_height()
        height = canvas.winfo_height()
        if start < canvas.canvasy(0):
            canvas.yview_moveto(start / form.winfo_height())
        elif end > canvas.canvasy(height):
            canvas.yview_moveto((end - height) / form.winfo_height())

    popup.bind("<MouseWheel>", scroll_settings)
    popup.bind("<FocusIn>", reveal_focused_field)

    texts = []

    def t(source, **values):
        return translate(app.ui_language, COPY, source, **values)

    def label(parent, source, **kwargs):
        widget = app._label(parent, t(source), **kwargs)
        texts.append((widget, source))
        return widget

    def button(parent, source, command, **kwargs):
        widget = app._button(parent, t(source), command, **kwargs)
        texts.append((widget, source))
        return widget

    label(form, "Настройки", size=16, bold=True, bg=background).pack(fill="x")
    label(form, "Распознавание, ответы и поиск по документам", color=muted,
          bg=background).pack(fill="x", pady=(2, 12))

    stt = tk.StringVar()
    stt_model = tk.StringVar(value=settings["stt_model"])
    stt_url = tk.StringVar(value=settings["stt_url"])
    builtin_model = tk.StringVar()
    current_speech = tk.StringVar()
    current_answer = tk.StringVar()
    provider = tk.StringVar()
    model = tk.StringVar()
    endpoint = tk.StringVar()
    retrieval = tk.StringVar()
    rag_url = tk.StringVar(value=settings["rag_url"])
    directory = tk.StringVar(value=settings["rag_directory"])
    feedback = tk.StringVar()
    vram = tk.StringVar()
    loaded_model = tk.StringVar()
    feedback_message = ("Изменения применятся после перезапуска приложения.", {})
    poll_id = None
    vram_poll_id = None
    speech_poll_id = None
    picker = None
    speech_picker = None
    knowledge_window = None
    vram_reading = None
    measured_server = None
    unloading = False
    model_keys = {"ollama": "ollama", "ollama_local": "ollama_model", "openai_local": "llm_model"}
    models = {key: settings[model_keys[key]] for key in BRAIN_PROVIDERS}
    urls = {"ollama": "", "ollama_local": settings["ollama_url"], "openai_local": settings["llm_url"]}
    selected_provider = settings["llm_provider"] if settings["llm_provider"] in models else "ollama"
    selected_stt = settings["stt_engine"] if settings["stt_engine"] in ASR_ENGINES else "qwen"
    builtin_stt = selected_stt if selected_stt != "openai_local" else settings.get("stt_builtin_engine", "qwen")
    if builtin_stt not in ("qwen", "whisper"):
        builtin_stt = "qwen"
    whisper_model = settings.get("whisper_model", "large-v3")
    whisper_device = settings["whisper_device"]
    qwen_model = settings["qwen_model"]
    stt_sources = ("Встроенные модели", ASR_ENGINES["openai_local"])
    selected_retrieval = settings["rag_provider"]
    if selected_retrieval not in RETRIEVAL_PROVIDERS:
        selected_retrieval = "sqlite"
    model.set(models[selected_provider])
    endpoint.set(urls[selected_provider])

    def section(title):
        card = tk.Frame(form, bg=surface, padx=12, pady=10,
                        highlightbackground=border, highlightthickness=1)
        card.pack(fill="x", pady=(0, 9))
        card.columnconfigure(1, weight=1)
        label(card, title, size=11, bold=True, bg=surface).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        return card

    field_labels = {}

    def field(card, title, number):
        heading = label(card, title, size=9, color=muted, bg=surface)
        heading.grid(row=number, column=0, sticky="w", padx=(0, 12), pady=3)
        row = tk.Frame(card, bg=surface)
        row.grid(row=number, column=1, sticky="ew", pady=3)
        field_labels[row] = heading
        return row

    def set_field_visible(row, visible):
        for widget in (field_labels[row], row):
            widget.grid() if visible else widget.grid_remove()

    def combo(row, var, choices=(), state="readonly"):
        widget = ttk.Combobox(row, textvariable=var, values=list(choices), state=state,
                              style="Copilot.TCombobox")
        widget.pack(side="left", fill="x", expand=True)
        return widget

    def entry_field(card, title, number, var):
        row = field(card, title, number)
        ttk.Entry(row, textvariable=var, style="Copilot.Settings.TEntry").pack(fill="x")
        return row

    speech_section = section("Распознавание речи")
    stt_box = combo(field(speech_section, "Источник распознавания", 1), stt)
    stt_address = entry_field(speech_section, "Адрес сервера распознавания", 2, stt_url)
    stt_model_row = entry_field(speech_section, "Модель распознавания", 3, stt_model)
    builtin_speech_row = field(speech_section, "Модель распознавания", 4)
    app._label(builtin_speech_row, var=builtin_model, bg=surface, size=9, wrap=240).pack(
        side="left", fill="x", expand=True)
    speech_status_row = tk.Frame(speech_section, bg=surface)
    speech_status_row.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(4, 0))
    app._label(speech_status_row, var=current_speech, bg=surface, color=muted, size=9, wrap=360).pack(
        side="left", fill="x", expand=True)
    model_section = section("Ответы")
    backend = combo(field(model_section, "Сервер ответов", 1), provider)
    address_row = entry_field(model_section, "Адрес локального сервера", 2, endpoint)
    row = field(model_section, "Модель ответов", 3)
    model_box = combo(row, model, state="normal")
    selected_model_label = app._label(row, var=model, bg=surface, size=9, wrap=240)
    gpu_row = tk.Frame(model_section, bg=surface)
    gpu_row.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(4, 0))
    app._label(gpu_row, var=current_answer, color=muted, bg=surface, size=9, wrap=500).pack(fill="x")
    app._label(gpu_row, var=vram, color=muted, bg=surface, size=9, wrap=500).pack(fill="x")
    gpu_actions = tk.Frame(gpu_row, bg=surface)
    gpu_actions.pack(fill="x", pady=(3, 0))
    unload_row = tk.Frame(gpu_row, bg=surface)
    loaded_box = combo(unload_row, loaded_model)
    loaded_box.pack(side="left", fill="x", expand=True)
    knowledge_section = section("База знаний")
    retrieval_box = combo(field(knowledge_section, "Поиск по проекту", 1), retrieval)
    search_address = entry_field(knowledge_section, "Адрес API поиска", 2, rag_url)
    row = field(knowledge_section, "Папка индекса SQLite", 3)
    ttk.Entry(row, textvariable=directory, style="Copilot.Settings.TEntry").pack(
        side="left", fill="x", expand=True)

    def choose_directory():
        folder = filedialog.askdirectory(parent=popup, title=t("Папка индекса SQLite"))
        if folder:
            directory.set(folder)

    button(row, "Выбрать…", choose_directory).pack(side="left", padx=(6, 0))
    label(knowledge_section, "Пустое поле использует папку .runtime приложения.",
          color=muted, bg=surface, size=9).grid(row=4, column=0, columnspan=2, sticky="w", pady=(1, 8))

    def show_feedback(source, *, error=False, **values):
        nonlocal feedback_message
        feedback_message = (source, values)
        feedback.set(t(source, **values))
        feedback_label.configure(fg=error_color if error else accent)

    def show_error(error, fallback):
        detail = str(error)
        if detail in COPY:
            show_feedback(detail, error=True)
        else:
            show_feedback(fallback, error=True, detail=detail)

    def resize_to_form():
        popup.update_idletasks()
        width = max(560, popup.winfo_width(), form.winfo_reqwidth() + scroll.winfo_reqwidth() + 36)
        footer_height = footer.winfo_reqheight() + 32
        available_height = max(240, popup.winfo_screenheight() - 100)
        height = min(available_height, form.winfo_reqheight() + footer_height)
        popup.minsize(560, min(height, footer_height + 80))
        popup.geometry(f"{width}x{height}")

    def switch_provider(_event):
        nonlocal selected_provider
        models[selected_provider] = model.get()
        urls[selected_provider] = endpoint.get()
        selected_provider = tuple(BRAIN_PROVIDERS)[backend.current()]
        model.set(models[selected_provider])
        endpoint.set(urls[selected_provider])
        model_box["values"] = []
        update_fields()
        refresh_vram()

    backend.bind("<<ComboboxSelected>>", switch_provider)

    def switch_stt(_event):
        nonlocal selected_stt
        selected_stt = "openai_local" if stt_box.current() == 1 else builtin_stt
        update_fields()

    def switch_retrieval(_event):
        nonlocal selected_retrieval
        selected_retrieval = tuple(RETRIEVAL_PROVIDERS)[retrieval_box.current()]
        update_fields()

    stt_box.bind("<<ComboboxSelected>>", switch_stt)
    retrieval_box.bind("<<ComboboxSelected>>", switch_retrieval)

    def update_fields():
        set_field_visible(stt_address, selected_stt == "openai_local")
        set_field_visible(stt_model_row, selected_stt == "openai_local")
        set_field_visible(builtin_speech_row, selected_stt != "openai_local")
        builtin_model.set(speech_name())
        set_field_visible(address_row, selected_provider != "ollama")
        set_field_visible(search_address, selected_retrieval == "http_local")
        for widget in (model_box, list_button, selected_model_label, choose_model_button):
            widget.pack_forget()
        if selected_provider.startswith("ollama"):
            choose_model_button.pack(side="right")
            selected_model_label.pack(side="left", fill="x", expand=True)
        else:
            list_button.pack(side="right", padx=(5, 0))
            model_box.pack(side="left", fill="x", expand=True)
        resize_to_form()

    def speech_name():
        if builtin_stt == "whisper":
            return f"Faster Whisper · {whisper_model} · {WHISPER_DEVICES.get(whisper_device, 'Auto')}"
        return QWEN_ASR_MODELS[qwen_model][0]

    def render_current_models():
        actual = app.settings["stt_engine"]
        speech = app.speech_session.loaded() if app.speech_session is not None else None
        if actual == "openai_local":
            status = f"{app.settings['stt_model']} · {t('Моделью управляет локальный сервер.')}"
        elif app.speech_unloading.is_set():
            status = t("Распознавание выгружается…")
        elif speech is None:
            status = t("Модель распознавания не загружена.")
        else:
            name, device = speech
            status = t("В памяти · {name} · {device}", name=name, device=device.upper())
        if current_speech.get() != status:
            current_speech.set(status)
        speech_unload.state(["!disabled"] if speech and actual != "openai_local"
                            and not app.speech_unloading.is_set() else ["disabled"])
        name = app.llm.model or "—"
        status = t("Модель сеанса · {name}", name=name)
        if app.settings["llm_provider"] == "openai_local":
            status += f" · {t('Моделью управляет локальный сервер.')}"
        if current_answer.get() != status:
            current_answer.set(status)

    def poll_speech():
        nonlocal speech_poll_id
        render_current_models()
        speech_poll_id = popup.after(650, poll_speech)

    def unload_speech():
        app.unload_speech()
        render_current_models()

    def choose_speech_model():
        nonlocal speech_picker
        if speech_picker is not None and speech_picker.winfo_exists():
            speech_picker.lift()
            return

        def use_model(engine, variant, device):
            nonlocal selected_stt, builtin_stt, whisper_model, whisper_device, qwen_model
            updates = {"stt_engine": engine, "stt_builtin_engine": engine}
            if engine == "whisper":
                updates.update(whisper_model=variant, whisper_device=device)
            else:
                updates["qwen_model"] = variant
            save_settings(updates)
            selected_stt = builtin_stt = engine
            if engine == "whisper":
                whisper_model = variant
                whisper_device = device
            else:
                qwen_model = variant
            update_fields()
            show_feedback("Сохранено. Настройки применятся при следующем запуске.")

        speech_picker = show_speech_picker(
            app, popup, runtime=RUNTIME, use_model=use_model, vram=vram,
            current=current_speech, unload=unload_speech, device=whisper_device,
            selected=whisper_model if builtin_stt == "whisper" else qwen_model,
        )

    def brain_options():
        name = model.get().strip()
        return {"llm_provider": selected_provider, "ollama": name, "ollama_model": name,
                "llm_model": name, "ollama_url": endpoint.get(), "llm_url": endpoint.get()}

    def open_brain(options):
        key = options["llm_provider"]
        if key == "ollama" and app.settings["llm_provider"] == "ollama":
            return app.llm
        return create_brain(RUNTIME, options)

    def choose_ollama_model():
        nonlocal picker
        if picker is not None and picker.winfo_exists():
            picker.lift()
            return
        options = brain_options()
        key = options["llm_provider"]
        if key == "ollama_local":
            try:
                options["ollama_url"] = local_ollama_url(options["ollama_url"])
            except ValueError as error:
                show_error(error, "Не удалось проверить адрес. {detail}")
                return

        def with_brain(action):
            brain = open_brain(options)
            try:
                return action(brain)
            finally:
                if brain is not app.llm:
                    brain.close()

        def use_model(name):
            updates = {"llm_provider": key, model_keys[key]: validate_ollama_model(name)}
            if key == "ollama_local":
                updates["ollama_url"] = options["ollama_url"]
            save_settings(updates)
            if key == "ollama":
                (RUNTIME / "installer-setup.complete").touch()
            models[key] = name
            model.set(name)
            show_feedback("Выбрана {model}. Перезапусти Agent Utka, чтобы использовать её для ответов.", model=name)

        def load_installed():
            if key == "ollama" and not (RUNTIME / "ollama" / "ollama.exe").is_file():
                return []
            return with_brain(lambda brain: brain.model_details())

        def load_running():
            return with_brain(lambda brain: brain.running_models() if brain.external_host or brain.host else [])

        picker = show_model_picker(
            app, popup,
            load_installed=load_installed,
            download=lambda name, progress, cancelled: with_brain(
                lambda brain: download_answer_model(brain, name, progress, cancelled)),
            use_model=use_model, vram=vram, selected=model.get(), current=current_answer,
            load_running=load_running, unload=lambda name: with_brain(lambda brain: brain.unload_model(name)),
            after_unload=refresh_vram,
        )

    def fetch_compatible_models():
        nonlocal poll_id
        if poll_id is not None:
            return
        options = brain_options()
        try:
            local_api_url(options["llm_url"])
        except ValueError as error:
            show_error(error, "Не удалось проверить адрес. {detail}")
            return
        list_button.state(["disabled"])
        show_feedback("Получаю список моделей…")
        result = queue.SimpleQueue()

        def work():
            brain = None
            try:
                brain = create_brain(RUNTIME, options)
                result.put((brain.models(), None))
            except (OSError, ValueError, RuntimeError) as error:
                result.put(([], error))
            finally:
                if brain is not None:
                    brain.close()

        def read_result():
            nonlocal poll_id
            try:
                names, error = result.get_nowait()
            except queue.Empty:
                poll_id = popup.after(100, read_result)
                return
            poll_id = None
            list_button.state(["!disabled"])
            if selected_provider != "openai_local" or endpoint.get() != options["llm_url"]:
                return
            model_box["values"] = names
            if error is not None:
                show_error(error, "Список недоступен. {detail}")
            elif names:
                if not model.get().strip():
                    model.set(names[0])
                show_feedback("Доступно моделей · {count}", count=len(names))
            else:
                show_feedback("На сервере пока нет моделей.")

        threading.Thread(target=work, daemon=True).start()
        poll_id = popup.after(100, read_result)

    def render_vram():
        if vram_reading is None:
            vram.set(t("Запрашиваю VRAM…"))
            return
        devices, running = vram_reading
        lines = [t("Свободно {free:.1f} из {total:.1f} ГиБ · {name}", name=gpu.name,
                   free=gpu.free_mib / 1024, total=gpu.total_mib / 1024) for gpu in devices]
        if not lines:
            lines.append(t("Замер свободной VRAM недоступен. Для замера нужен NVIDIA nvidia-smi."))
        lines.extend(t("Ollama · {name} занимает {size:.1f} ГиБ VRAM", name=item.name,
                       size=item.size_vram / 1024**3) for item in running if item.size_vram is not None)
        vram.set("\n".join(lines))

    def open_task_manager():
        try:
            subprocess.Popen(["Taskmgr.exe"])
        except OSError as error:
            show_error(error, "Не удалось открыть Диспетчер задач. {detail}")

    def refresh_vram(unload=None):
        nonlocal vram_poll_id, vram_reading, unloading
        if unloading:
            return
        if vram_poll_id is not None:
            popup.after_cancel(vram_poll_id)
        vram_reading = None
        render_vram()
        vram_button.state(["disabled"])
        unload_row.pack_forget()
        options = brain_options()
        server = (options["llm_provider"], options["ollama_url"])
        unloading = unload is not None
        result = queue.SimpleQueue()

        def work():
            running = []
            brain = None
            error = None
            try:
                key = options["llm_provider"]
                if key == "ollama_local":
                    brain = open_brain(options)
                elif key == "ollama" and app.settings["llm_provider"] == "ollama" and getattr(app.llm, "host", None):
                    brain = app.llm
                if brain is not None:
                    if unload is not None:
                        brain.unload_model(unload)
                    running = brain.running_models()
                elif unload is not None:
                    raise RuntimeError("Локальный сервер уже закрыт.")
            except (OSError, ValueError, RuntimeError) as exc:
                error = exc
            finally:
                if brain is not None and brain is not app.llm:
                    brain.close()
            result.put((read_vram(), running, error))

        def read_result():
            nonlocal vram_poll_id, vram_reading, unloading, measured_server
            try:
                devices, running, error = result.get_nowait()
            except queue.Empty:
                vram_poll_id = popup.after(100, read_result)
                return
            vram_poll_id = None
            unloading = False
            vram_button.state(["!disabled"])
            measured_server = server
            vram_reading = devices, running
            names = [item.name for item in running]
            loaded_box["values"] = names
            if names:
                if loaded_model.get() not in names:
                    loaded_model.set(names[0])
                unload_row.pack(fill="x", pady=(4, 0))
            if unload is not None:
                if error is not None:
                    show_feedback("Не удалось выгрузить {name}. {detail}", error=True,
                                  name=unload, detail=t(str(error)))
                else:
                    show_feedback("{name} всё ещё в памяти. Обнови VRAM после завершения запроса."
                                  if unload in names else "{name} выгружена из памяти Ollama.", name=unload)
                if (selected_provider, endpoint.get()) != server:
                    refresh_vram()
                    return
            render_vram()
            resize_to_form()

        threading.Thread(target=work, daemon=True).start()
        vram_poll_id = popup.after(100, read_result)

    def unload_model():
        if (selected_provider, endpoint.get()) != measured_server:
            refresh_vram()
            return
        name = loaded_model.get()
        if vram_reading is not None and any(item.name == name for item in vram_reading[1]):
            show_feedback("Выгружаю {name} из Ollama…", name=name)
            refresh_vram(unload=name)

    list_button = button(model_box.master, "Список", fetch_compatible_models)
    choose_model_button = button(model_box.master, "Выбрать модель…", choose_ollama_model, primary=True)
    button(builtin_speech_row, "Выбрать модель…", choose_speech_model, primary=True).pack(side="right")
    speech_unload = button(speech_status_row, "Выгрузить модель", unload_speech)
    speech_unload.pack(side="right", padx=(6, 0))
    vram_button = button(gpu_actions, "Проверить VRAM", refresh_vram)
    vram_button.pack(side="right")
    button(gpu_actions, "Диспетчер задач", open_task_manager).pack(side="left")
    button(unload_row, "Выгрузить модель", unload_model).pack(side="right", padx=(6, 0))

    def save():
        try:
            name = model.get().strip()
            if not name:
                raise ValueError("Укажи имя модели ответов.")
            folder = directory.get().strip()
            if folder and not Path(folder).expanduser().is_dir():
                raise ValueError("Выбери существующую папку для индекса.")
            updates = {"stt_engine": selected_stt, "llm_provider": selected_provider,
                       "stt_builtin_engine": builtin_stt, "rag_directory": folder, "rag_provider": selected_retrieval}
            if selected_stt == "openai_local":
                speech_name = stt_model.get().strip()
                if not speech_name:
                    raise ValueError("Укажи имя модели распознавания.")
                updates.update(stt_url=local_api_url(stt_url.get()), stt_model=speech_name)
            if selected_retrieval == "http_local":
                updates["rag_url"] = local_search_url(rag_url.get())
            if selected_provider == "openai_local":
                updates.update(llm_url=local_api_url(endpoint.get()), llm_model=name)
            else:
                updates[model_keys[selected_provider]] = validate_ollama_model(name)
                if selected_provider == "ollama_local":
                    updates["ollama_url"] = local_ollama_url(endpoint.get())
            save_settings(updates)
        except (OSError, ValueError) as error:
            show_error(error, "Не удалось сохранить настройки. {detail}")
            return
        show_feedback("Сохранено. Настройки применятся при следующем запуске.")

    def copy_prompt():
        try:
            suffix = {"ru": ".ru", "es": ".es"}.get(app.ui_language, "")
            prompt = (BASE / "docs" / f"knowledge-pack-prompt{suffix}.md").read_text(encoding="utf-8")
        except OSError as error:
            show_error(error, "Не удалось скопировать промпт. {detail}")
            return
        popup.clipboard_clear()
        popup.clipboard_append(prompt)
        show_feedback("Промпт скопирован. Вставь его в чат агента в папке проекта.")

    prompt_row = tk.Frame(knowledge_section, bg=surface)
    prompt_row.grid(row=5, column=0, columnspan=2, sticky="ew")
    label(prompt_row, "Документ проекта из Codex или Claude Code", color=muted,
          bg=surface, size=9, wrap=260).pack(side="left", fill="x", expand=True)
    button(prompt_row, "Копировать промпт", copy_prompt).pack(side="right", padx=(8, 0))

    def browse_knowledge():
        nonlocal knowledge_window
        if knowledge_window is not None and knowledge_window.winfo_exists():
            knowledge_window.lift()
        elif app.project is None or app.index is None:
            show_feedback("Выбери проект или импортируй документы, чтобы открыть индекс.")
        else:
            knowledge_window = show_knowledge_window(app, popup, app.index, app.project)

    button(knowledge_section, "Посмотреть индекс…", browse_knowledge).grid(row=6, column=0, columnspan=2,
                                                                        sticky="e", pady=(7, 0))

    def cleanup(event):
        if event.widget is not popup:
            return
        if poll_id is not None:
            popup.after_cancel(poll_id)
        if vram_poll_id is not None:
            popup.after_cancel(vram_poll_id)
        if speech_poll_id is not None:
            popup.after_cancel(speech_poll_id)
        app.settings_window = None

    def close(_event=None):
        popup.destroy()
        return "break"

    feedback_label = app._label(footer, var=feedback, size=9, color=accent, bg=background, wrap=462)
    feedback_label.configure(height=2, anchor="nw")
    feedback_label.pack(fill="x", pady=(1, 5))
    actions = tk.Frame(footer, bg=background)
    actions.pack(fill="x")
    button(actions, "Закрыть", close).pack(side="right")
    save_button = button(actions, "Сохранить", save, primary=True)
    save_button.pack(side="right", padx=(0, 8))

    def refresh_language(_event=None):
        popup.title(t("Настройки Agent Utka"))
        for widget, source in texts:
            widget.configure(text=t(source))
        backend["values"] = [t(title) for title in BRAIN_PROVIDERS.values()]
        provider.set(t(BRAIN_PROVIDERS[selected_provider]))
        stt_box["values"] = [t(title) for title in stt_sources]
        stt.set(t(stt_sources[int(selected_stt == "openai_local")]))
        retrieval_box["values"] = [t(title) for title in RETRIEVAL_PROVIDERS.values()]
        retrieval.set(t(RETRIEVAL_PROVIDERS[selected_retrieval]))
        source, values = feedback_message
        feedback.set(t(source, **values))
        render_vram()
        render_current_models()
        update_fields()

    popup.protocol("WM_DELETE_WINDOW", close)
    popup.bind("<Escape>", close)
    popup.bind("<Destroy>", cleanup)
    popup.bind("<<UILanguageChanged>>", refresh_language)
    refresh_language()
    refresh_vram()
    poll_speech()
    stt_box.focus_set()
