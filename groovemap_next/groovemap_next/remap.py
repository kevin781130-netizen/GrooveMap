"""Clean-room drum note remapping.

AD2/SD3 can use user-selectable keymaps, so GrooveMap does not hard-code one
vendor map as universal truth.  A profile is an ordinary JSON object keyed by
semantic labels (kick, snare, closed_hat, ...), allowing exact project maps.
"""
from __future__ import annotations
import json
from pathlib import Path
from .models import DrumEvent

DEFAULT_GM_BY_LABEL = {
    "kick": 36,
    "snare": 38,
    "closed_hat": 42,
}

def load_mapping(path: str | Path) -> dict[str, int]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("mapping JSON must be an object")
    mapping: dict[str, int] = {}
    for label, note in raw.items():
        value = int(note)
        if not 0 <= value <= 127:
            raise ValueError(f"invalid MIDI note for {label}: {value}")
        mapping[str(label)] = value
    return mapping

def remap_events(events: list[DrumEvent], mapping: dict[str, int]) -> list[DrumEvent]:
    out: list[DrumEvent] = []
    for event in events:
        note = mapping.get(event.label, event.note)
        out.append(DrumEvent(event.time_sec, note, event.velocity, event.label))
    return out
