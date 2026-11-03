"""Independent mido integration of tempo messages, not the export inverse."""
import mido
import pytest
from groovemap_next.models import BeatAnalysis, DrumEvent
from groovemap_next.tempo_map import build_tempo_map, choose_tick_shift
from groovemap_next.midi_export import write_drum_midi

@pytest.mark.parametrize('intervals', [(0.15,3.0)*8, (0.5000003,0.4999997)*7200])
def test_absolute_seconds_preroll_tail_and_long_tempo_rounding(tmp_path,intervals):
    beats=[2.3]
    for interval in intervals:
        beats.append(beats[-1]+interval)
    tm=build_tempo_map(BeatAnalysis(tuple(beats),(beats[3],)),repair_missing_beats=False)
    times=[0.0,2.31,beats[len(beats)//2]+0.031,beats[-1]+1.2]
    events=[DrumEvent(t,36+i%3,70+i,'fixture') for i,t in enumerate(times)]
    path=tmp_path/'independent.mid'
    write_drum_midi(tm,events,path,tick_shift=choose_tick_shift(tm,0.0))
    midi=mido.MidiFile(path)
    elapsed=0; ons=[]; active={}; offs=0
    for msg in midi:
        elapsed+=msg.time
        if msg.type=='note_on' and msg.velocity:
            assert msg.channel==9 and 1<=msg.velocity<=127
            ons.append(elapsed); active[msg.note]=active.get(msg.note,0)+1
        if msg.type=='note_off':
            assert active.get(msg.note,0)>0
            active[msg.note]-=1; offs+=1
    assert offs==len(events) and not any(active.values())
    assert len(ons)==len(times)
    # One tick at the slowest supported tempo; no new musical accuracy promise.
    for actual,source in zip(ons,times):
        assert abs((actual-ons[0])-source)<3.0/960
