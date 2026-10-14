#!/bin/bash
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "Environnement Python absent. Suivre la rubrique Installation du README."
  read -r -p "Appuyer sur Entrée pour fermer."
  exit 1
fi
exec .venv/bin/python -m streamlit run app.py --server.address 127.0.0.1 --browser.gatherUsageStats false
