"""MIT Beat This! adapter. Uses minimal postprocessing (dbn=False)."""
from __future__ import annotations
from pathlib import Path
from .models import BeatAnalysis

class BeatThisTracker:
    def __init__(self, *, checkpoint: str = "final0", device: str = "cpu", float16: bool = False) -> None:
        try:
            from beat_this.inference import File2Beats
        except ImportError as exc:
            raise RuntimeError('Install AI support with: pip install -e ".[ai]"') from exc
        self._runner = File2Beats(
            checkpoint_path=checkpoint, device=device, float16=float16, dbn=False
        )

    def analyze(self, audio_path: str | Path) -> BeatAnalysis:
        beats, downbeats = self._runner(str(audio_path))
        return BeatAnalysis(
            beats_sec=tuple(float(x) for x in beats),
            downbeats_sec=tuple(float(x) for x in downbeats),
            source="CPJKU/beat_this:minimal",
        )
