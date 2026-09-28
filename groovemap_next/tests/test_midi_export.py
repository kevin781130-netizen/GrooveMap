from groovemap_next.midi_export import _downbeat_ticks
from groovemap_next.models import BeatAnalysis
from groovemap_next.tempo_map import build_tempo_map

def test_downbeat_marker_snaps_to_exact_beat_tick():
    analysis = BeatAnalysis(
        beats_sec=(0.0, 0.5, 1.0, 1.5, 2.0),
        downbeats_sec=(0.018, 2.012),
    )
    tm = build_tempo_map(analysis, repair_missing_beats=False)
    ticks = _downbeat_ticks(tm, tick_shift=3840)
    assert ticks == [3840, 7680]
