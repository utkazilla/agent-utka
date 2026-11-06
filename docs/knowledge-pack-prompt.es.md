# Prepara un documento para Agent Utka

Examina el proyecto actual y guarda `utka-cue-knowledge.md` en su carpeta raíz. Usa Markdown en UTF‑8 y un máximo de 180 000 bytes. Actualiza el mismo archivo cuando cambie el proyecto.

1. Examina el README, la documentación, los contratos, el código y las pruebas disponibles. Resume el comportamiento vigente de los módulos, flujos, condiciones, límites, estados y errores. Distingue el comportamiento comprobado de los planes y las decisiones históricas.
2. Escribe preguntas que podrían surgir en una llamada y respuestas breves que se entiendan por separado. Coloca las condiciones de cada respuesta y su fuente en el mismo párrafo. Cita archivos con rutas relativas y líneas, como `src/...:42`. Para un documento externo, registra el título, la sección y el enlace si está disponible. Si hay discrepancias o falta evidencia, indícalo.
3. Recopila los nombres exactos de servicios, campos, métodos, códigos y abreviaturas que se suelen pronunciar. Mantén las mayúsculas, los guiones y los guiones bajos. Explica cada término en el idioma de trabajo del proyecto e incluye la fuente.
4. Añade al final un único bloque `utka-cue-asr` con JSON válido. Usa un máximo de 200 `terms`, con hasta 120 caracteres por término. Elige hasta 10 términos prioritarios en `hotwords`. Añade hasta 200 reglas en `aliases` y de una a 16 variantes claras en cada `heard`. Cuando una variante sea ambigua, usa un `context` con palabras cercanas, separadas por `|` si hay varias. Omite las variantes que no puedas desambiguar con fiabilidad.

Ejemplo ficticio:

```utka-cue-asr
{
  "terms": ["syncJobId"],
  "hotwords": ["syncJobId"],
  "aliases": [
    {"term": "syncJobId", "heard": ["sinc yob ai di", "sync job ID"]},
    {"term": "syncJobId", "heard": ["id de tarea"], "context": "sincronización|sincronizar"}
  ]
}
```

Utiliza únicamente materiales que se puedan compartir con los destinatarios. Excluye datos personales, credenciales, variables de entorno, registros sin procesar y transcripciones. Antes de guardar, comprueba las referencias, revisa los hechos y confirma que las entradas de `hotwords` y `aliases` están en `terms`. Indica la ruta del archivo terminado.
