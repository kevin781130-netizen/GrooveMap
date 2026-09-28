import struct
import numpy as np

from groovemap_next.drum_transcriber import (
    _adaptive_z,
    _pick_peaks,
    load_wav_mono,
)

PCM_GUID = bytes.fromhex("0100000000001000800000aa00389b71")

def _riff(chunks):
    body = b"WAVE"
    for chunk_id, payload in chunks:
        body += chunk_id + struct.pack("<I", len(payload)) + payload
        if len(payload) & 1:
            body += b"\x00"
    return b"RIFF" + struct.pack("<I", len(body)) + body

def test_adaptive_window_is_capped_to_short_score():
    score = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    z = _adaptive_z(score, 100)
    assert z.shape == score.shape

def test_peak_picker_keeps_boundary_peaks():
    z = np.array([4.0, 0.0, 0.0, 5.0], dtype=np.float32)
    assert _pick_peaks(z, threshold=2.0, min_gap_frames=1) == [0, 3]

def test_reads_wave_format_extensible_pcm16(tmp_path):
    samples = np.array([0, 32767, -32768, 0], dtype="<i2")
    channels = 1
    sr = 48000
    bits = 16
    block_align = channels * 2
    avg = sr * block_align
    fmt = struct.pack(
        "<HHIIHHHHI",
        0xFFFE, channels, sr, avg, block_align, bits,
        22, bits, 0,
    ) + PCM_GUID
    path = tmp_path / "extensible.wav"
    path.write_bytes(_riff([(b"fmt ", fmt), (b"data", samples.tobytes())]))
    audio, got_sr = load_wav_mono(path)
    assert got_sr == sr
    assert audio.shape == (4,)
    assert audio[1] > 0.99
    assert audio[2] <= -1.0
