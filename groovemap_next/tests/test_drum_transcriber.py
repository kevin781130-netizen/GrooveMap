import struct
import numpy as np
import pytest

from groovemap_next.drum_transcriber import (
    _adaptive_z,
    _pick_peaks,
    load_wav_mono,
    transcribe_drum_stem,
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


FLOAT_GUID = bytes.fromhex("0300000000001000800000aa00389b71")


@pytest.mark.parametrize("extensible", [False, True])
def test_load_float32_wav_stereo_including_extensible(tmp_path, extensible):
    # Typical 32-bit float stems exported by professional DAWs.
    samples = np.array([[0.25, 0.75], [-0.25, 0.75], [1.0, 0.0]], dtype="<f4")
    sr = 48000
    channels = 2
    block_align = channels * 4
    avg = sr * block_align
    if extensible:
        fmt = struct.pack(
            "<HHIIHHHHI",
            0xFFFE, channels, sr, avg, block_align, 32,
            22, 32, 0,
        ) + FLOAT_GUID
    else:
        fmt = struct.pack("<HHIIHH", 3, channels, sr, avg, block_align, 32)

    path = tmp_path / ("float-extensible.wav" if extensible else "float.wav")
    path.write_bytes(_riff([(b"fmt ", fmt), (b"data", samples.tobytes())]))
    audio, got_sr = load_wav_mono(path)
    assert got_sr == sr
    assert np.allclose(audio, [0.5, 0.25, 0.5], atol=1e-7)


def test_reject_float32_nan_instead_of_producing_unstable_midi(tmp_path):
    samples = np.array([0.0, float("nan")], dtype="<f4")
    fmt = struct.pack("<HHIIHH", 3, 1, 48000, 192000, 4, 32)
    path = tmp_path / "nonfinite.wav"
    path.write_bytes(_riff([(b"fmt ", fmt), (b"data", samples.tobytes())]))
    with pytest.raises(ValueError, match="non-finite"):
        load_wav_mono(path)


def test_reject_nonstandard_float64_format(tmp_path):
    fmt = struct.pack("<HHIIHH", 3, 1, 48000, 384000, 8, 64)
    path = tmp_path / "float64.wav"
    path.write_bytes(_riff([(b"fmt ", fmt), (b"data", b"\x00" * 8)]))
    with pytest.raises(ValueError, match="32-bit IEEE float"):
        load_wav_mono(path)


@pytest.mark.parametrize("sample_rate", [16000, 48000])
def test_kick_fft_timestamp_tracks_real_attack_instead_of_window_start(
    tmp_path, sample_rate
):
    # Source is a deterministic isolated drum stem with known absolute onset
    # timestamps. This executes actual DSP, not a stubbed transcription result.
    sr = sample_rate
    audio = np.zeros(sr * 3, dtype=np.float32)
    n = np.arange(round(sr * 0.15))
    kick = (
        0.5 * np.sin(2 * np.pi * 70 * n / sr)
        * np.exp(-n / (sr * 0.045))
    ).astype(np.float32)
    timestamps = (0.5, 1.5, 2.5)
    for onset in timestamps:
        i = round(onset * sr)
        audio[i:i + len(kick)] += kick
    pcm16 = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    fmt = struct.pack("<HHIIHH", 1, 1, sr, sr * 2, 2, 16)
    wav = tmp_path / f"known-kick-{sr}.wav"
    wav.write_bytes(_riff([(b"fmt ", fmt), (b"data", pcm16.tobytes())]))

    detected = transcribe_drum_stem(wav)
    kicks = [event.time_sec for event in detected if event.note == 36]
    for onset in timestamps:
        assert any(abs(t - onset) < 0.02 for t in kicks), (sr, onset, kicks)
