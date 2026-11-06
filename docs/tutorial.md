# Agent Utka tutorial

## Install on Windows

1. Extract the source ZIP or clone the repository into a writable folder, such as `C:\Apps\Agent Utka`. Use an x64 Windows PC with a playback device.
2. Install 64-bit Python 3.12 with Tk support and either the Python launcher or `python.exe` on PATH. Install Git if you want to index Git worktrees. If a native dependency reports a missing DLL, install the Microsoft Visual C++ Redistributable for x64. [Python for Windows](https://www.python.org/downloads/windows/) · [Git for Windows](https://git-scm.com/install/windows) · [Microsoft runtime](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)
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

1. Create an empty directory for the demo, such as `C:\Agent Utka Bases\Orbit`.
2. Under **Knowledge base**, click **Folder…** and select that directory. Click **Import…** and choose the fictional [Orbit Sync example](examples/orbit-knowledge.md). Wait for **Ready** and a nonzero file count.
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

Choose the root folder of a code or documentation project with **Folder…**. Agent Utka indexes supported text files, such as code, Markdown, and text. For a Git repository, it considers tracked files and unignored working files. A writable folder is needed when you import. Use a dedicated folder if you want the search to cover only reviewed documents.

Use **Import…** to copy one or more UTF‑8 `.md` or `.txt` files into `.copilot-knowledge/imports` under the selected folder. Each file can be up to 180,000 bytes. Reimport a file with the same name to replace the earlier copy after confirming the replacement. Export or convert PDFs, Word documents, and wiki pages to Markdown or text first.

Agent Utka searches the selected project's index. The default SQLite file is `.runtime/knowledge.sqlite`. **Settings → SQLite index folder** sets a different directory for the index file. Imported files remain in the selected project folder. The running app checks for file changes periodically.

## Prepare and update a pack with Codex or Claude Code

1. Open the project in Codex or Claude Code. In Agent Utka, open **Settings** and click **Copy prompt**. Paste it into the coding agent's project chat. The prompt asks the agent to inspect the sources it can access and save `utka-cue-knowledge.md` in the project root.
2. Review the generated file. Keep current behavior, constraints, and source paths close to each answer. A `utka-cue-asr` fenced JSON block holds exact terms and pronunciation aliases. Existing knowledge documents can use the same format as the [example pack](examples/orbit-knowledge.md).
3. If Agent Utka points at that working folder, it discovers the pack in the root. Keep the file visible to Git when the folder is a repository. If the assistant uses a separate knowledge folder, import the pack there.
4. After a project change, ask the agent to run the prompt again and overwrite the same file. Reimport it if you maintain a separate copy. Citations refer to the files the app indexed, so a citation from an imported summary points to that summary. Keep original source links inside the summary.

Existing packs named `utka-knowledge.md` or `call-copilot-knowledge.md` and glossary blocks marked `utka-asr` or `call-copilot-asr` still work. Agent Utka indexes the text of all eligible packs in the project root. When `utka-cue-knowledge.md` is eligible, its glossary takes priority.

The prompt is available in [English](knowledge-pack-prompt.md), [Russian](knowledge-pack-prompt.ru.md), and [Spanish](knowledge-pack-prompt.es.md).

## Choose speech, answer, and search modules

Open **Settings** to choose your providers. The model pickers save your selection when it succeeds. For settings you edit directly, click **Save**. Restart Agent Utka to apply these changes. The flag menu switches the interface language separately.

| Component | Built-in option | Connect your own |
| --- | --- | --- |
| Speech recognition | Qwen3-ASR 0.6B and multilingual Faster Whisper variants | Local OpenAI-compatible transcription endpoint |
| Answer model | Portable Ollama | Existing local Ollama server or local OpenAI-compatible chat endpoint with JSON Schema |
| Knowledge search | SQLite FTS5, with a configurable index folder | Local search API that returns references to indexed project text |

### Speech recognition

1. Open **Settings → Speech recognition → Choose model…**. If a local speech server is selected, switch the source to **Built-in models** to open the picker. Compare the model file sizes and check which ones are installed. The picker includes Qwen3-ASR 0.6B and multilingual Faster Whisper variants `tiny`, `base`, `small`, `medium`, `large-v3-turbo`, and `large-v3`. [Faster Whisper model list](https://github.com/SYSTRAN/faster-whisper/blob/master/faster_whisper/utils.py)
2. Select a model and click **Download and select** or **Select** if it is installed. Agent Utka downloads the weights and installs the Faster Whisper dependency if needed. It saves the selected speech engine and model when installation finishes. Canceling a download keeps your previous selection. Restart Agent Utka to use the chosen model. The picker shows download size and, when available, free VRAM on your NVIDIA GPU.
3. The picker installs the CPU INT8 bundle for Qwen3-ASR. Qwen and Faster Whisper use CUDA if their GPU requirements are already met, and can run on CPU. To set up the optional NVIDIA packages, close the app and run `Setup Agent Utka.ps1` with the speech engine selected.

For a separate service, choose **Local OpenAI-compatible STT**, enter its numeric loopback base URL, for example `http://127.0.0.1:8000/v1`, and set the model ID the server expects. The server manages its own models. Agent Utka sends each segment as 16 kHz mono WAV to `POST /v1/audio/transcriptions`. The service must accept multipart `file`, `model`, `response_format=json`, and an optional `prompt`, and return JSON with a string `text` field. One possible server is Speaches with an installed model such as `Systran/faster-whisper-small`. [Speaches transcription API](https://speaches.ai/usage/speech-to-text/) · [Speaches model discovery](https://speaches.ai/usage/model-discovery/)

### Ollama and other answer servers

1. Choose **Ollama · built-in** to use the portable server from setup. If Ollama already runs on this PC, select **Ollama · existing server** and enter its local base address, normally `http://127.0.0.1:11434`. Disable Ollama's cloud features and restart the server before connecting it. Agent Utka checks this setting on the installed server. [Disable Ollama cloud features](https://docs.ollama.com/faq#how-do-i-disable-ollamas-cloud-features)
2. Under **Answers**, click **Choose model…**. Open **Catalog** and find a model family by name. Select a variant and check its file size before starting the download. A suffix such as `4b` means four billion parameters. The size shown in GB is the published model file size. [Ollama model library](https://ollama.com/library)
3. Click **Download and select**. Agent Utka shows progress while the selected Ollama server downloads and installs the model, then saves the model and answer server together. For a model already on that server, open **Installed** and click **Select**. Restart Agent Utka to use the selected model for answers. If you also edited the external speech server or search settings, click **Save** in **Settings** before restarting.
4. Click **Refresh VRAM** to check free and total video memory on supported NVIDIA GPUs and the VRAM reported for models loaded by Ollama. Actual GPU use depends on quantization, context length, the speech engine, and other running software. [Ollama running model API](https://docs.ollama.com/api/ps) · [NVIDIA memory reporting](https://docs.nvidia.com/deploy/nvidia-smi/index.html#fb-memory-usage)

With another local LLM server, select **OpenAI-compatible · local**, enter its loopback base URL such as `http://127.0.0.1:1234/v1`, and choose the model ID. The service must implement `GET /v1/models` and `POST /v1/chat/completions` and support `response_format` with `json_schema`. Agent Utka validates a selected excerpt and displays the source text, so schema support and the model's ability to judge evidence both matter.

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

Choose **Local search API**, keep the URL above, save, and restart Agent Utka. Ask the Orbit retry question again. The demo returns the indexed citation for this specific example. Replace the fixed response with ranked path and line references from your search engine when building your own adapter.

## Local data and common fixes

The app listens to the default Windows playback endpoint, including any application playing through it. It keeps the full transcript in memory for the current window and stores recent requested answers, excerpts, and citations in `.runtime/history.sqlite`. The SQLite knowledge index contains text from source documents. Audio is processed in memory. Set up only local adapters you trust because they receive speech, questions, or source excerpts appropriate to their role. Browsing the Ollama catalog contacts Ollama's public library. Downloads go through the selected Ollama server.

The app discovers local project folders from Codex when available and refreshes their indexes along with folders you add. Questions and custom search requests use the project selected in the app.

| What you see | What to check |
| --- | --- |
| A YouTube video plays with no transcript | Resume listening. In Windows **Settings → System → Sound → Volume mixer**, verify that the browser uses the default playback device. Unmute the tab and device. Play several seconds of clear speech and allow a short pause. |
| Your own voice does not appear | The app captures playback. If you speak into a microphone and your own audio is not played back by Windows, it is outside the capture. |
| The Windows device changed | Let the app reconnect. Check the default output again after reconnecting Bluetooth headphones or moving a call to another device. |
| An imported file does not appear | Confirm the selected folder, check **Ready**, and verify UTF‑8, supported extension, and file size. |
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
