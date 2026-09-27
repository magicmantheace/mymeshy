"""Named generation workload presets shared by API clients and the UI."""
from __future__ import annotations

from dataclasses import asdict
from typing import Literal

from .base import GenOptions

PresetName = Literal["fast", "balanced", "quality"]

_PRESETS: dict[PresetName, GenOptions] = {
    "fast": GenOptions(adapter="triposr", target_polycount=20_000, texture_size=1024, generate_pbr=True),
    "balanced": GenOptions(adapter=None, target_polycount=30_000, texture_size=1024, generate_pbr=True),
    "quality": GenOptions(adapter="hunyuan3d", target_polycount=50_000, texture_size=2048, generate_pbr=True),
}


def names() -> tuple[str, ...]:
    return tuple(_PRESETS)


def resolve(name: str) -> GenOptions:
    try:
        preset = _PRESETS[name]
    except KeyError as exc:
        raise ValueError(f"unknown generation preset: {name}") from exc
    return GenOptions(**asdict(preset))


def public(adapter_status: list[dict]) -> list[dict]:
    available = {item["name"] for item in adapter_status if item.get("available")}
    rows = []
    for name, preset in _PRESETS.items():
        data = asdict(preset)
        required = data.get("adapter")
        rows.append({
            "name": name,
            "available": required is None or required in available,
            "required_adapter": required,
            "settings": data,
        })
    return rows
