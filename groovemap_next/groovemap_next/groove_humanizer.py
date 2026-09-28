"""Clean-room groove extraction and humanization.

This module implements behavior similar in purpose to a drum humanizer without
copying Magenta/GrooVAE source or model parameters.  A source performance is
represented by:
- which subdivision each event belongs to,
- its microtiming offset from that subdivision, in subdivision units, and
- its velocity.

Storing timing as a fraction of the beat rather than fixed milliseconds makes
the template follow GrooveMap's variable tempo curve.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from statistics import median
from typing import Iterable

from .models import DrumEvent, TempoMap
from .tempo_map import beat_position_to_seconds, seconds_to_beat_position


@dataclass(frozen=True, slots=True)
class GrooveCell:
    phase_step: int
    label: str
    offset_steps: float
    target_velocity: int
    count: int


@dataclass(frozen=True, slots=True)
class GrooveTemplate:
    subdivisions_per_beat: int
    pattern_beats: int
    cells: tuple[GrooveCell, ...]
    source: str = "groovemap-cleanroom-v1"

    @property
    def pattern_steps(self) -> int:
        return self.subdivisions_per_beat * self.pattern_beats

    def to_dict(self) -> dict:
        return {
            "schema": "groovemap-groove-v1",
            "source": self.source,
            "subdivisions_per_beat": self.subdivisions_per_beat,
            "pattern_beats": self.pattern_beats,
            "cells": [asdict(cell) for cell in self.cells],
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "GrooveTemplate":
        if payload.get("schema") != "groovemap-groove-v1":
            raise ValueError("unsupported GrooveMap groove schema")
        cells = tuple(
            GrooveCell(
                phase_step=int(item["phase_step"]),
                label=str(item["label"]),
                offset_steps=float(item["offset_steps"]),
                target_velocity=int(item["target_velocity"]),
                count=int(item["count"]),
            )
            for item in payload["cells"]
        )
        return cls(
            subdivisions_per_beat=int(payload["subdivisions_per_beat"]),
            pattern_beats=int(payload["pattern_beats"]),
            cells=cells,
            source=str(payload.get("source", "groovemap-cleanroom-v1")),
        )


def _median_cell(
    phase_step: int,
    label: str,
    rows: list[tuple[float, int]],
) -> GrooveCell:
    offset = max(-0.49, min(0.49, float(median(x[0] for x in rows))))
    velocity = int(round(median(x[1] for x in rows)))
    return GrooveCell(
        phase_step=phase_step,
        label=label,
        offset_steps=offset,
        target_velocity=max(1, min(127, velocity)),
        count=len(rows),
    )


def extract_groove_template(
    events: Iterable[DrumEvent],
    tempo_map: TempoMap,
    *,
    subdivisions_per_beat: int = 4,
    pattern_bars: int = 2,
) -> GrooveTemplate:
    """Learn microtiming and velocity from a performed drum track.

    The default 4 subdivisions/beat is a 16th-note grid in 4/4.  The pattern
    repeats every two bars, but cell statistics may aggregate repeated
    occurrences across the whole song.
    """
    spb = int(subdivisions_per_beat)
    if spb < 1 or spb > 16:
        raise ValueError("subdivisions_per_beat must be in 1..16")
    if pattern_bars < 1:
        raise ValueError("pattern_bars must be >= 1")

    pattern_beats = tempo_map.beats_per_bar * int(pattern_bars)
    pattern_steps = pattern_beats * spb

    specific: dict[tuple[int, str], list[tuple[float, int]]] = {}
    phase_any: dict[int, list[tuple[float, int]]] = {}
    label_any: dict[str, list[tuple[float, int]]] = {}
    all_rows: list[tuple[float, int]] = []

    for event in events:
        beat_pos = seconds_to_beat_position(tempo_map, event.time_sec)
        floating_step = beat_pos * spb
        nearest_step = round(floating_step)
        phase = nearest_step % pattern_steps
        offset_steps = floating_step - nearest_step
        row = (offset_steps, event.velocity)

        specific.setdefault((phase, event.label), []).append(row)
        phase_any.setdefault(phase, []).append(row)
        label_any.setdefault(event.label, []).append(row)
        all_rows.append(row)

    if not all_rows:
        raise ValueError("cannot extract groove from an empty event list")

    cells: list[GrooveCell] = []
    for (phase, label), rows in sorted(specific.items()):
        cells.append(_median_cell(phase, label, rows))
    for phase, rows in sorted(phase_any.items()):
        cells.append(_median_cell(phase, "*", rows))
    for label, rows in sorted(label_any.items()):
        cells.append(_median_cell(-1, label, rows))
    cells.append(_median_cell(-1, "*", all_rows))

    return GrooveTemplate(
        subdivisions_per_beat=spb,
        pattern_beats=pattern_beats,
        cells=tuple(cells),
    )


def _cell_lookup(template: GrooveTemplate) -> dict[tuple[int, str], GrooveCell]:
    return {(cell.phase_step, cell.label): cell for cell in template.cells}


def apply_groove_template(
    events: Iterable[DrumEvent],
    tempo_map: TempoMap,
    template: GrooveTemplate,
    *,
    timing_strength: float = 1.0,
    velocity_strength: float = 1.0,
) -> list[DrumEvent]:
    """Quantize to the skeleton then reconstruct timing/velocity from template.

    strength=0 produces the quantized/unchanged-velocity skeleton.
    strength=1 applies the complete learned template.
    """
    timing_strength = max(0.0, min(1.5, float(timing_strength)))
    velocity_strength = max(0.0, min(1.5, float(velocity_strength)))
    spb = template.subdivisions_per_beat
    steps = template.pattern_steps
    lookup = _cell_lookup(template)

    out: list[DrumEvent] = []
    for event in events:
        beat_pos = seconds_to_beat_position(tempo_map, event.time_sec)
        grid_step = round(beat_pos * spb)
        phase = grid_step % steps

        cell = (
            lookup.get((phase, event.label))
            or lookup.get((phase, "*"))
            or lookup.get((-1, event.label))
            or lookup.get((-1, "*"))
        )
        if cell is None:
            # Defensive fallback; extract_groove_template always emits global.
            offset = 0.0
            target_velocity = event.velocity
        else:
            offset = cell.offset_steps
            target_velocity = cell.target_velocity

        human_step = grid_step + offset * timing_strength
        human_beat = human_step / spb
        time_sec = beat_position_to_seconds(tempo_map, human_beat)

        velocity = round(
            event.velocity
            + (target_velocity - event.velocity) * velocity_strength
        )
        out.append(
            DrumEvent(
                time_sec=max(0.0, time_sec),
                note=event.note,
                velocity=max(1, min(127, velocity)),
                label=event.label,
            )
        )

    return sorted(out, key=lambda e: (e.time_sec, e.note, e.label))


def save_groove_template(template: GrooveTemplate, path: str | Path) -> Path:
    output = Path(path)
    output.write_text(
        json.dumps(template.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output


def load_groove_template(path: str | Path) -> GrooveTemplate:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return GrooveTemplate.from_dict(payload)
