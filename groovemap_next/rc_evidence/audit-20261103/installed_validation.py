"""Run outside checkout against a non-editable wheel. No model evidence."""
import hashlib, importlib.metadata as md, json, os, pathlib, runpy, subprocess, sys, wave
import numpy as np
import mido
import groovemap_next
from groovemap_next import pipeline
from groovemap_next.models import BeatAnalysis

root=pathlib.Path.cwd()
assert 'site-packages' in groovemap_next.__file__
assert not os.environ.get('PYTHONPATH') and not os.environ.get('PYTHONHOME')
report={'mode':'INSTALLED_WHEEL_STRUCTURAL_EXPLICIT_STUB_NOT_REAL_INFERENCE',
        'python':sys.version,'prefix':sys.prefix,'imports':{},'versions':{},'commands':[]}
for module in (groovemap_next,np,mido):
    report['imports'][module.__name__]=module.__file__
for name in ('groovemap-next','numpy','mido'):
    report['versions'][name]=md.version(name)
report['entry_points']=[str(x) for x in md.distribution('groovemap-next').entry_points]
report['venv_config']=(pathlib.Path(sys.prefix)/'pyvenv.cfg').read_text()
assert 'include-system-site-packages = false' in report['venv_config']
cli=pathlib.Path(sys.executable).with_name('groovemap-next')
def command(args, expected=0):
    p=subprocess.run([str(cli),*args],capture_output=True,text=True)
    report['commands'].append({'args':args,'exit_code':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
    assert (p.returncode==0)==(expected==0),p.stderr
    return p
sr=48000
signal=np.zeros(sr*4,dtype=np.float32)
n=np.arange(int(sr*.15))
kick=.6*np.sin(2*np.pi*70*n/sr)*np.exp(-n/(sr*.045))
for onset in (.5,1.5,2.5,3.5):
    i=round(onset*sr);signal[i:i+len(kick)]+=kick
wav=root/'合法性未主張 synthetic 鼓.wav'
with wave.open(str(wav),'wb') as f:
    f.setnchannels(1);f.setsampwidth(2);f.setframerate(sr);f.writeframes((signal*32767).astype('<i2').tobytes())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before=sha(wav)
prefix=root/'輸出 空白'
# Use the wheel's actual console script, with only the tracker explicitly replaced.
class ExplicitStub:
    def __init__(self,**kw): pass
    def analyze(self,path):
        assert pathlib.Path(path)==wav
        return BeatAnalysis((.3,.8,1.31,1.81,2.32,2.82,3.33,3.83),(1.31,),
                            'EXPLICIT-STUB-not-real-beat-this')
pipeline.BeatThisTracker=ExplicitStub
sys.argv=[str(cli),'suno','--drums',str(wav),'--out',str(prefix),'--humanize-source']
try:
    runpy.run_path(str(cli),run_name='__main__')
except SystemExit as exc:
    assert exc.code in (None,0), exc.code
payload=json.loads(prefix.with_name(prefix.name+'_timing.json').read_text())
assert payload['beat_source']=='EXPLICIT-STUB-not-real-beat-this'
assert payload['drum_events'] and payload['humanized_events']
beats=payload['beats_sec'];interval=beats[1]-beats[0]
audio_zero=(payload['tick_shift']/payload['ppq']-payload['origin_beat_index'])*interval-beats[0]
for suffix,key in (('_drums.mid','drum_events'),('_drums_humanized.mid','humanized_events')):
    midi=mido.MidiFile(prefix.with_name(prefix.name+suffix))
    seconds=0;notes=[];active={};off=0
    for msg in midi:
        assert msg.time>=0
        seconds+=msg.time
        if msg.type=='note_on' and msg.velocity:
            assert msg.channel==9 and msg.note in (36,38,42) and 1<=msg.velocity<=127
            notes.append((seconds-audio_zero,msg.note,msg.velocity))
            active[msg.note]=active.get(msg.note,0)+1
        elif msg.type=='note_off':
            assert active.get(msg.note,0)>0
            active[msg.note]-=1;off+=1
    expected=sorted(payload[key],key=lambda e:(e['time_sec'],e['note']))
    assert len(notes)==len(expected)==off and not any(active.values())
    for (t,n,v),e in zip(notes,expected):
        assert e['time_sec']>=0 and abs(t-e['time_sec'])<.001 and (n,v)==(e['note'],e['velocity'])
command(['humanize-midi','--midi',str(prefix.with_name(prefix.name+'_drums.mid')),
         '--timing',str(prefix.with_name(prefix.name+'_timing.json')),
         '--groove',str(prefix.with_name(prefix.name+'_groove.json')),
         '--input-has-groovemap-preroll','--out',str(root/'reapplied.mid')])
assert mido.MidiFile(root/'reapplied.mid').tracks
# Real installed CLI with no AI extra: fail loudly, keep all prior outputs.
old={p:sha(p) for p in root.glob('輸出 空白_*')}
p=command(['suno','--drums',str(wav),'--out',str(prefix)],expected=1)
assert 'tempo MIDI     :' not in p.stdout
assert all(sha(p)==h for p,h in old.items())
assert sha(wav)==before
report.update({'source_sha256_before':before,'source_sha256_after':sha(wav),
               'events':len(payload['drum_events']),'humanized_events':len(payload['humanized_events']),
               'independent_mido_seconds_notes_offs_json':'PASS','exit_code':0})
(root/'installed-report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
print(json.dumps(report,indent=2,ensure_ascii=False))
