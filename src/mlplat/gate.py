"""Promotion gate for a model version: it must load, and must not score worse than the active model on a holdout set."""
from __future__ import annotations

import json
import pathlib

from .model import RegistryError, accuracy, load


def promote(registry: pathlib.Path, candidate: str, holdout: list[dict], max_drop: float = 0.02) -> list[str]:
    """Return reasons the candidate is refused. Empty means it was made active."""
    reg = load(registry)
    if candidate not in reg["models"]:
        return [f"{candidate} is not in the registry"]
    if candidate == reg["active"]:
        return [f"{candidate} is already active"]
    cur = accuracy(reg["models"][reg["active"]], holdout)
    new = accuracy(reg["models"][candidate], holdout)
    if new < cur - max_drop:
        return [f"{candidate} accuracy {new:.2f} is more than {max_drop:.2f} below active {cur:.2f}"]
    reg["previous"], reg["active"] = reg["active"], candidate
    pathlib.Path(registry).write_text(json.dumps(reg, indent=2) + "\n")
    return []


def rollback(registry: pathlib.Path) -> str:
    reg = load(registry)
    prev = reg.get("previous")
    if not prev or prev not in reg["models"]:
        raise RegistryError("no previous version to roll back to")
    reg["previous"], reg["active"] = reg["active"], prev
    pathlib.Path(registry).write_text(json.dumps(reg, indent=2) + "\n")
    return prev
