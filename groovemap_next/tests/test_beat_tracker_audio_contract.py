"""Adapter contract only: no weights or model inference are represented here."""
import sys
import types
import wave
import numpy as np
import pytest
from groovemap_next.beat_tracker import BeatThisTracker


def test_adapter_supplies_validated_mono_samples_and_original_rate(tmp_path, monkeypatch):
    path=tmp_path/'鼓 空白.wav'
    stereo=np.array([[0,32767],[-32768,0],[0,0]],dtype='<i2')
    with wave.open(str(path),'wb') as f:
        f.setnchannels(2);f.setsampwidth(2);f.setframerate(48000);f.writeframes(stereo.tobytes())
    seen={}
    class ContractRunner:
        def __init__(self,**kwargs): seen['kwargs']=kwargs
        def __call__(self,signal,sr):
            seen['signal']=signal;seen['sr']=sr
            return np.array([.1,.6]),np.array([.1])
    module=types.ModuleType('beat_this.inference')
    module.Audio2Beats=ContractRunner
    # File2Beats intentionally absent: this adapter must not depend on the
    # optional torchcodec/soundfile/madmom file-decoding chain.
    monkeypatch.setitem(sys.modules,'beat_this.inference',module)
    tracker=BeatThisTracker(checkpoint='/trusted/local.ckpt',device='cpu')
    analysis=tracker.analyze(path)
    assert seen['kwargs']==dict(checkpoint_path='/trusted/local.ckpt',device='cpu',float16=False,dbn=False)
    assert seen['signal'].dtype==np.float32 and seen['signal'].shape==(3,)
    assert np.allclose(seen['signal'],[32767/65536,-.5,0])
    assert seen['sr']==48000
    assert analysis.beats_sec==(.1,.6) and analysis.downbeats_sec==(.1,)


def test_adapter_propagates_real_runner_errors(tmp_path,monkeypatch):
    path=tmp_path/'a.wav'
    with wave.open(str(path),'wb') as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(b'\0\0'*16000)
    class Failure:
        def __init__(self,**kwargs):pass
        def __call__(self,signal,sr):raise RuntimeError('model execution failed')
    module=types.ModuleType('beat_this.inference');module.Audio2Beats=Failure
    monkeypatch.setitem(sys.modules,'beat_this.inference',module)
    with pytest.raises(RuntimeError,match='model execution failed'):
        BeatThisTracker().analyze(path)
