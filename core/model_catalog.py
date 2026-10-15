"""Formats physiques documentés ; un numéro de gamme ne désigne pas une taille."""

import json
from functools import lru_cache
from pathlib import Path

FORMATS = ["Tour", "SFF / Slim", "Micro", "Portable", "À confirmer"]
SIZE_RANK = {name: rank for rank, name in enumerate(FORMATS)}


@lru_cache(maxsize=1)
def catalog():
    return json.loads(
        (
            Path(__file__).resolve().parents[1] / "data/public/model_formats.json"
        ).read_text()
    )


def model_profile(model, overrides=None):
    reference = catalog().get(model, {})
    form = (overrides or {}).get(model) or reference.get("format", "À confirmer")
    confirmed = model in (overrides or {})
    return {
        "format": form,
        "dimensions": reference.get("dimensions_mm")
        if form == reference.get("format")
        else None,
        "source": "Format confirmé localement"
        if confirmed
        else reference.get("evidence", "Format absent du nom : vérifier le boîtier"),
        "url": reference.get("url"),
    }


def model_rows(models, data):
    rows = []
    for model in models:
        profile = model_profile(model, data.model_formats)
        dims = profile["dimensions"]
        volume = round(dims[0] * dims[1] * dims[2] / 1_000_000, 2) if dims else None
        rows.append(
            {
                "Modèle": model,
                "Format": profile["format"],
                "Dimensions H × L × P (mm)": " × ".join(f"{v:g}" for v in dims)
                if dims
                else "À confirmer",
                "Encombrement (L)": volume,
                "Vérification": profile["source"],
                "Fiche constructeur": profile["url"],
                "Présent dans l’inventaire": model in models
                and any(m == model and q > 0 for (_, m), q in data.inventory.items()),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            SIZE_RANK[row["Format"]],
            -(row["Encombrement (L)"] or 0),
            row["Modèle"],
        ),
    )
