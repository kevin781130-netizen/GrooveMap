"""Small immutable data models used by the GrooveMap Next pipeline."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True, slots=True)
class DrumEvent:
    time_sec: float
    note: int
    velocity: int
    label: str
    def __post_init__(self) -> None:
        if self.time_sec < 0: raise ValueError("time_sec must be >= 0")
        if not 0 <= self.note <= 127: raise ValueError("MIDI note must be in 0..127")
        if not 1 <= self.velocity <= 127: raise ValueError("velocity must be in 1..127")

@dataclass(frozen=True, slots=True)
class TempoPoint:
    # Relative to chosen musical origin; pre-roll beat indices may be negative.
    beat_index: int
    time_sec: float
    bpm: float
    def __post_init__(self) -> None:
        if self.time_sec < 0: raise ValueError("time_sec must be >= 0")
        if not 20.0 <= self.bpm <= 400.0: raise ValueError(f"implausible BPM: {self.bpm}")

@dataclass(frozen=True, slots=True)
class BeatAnalysis:
    beats_sec: tuple[float, ...]
    downbeats_sec: tuple[float, ...]
    source: str = "beat-this"

@dataclass(frozen=True, slots=True)
class TempoMap:
    beats_sec: tuple[float, ...]
    downbeats_sec: tuple[float, ...]
    tempo_points: tuple[TempoPoint, ...]
    origin_sec: float
    origin_beat_index: int
    ppq: int = 960
    beats_per_bar: int = 4
    @property
    def duration_sec(self) -> float:
        return self.beats_sec[-1] - self.beats_sec[0] if len(self.beats_sec) >= 2 else 0.0

@dataclass(frozen=True, slots=True)
class PipelineOutputs:
    tempo_midi: Path
    drum_midi: Path
    timing_json: Path
    humanized_midi: Path | None = None
    groove_json: Path | None = None
