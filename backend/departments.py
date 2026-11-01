"""Controlled label-to-code resolution. AI cannot create department codes."""

import json
import unicodedata
from pathlib import Path


# View: backend/database-schema.svg#D11
# Load the versioned controlled catalog. Fail startup if one normalized alias maps
# to multiple departments; silently choosing one would corrupt filing.
CATALOG = json.loads((Path(__file__).parent / "catalogs" / "departments.json").read_text(encoding="utf-8"))
VERSION = CATALOG["catalog_version"]


# View: backend/database-schema.svg#D11
# Normalize Unicode, whitespace and case for exact catalog aliases, not semantic inference.
def normalize(value):
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


LABELS = {}
for entry in CATALOG["departments"]:
    for name in [entry["name_en"], entry["name_zh"], *entry["aliases_en"], *entry["aliases_zh"]]:
        label = normalize(name)
        if label in LABELS and LABELS[label] != entry["code"]:
            raise ValueError(f"Ambiguous registered department alias: {name}")
        LABELS[label] = entry["code"]


# View: backend/database-schema.svg#D11
# Return a registered code or None. The model cannot manufacture a valid department code.
def resolve(label):
    # database-schema.svg#D11: exact registered aliases only; no translation or guessing.
    return LABELS.get(normalize(label))
