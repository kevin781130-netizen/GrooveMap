import pytest

from groovemap_next.models import BeatAnalysis
from groovemap_next.tempo_map import (
    build_tempo_map,
    choose_tick_shift,
    seconds_to_beat_position,
    seconds_to_ticks,
)

def test_variable_tempo_is_per_beat():
    analysis = BeatAnalysis(
        beats_sec=(0.0, 0.5, 1.01, 1.49, 1.98),
        downbeats_sec=(0.0,),
    )
    tm = build_tempo_map(analysis, repair_missing_beats=False)
    assert round(tm.tempo_points[0].bpm, 3) == 120.0
    assert round(tm.tempo_points[1].bpm, 3) == round(60 / 0.51, 3)
    assert round(tm.tempo_points[2].bpm, 3) == 125.0
    assert abs(seconds_to_beat_position(tm, 0.25) - 0.5) < 1e-9
    assert seconds_to_ticks(tm, 0.5) == 960

def test_downbeat_origin_preserves_negative_preroll_beats():
    analysis = BeatAnalysis(
        beats_sec=(0.3, 0.8, 1.3, 1.8, 2.3),
        downbeats_sec=(1.3,),
    )
    tm = build_tempo_map(analysis, repair_missing_beats=False)
    assert tm.origin_beat_index == 2
    assert seconds_to_ticks(tm, 0.3) == -2 * 960
    assert choose_tick_shift(tm, 0.0) >= 4 * 960

def test_missing_single_beat_is_repaired_conservatively():
    analysis = BeatAnalysis(
        beats_sec=(0.0, 0.5, 1.0, 2.0, 2.5, 3.0),
        downbeats_sec=(0.0,),
    )
    tm = build_tempo_map(analysis, repair_missing_beats=True)
    assert any(abs(x - 1.5) < 1e-9 for x in tm.beats_sec)

def test_sustained_half_time_section_is_not_repaired():
    analysis = BeatAnalysis(
        beats_sec=(0.0, 0.5, 1.0, 1.5, 2.5, 3.5, 4.5),
        downbeats_sec=(0.0,),
    )
    tm = build_tempo_map(analysis, repair_missing_beats=True)
    assert tm.beats_sec == analysis.beats_sec
    assert round(tm.tempo_points[3].bpm, 3) == 60.0
    assert round(tm.tempo_points[4].bpm, 3) == 60.0

def test_invalid_interval_rejects_entire_map_instead_of_partial_export():
    analysis = BeatAnalysis(
        beats_sec=(0.0, 0.5, 4.5, 5.0),
        downbeats_sec=(0.0,),
    )
    with pytest.raises(ValueError, match="partial tempo map"):
        build_tempo_map(analysis, repair_missing_beats=False)
