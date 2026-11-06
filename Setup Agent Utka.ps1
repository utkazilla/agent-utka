param([switch]$SkipCuda)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonCheck = "import platform, sys; sys.exit(0 if sys.version_info[:2] == (3, 12) and platform.machine().upper() in ('AMD64', 'X86_64') else 1)"
$venvPython = '.venv/Scripts/python.exe'

function Test-Python312([string]$Program, [string[]]$LauncherArgs = @()) {
    try {
        & $Program @LauncherArgs -c $pythonCheck 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

if (!(Test-Path -LiteralPath $venvPython)) {
    $python = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
    $launcherArgs = @()
    if (!(Test-Path -LiteralPath $python) -or !(Test-Python312 $python)) {
        $pyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
        $pathPython = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($pyLauncher -and (Test-Python312 $pyLauncher.Source @('-3.12'))) {
            $python = $pyLauncher.Source
            $launcherArgs = @('-3.12')
        } elseif ($pathPython -and (Test-Python312 $pathPython.Source)) {
            $python = $pathPython.Source
        } else {
            throw 'Install 64-bit Python 3.12 from python.org, then run setup again.'
        }
    }
    & $python @launcherArgs -m venv .venv
    if ($LASTEXITCODE) { throw 'Python environment could not be created.' }
} elseif (!(Test-Python312 $venvPython)) {
    throw 'This .venv uses another Python version. Rename the .venv directory and rerun setup with 64-bit Python 3.12 installed.'
}

& $venvPython -m pip install -r requirements.txt
if ($LASTEXITCODE) { throw 'Python dependencies could not be installed.' }

$selected = & $venvPython -X utf8 -c "from copilot.configuration import load_settings; s = load_settings(); print(s['stt_engine']); print(s['llm_provider'])"
if ($LASTEXITCODE -or $selected.Count -ne 2) { throw 'Could not read Agent Utka settings.' }
$sttEngine, $llmProvider = $selected
$useCuda = !$SkipCuda -and (Get-Command nvidia-smi -ErrorAction SilentlyContinue)
New-Item -ItemType Directory -Force -Path '.runtime' | Out-Null

if ($llmProvider -eq 'ollama' -and !(Test-Path -LiteralPath '.runtime/ollama/ollama.exe')) {
    New-Item -ItemType Directory -Force -Path '.runtime/ollama' | Out-Null
    curl.exe -fL --retry 3 -o '.runtime/ollama.zip' 'https://github.com/ollama/ollama/releases/latest/download/ollama-windows-amd64.zip'
    if ($LASTEXITCODE) { throw 'Could not download portable Ollama.' }
    tar.exe -xf '.runtime/ollama.zip' -C '.runtime/ollama'
    if ($LASTEXITCODE) { throw 'Could not extract portable Ollama.' }
    Remove-Item -LiteralPath '.runtime/ollama.zip'
}

if ($sttEngine -eq 'qwen') {
    $asrModel = 'sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25'
    $asrFiles = @{
        'conv_frontend.onnx' = 44148281
        'encoder.int8.onnx' = 182491662
        'decoder.int8.onnx' = 755914231
    }
    $incomplete = $asrFiles.Keys | Where-Object {
        $item = Get-Item -LiteralPath ".runtime/$asrModel/$_" -ErrorAction SilentlyContinue
        !$item -or $item.Length -ne $asrFiles[$_]
    }
    if ($incomplete -or !(Test-Path -LiteralPath ".runtime/$asrModel/tokenizer/merges.txt") -or
            !(Test-Path -LiteralPath ".runtime/$asrModel/tokenizer/vocab.json")) {
        $archive = ".runtime/$asrModel.tar.bz2"
        curl.exe -fL --retry 3 --output $archive "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/$asrModel.tar.bz2"
        if ($LASTEXITCODE) { throw 'Could not download Qwen ASR.' }
        if ((Get-FileHash -LiteralPath $archive).Hash -ne '393f8a14e2f5fb96746aaab342997a40641001fbd5bf9592a080a8329178ee96') {
            throw 'Qwen ASR archive checksum did not match.'
        }
        tar.exe -xf $archive -C '.runtime' "$asrModel/conv_frontend.onnx" "$asrModel/encoder.int8.onnx" "$asrModel/decoder.int8.onnx" "$asrModel/tokenizer"
        if ($LASTEXITCODE) { throw 'Could not extract Qwen ASR.' }
        Remove-Item -LiteralPath $archive
    }
} elseif ($sttEngine -eq 'whisper') {
    & $venvPython -m pip install 'faster-whisper==1.2.1'
    if ($LASTEXITCODE) { throw 'Faster Whisper could not be installed.' }
    if ($useCuda) {
        try {
            & $venvPython -m pip install 'nvidia-cublas-cu12==12.9.2.10' 'nvidia-cudnn-cu12==9.28.0.42'
            if ($LASTEXITCODE) { throw 'Faster Whisper CUDA libraries could not be installed.' }
        } catch {
            Write-Warning 'Faster Whisper CUDA setup failed. The CPU version is available.'
        }
    }
}

if ($sttEngine -eq 'qwen' -and $useCuda) {
    try {
        & $venvPython -X utf8 -m pip install 'torch==2.11.0+cu128' --extra-index-url 'https://download.pytorch.org/whl/cu128'
        if ($LASTEXITCODE) { throw 'Could not install PyTorch CUDA.' }
        & $venvPython -X utf8 -m pip install 'transformers==5.13.0'
        if ($LASTEXITCODE) { throw 'Could not install Transformers.' }
        $cudaModel = New-Item -ItemType Directory -Force -Path '.runtime/qwen3-asr-0.6b-hf'
        $revision = '7f1569a48a89f3e3f4dc3a5c9d28bddd903bc76c'
        $cudaFiles = @{
            'chat_template.jinja' = 1434
            'config.json' = 2398
            'generation_config.json' = 165
            'processor_config.json' = 487
            'tokenizer.json' = 11429653
            'tokenizer_config.json' = 998
            'model.safetensors' = 1564928088
        }
        foreach ($file in $cudaFiles.Keys) {
            $path = Join-Path $cudaModel.FullName $file
            $item = Get-Item -LiteralPath $path -ErrorAction SilentlyContinue
            if ($item -and $item.Length -eq $cudaFiles[$file]) { continue }
            $partial = "$path.part"
            curl.exe -fL --retry 3 --output $partial "https://huggingface.co/Qwen/Qwen3-ASR-0.6B-hf/resolve/$revision/$file"
            if ($LASTEXITCODE -or (Get-Item -LiteralPath $partial).Length -ne $cudaFiles[$file]) {
                throw "Could not download $file."
            }
            if ($file -eq 'model.safetensors' -and
                    (Get-FileHash -LiteralPath $partial).Hash -ne 'd3f212dd20abecd315d830bc54ae3865e56ebfc3276484e57b771288ba27fd35') {
                throw 'Qwen ASR weights checksum did not match.'
            }
            Move-Item -LiteralPath $partial -Destination $path -Force
        }
    } catch {
        Write-Warning "Qwen ASR CUDA setup failed. The CPU version is available. $_"
    }
}
& $venvPython -X utf8 -m copilot.prepare
if ($LASTEXITCODE) { throw 'Models could not be prepared.' }
Write-Host 'Ready. Double-click Start Agent Utka.cmd.'
