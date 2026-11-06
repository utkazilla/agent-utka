import os
import subprocess

from .brains import create_brain
from .configuration import RUNTIME, load_settings
from .speech import create_asr


def main():
    settings = load_settings()
    create_asr(RUNTIME, settings["stt_engine"], print,
               url=settings["stt_url"], model=settings["stt_model"], download=True,
               whisper_model=settings["whisper_model"])
    if settings["llm_provider"] != "ollama":
        return
    llm = create_brain(RUNTIME, settings)
    try:
        host = llm.start()
        subprocess.run(
            [str(RUNTIME / "ollama" / "ollama.exe"), "pull", llm.model],
            env=dict(os.environ, OLLAMA_HOST=host), check=True)
    finally:
        llm.close()


if __name__ == "__main__":
    main()
