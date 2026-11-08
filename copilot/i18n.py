import re
import tkinter as tk


LANGUAGES = {"ru": "Русский", "en": "English", "es": "Español"}


def translate(language, catalog, source, **values):
    translations = catalog.get(source)
    if translations and language in ("en", "es"):
        source = translations[0 if language == "en" else 1]
    return source.format(**values) if values else source


def flag_images(master):
    """Small native Tk images so Windows does not depend on emoji fonts."""
    images = {code: tk.PhotoImage(master=master, width=18, height=12) for code in LANGUAGES}

    def band(code, color, top, bottom, left=0, right=18):
        images[code].put(color, to=(left, top, right, bottom))

    for row, color in enumerate(("#ffffff", "#2355a5", "#ca3437")):
        band("ru", color, row * 4, row * 4 + 4)
    for row in range(12):
        band("en", "#b22234" if row % 2 == 0 else "#ffffff", row, row + 1)
    band("en", "#3c3b6e", 0, 7, right=8)
    for x, y in ((1, 1), (4, 1), (6, 2), (2, 3), (4, 4), (1, 5), (6, 5)):
        images["en"].put("#ffffff", (x, y))
    band("es", "#aa151b", 0, 12)
    band("es", "#f1bf00", 3, 9)
    band("es", "#aa151b", 5, 8, left=5, right=7)
    return images


