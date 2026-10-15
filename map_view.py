"""Carte des bâtiments recensés, sans exposer l'inventaire à un serveur de carte."""

from collections import Counter
from html import escape

import pydeck as pdk
import streamlit as st

from core.campus import MAP_SOURCE, building_distance, campus_catalog

PALETTE = [
    [37, 122, 86, 205],
    [69, 108, 190, 205],
    [155, 89, 182, 205],
    [218, 136, 43, 205],
    [207, 83, 91, 205],
    [34, 148, 154, 205],
    [118, 130, 43, 205],
    [154, 100, 63, 205],
    [102, 83, 179, 205],
    [186, 75, 139, 205],
    [58, 127, 145, 205],
    [98, 111, 120, 205],
]


def map_rows(data, models, selected_model=None):
    catalog = campus_catalog()
    colors = {
        model: PALETTE[index % len(PALETTE)]
        for index, model in enumerate(sorted(models))
    }
    rows = []
    missing = []
    for building in sorted({room.building for room in data.rooms.values()}):
        feature = catalog.get(building)
        if feature is None:
            missing.append(building)
            continue
        rooms = {
            key
            for key, info in data.rooms.items()
            if info.building == building and info.room_type == "classroom"
        }
        installed = Counter()
        stock = 0
        for (room, model), quantity in data.inventory.items():
            if room in rooms:
                installed[model] += quantity
            elif data.rooms[room].building == building:
                stock += quantity
        total = sum(installed.values())
        dominant = (
            min(installed, key=lambda model: (-installed[model], model))
            if total
            else None
        )
        if selected_model:
            quantity = installed[selected_model]
            color = colors[selected_model] if quantity else [173, 183, 180, 130]
        else:
            quantity = total
            color = colors.get(dominant, [173, 183, 180, 130])
        properties = feature["properties"]
        details = (
            "<br>".join(
                f"{escape(model)} : {count}"
                for model, count in sorted(installed.items())
                if count
            )
            or "Aucun poste installé"
        )
        rows.append(
            {
                "code": building,
                "name": escape(properties["name"]),
                "polygon": feature["geometry"]["coordinates"][0],
                "position": [properties["longitude"], properties["latitude"]],
                "color": color,
                "rooms": len(rooms),
                "installed": total,
                "stock": stock,
                "quantity": quantity,
                "details": details,
                "dominant": dominant or "Aucun",
            }
        )
    return rows, missing, colors


def campus_map(data, models):
    st.subheader("Carte du parc informatique")
    options = ["Tous les modèles"] + list(models)
    selected = st.selectbox("Colorer la carte par modèle", options, key="map_model")
    model = None if selected == "Tous les modèles" else selected
    rows, missing, colors = map_rows(data, models, model)
    if missing:
        st.warning(
            "Bâtiments sans coordonnées officielles dans le référentiel : "
            + ", ".join(missing)
        )
    if not rows:
        st.info(
            "Aucun bâtiment de cet inventaire ne possède de coordonnées dans la carte chargée."
        )
        return None

    area = st.selectbox(
        "Cadrage de la carte",
        ["Campus principal", "Tous les bâtiments", "Campus Lees", "Roger-Guindon"],
        key="map_area",
    )
    focus = rows
    if area == "Campus principal":
        focus = [row for row in rows if row["code"] not in {"LEE", "RGN"}]
    elif area == "Campus Lees":
        focus = [row for row in rows if row["code"] == "LEE"]
    elif area == "Roger-Guindon":
        focus = [row for row in rows if row["code"] == "RGN"]
    focus = focus or rows
    positions = [row["position"] for row in focus]
    if len(positions) == 1:
        longitude, latitude = positions[0]
        view = pdk.ViewState(latitude=latitude, longitude=longitude, zoom=16)
    else:
        view = pdk.data_utils.compute_view(positions, view_proportion=1)
    view.zoom = min(view.zoom, 17)
    layer = pdk.Layer(
        "PolygonLayer",
        id="campus-buildings",
        data=rows,
        get_polygon="polygon",
        get_fill_color="color",
        get_line_color=[30, 74, 61, 240],
        line_width_min_pixels=1,
        pickable=True,
        auto_highlight=True,
        highlight_color=[255, 215, 90, 190],
    )
    labels = pdk.Layer(
        "TextLayer",
        id="campus-labels",
        data=rows,
        get_position="position",
        get_text="code",
        get_size=13,
        get_color=[25, 45, 37],
        get_pixel_offset=[0, -10],
        background=True,
        get_background_color=[255, 255, 255, 215],
    )
    layers = [layer, labels]
    if st.checkbox("Comparer la distance entre deux bâtiments", key="map_compare"):
        codes = [row["code"] for row in rows]
        left, right = st.columns(2)
        origin = left.selectbox(
            "Bâtiment de départ",
            codes,
            index=codes.index("MRT") if "MRT" in codes else 0,
            key="map_origin",
        )
        destination = right.selectbox(
            "Bâtiment d’arrivée", codes, key="map_destination"
        )
        distance = building_distance(origin, destination)
        st.info(
            f"{origin} → {destination} : {distance:.0f} m à vol d’oiseau. Le trajet piéton et les distances intérieures ne sont pas évalués."
        )
        positions_by_code = {row["code"]: row["position"] for row in rows}
        layers.append(
            pdk.Layer(
                "LineLayer",
                id="building-distance",
                data=[
                    {
                        "source": positions_by_code[origin],
                        "target": positions_by_code[destination],
                    }
                ],
                get_source_position="source",
                get_target_position="target",
                get_color=[120, 75, 180, 230],
                get_width=3,
                pickable=False,
            )
        )
    deck = pdk.Deck(
        layers=layers,
        initial_view_state=view,
        map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
        tooltip={
            "html": (
                "<b>{code} — {name}</b><br>"
                "{rooms} salles · {installed} postes installés<br>"
                "Stock : {stock}<hr>{details}"
            ),
            "style": {
                "backgroundColor": "#183c2f",
                "color": "white",
                "fontSize": "13px",
            },
        },
    )
    event = st.pydeck_chart(
        deck,
        height=510,
        on_select="rerun",
        selection_mode="single-object",
        key="campus_map_" + str(st.session_state.get("active_context", "default")),
    )
    legend = []
    for name, color in colors.items():
        if model and name != model:
            continue
        rgb = ",".join(str(value) for value in color[:3])
        legend.append(
            f'<span style="display:inline-block;margin:0 16px 6px 0">'
            f'<span style="color:rgb({rgb})">●</span> {escape(name)}</span>'
        )
    st.markdown("".join(legend), unsafe_allow_html=True)
    st.caption(
        "Survole un bâtiment pour voir ses modèles et quantités ; clique pour son détail. "
        "Sans filtre, la couleur indique le modèle dominant. En gris : aucun poste du modèle choisi. "
        "Les bâtiments non recensés dans l’inventaire ne sont pas affichés."
    )
    st.caption(
        f"[Contours et coordonnées : carte officielle uOttawa]({MAP_SOURCE}) · "
        "Extraction du 15 octobre 2026. Fond CARTO / OpenStreetMap, connexion Internet requise. "
        "LEE correspond à LEES-FHS, selon ta confirmation."
    )
    objects = event.selection.objects.get("campus-buildings", [])
    return objects[0]["code"] if objects else None
