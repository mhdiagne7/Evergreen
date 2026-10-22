#!/bin/sh
if ! command -v ollama >/dev/null 2>&1; then
  echo "Installer Ollama et qwen3:4b selon le README."
  exit 1
fi
export OLLAMA_NO_CLOUD=1
export OLLAMA_HOST=127.0.0.1:11434
exec ollama serve
