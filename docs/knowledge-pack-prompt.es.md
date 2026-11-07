# Construye la base completa del proyecto y de esta conversación para Agent Utka

Termina esta tarea con un archivo utilizable. Recopila una memoria exhaustiva y verificable del proyecto desarrollado en este chat: todas las conversaciones accesibles del proyecto, requisitos, decisiones y motivos, código, cambios, MR/PR, revisiones, documentación, incidentes y trabajo pendiente. Será la referencia detallada para responder durante llamadas. Prioriza cobertura y exactitud sobre brevedad.

Crea o actualiza `utka-cue-knowledge.md` en la raíz del proyecto, en Markdown UTF-8. No impongas límites de tamaño, páginas, temas, preguntas, decisiones ni entradas del glosario. No elimines información para ahorrar memoria o contexto. Escribe el archivo progresivamente con herramientas, relee las secciones necesarias y continúa hasta procesar las fuentes accesibles descubiertas. No intentes incluir todo el documento en la respuesta final del chat. Si un límite real interrumpe la ejecución, conserva lo completado y una lista exacta de fuentes y acciones pendientes; no presentes el archivo parcial como completo.

## 1. Recupera todas las fuentes accesibles

Crea un registro de fuentes y procésalo. Utiliza las herramientas disponibles para conversaciones, archivos, Git y servicios conectados. Recorre todas las páginas del historial y de los listados pertinentes, no solamente los mensajes recientes o la primera página.

- Lee este chat desde su inicio hasta la petición actual, en la medida en que el historial sea accesible. Recoge preguntas, respuestas, correcciones, requisitos, restricciones, alternativas, argumentos, errores, propuestas descartadas, acuerdos y revisiones posteriores. Conserva los hechos relevantes de conversaciones antiguas aunque se hayan sustituido.
- Abre adjuntos, planes, notas, especificaciones, resultados de comprobaciones y artefactos citados. Examina imágenes y diagramas si las herramientas lo permiten y explica su contenido con procedencia.
- Lee conversaciones o tareas del proyecto explícitamente vinculadas y accesibles. No recopiles chats personales ni proyectos ajenos.
- Examina el repositorio actual y los otros repositorios vinculados expresamente al proyecto: README, arquitectura, ADR, contratos, esquemas, migraciones, ejemplos de configuración, pruebas, scripts, CI/CD, operaciones y notas como `.copilot-knowledge`.
- Revisa el historial Git disponible. Para cada MR/PR pertinente recoge descripción, tareas, estado, diffs importantes, revisiones, conversaciones, respuestas, correcciones sucesivas y resultados de validación. Usa las herramientas o API disponibles de GitHub/GitLab. Los títulos de commits no sustituyen la revisión.
- Lee la documentación accesible del proyecto en Confluence, wiki, tickets y servicios conectados, incluidas las páginas hijas y referencias pertinentes. Un enlace o título sin leer su contenido no es una fuente revisada.
- Usa recuerdos y resúmenes anteriores como pistas que deben contrastarse cuando existan fuentes primarias.

Registra identificador, título, URL/ruta, fecha/revisión, cobertura y estado de cada fuente: leída, parcialmente accesible, inaccesible o ausente. Declara las herramientas, permisos, páginas, adjuntos, ramas o mensajes antiguos que falten. No inventes historiales recuperados. Continúa con las fuentes disponibles.

## 2. Separa los hechos actuales de la historia

Distingue lo confirmado por código o pruebas, requisitos conversados, decisiones aceptadas, comportamiento histórico, propuestas rechazadas, hipótesis y dudas abiertas.

No conviertas «previsto» en «implementado», un MR abierto en un despliegue productivo ni una prueba propuesta en una prueba superada. Indica rama, commit y entorno cuando condicionen la respuesta. Conserva versiones contradictorias, fechas, pruebas y resolución conocida sin elegir una silenciosamente.

