import os
import subprocess

from .brains import create_brain
from .configuration import RUNTIME, load_settings
from .qwen_install import install_qwen
from .speech import QWEN_LARGE_MODEL, create_asr


def main():
    settings = load_settings()
    if settings["stt_engine"] == "qwen" and settings["qwen_model"] == QWEN_LARGE_MODEL:
        install_qwen(RUNTIME, variant=QWEN_LARGE_MODEL)
    create_asr(RUNTIME, settings["stt_engine"], print,
               url=settings["stt_url"], model=settings["stt_model"], download=True,
               whisper_model=settings["whisper_model"], qwen_model=settings["qwen_model"])
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
