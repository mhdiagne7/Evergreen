"""Ouvrir les trajets piétons dans Google Maps sans connexion API."""

import streamlit as st

from core.google_routes import directions_url


def google_distances(data):
    st.subheader("Trajets à pied · Google Maps")
    st.caption(
        "Choisis deux bâtiments puis ouvre Google Maps pour consulter la distance "
        "et la durée à pied. Aucune clé API nécessaire. Les distances affichées "
        "dans Evergreen restent à vol d’oiseau."
    )
    codes = sorted({room.building for room in data.rooms.values()})
    if len(codes) < 2:
        st.info("Deux bâtiments sont nécessaires pour comparer un trajet.")
        return
    left, right = st.columns(2)
    source = left.selectbox("Départ dans Google Maps", codes, key="google_from")
    target = right.selectbox(
        "Arrivée dans Google Maps", codes, index=1, key="google_to"
    )
    link = directions_url(source, target)
    if link and source != target:
        st.link_button("Ouvrir le trajet à pied dans Google Maps", link)
    else:
        st.info("Choisis deux bâtiments distincts avec des coordonnées connues.")
