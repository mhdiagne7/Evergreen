"""Connexion Google Maps et consultation de la matrice piétonne en session."""

import os

import streamlit as st

from core.campus import building_position
from core.google_routes import compute_walking_matrix, directions_url, matrix_signature


def active_matrix(data):
    codes = sorted({room.building for room in data.rooms.values()})
    packet = st.session_state.get("google_walking_matrix")
    if packet and packet["signature"] == matrix_signature(codes):
        return packet
    return None


def google_distances(data):
    st.subheader("Trajets piétons entre bâtiments · Google Maps")
    codes = sorted({room.building for room in data.rooms.values()})
    st.caption(
        "Les trajets partent des points publics des bâtiments. Ils ne comprennent pas "
        "les déplacements entre les salles, étages et quais de livraison. "
        "Les distances calculées par Google Maps peuvent évoluer."
    )
    key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not key:
        try:
            key = st.secrets.get("GOOGLE_MAPS_API_KEY", "")
        except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
            key = ""
    with st.expander("Connecter Google Maps", expanded=not bool(key)):
        if not key:
            key = st.text_input(
                "Clé Google Maps Routes API", type="password", key="google_routes_key"
            )
        st.caption(
            "La clé reste sur cet ordinateur et n’est pas publiée. Routes API doit être activée "
            "dans ton projet Google Cloud, avec facturation configurée. "
            "Seules les coordonnées publiques des bâtiments sont envoyées à Google."
        )
        st.link_button(
            "Configurer Routes API",
            "https://developers.google.com/maps/documentation/routes/cloud-setup",
        )
        st.link_button(
            "Tarifs et quotas Google Maps",
            "https://developers.google.com/maps/documentation/routes/usage-and-billing",
        )
    n = len(codes)
    approved = st.checkbox(
        f"Je souhaite calculer la matrice : {n * n} éléments API pour {n * (n - 1)} trajets distincts, selon la tarification de mon projet Google Cloud",
        key="google_billing_ack",
    )
    unknown = [code for code in codes if building_position(code) is None]
    if unknown:
        st.info("Coordonnées à renseigner avant le calcul : " + ", ".join(unknown))
    if st.button(
        "Calculer tous les trajets à pied",
        disabled=not key or not approved or bool(unknown),
        key="google_compute",
    ):
        try:
            with st.spinner("Calcul des trajets piétons avec Google Maps…"):
                packet = compute_walking_matrix(codes, key)
            st.session_state.google_walking_matrix = packet
            st.session_state.pop("preview", None)
            st.session_state.pop("uniform_preview", None)
            st.rerun()
        except ValueError as error:
            st.error(str(error))
    packet = active_matrix(data)
    if not packet:
        st.info(
            "Aucune distance Google Maps n’a encore été calculée. Les distances actuelles de planification restent à vol d’oiseau."
        )
    else:
        rows = []
        for (source, target), route in sorted(packet["routes"].items()):
            if source == target:
                continue
            rows.append(
                {
                    "Départ": source,
                    "Arrivée": target,
                    "Distance piétonne (m)": route["distance_m"],
                    "Durée indicative (min)": round(route["duration_s"] / 60, 1)
                    if route["duration_s"] is not None
                    else None,
                    "État": route["status"],
                    "Itinéraire": directions_url(source, target),
                }
            )
        st.markdown(
            '<span translate="no" style="font:400 14px sans-serif;color:#5e5e5e">Google Maps</span>',
            unsafe_allow_html=True,
        )
        st.dataframe(
            rows,
            hide_index=True,
            width="stretch",
            column_config={
                "Itinéraire": st.column_config.LinkColumn(
                    "Google Maps", display_text="Ouvrir le trajet"
                ),
            },
        )
        st.caption(
            f"Calcul effectué : {packet['calculated_at']} (UTC). Résultats conservés uniquement dans cette session, "
            "sans enregistrement en base ni export des distances Google Maps. "
            "Les trajets indisponibles ne sont pas remplacés par une distance à vol d’oiseau."
        )
    if len(codes) >= 2:
        left, right = st.columns(2)
        source = left.selectbox("Départ dans Google Maps", codes, key="google_from")
        target = right.selectbox(
            "Arrivée dans Google Maps", codes, index=1, key="google_to"
        )
        link = directions_url(source, target)
        if link:
            st.link_button("Voir cet itinéraire à pied dans Google Maps", link)
