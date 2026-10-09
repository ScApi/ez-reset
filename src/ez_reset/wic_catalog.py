"""WIC support catalog is informational only and must not authorize EEPROM writes."""
from __future__ import annotations

import csv
import re
from importlib.resources import files


def normalized_model(model: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", model.upper().removeprefix("EPSON "))


def candidate_info(model: str) -> dict | None:
    with files(__package__).joinpath("wic_candidates.csv").open("r", encoding="utf-8") as stream:
        for row in csv.DictReader(stream, delimiter=";"):
            if normalized_model(row["wic_model"]) == normalized_model(model):
                return row
    return None
