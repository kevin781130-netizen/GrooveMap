import json
from mido import Message, MidiFile, MidiTrack

from groovemap_next.groove_humanizer import GrooveCell, GrooveTemplate, save_groove_template
from groovemap_next.midi_humanize import humanize_midi_file, read_drum_midi
from groovemap_next.models import BeatAnalysis
from groovemap_next.tempo_map import build_tempo_map

def _tempo():
    return build_tempo_map(
        BeatAnalysis(
            beats_sec=(0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0),
            downbeats_sec=(0.0, 2.0),
        ),
        repair_missing_beats=False,
    )

def _write_skeleton(path, input_shift_beats=0.0):
    midi = MidiFile(type=1, ticks_per_beat=480)
    track = MidiTrack()
    midi.tracks.append(track)
    # External patterns normally start at musical beat zero.
    absolute_tick = round((input_shift_beats + 1.0) * 480)
    track.append(Message("note_on", channel=9, note=38, velocity=80, time=absolute_tick))
    track.append(Message("note_off", channel=9, note=38, velocity=0, time=30))
    midi.save(path)

def test_read_external_midi_uses_groovemap_timeline(tmp_path):
    tm = _tempo()
    tick_shift = 3840
    path = tmp_path / "skeleton.mid"
    _write_skeleton(path)
    events = read_drum_midi(path, tm, input_tick_shift=0)
    assert len(events) == 1
    assert events[0].label == "snare"
    assert abs(events[0].time_sec - 0.5) < 1e-9

def test_humanize_midi_file_roundtrip(tmp_path):
    tm = _tempo()
    tick_shift = 3840
    midi_in = tmp_path / "skeleton.mid"
    midi_out = tmp_path / "human.mid"
    timing = tmp_path / "timing.json"
    groove = tmp_path / "groove.json"
    _write_skeleton(midi_in)

    timing.write_text(
        json.dumps({
            "schema": "groovemap-next-timing-v2",
            "ppq": tm.ppq,
            "beats_per_bar": tm.beats_per_bar,
            "origin_sec": tm.origin_sec,
            "origin_beat_index": tm.origin_beat_index,
            "tick_shift": tick_shift,
            "beats_sec": list(tm.beats_sec),
            "downbeats_sec": list(tm.downbeats_sec),
            "tempo_points": [
                {"beat_index": p.beat_index, "time_sec": p.time_sec, "bpm": p.bpm}
                for p in tm.tempo_points
            ],
        }),
        encoding="utf-8",
    )
    # Beat position 1.0 = grid step 4. Apply +0.2 of one 16th step:
    # +0.05 beat = +25 ms at 120 BPM.
    template = GrooveTemplate(
        subdivisions_per_beat=4,
        pattern_beats=4,
        cells=(
            GrooveCell(4, "snare", 0.2, 120, 1),
            GrooveCell(-1, "*", 0.0, 90, 1),
        ),
    )
    save_groove_template(template, groove)

    humanize_midi_file(
        midi_in,
        timing,
        groove,
        midi_out,
        timing_strength=1.0,
        velocity_strength=1.0,
    )
    events = read_drum_midi(midi_out, tm, input_tick_shift=tick_shift)
    assert len(events) == 1
    assert abs(events[0].time_sec - 0.525) < 0.001
    assert events[0].velocity == 120

def test_can_read_a_groovemap_export_with_preroll(tmp_path):
    tm = _tempo()
    tick_shift = 3840
    path = tmp_path / "groovemap.mid"
    _write_skeleton(path, input_shift_beats=tick_shift / tm.ppq)
    events = read_drum_midi(path, tm, input_tick_shift=tick_shift)
    assert len(events) == 1
    assert abs(events[0].time_sec - 0.5) < 1e-9