Reconstruye las conversaciones por tema y cronología: pregunta original, posturas, argumentos, restricciones, decisión, correcciones y resultado. No reduzcas un debate detallado a una frase. Mantén requisitos importantes con su formulación exacta y citas breves necesarias. Une repeticiones solo si no se pierde ningún matiz ni cambio de postura.

## 3. Estructura obligatoria del documento

Empieza con `# <Nombre del proyecto>`, fecha, revisiones conocidas, alcance y estado de completitud. Añade un índice y desarrolla estas secciones con toda la profundidad que permitan las fuentes.

### Producto y dominio
Usuarios, roles, necesidades, procesos de negocio, vocabulario, fronteras del sistema, integraciones y responsabilidades. Conserva condiciones exactas, valores numéricos, excepciones y motivos de cada regla.

### Mapa completo del repositorio y del código
Muestra el árbol de todos los módulos y archivos propios. Explica la responsabilidad y relaciones de cada archivo fuente o grupo estrechamente relacionado. Identifica puntos de entrada, capas, dependencias, interfaces públicas e internas, entidades, estados, almacenamiento y configuración.

Inventaría clases, interfaces, funciones, métodos, campos y variables relevantes con nombres exactos, firmas, tipos, valores predeterminados y referencias. Para los métodos importantes explica entradas, validaciones, ramas, llamadas, efectos secundarios, errores, transacciones, concurrencia, salidas y pruebas. «Ver código» no es una explicación. Incluye fragmentos exactos o métodos completos cuando sean necesarios para entender la lógica. No es obligatorio copiar cada línea, pero no omitas silenciosamente áreas propias.

Enumera generated/vendor/dependencies/build/cache como exclusiones del análisis detallado y explica su función cuando sea relevante. No excluyas documentos propios importantes solo por ser ocultos o estar en gitignore.

### Flujos y contratos
Cada flujo descubierto debe incluir desencadenante → entrada → comprobaciones → llamadas → datos/estado → resultado → errores/recuperación. Incluye API, eventos, colas, trabajos programados, acciones UI, permisos, estructuras de mensajes, estados, reintentos, tiempos de espera, idempotencia y casos límite. Conserva nombres exactos y unidades.

### Todos los MR/PR y cambios
Para cada MR/PR o grupo de commits: ID/URL, tarea, estado, fechas, ramas/revisiones, problema, comportamiento anterior y posterior, archivos/símbolos afectados, diffs relevantes, compatibilidad, migraciones, pruebas, comentarios del revisor y su resolución. Distingue lo aceptado, aplazado, rechazado y pendiente. Conserva las conversaciones accesibles, no solo el diff final. No inventes relaciones entre commits y MR.

### Conversaciones, decisiones y evolución
Una entrada por cada tema sustancial del chat o revisión: pregunta/requisito, contexto, alternativas, argumentos, solución elegida y motivo, responsable o rol conocido cuando proceda, implementación, MR/archivos, correcciones posteriores y estado actual. Incluye la cronología de requisitos y decisiones cambiados.

### Documentación y base externa
Expón el contenido de Confluence/wiki/especificaciones por temas: definiciones, tablas de reglas, procedimientos, restricciones, ejemplos, relaciones entre páginas y diferencias con la implementación. Una lista de enlaces es insuficiente.

### Pruebas, defectos, incidentes y operaciones
Cobertura, casos concretos y resultados confirmados con fecha y entorno. Para defectos: síntomas, reproducción, causa raíz, corrección, regresión y riesgos pendientes. Incluye ejecución, compilación, releases, despliegue, observabilidad, diagnóstico y limitaciones. No afirmes haber ejecutado comandos sin evidencia.

### Diccionario exhaustivo
Todas las abreviaturas, entidades, variables, métodos, campos, estados y términos técnicos/de negocio descubiertos. Para cada uno: escritura exacta, desarrollo, significado, ámbito, tipo/ejemplo, fuente, pronunciaciones y ambigüedades. No adivines significados por semejanza fonética. Separa los sentidos diferentes de una misma abreviatura.