OVERLAY_COPY = {
    "Импорт файла…": ("Import a file…", "Importar archivo…"),
    "Добавить файл в базу": ("Add file to knowledge base", "Añadir archivo a la base"),
    "Изменить название выжимки…": ("Edit document name…", "Editar nombre del documento…"),
    "Добавь файл .md или .txt. Если файла нет, скопируй промпт в чат проекта в Codex или Claude Code.": (
        "Add an .md or .txt file. To create one, copy the prompt into your project chat in Codex or Claude Code.",
        "Añade un archivo .md o .txt. Para crearlo, copia el prompt en el chat del proyecto en Codex o Claude Code."),
    "Создай базу или импортируй готовую выжимку. Промпт поможет собрать знания.": (
        "Create a base or import a summary. Use the prompt to gather knowledge.",
        "Crea una base o importa un resumen. Usa el prompt para reunir conocimientos."),
    "Новая база": ("New base", "Nueva base"),
    "Название базы": ("Base name", "Nombre de la base"),
    "Создать базу": ("Create base", "Crear base"),
    "Открыть базу": ("Open base", "Abrir base"),
    "Не удалось создать базу": ("Couldn't create the base", "No se pudo crear la base"),
    "Например: проект, продукт или команда. Выжимки добавишь после создания.": (
        "For example: a project, product or team. Add documents after creating it.",
        "Por ejemplo: un proyecto, producto o equipo. Añade documentos después."),
    "База создана. Скопируй промпт или импортируй готовую выжимку.": (
        "Base created. Copy the prompt or import an existing summary.",
        "Base creada. Copia el prompt o importa un resumen existente."),
    "Создай или выбери базу на главном экране.": (
        "Create or select a base on the main screen.", "Crea o selecciona una base en la pantalla principal."),
    "Готово · напиши вопрос или выдели реплику в расшифровке.": (
        "Ready · type a question or select a transcript passage.",
        "Listo · escribe una pregunta o selecciona un fragmento."),
    "Название выжимки": ("Document name", "Nombre del documento"),
    "Название видно в источниках. Исходный файл не изменится.": (
        "Shown in sources. The original file stays unchanged.",
        "Se muestra en las fuentes. El archivo original no cambia."),
    "Введи название выжимки — до 100 символов.": (
        "Enter a document name, up to 100 characters.", "Escribe un nombre de documento de hasta 100 caracteres."),
    "Свой вопрос · Ctrl+Enter": ("Your question · Ctrl+Enter", "Tu pregunta · Ctrl+Enter"),
    "Спросить": ("Ask", "Preguntar"),
    "Напиши вопрос в поле.": ("Type a question in the field.", "Escribe una pregunta en el campo."),
    "Все базы": ("All bases", "Todas las bases"),
    "Добавить в базу": ("Add to knowledge base", "Añadir a una base"),
    "Новая база…": ("New base…", "Nueva base…"),
    "Название новой базы": ("New base name", "Nombre de la nueva base"),
    "Введи название базы — до 100 символов.": (
        "Enter a base name, up to 100 characters.", "Escribe un nombre de hasta 100 caracteres."),
    "Такая база уже есть. Выбери её в списке.": (
        "This base already exists. Choose it from the list.", "Esta base ya existe. Selecciónala en la lista."),
    "В одну базу можно добавить несколько выжимок.": (
        "You can add several summaries to one base.", "Puedes añadir varios resúmenes a una base."),
    "Импортировать": ("Import", "Importar"),
    "Отмена": ("Cancel", "Cancelar"),
    "Ищу ответ во всех базах…": ("Searching all bases…", "Buscando en todas las bases…"),
    "ИИ-помощник для звонков": ("AI assistant for calls", "Asistente de IA para llamadas"),
    "Подготовка локальных моделей…": ("Preparing local models…", "Preparando los modelos locales…"),
    "Скопируй промпт в Codex или Claude Code. Затем импортируй готовую выжимку.": (
        "Paste the prompt into Codex or Claude Code, then import the summary.",
        "Pega el prompt en Codex o Claude Code e importa el resumen."),
    "Скопировать промпт": ("Copy prompt", "Copiar prompt"),
    "Импортировать выжимку": ("Import summary", "Importar resumen"),
    "Выбери готовую выжимку": ("Choose the finished summary", "Elige el resumen generado"),
    "Не удалось скопировать промпт": ("Couldn't copy the prompt", "No se pudo copiar el prompt"),
    "Промпт скопирован. Вставь его в Codex или Claude Code, затем импортируй выжимку.": (
        "Prompt copied. Paste it into Codex or Claude Code, then import the summary.",
        "Prompt copiado. Pégalo en Codex o Claude Code e importa el resumen."),
    "Импортирую выжимку…": ("Importing summary…", "Importando el resumen…"),
    "Импорт не завершён. Проверь файл и повтори.": (
        "Import failed. Check the file and try again.", "Error al importar. Revisa el archivo e inténtalo de nuevo."),
    "Импортируй выжимку, чтобы получать ответы.": (
        "Import a summary to get answers.", "Importa un resumen para obtener respuestas."),
    "Готово · выдели вопрос в расшифровке и нажми «Дай ответ».": (
        "Ready · select a question in the transcript and click Ask.",
        "Listo · selecciona una pregunta en la transcripción y pulsa Preguntar."),
    "Подготавливаю базу…": ("Preparing knowledge…", "Preparando la base…"),
    "Пауза": ("Pause", "Pausar"),
    "Речь появится в расшифровке": ("Waiting for speech", "Esperando que alguien hable"),
    "Свернуть": ("Minimize", "Contraer"),
    "Развернуть": ("Expand", "Expandir"),
    "БАЗА ЗНАНИЙ": ("KNOWLEDGE BASE", "BASE DE CONOCIMIENTO"),
    "Поверх · вкл.": ("On top · on", "Siempre visible"),
    "Поверх · выкл.": ("On top · off", "Sin fijar"),
    "Папка…": ("Folder…", "Carpeta…"),
    "Импорт…": ("Import…", "Importar…"),
    "Настройки": ("Settings", "Ajustes"),
    "Расшифровка": ("Transcript", "Transcripción"),
    "К концу": ("Jump to end", "Ir al final"),
    "Здесь появится речь, которую воспроизводит Windows.": (
        "Speech from Windows audio will appear here.", "Aquí aparecerá lo que se diga en el audio de Windows."),
    "Дай ответ": ("Ask", "Responder"),
    "Ответ": ("Answer", "Respuesta"),
    "Источники": ("Sources", "Fuentes"),
    "Источники · {count}": ("Sources · {count}", "Fuentes · {count}"),
    "Выдели реплику или напиши свой вопрос.": (
        "Select a passage or type your own question.", "Selecciona un fragmento o escribe tu pregunta."),
    "К последней": ("Latest", "Última"),
    "История": ("History", "Historial"),
    "Слушать": ("Listen", "Escuchar"),
    "Пауза · звук не обрабатывается": ("Paused · audio processing stopped", "En pausa · no se procesa el audio"),
    "Подключение к звуку Windows…": ("Connecting to Windows audio…", "Conectando con el audio de Windows…"),
    "База не выбрана": ("No knowledge base selected", "Sin base de conocimiento seleccionada"),
    "Не удалось сохранить выбор": ("Couldn't save your selection", "No se pudo guardar la selección"),
    "Не удалось сохранить язык": ("Couldn't save your language", "No se pudo guardar el idioma"),
    "Индекс обновляется…": ("Updating the index…", "Actualizando el índice…"),
    "Выбери папку базы знаний": ("Choose a knowledge base folder", "Elige una carpeta para la base de conocimiento"),
    "Не удалось открыть базу": ("Couldn't open the knowledge base", "No se pudo abrir la base de conocimiento"),
    "Импорт в базу «{name}»": ("Import into “{name}”", "Importar a «{name}»"),
    "Документы Markdown и текст": ("Markdown and text documents", "Documentos Markdown y de texto"),
    "Обновить документы": ("Update documents", "Actualizar documentos"),
    "Заменить документы в базе «{name}»?": ("Replace documents in “{name}”?", "¿Reemplazar los documentos en «{name}»?"),
    "Загружаю документы…": ("Importing documents…", "Importando documentos…"),
    " · модель ответов недоступна": (" · answer model unavailable", " · modelo de respuesta no disponible"),
    "Прогрев локальной модели подсказок…": ("Starting the local answer model…", "Iniciando el modelo local de respuestas…"),
    "Распознавание не запустилось: {error}": ("Couldn't start speech recognition. {error}", "No se pudo iniciar el reconocimiento de voz. {error}"),
    "Звук недоступен · переподключение: {error}": ("Audio unavailable · reconnecting. {error}", "Audio no disponible · reconectando. {error}"),
    "{index} из {count}": ("{index} of {count}", "{index} de {count}"),
    " · новых {count}": (" · {count} more", " · {count} más"),
    "Ответов · {count}": ("Answers · {count}", "Respuestas · {count}"),
    "История · Agent Utka": ("History · Agent Utka", "Historial · Agent Utka"),
    "История подсказок": ("Answer history", "Historial de respuestas"),
    "Выделено · {count} симв. · Ctrl+Enter": ("Selection · {count} chars · Ctrl+Enter", "Selección · {count} car. · Ctrl+Enter"),
    "Последняя реплика · Ctrl+Enter": ("Latest remark · Ctrl+Enter", "Última intervención · Ctrl+Enter"),
    "Дождись реплики в расшифровке.": ("Wait for speech to appear in the transcript.", "Espera a que aparezca texto en la transcripción."),
    "Выбери базу через «Папка…».": ("Choose a knowledge base with Folder…", "Elige una base de conocimiento con Carpeta…"),
    "База ещё готовится. Попробуй после обновления.": ("The knowledge base is still being indexed. Try again when it's ready.", "La base de conocimiento aún se está indexando. Inténtalo cuando esté lista."),
    "Загрузи документы через «Импорт…».": ("Add documents with Import…", "Añade documentos con Importar…"),
    "Ищу ответ в базе проекта…": ("Searching the project knowledge base…", "Buscando en la base de conocimiento del proyecto…"),
    "Источники · Agent Utka": ("Sources · Agent Utka", "Fuentes · Agent Utka"),
    "Источники ответа": ("Answer sources", "Fuentes de la respuesta"),
    "Фрагменты, на которых основан ответ.": ("Excerpts that support the answer.", "Fragmentos que respaldan la respuesta."),
    "строка {line}": ("line {line}", "línea {line}"),
    "Готова · файлов {count}{stamp}": ("Ready · {count} files{stamp}", "Lista · {count} archivos{stamp}"),
    "В базе пока нет документов. Нажми «Импорт…».": ("No documents yet. Select Import…", "Aún no hay documentos. Selecciona Importar…"),
    "Ошибка обновления: {error}": ("Couldn't update the index. {error}", "No se pudo actualizar el índice. {error}"),
    "Импорт базы знаний": ("Knowledge base import", "Importación de la base de conocimiento"),
    "Загружено документов · {count}. Обновляю индекс…": ("Documents imported · {count}. Updating the index…", "Documentos importados · {count}. Actualizando el índice…"),
    "Слушаю · {device}{warning}": ("Listening · {device}{warning}", "Escuchando · {device}{warning}"),
    "Готово · {elapsed:.1f} с": ("Ready · {elapsed:.1f} s", "Lista · {elapsed:.1f} s"),
    "Не удалось получить ответ из базы": ("Couldn't get an answer from the knowledge base", "No se pudo obtener una respuesta de la base de conocimiento"),
    "Локальный API поиска недоступен. Проверь адрес в настройках.": (
        "Local search API unavailable. Check its address in Settings.",
        "API de búsqueda local no disponible. Comprueba la dirección en Ajustes.",
    ),
    "Слышу речь…": ("Speech detected…", "Voz detectada…"),
    "Распознаю реплику…": ("Transcribing…", "Transcribiendo…"),
    "Ответ из базы": ("Answer from the knowledge base", "Respuesta de la base de conocimiento"),
    "Нет ответа в базе": ("No answer in the knowledge base", "Sin respuesta en la base de conocimiento"),
    "По этому фрагменту не нашёл подтверждённого ответа.": ("No verified answer found for this passage.", "No se encontró una respuesta verificada para este fragmento."),
    "Локальная модель подсказок недоступна.": ("The local answer model is unavailable.", "El modelo local de respuestas no está disponible."),
    "Ошибка ответа": ("Answer unavailable", "Respuesta no disponible"),
    "Подсказка": ("Suggestion", "Sugerencia"),
    "Варианты ответа": ("Suggested answers", "Respuestas sugeridas"),
    "Вариант уточнения": ("Suggested clarification", "Aclaración sugerida"),
    "Из разговора": ("From the conversation", "De la conversación"),
    "Услышано": ("Heard", "Texto reconocido"),
    "Услышано · генерация недоступна": ("Heard · generation unavailable", "Texto reconocido · generación no disponible"),
    "Загрузка {model} · {device}…": ("Loading {model} · {device}…", "Cargando {model} · {device}…"),
    "Загрузка {model} INT8 · CPU…": ("Loading {model} INT8 · CPU…", "Cargando {model} INT8 · CPU…"),
    "Проверяю модель {model}…": ("Checking {model}…", "Comprobando {model}…"),
    "Qwen ASR на GPU недоступен. Загружаю Qwen ASR на CPU…": ("Qwen ASR is unavailable on the GPU. Loading it on the CPU…", "Qwen ASR no está disponible en la GPU. Cargando en la CPU…"),
    "Faster Whisper на GPU недоступен. Загружаю модель на CPU…": ("Faster Whisper is unavailable on the GPU. Loading it on the CPU…", "Faster Whisper no está disponible en la GPU. Cargando en la CPU…"),
    "Распознавание: {error}": ("Speech recognition. {error}", "Reconocimiento de voz. {error}"),
    "Не найдены файлы Qwen ASR. Запусти Setup Agent Utka.ps1.": ("Qwen ASR files are missing. Run Setup Agent Utka.ps1.", "Faltan los archivos de Qwen ASR. Ejecuta Setup Agent Utka.ps1."),
    "Укажи имя модели распознавания.": ("Enter a speech recognition model name.", "Indica el nombre del modelo de reconocimiento de voz."),
    "Укажи локальный адрес вида http://127.0.0.1:1234/v1.": ("Enter a loopback address such as http://127.0.0.1:8000/v1.", "Indica una dirección local como http://127.0.0.1:8000/v1."),
    "Сервер распознавания не вернул текст в ожидаемом формате.": ("The transcription server returned an unexpected response.", "El servidor de transcripción devolvió una respuesta inesperada."),
    "Faster Whisper недоступен. Установи faster-whisper и Microsoft Visual C++ Runtime.": ("Faster Whisper is unavailable. Install faster-whisper and the Microsoft Visual C++ Runtime.", "Faster Whisper no está disponible. Instala faster-whisper y Microsoft Visual C++ Runtime."),
    "Модель Faster Whisper large-v3 отсутствует в .runtime/whisper. Подготовь её по README.": ("Faster Whisper large-v3 is missing from .runtime/whisper. See the README for setup.", "Falta Faster Whisper large-v3 en .runtime/whisper. Consulta el README para instalarlo."),
    "Устройство вывода Windows изменилось": ("The Windows playback device changed", "Cambió el dispositivo de reproducción de Windows"),
    "Выбери отдельную папку проекта.": ("Choose a separate project folder.", "Elige una carpeta de proyecto separada."),
    "В словаре нужны terms с точными написаниями.": ("The glossary needs terms with their exact spelling.", "El glosario necesita terms con la ortografía exacta."),
    "hotwords должен содержать до 20 терминов из terms.": ("hotwords can contain up to 20 entries from terms.", "hotwords admite hasta 20 entradas de terms."),
    "aliases должен содержать до 200 правил произношения.": ("aliases can contain up to 200 pronunciation rules.", "aliases admite hasta 200 reglas de pronunciación."),
    "Каждое правило aliases должно содержать term из terms и список heard.": ("Each aliases rule needs a term from terms and a heard list.", "Cada regla de aliases necesita un term de terms y una lista heard."),
    "context должен содержать короткие соседние слова или фразы.": ("context must contain short surrounding words or phrases.", "context debe contener palabras o frases breves del contexto."),
    r"context допускает слова, фразы, |, \b и окончание \w*.": (r"context accepts words, phrases, |, \b, and a trailing \w*.", r"context admite palabras, frases, |, \b y la terminación \w*."),
    "В одном документе допустим один блок словаря распознавания.": ("A document can contain one speech glossary block.", "Cada documento puede contener un bloque de glosario de voz."),
    "Блок словаря распознавания нужно закрыть тройными обратными кавычками.": ("Close the speech glossary block with three backticks.", "Cierra el bloque de glosario de voz con tres acentos graves."),
    "Добавь текст знаний вне блока словаря.": ("Add knowledge text outside the glossary block.", "Añade texto fuera del bloque del glosario."),
    "Неверный JSON в словаре на строке {line}.": ("Invalid JSON in the glossary on line {line}.", "JSON no válido en el glosario en la línea {line}."),
    "Папка импорта не может быть ссылкой: {path}": ("The import folder cannot be a link. {path}", "La carpeta de importación no puede ser un enlace. {path}"),
    "Выбери документ .md или .txt с допустимым именем: {name}": ("Choose a .md or .txt file with a valid name. {name}", "Elige un archivo .md o .txt con un nombre válido. {name}"),
    "В одном импорте два файла с именем {name}.": ("Two files in this import have the name {name}.", "Hay dos archivos con el nombre {name} en esta importación."),
    "{name}: выбери существующий файл.": ("Choose an existing file. {name}", "Elige un archivo existente. {name}"),
    "{name}: размер документа должен быть от 1 до {limit} байт.": ("{name} must be between 1 and {limit} bytes.", "El archivo {name} debe tener entre 1 y {limit} bytes."),
    "{name}: обнаружены ключи, пароли или двоичные данные.": ("Keys, passwords or binary data found in {name}.", "Se encontraron claves, contraseñas o datos binarios en {name}."),
    "Недопустимый путь назначения: {path}": ("Invalid destination path. {path}", "La ruta de destino no es válida. {path}"),
    "Импортировано {count} из {total}. Не удалось записать {name}.": ("Imported {count} of {total}. Couldn't write {name}.", "Se importaron {count} de {total}. No se pudo escribir {name}."),
    "Не удалось прочитать файлы Git: {name}": ("Couldn't read Git files in {name}.", "No se pudieron leer los archivos Git de {name}."),
}


