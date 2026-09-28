from groovemap_next.groove_humanizer import (
    apply_groove_template,
    extract_groove_template,
    load_groove_template,
    save_groove_template,
)
from groovemap_next.models import BeatAnalysis, DrumEvent
from groovemap_next.tempo_map import (
    beat_position_to_seconds,
    build_tempo_map,
    seconds_to_beat_position,
)

def _tempo():
    return build_tempo_map(
        BeatAnalysis(
            beats_sec=(0.0, 0.5, 1.01, 1.49, 1.98, 2.48, 2.99, 3.48, 3.98),
            downbeats_sec=(0.0, 1.98, 3.98),
        ),
        repair_missing_beats=False,
    )

def test_beat_position_inverse_round_trip():
    tm = _tempo()
    for time_sec in (0.0, 0.22, 0.5, 0.93, 1.72, 3.7):
        beat = seconds_to_beat_position(tm, time_sec)
        rebuilt = beat_position_to_seconds(tm, beat)
        assert abs(rebuilt - time_sec) < 1e-9

def test_source_groove_reconstructs_microtiming_and_velocity():
    tm = _tempo()
    source = [
        DrumEvent(0.020, 36, 83, "kick"),
        DrumEvent(0.492, 38, 116, "snare"),
        DrumEvent(1.018, 42, 71, "closed_hat"),
        DrumEvent(1.475, 38, 109, "snare"),
    ]
    template = extract_groove_template(source, tm, pattern_bars=1)
    rebuilt = apply_groove_template(
        source, tm, template, timing_strength=1.0, velocity_strength=1.0
    )
    assert [x.velocity for x in rebuilt] == [x.velocity for x in source]
    for got, expected in zip(rebuilt, source):
        assert abs(got.time_sec - expected.time_sec) < 1e-9

def test_zero_timing_strength_returns_quantized_skeleton():
    tm = _tempo()
    source = [DrumEvent(0.020, 36, 83, "kick")]
    template = extract_groove_template(source, tm, pattern_bars=1)
    rebuilt = apply_groove_template(
        source, tm, template, timing_strength=0.0, velocity_strength=0.0
    )
    assert rebuilt[0].time_sec == 0.0
    assert rebuilt[0].velocity == 83

def test_groove_template_json_roundtrip(tmp_path):
    tm = _tempo()
    source = [DrumEvent(0.020, 36, 83, "kick")]
    template = extract_groove_template(source, tm, pattern_bars=1)
    path = save_groove_template(template, tmp_path / "groove.json")
    loaded = load_groove_template(path)
    assert loaded == template
