"""Navigation commune aux pages du dashboard."""

import streamlit as st

TITLES = {
    "home": "Accueil",
    "buildings": "Bâtiments",
    "building": "Détail du bâtiment",
    "regroup": "Regroupements",
    "suggestions": "Par modèle dominant",
    "blocks": "Par blocs proches",
    "manual": "Renouvellement",
    "lots": "Lots de déplacements",
    "lot": "Détail du lot",
    "stock": "Stock central",
    "receipts": "Recevoir du matériel",
    "models": "Catalogue des modèles",
    "history": "Historique",
    "data": "Données et sauvegardes",
    "routes": "Salles et trajets",
}
PAGES = {name: f"ui/pages/{name}.py" for name in TITLES}


def go(name, **selection):
    for key, value in selection.items():
        st.session_state[key] = value
    st.switch_page(PAGES[name])


def heading(title, parent=None):
    if parent:
        st.page_link(PAGES[parent], label="← " + TITLES[parent])
    st.title(title)
