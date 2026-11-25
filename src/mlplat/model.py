"""Scoring model and registry. A model is a logistic score over a few named features; the registry says which version is active."""
from __future__ import annotations

import json
import math
import pathlib


class RegistryError(Exception):
    pass


def load(path: pathlib.Path) -> dict:
    try:
        reg = json.loads(pathlib.Path(path).read_text())
        reg["models"][reg["active"]]
    except (OSError, ValueError, KeyError) as e:
        raise RegistryError(f"registry {path} is not usable: {e!r}") from e
    return reg


def score(model: dict, features: dict) -> float:
    z = model["bias"] + sum(w * float(features.get(k, 0)) for k, w in model["weights"].items())
    return 1 / (1 + math.exp(-z))


def decide(model: dict, features: dict) -> tuple[float, bool]:
    s = score(model, features)
    return s, s >= model["threshold"]


def accuracy(model: dict, rows: list[dict]) -> float:
    hits = sum(decide(model, r["features"])[1] == bool(r["fraud"]) for r in rows)
    return hits / len(rows)
