"""Clean-room groove extraction and humanization.

This module implements drum-groove transfer without copying Magenta/GrooVAE
source or model parameters.  A source performance is represented by:
- subdivision phase,
- microtiming offset in subdivision units, and
- velocity.

Timing is expressed relative to the beat so a learned feel follows GrooveMap's
variable-tempo curve rather than using fixed millisecond offsets.
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

        spb = int(payload["subdivisions_per_beat"])
        pattern_beats = int(payload["pattern_beats"])
        if not 1 <= spb <= 16:
            raise ValueError("subdivisions_per_beat must be in 1..16")
        if pattern_beats < 1:
            raise ValueError("pattern_beats must be >= 1")

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
        for cell in cells:
            if not -1 <= cell.phase_step < spb * pattern_beats:
                raise ValueError(f"invalid groove phase_step: {cell.phase_step}")
            if not -0.5 <= cell.offset_steps <= 0.5:
                raise ValueError(f"invalid groove offset: {cell.offset_steps}")
            if not 1 <= cell.target_velocity <= 127:
                raise ValueError(f"invalid groove velocity: {cell.target_velocity}")
            if cell.count < 1:
                raise ValueError("groove cell count must be >= 1")

        return cls(
            subdivisions_per_beat=spb,
            pattern_beats=pattern_beats,
            cells=cells,
            source=str(payload.get("source", "groovemap-cleanroom-v1")),
        )


@dataclass(frozen=True, slots=True)
class _PreparedEvent:
    event: DrumEvent
    grid_step: int
    phase: int
    original_offset: float
    target_offset: float
    target_velocity: int


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


def _validated_strength(value: float, name: str) -> float:
    result = float(value)
    if not 0.0 <= result <= 1.5:
        raise ValueError(f"{name} must be in 0.0..1.5")
    return result


def extract_groove_template(
    events: Iterable[DrumEvent],
    tempo_map: TempoMap,
    *,
    subdivisions_per_beat: int = 4,
    pattern_bars: int = 2,
) -> GrooveTemplate:
    """Learn microtiming and velocity from a performed drum track."""
    spb = int(subdivisions_per_beat)
    if not 1 <= spb <= 16:
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


def _prepare_event(
    event: DrumEvent,
    tempo_map: TempoMap,
    template: GrooveTemplate,
    lookup: dict[tuple[int, str], GrooveCell],
) -> _PreparedEvent:
    spb = template.subdivisions_per_beat
    beat_pos = seconds_to_beat_position(tempo_map, event.time_sec)
    floating_step = beat_pos * spb
    grid_step = round(floating_step)
    phase = grid_step % template.pattern_steps
    original_offset = floating_step - grid_step

    cell = (
        lookup.get((phase, event.label))
        or lookup.get((phase, "*"))
        or lookup.get((-1, event.label))
        or lookup.get((-1, "*"))
    )
    if cell is None:
        target_offset = 0.0
        target_velocity = event.velocity
    else:
        target_offset = cell.offset_steps
        target_velocity = cell.target_velocity

    return _PreparedEvent(
        event=event,
        grid_step=grid_step,
        phase=phase,
        original_offset=original_offset,
        target_offset=target_offset,
        target_velocity=target_velocity,
    )


def apply_groove_template(
    events: Iterable[DrumEvent],
    tempo_map: TempoMap,
    template: GrooveTemplate,
    *,
    timing_strength: float = 1.0,
    velocity_strength: float = 1.0,
) -> list[DrumEvent]:
    """Reconstruct timing/velocity while preserving flams and rolls.

    Events sharing the same instrument and nearest subdivision are moved as a
    group. Their center follows the groove template, while their internal
    spacing and velocity differences remain intact.

    timing_strength=0 centers each group on the quantized subdivision.
    timing_strength=1 moves the group center to the learned template offset.
    """
    timing_strength = _validated_strength(timing_strength, "timing_strength")
    velocity_strength = _validated_strength(velocity_strength, "velocity_strength")

    spb = template.subdivisions_per_beat
    if spb < 1 or template.pattern_steps < 1:
        raise ValueError("invalid groove template dimensions")

    lookup = _cell_lookup(template)
    prepared = [
        _prepare_event(event, tempo_map, template, lookup)
        for event in events
    ]

    groups: dict[tuple[int, str], list[_PreparedEvent]] = {}
    for item in prepared:
        groups.setdefault((item.grid_step, item.event.label), []).append(item)

    out: list[DrumEvent] = []
    for group in groups.values():
        offsets = [item.original_offset for item in group]
        velocities = [item.event.velocity for item in group]

        original_center = float(median(offsets))
        target_center = float(median(item.target_offset for item in group))
        desired_center = target_center * timing_strength
        requested_shift = desired_center - original_center

        # Move the entire flam/roll together and keep every hit inside the same
        # nearest subdivision. This prevents note-order inversions/cell jumps.
        min_shift = -0.49 - min(offsets)
        max_shift = 0.49 - max(offsets)
        shift = max(min_shift, min(max_shift, requested_shift))

        original_velocity_center = float(median(velocities))
        target_velocity_center = float(
            median(item.target_velocity for item in group)
        )
        velocity_shift = (
            target_velocity_center - original_velocity_center
        ) * velocity_strength

        for item in group:
            new_offset = item.original_offset + shift
            human_step = item.grid_step + new_offset
            human_beat = human_step / spb
            time_sec = beat_position_to_seconds(tempo_map, human_beat)

            velocity = round(item.event.velocity + velocity_shift)
            out.append(
                DrumEvent(
                    time_sec=max(0.0, time_sec),
                    note=item.event.note,
                    velocity=max(1, min(127, velocity)),
                    label=item.event.label,
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