_DIAGNOSTIC_FORMATS = (
    (r"Загрузка (?P<model>.+) INT8 · CPU…", "Загрузка {model} INT8 · CPU…"),
    (r"Загрузка (?P<model>.+) · (?P<device>.+)…", "Загрузка {model} · {device}…"),
    (r"Проверяю модель (?P<model>.+)…", "Проверяю модель {model}…"),
    (r"Неверный JSON в словаре на строке (?P<line>\d+)\.", "Неверный JSON в словаре на строке {line}."),
    (r"Папка импорта не может быть ссылкой: (?P<path>.+)", "Папка импорта не может быть ссылкой: {path}"),
    (r"Выбери документ \.md или \.txt с допустимым именем: (?P<name>.+)", "Выбери документ .md или .txt с допустимым именем: {name}"),
    (r"В одном импорте два файла с именем (?P<name>.+)\.", "В одном импорте два файла с именем {name}."),
    (r"(?P<name>.+): выбери существующий файл\.", "{name}: выбери существующий файл."),
    (r"(?P<name>.+): размер документа должен быть от 1 до (?P<limit>\d+) байт\.", "{name}: размер документа должен быть от 1 до {limit} байт."),
    (r"(?P<name>.+): обнаружены ключи, пароли или двоичные данные\.", "{name}: обнаружены ключи, пароли или двоичные данные."),
    (r"Недопустимый путь назначения: (?P<path>.+)", "Недопустимый путь назначения: {path}"),
    (r"Импортировано (?P<count>\d+) из (?P<total>\d+)\. Не удалось записать (?P<name>.+)\.", "Импортировано {count} из {total}. Не удалось записать {name}."),
    (r"Не удалось прочитать файлы Git: (?P<name>.+)", "Не удалось прочитать файлы Git: {name}"),
)


def translate_diagnostic(language, message):
    """Localize known application diagnostics while preserving external error details."""
    if language == "ru":
        return message
    if message in OVERLAY_COPY:
        return translate(language, OVERLAY_COPY, message)
    for pattern, source in _DIAGNOSTIC_FORMATS:
        if match := re.fullmatch(pattern, message):
            return translate(language, OVERLAY_COPY, source, **match.groupdict())
    subject, sep, detail = message.partition(": ")
    if sep and subject == "Распознавание":
        return translate(language, OVERLAY_COPY, "Распознавание: {error}",
                         error=translate_diagnostic(language, detail))
    if sep and subject.lower().endswith((".md", ".txt")):
        return f"{subject}: {translate_diagnostic(language, detail)}"
    return message
