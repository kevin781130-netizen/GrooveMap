"""Targeted safety regressions; controlled fixtures never imply model inference."""
import struct

import pytest
from groovemap_next import pipeline
from groovemap_next.drum_transcriber import load_wav_mono


@pytest.mark.parametrize('channels,bits,raw', [(1,16,b'\0'), (2,16,b'\0\0'), (1,24,b'\0\0')])
def test_incomplete_pcm_frame_is_rejected(tmp_path, channels, bits, raw):
    align = channels * (bits // 8)
    fmt = struct.pack('<HHIIHH',1,channels,48000,48000*align,align,bits)
    body = b'WAVEfmt ' + struct.pack('<I',len(fmt)) + fmt
    body += b'data' + struct.pack('<I',len(raw)) + raw + (b'\0' if len(raw)%2 else b'')
    p = tmp_path/'broken.wav'
    p.write_bytes(b'RIFF'+struct.pack('<I',len(body))+body)
    with pytest.raises(ValueError, match='incomplete WAV frame'):
        load_wav_mono(p)


def test_overlapping_publication_cannot_be_rolled_back_by_other_run(tmp_path, monkeypatch):
    target = tmp_path/'曲 空白_tempo.mid'
    target.write_bytes(b'old')
    first = tmp_path/'first'; first.write_bytes(b'first')
    second = tmp_path/'second'; second.write_bytes(b'second')
    replace = pipeline.os.replace
    attempted = False
    def interleave(src,dst):
        nonlocal attempted
        if src == first:
            attempted = True
            with pytest.raises(FileExistsError, match='publication'):
                pipeline._publish_staged_outputs({target:second}, (), backup_dir=tmp_path/'b2')
        return replace(src,dst)
    monkeypatch.setattr(pipeline.os,'replace',interleave)
    pipeline._publish_staged_outputs({target:first}, (), backup_dir=tmp_path/'b1')
    assert attempted and target.read_bytes() == b'first'
    assert second.read_bytes() == b'second'


def test_source_cannot_be_output_or_stale_optional(tmp_path, monkeypatch):
    source = tmp_path/'song_groove.json'
    source.write_bytes(b'RIFF-source-sentinel')
    def should_not_run(*a,**k):
        pytest.fail('collision must fail before inference')
    monkeypatch.setattr(pipeline,'_transcribe',should_not_run)
    with pytest.raises(ValueError, match='source audio'):
        pipeline.run_suno_drum_pipeline(source,tmp_path/'song')
    assert source.read_bytes() == b'RIFF-source-sentinel'
