#!/usr/bin/env bash
set -e

cd -- "$(dirname -- "$0")"

if [ ! -x .venv/bin/python ]; then
    echo "Environnement absent : suivre l’installation du README."
    exit 1
fi

exec .venv/bin/python -m streamlit run app.py "$@"
