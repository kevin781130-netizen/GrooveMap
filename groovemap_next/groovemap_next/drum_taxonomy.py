"""GrooveMap semantic 20-class drum taxonomy.

The default notes are General MIDI-compatible anchors. Vendor-specific AD2/SD3
maps remain a separate remapping layer.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DrumClass:
    label: str
    midi_note: int


DRUM_CLASSES_20: tuple[DrumClass, ...] = (
    DrumClass("kick", 36),
    DrumClass("snare", 38),
    DrumClass("sidestick", 37),
    DrumClass("clap", 39),
    DrumClass("closed_hat", 42),
    DrumClass("pedal_hat", 44),
    DrumClass("open_hat", 46),
    DrumClass("low_floor_tom", 41),
    DrumClass("high_floor_tom", 43),
    DrumClass("low_tom", 45),
    DrumClass("low_mid_tom", 47),
    DrumClass("high_mid_tom", 48),
    DrumClass("high_tom", 50),
    DrumClass("crash_1", 49),
    DrumClass("ride", 51),
    DrumClass("china", 52),
    DrumClass("ride_bell", 53),
    DrumClass("splash", 55),
    DrumClass("crash_2", 57),
    DrumClass("cowbell", 56),
)

BY_LABEL = {item.label: item for item in DRUM_CLASSES_20}
BY_NOTE = {item.midi_note: item for item in DRUM_CLASSES_20}
