@echo off
where ollama >nul 2>nul
if errorlevel 1 (
  echo Installer Ollama et qwen3:4b selon le README.
  pause
  exit /b 1
)
set OLLAMA_NO_CLOUD=1
set OLLAMA_HOST=127.0.0.1:11434
ollama serve
pause
