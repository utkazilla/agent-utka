# Agent Utka tutorial

## Install on Windows

1. Download the x64 `.exe` installer from [GitHub Releases](https://github.com/utkazilla/agent-utka/releases/latest) and double-click it on Windows 10 or 11. Python and the app's dependencies are included. The release provides a SHA-256 checksum for the installer.
2. Launch **Agent Utka** from the Start menu. Click **Download and start** to prepare Qwen3-ASR, portable Ollama, and the `qwen3.5:4b` answer model. The initial download is about 6 GB; allow about 12 GB free for downloads and extraction. If you already run compatible local services, click **Open app** and configure them in Settings.
3. Wait for the audio status to show that the app is listening. Select English, Russian, or Spanish from the flag menu. The app saves your choice for the next run.

The default install folder is `%LOCALAPPDATA%\Programs\Agent Utka`. Models and indexes stay in `.runtime` inside that folder. The default installer setup uses the CPU bundle for Qwen. To install another speech or Ollama model, use the pickers in **Settings**.

## Run from source

1. Extract the source ZIP or clone the repository into a writable folder, such as `C:\Apps\Agent Utka`. Use an x64 Windows PC with a playback device.
2. Install 64-bit Python 3.12 with Tk support and either the Python launcher or `python.exe` on PATH. If a native dependency reports a missing DLL, install the Microsoft Visual C++ Redistributable for x64. [Python for Windows](https://www.python.org/downloads/windows/) · [Microsoft runtime](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)
3. Open PowerShell in the application folder and run setup. The first run needs internet access and several gigabytes of disk space. The defaults download Qwen3-ASR and the `qwen3.5:4b` model for portable Ollama. Add `-SkipCuda` to skip optional NVIDIA speech packages and weights. Ollama manages its own CPU/GPU placement.

   ~~~powershell
   & '.\Setup Agent Utka.ps1'
   ~~~

   If PowerShell blocks the downloaded script, review it and use the following for this setup invocation.

   ~~~powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\Setup Agent Utka.ps1'
   ~~~

4. Double-click `Start Agent Utka.cmd`. Wait for the audio status to show that the app is listening. Choose English, Russian, or Spanish from the flag menu. The setting takes effect immediately and is saved for the next run.

To configure your own services before the first setup, copy `settings.example.json` to `settings.local.json` and edit the entries described below. Setup prepares the selected built-in engines. Start your own local servers separately.

## Create a knowledge base and try an answer

**New base** is always available beside the knowledge selector on the main screen. Enter a name and click **Create base**. No document or folder is required. Your empty base is selected immediately and remains available after restarting. Then use **Copy prompt** or **Import**. **Open base** shows its documents and retrieval results; an empty base offers an import action.

1. Save the fictional [Orbit Sync example](examples/orbit-knowledge.md) on your PC.
2. Click **Import**, select that file, choose **New base…**, and click **Import**. Wait for **Ready**. Agent Utka creates and selects the base.
3. Play the question **“How long does the Orbit sync worker wait before retrying a temporary failure?”** through the default Windows output. You can play a recording or generate the question locally using Windows PowerShell. Run the following while Agent Utka is listening.

   ~~~powershell
   Add-Type -AssemblyName System.Speech
   $voice = [System.Speech.Synthesis.SpeechSynthesizer]::new()
   try {
       $english = $voice.GetInstalledVoices() | Where-Object {
           $_.Enabled -and $_.VoiceInfo.Culture.TwoLetterISOLanguageName -eq 'en'
       } | Select-Object -First 1
       if (!$english) { throw 'Install an English Windows speech voice or play a recording of the question.' }
       $voice.SelectVoice($english.VoiceInfo.Name)
       $voice.SetOutputToDefaultAudioDevice()
       $voice.Speak('How long does the Orbit sync worker wait before retrying a temporary failure?')
   } finally {
       $voice.Dispose()
   }
   ~~~

4. Highlight the recognized question and press **Ask** or **Ctrl+Enter**. With no selection, Ask uses the latest utterance. The expected answer is **5 seconds**. **Sources** opens the excerpt with its file and line number. If the app finds insufficient evidence, it shows **No answer in the knowledge base**.
5. Keep listening. New paragraphs append to the transcript while you read the current answer. Use **History** or the arrow buttons to revisit answers. **Pause** stops new capture. You can still ask about existing transcript text.

## Connect your own project

Click **Copy prompt** on the main screen and paste it into Codex or Claude Code in your project. Review the summary it creates, then click **Import** and select the file.

In **Add to knowledge base**, choose an existing base or **New base…**. For a new base, the document's first heading supplies a suggested name that you can edit. Click **Import** and wait for **Ready**. Several summaries can belong to one base. Files must be UTF‑8 `.md` or `.txt`. Explicit imports have no application-imposed file-size cap. Export or convert PDFs, Word documents, and wiki pages to Markdown or text first.

The selector on the main screen controls where answers are searched: one named base or **All bases**. **Open base** uses that same selection. Combined results and citations include the originating base.

In the import dialog, **Document name** controls the document's display name in sources and the knowledge browser. **Add to knowledge base** chooses its destination separately. Click **New base…** and enter a **New base name** to create one. **All bases** is a search scope, not an import destination. To rename an existing summary, reimport the same original file into the same base and edit its document name; the existing document is updated without a duplicate. The original file and its contents stay unchanged.

To ask without speech, type or paste into **Your question** on the main screen. Click **Ask** beside that field or press **Ctrl+Enter** inside it; Enter inserts a new line. Typed questions use the selected base or **All bases**, and their answers appear in the same history with sources. Your draft stays available for editing and incoming speech does not change it.

Import an updated version from the same original file location into the same base to replace that document. Different source files remain separate even when their filenames match. Imported copies are stored under `.runtime/knowledge`, and the search index is `.runtime/agent-utka-imports.sqlite`. Storage is managed automatically. Advanced users can change the index location in Settings.

## Prepare and update a pack with Codex or Claude Code

1. Open the project in Codex or Claude Code. In Agent Utka, click **Copy prompt** on the main screen. Paste it into the coding agent's project chat. The prompt asks the agent to reconstruct all accessible project conversation history, code structure, MR/PR changes and reviews, and linked documentation, then save the detailed knowledge file as `utka-cue-knowledge.md` in the project root. It requires a source register, coverage map, historical/current labels and explicit gaps for unavailable evidence. There is no output-length or full-glossary entry quota.
2. Review the generated file. Keep current behavior, constraints, and source paths close to each answer. A `utka-cue-asr` fenced JSON block holds exact terms and pronunciation aliases. Existing knowledge documents can use the same format as the [example pack](examples/orbit-knowledge.md).
3. In Agent Utka, click **Import**, select the reviewed pack, and choose its destination base. Click **Import** and wait for **Ready**.
4. After a project change, ask the agent to refresh the pack, review it, then import it from the same file location into the same base. Citations point to lines in the imported pack. Keep original source links inside the pack.

Existing packs named `utka-knowledge.md` or `call-copilot-knowledge.md` and glossary blocks marked `utka-asr` or `call-copilot-asr` also work when imported.

The prompt is available in [English](knowledge-pack-prompt.md), [Russian](knowledge-pack-prompt.ru.md), and [Spanish](knowledge-pack-prompt.es.md).

## Choose speech, answer, and search modules

Open **Settings** to choose your providers. The model pickers save and apply your selection, then close. For settings you edit directly, click **Save** to apply them and close Settings. The flag menu switches the interface language separately.

| Component | Built-in option | Connect your own |
| --- | --- | --- |
| Speech recognition | Qwen3-ASR 0.6B and 1.7B INT8, plus Faster Whisper | Local OpenAI-compatible transcription endpoint |
| Answer model | Portable Ollama | Existing local Ollama server or local OpenAI-compatible chat endpoint with JSON Schema |
| Knowledge search | SQLite FTS5, with a configurable index folder | Local search API that returns references to indexed project text |

### Speech recognition

1. Open **Settings → Speech recognition → Choose model…**. If a local speech server is selected, switch the source to **Built-in models**. Search the **Catalog** by model name or language label, or open **Installed** to see models ready to select. The catalog includes both Qwen3-ASR sizes and all 17 distinct Faster Whisper 1.2.1 variants, including Turbo and Distil. Choose a multilingual model for Russian, Spanish, or conversations in several languages. [Qwen3-ASR model list](https://github.com/QwenLM/Qwen3-ASR) · [Faster Whisper model list](https://github.com/SYSTRAN/faster-whisper/blob/v1.2.1/faster_whisper/utils.py)
2. Select a model and click **Download and select** or **Select** if it is installed. Agent Utka downloads the weights and installs any required dependencies. It switches the speech engine and model in the current session. Canceling a download keeps your previous selection. The picker shows download size and, when available, free VRAM on your NVIDIA GPU.
3. For Faster Whisper, choose **NVIDIA GPU (CUDA)** to download cuBLAS and cuDNN on demand and verify GPU inference before saving. The first download adds about 1.3 GB of libraries and requires an NVIDIA driver. **CPU** explicitly uses the processor. **Auto** uses available libraries and can fall back to CPU. For Qwen, select the **BF16 · NVIDIA GPU** row for either 0.6B or 1.7B. The picker downloads the official BF16 weights and installs PyTorch CUDA and Transformers if needed. GPU weights are about 1.6 GB or 4.1 GB, plus the runtime on first setup. The **INT8 · CPU** rows use the sherpa-onnx builds. [Qwen BF16 model](https://huggingface.co/Qwen/Qwen3-ASR-1.7B-hf) · [Qwen ONNX builds](https://k2-fsa.github.io/sherpa/onnx/qwen3-asr/pretrained.html)
4. **Unload model** under Speech recognition pauses listening and releases the loaded built-in model. **Listen** resumes capture and the next speech segment reloads the model. The status shows which model is in memory and on which device.

For a separate service, choose **Local OpenAI-compatible STT**, enter its numeric loopback base URL, for example `http://127.0.0.1:8000/v1`, and set the model ID the server expects. The server manages its own models. Agent Utka sends each segment as 16 kHz mono WAV to `POST /v1/audio/transcriptions`. The service must accept multipart `file`, `model`, `response_format=json`, and an optional `prompt`, and return JSON with a string `text` field. One possible server is Speaches with an installed model such as `Systran/faster-whisper-small`. [Speaches transcription API](https://speaches.ai/usage/speech-to-text/) · [Speaches model discovery](https://speaches.ai/usage/model-discovery/)

### Ollama and other answer servers

1. Choose **Ollama · built-in** to use the portable server from setup. If Ollama already runs on this PC, select **Ollama · existing server** and enter its local base address, normally `http://127.0.0.1:11434`. Disable Ollama's cloud features and restart the server before connecting it. Agent Utka checks this setting on the installed server. [Disable Ollama cloud features](https://docs.ollama.com/faq#how-do-i-disable-ollamas-cloud-features)
2. Under **Answers**, click **Choose model…**. Open **Catalog** and find a model family by name. Select a variant and check its file size before starting the download. A suffix such as `4b` means four billion parameters. The size shown in GB is the published model file size. [Ollama model library](https://ollama.com/library)
3. Click **Download and select**. Agent Utka shows progress while the selected Ollama server downloads and installs the model, then applies the model and answer server together. For a model already on that server, open **Installed** and click **Select**. If you also edited the speech server or search settings, click **Save** in **Settings** to apply those changes.
4. Click **Refresh VRAM** to check free and total video memory on supported NVIDIA GPUs and the VRAM reported for models loaded by Ollama. Actual GPU use depends on quantization, context length, the speech engine, and other running software. [Ollama running model API](https://docs.ollama.com/api/ps) · [NVIDIA memory reporting](https://docs.nvidia.com/deploy/nvidia-smi/index.html#fb-memory-usage)
5. Use **Unload model** in Answers or select a loaded model in the Ollama picker and unload it there. The session model is shown separately from the saved choice. Ollama can reload it for the next request. Other local servers manage memory through their own controls.

With another local LLM server, select **OpenAI-compatible · local**, enter its loopback base URL such as `http://127.0.0.1:1234/v1`, and choose the model ID. The service must implement `GET /v1/models` and `POST /v1/chat/completions` and support `response_format` with `json_schema`. Agent Utka validates a selected excerpt and displays the source text, so schema support and the model's ability to judge evidence both matter.

### Inspect the knowledge index

Select a project or import documents, then open **Open base** on the main screen. Select a document to see the indexed excerpts and their source lines. Enter a question and select **Test retrieval** to see the passages that the answer model would receive, in search order. The built-in index uses SQLite FTS5.

### Use a local search API

Select **Local search API** as the knowledge provider and enter the full loopback URL, for example `http://127.0.0.1:8090/search`. Agent Utka sends a JSON POST.

~~~json
{"project":"C:\\Agent Utka Bases\\Orbit","query":"How long is the retry delay?","limit":8}
~~~

The response lists references in rank order.

~~~json
{"hits":[{"path":".copilot-knowledge/imports/orbit-knowledge.md","line":7}]}
~~~

The `project` is the selected absolute directory. Every `path` is relative to it and uses forward slashes. Line numbers start at 1. Return `{"hits":[]}` if there are no candidates. Your server can rank by keyword, vectors, or another method. The app checks references against its own SQLite index and reads the cited text from that index. Keep the project connected and indexed even with a custom search provider.

The **Ready** status describes the local source index. If a request says the local search API is unavailable, check its address and confirm that the service returns the response shape above.

To try the adapter before connecting your own search service, first import the Orbit pack, then run the [demo server](examples/local-search-demo.py) in a separate PowerShell window from the application folder.

~~~powershell
& '.\.venv\Scripts\python.exe' '.\docs\examples\local-search-demo.py'
~~~

Choose **Local search API**, keep the URL above, and save. Ask the Orbit retry question again. The demo returns the indexed citation for this specific example. Replace the fixed response with ranked path and line references from your search engine when building your own adapter.

## Local data and common fixes

The app listens to the default Windows playback endpoint, including any application playing through it. It keeps the full transcript in memory for the current window and stores recent requested answers, excerpts, and citations in `.runtime/history.sqlite`. The SQLite knowledge index contains text from source documents. Audio is processed in memory. Set up only local adapters you trust because they receive speech, questions, or source excerpts appropriate to their role. Browsing the Ollama catalog contacts Ollama's public library. Downloads go through the selected Ollama server.

The app lists the summaries you import. Questions and custom search requests use the currently selected base.

| What you see | What to check |
| --- | --- |
| A YouTube video plays with no transcript | Resume listening. In Windows **Settings → System → Sound → Volume mixer**, verify that the browser uses the default playback device. Unmute the tab and device. Play several seconds of clear speech and allow a short pause. |
| Your own voice does not appear | The app captures playback. If you speak into a microphone and your own audio is not played back by Windows, it is outside the capture. |
| The Windows device changed | Let the app reconnect. Check the default output again after reconnecting Bluetooth headphones or moving a call to another device. |
| An imported file does not appear | Check the selected base and **Ready** status, and verify UTF‑8, supported extension, and file size. |
| The answer is missing or cites a summary | Import the original supporting text, or include a direct answer and a source link in the knowledge pack. Ask using the wording or exact term found in the source. |
| A local model does not appear or respond | Check that the intended server is running at the configured address and the model is installed on that server. For an OpenAI-compatible answer server, verify JSON Schema support. |
| The Ollama catalog does not load | Check your internet connection and retry. **Installed** still lets you choose models already on the selected Ollama server. |
| Setup or startup fails | Run the commands below in a terminal so you can read the error. Check `.runtime/assistant.log` for startup details. |

## Verify the installation

Run these from the application directory after setup.

~~~powershell
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test_*.py'
& '.\.venv\Scripts\python.exe' -m copilot.app --ui-test
& '.\.venv\Scripts\python.exe' -m copilot.app --launch-check
~~~

The unit and UI checks use fixtures. The launch check starts the configured engines, Windows audio capture, and indexing. The Orbit walkthrough above checks the actual path from speech playback to a source citation.