### Preguntas y respuestas demostrables
Crea preguntas reales y previsibles que cubran cada área estudiada, sin un número fijo. Incluye qué/cómo/por qué/dónde en el código, qué cambió, quién/cuándo decidió, excepciones, comprobaciones y comparaciones.
Cada entrada debe tener respuesta directa e independiente, detalles, condiciones, vigencia histórica/actual y fuentes exactas. Conserva toda la lógica necesaria de las preguntas complejas. Si faltan pruebas, especifica qué se desconoce.

### Pendientes y mapa de cobertura
Enumera fuentes inaccesibles, lagunas, contradicciones, hipótesis sin verificar y trabajo pendiente. Añade una tabla fuente/área → secciones que la cubren → estado → laguna restante. Cada área propia del código, MR, conversación y página descubierta debe estar representada o tener una razón explícita de ausencia.

## 4. Fragmentos recuperables y citables

Redacta secciones autónomas con títulos informativos, párrafos, pasos y tablas legibles. Repite proyecto/módulo, entidad, pregunta/regla, condiciones y vigencia cerca de cada hecho para que se entienda por separado. No limites el tamaño total, pero evita esconder información en una línea enorme, una lista de enlaces o «como se explicó arriba».

Pon la referencia junto a cada afirmación: ruta + líneas + commit, URL del MR + conversación, wiki + sección/versión, o chat + fecha/ID del mensaje si existen. No inventes números de línea ni identificadores. Conserva valores, mayúsculas y diferencias entre entornos. Identifica los ejemplos ilustrativos.

Respeta el acceso autorizado. Excluye contraseñas, tokens, claves privadas, secretos activos, contactos personales y conversaciones ajenas al proyecto. Sustituye valores sensibles por placeholders sin perder la explicación. Mantén el archivo local; no lo publiques ni envíes sin autorización adicional.

## 5. Glosario de voz legible por máquina

Termina con un único bloque JSON válido `utka-cue-asr`. Incluye todas las grafías canónicas recopiladas en `terms` y todas las reglas fiables en `aliases`, sin cuota de entradas. Conserva también significados, contexto y fuentes en el diccionario normal.

`hotwords` contiene hasta 20 términos prioritarios de `terms` para el contexto STT activo; no limita la base ni el diccionario completo. Cada lista `heard` admite hasta 16 variantes; usa varias reglas si hacen falta más. `context` puede contener hasta 240 caracteres de palabras/frases próximas separadas por `|`, sin regex complejas. Para pronunciaciones ambiguas exige contexto diferenciador u omite la sustitución automática. No inventes alias seguros para abreviaturas dudosas.

Sustituye este ejemplo ficticio por datos del proyecto:
```utka-cue-asr
{"terms":["syncJobId"],"hotwords":["syncJobId"],"aliases":[{"term":"syncJobId","heard":["sync job id"],"context":"sincronización|trabajo"}]}
```

## 6. Comprueba y entrega

Contrasta el archivo con el registro de fuentes y todo el historial accesible del proyecto. Recupera decisiones, condiciones, conversaciones, áreas de código y cambios omitidos. Selecciona preguntas de control de cada área, encuentra las respuestas dentro del propio archivo y compruébalas con fuentes primarias. Corrige omisiones y registra honestamente lo inaccesible.

Valida Markdown, JSON, referencias, líneas, identificadores, vigencia de estados y ausencia de valores sensibles. Al actualizar, conserva los conocimientos históricos etiquetados y separa el comportamiento actual. No borres hechos anteriores solo porque su fuente sea temporalmente inaccesible: márcalos como no reverificados.

Entrega un enlace al archivo, tamaño real, cantidades de fuentes/áreas procesadas y lagunas importantes. Indica que en Agent Utka hay que pulsar **Importar resumen**, elegir el archivo y seleccionar una base existente o crear una. No prometas acceso a información inaccesible ni una respuesta garantizada a cualquier pregunta imaginable.
