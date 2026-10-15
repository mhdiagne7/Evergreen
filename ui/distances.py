"""Ouvrir les trajets piétons dans Google Maps sans connexion API."""

import streamlit as st

from core.google_routes import directions_url


def google_distances(data, store=None, identifier=None, revision=None):
    st.subheader("Trajets à pied · Google Maps")
    st.caption(
        "Choisis deux bâtiments puis ouvre Google Maps pour consulter la distance "
        "et la durée à pied. Aucune clé API nécessaire. Les distances affichées "
        "dans Evergreen utilisent tes distances de marche renseignées, sinon une estimation à vol d’oiseau."
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

    if source != target and store is not None:
        current = data.walking_routes.get((source, target), {})
        with st.expander("Utiliser une distance de marche dans la planification"):
            st.caption(
                "Consulte le trajet dans Google Maps, puis renseigne ici sa distance en mètres. Aucun robot ne lit Google Maps. Sans saisie, l’estimation à vol d’oiseau reste indiquée."
            )
            with st.form("walking_distance"):
                metres = st.number_input(
                    "Distance du trajet à pied (m)",
                    min_value=1,
                    max_value=100000,
                    value=int(current.get("distance_m", 100)),
                    step=1,
                    key="walking_metres_" + source + "_" + target,
                )
                both = st.checkbox(
                    "J’ai vérifié que la distance est identique au retour",
                    key="walking_both",
                )
                confirmed = st.checkbox(
                    "J’ai vérifié cette distance pour ce trajet", key="walking_confirm"
                )
                save = st.form_submit_button("Enregistrer la distance de marche")
            if save:
                if not confirmed:
                    st.error("Vérifie et confirme la distance avant l’enregistrement.")
                else:
                    try:
                        from ui.common import refresh

                        store.set_walking_distance(
                            identifier, source, target, metres, revision, both
                        )
                        refresh("Distance de marche enregistrée pour la planification.")
                    except ValueError as error:
                        st.error(str(error))
    if data.walking_routes:
        st.dataframe(
            [
                {
                    "Départ": a,
                    "Arrivée": b,
                    "Distance de marche (m)": value["distance_m"],
                    "Renseignée le (UTC)": value["recorded_at"],
                }
                for (a, b), value in sorted(data.walking_routes.items())
            ],
            hide_index=True,
            width="stretch",
        )
