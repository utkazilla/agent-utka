# Agent Utka

<img src="assets/utka.png" alt="Agent Utka, a yellow rubber duck wearing black sunglasses" width="96">

Agent Utka is a local AI assistant for technical calls on Windows. It transcribes what you hear on a call and answers questions about it using your project's code and documentation. Each supported answer includes a source excerpt, file name, and line number.

## How it works

1. **Listen.** Agent Utka captures audio from the default Windows playback device and adds recognized speech to the transcript. Route Teams, Zoom, Meet, Discord, or your browser through that device. The app can hear other audio playing on the same output. Your microphone is outside the capture unless Windows plays it back through that output.
2. **Ask.** Select a passage in the transcript and press **Ask** or **Ctrl+Enter**. Without a selection, the app uses the latest utterance. New speech keeps appearing while you read the answer.
3. **Check the source.** The app searches the selected project and uses a local model to find a supporting excerpt. Open **Sources** to see the file and line number. If there is insufficient evidence, it shows **No answer in the knowledge base**. **History** lets you revisit previous answers.

## See it in action

In this demo, Qwen transcribed two spoken questions. Selecting the first one and pressing **Ask** searched the [Harry Potter demo file](docs/examples/harry-potter-demo.md) and returned an answer with a citation.

![Agent Utka with the first of two transcribed questions selected](docs/screenshots/harry-potter-selection.jpg)

![Agent Utka answering the selected question with a citation from the demo knowledge base](docs/screenshots/harry-potter-answer.jpg)

[View the cited passage in Agent Utka](docs/screenshots/harry-potter-source.jpg).

### See what the RAG search retrieved

Select a project or import documents, then open **Settings → Knowledge base → Browse knowledge…**. Enter a question and click **Test retrieval**. Select a result to read the indexed passage and its source line.

![Agent Utka's knowledge browser showing three ranked passages for a question about Hedwig](docs/screenshots/harry-potter-rag.jpg)

## Quick start

1. On a Windows 10 or 11 x64 PC, download `Agent-Utka-Setup-…-x64.exe` from [Releases](https://github.com/utkazilla/agent-utka/releases/latest) and double-click it. Python is included.
2. Open **Agent Utka** from Start. Choose **Download and start** to fetch the default Qwen speech and Ollama answer models. Allow about 6 GB of downloads and 12 GB of free disk space during setup. Models are stored on your PC. If you already run compatible local services, choose **Open app** and configure them under **Settings**.
3. After launch, choose English, Russian, or Spanish from the flag menu. Git is optional and helps the app identify files to index in Git worktrees.

[Windows tutorial](docs/tutorial.md#install-on-windows) · [Run from source](docs/tutorial.md#run-from-source)

### Try your first answer

1. Under **Knowledge base**, use **Folder…** to select an empty folder, then **Import…** to add the [fictional Orbit knowledge pack](docs/examples/orbit-knowledge.md). Wait for **Ready**.
2. Play or synthesize the question “How long does the Orbit sync worker wait before retrying a temporary failure?” through the default Windows output. [Text-to-speech example](docs/tutorial.md#create-a-knowledge-base-and-try-an-answer)
3. Select the question in the transcript and press **Ask**. The expected answer is **5 seconds**. Open **Sources** to see the supporting line.

## Use your own project

Select a project folder with **Folder…** or import UTF-8 Markdown and text files into a dedicated knowledge base. For Git worktrees, the index considers tracked files and unignored working files. To prepare a knowledge pack, open **Settings → Copy prompt** and paste it into Codex or Claude Code in your project. Review the resulting `utka-cue-knowledge.md` before using it. The pack can include a glossary for project terminology and pronunciation. [Connect a project](docs/tutorial.md#connect-your-own-project) · [Knowledge pack prompt](docs/knowledge-pack-prompt.md)

## Supported engines and services

| Component | Built in | Optional local service |
| --- | --- | --- |
| Speech recognition | Qwen3-ASR 0.6B and 1.7B INT8, plus 17 Faster Whisper variants | OpenAI-compatible `POST /v1/audio/transcriptions` |
| Answers | Portable Ollama | An existing Ollama instance with cloud features disabled, or an OpenAI-compatible chat server with JSON Schema support |
| Project search | SQLite FTS5 | A local search API that returns project-relative file paths and line numbers |

Choose these components independently in **Settings**. Both model pickers have **Catalog** and **Installed** tabs. Search by model name, compare download sizes, and download models in the app. The speech catalog labels English-only variants. Restart Agent Utka after changing engines or models. [Provider configuration and API contracts](docs/tutorial.md#choose-speech-answer-and-search-modules)

## Local data and troubleshooting

The built-in engines process speech and answers locally. Audio is processed in memory. The transcript stays in memory while the window is open, and recent answers and citations are stored in `.runtime/history.sqlite`. The search index contains excerpts from your project. Setup and model downloads need network access, and browsing the Ollama catalog contacts its public library.

If the transcript is empty, check that listening is enabled and the call app uses the default Windows playback device. If **Ask** returns no answer, check that the knowledge base is **Ready** and contains the source document. [Common fixes](docs/tutorial.md#local-data-and-common-fixes)

[Full Windows tutorial](docs/tutorial.md) · [Russian guide](docs/tutorial.ru.md) · [Verification commands](docs/tutorial.md#verify-the-installation)
