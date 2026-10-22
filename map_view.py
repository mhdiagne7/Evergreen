"""Carte des bâtiments recensés, sans exposer l'inventaire à un serveur de carte."""

from collections import Counter
from html import escape

import pydeck as pdk
import streamlit as st

from core.campus import building_distance, campus_catalog

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
        returned = 0
        for (room, model), quantity in data.inventory.items():
            if room in rooms:
                installed[model] += quantity
            elif data.rooms[room].building == building:
                stock += quantity
                returned += data.returned_stock.get((room, model), 0)
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
            "\n".join(
                f"{model} : {count} poste{'s' if count > 1 else ''} ({100 * count / total:.0f} %)"
                for model, count in sorted(
                    installed.items(), key=lambda item: (-item[1], item[0])
                )
                if count
            )
            or "Aucun poste installé"
        )
        rows.append(
            {
                "code": building,
                "name": properties["name"],
                "polygon": feature["geometry"]["coordinates"][0],
                "position": [properties["longitude"], properties["latitude"]],
                "color": color,
                "rooms": len(rooms),
                "installed": total,
                "stock": stock,
                "new_stock": stock - returned,
                "returned_stock": returned,
                "stock_summary": (
                    f"Morisset : {stock - returned} en stock neuf · {returned} retours"
                    if building == "MRT"
                    else "Aucun stock local : stock central à Morisset"
                ),
                "quantity": quantity,
                "details": details,
                "dominant": dominant or "Aucun",
                "dominant_share": round(100 * installed[dominant] / total, 1)
                if dominant
                else 0,
                "model_types": sum(count > 0 for count in installed.values()),
                "dominance_label": (
                    dominant
                    if dominant
                    and sum(
                        count == installed[dominant] for count in installed.values()
                    )
                    == 1
                    else "Égalité entre modèles"
                    if dominant
                    else "Aucun modèle installé"
                ),
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
        st.info(
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
    if st.checkbox(
        "Comparer la distance à vol d’oiseau entre deux bâtiments", key="map_compare"
    ):
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
            "text": (
                "{code} · {name}\n"
                "{rooms} salles · {installed} postes · {model_types} modèles\n\n"
                "MODÈLE PRINCIPAL\n{dominance_label} · {dominant_share} %\n\n"
                "RÉPARTITION DES POSTES\n{details}\n\n{stock_summary}"
            ),
            "style": {
                "backgroundColor": "#183c2f",
                "color": "white",
                "fontSize": "13px",
                "maxWidth": "360px",
                "whiteSpace": "pre-wrap",
                "lineHeight": "1.6",
                "padding": "14px",
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
    with st.expander("Légende des modèles"):
        st.markdown("".join(legend), unsafe_allow_html=True)
    objects = event.selection.objects.get("campus-buildings", [])
    return objects[0]["code"] if objects else None
