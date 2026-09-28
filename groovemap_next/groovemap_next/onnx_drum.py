"""Generic MIT-runtime ONNX drum-transcription adapter.

No model weights are bundled. A model is accepted only together with a
GrooveMap manifest that explicitly defines its tensor contract and class map.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np

from .drum_transcriber import _pick_peaks, load_wav_mono
from .models import DrumEvent


@dataclass(frozen=True, slots=True)
class OnnxDrumManifest:
    sample_rate: int
    hop_length: int
    labels: tuple[str, ...]
    midi_notes: tuple[int, ...]
    input_name: str
    onset_output: str
    velocity_output: str | None = None
    velocity_encoding: str | None = None
    input_layout: str = "B,T"
    output_layout: str = "B,T,C"
    output_activation: str = "probability"
    threshold: float = 0.5
    min_gap_ms: float = 25.0

    @classmethod
    def load(cls, path: str | Path) -> "OnnxDrumManifest":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("schema") != "groovemap-onnx-drum-v1":
            raise ValueError("unsupported GrooveMap ONNX drum manifest schema")

        labels = tuple(str(x) for x in payload["labels"])
        midi_notes = tuple(int(x) for x in payload["midi_notes"])
        if len(labels) != len(midi_notes):
            raise ValueError("labels and midi_notes must have equal length")
        if not labels:
            raise ValueError("manifest must define at least one class")
        if len(set(labels)) != len(labels):
            raise ValueError("manifest labels must be unique")
        if any(not 0 <= note <= 127 for note in midi_notes):
            raise ValueError("manifest contains invalid MIDI notes")

        input_layout = str(payload.get("input_layout", "B,T"))
        output_layout = str(payload.get("output_layout", "B,T,C"))
        if input_layout not in {"B,T", "B,C,T"}:
            raise ValueError("input_layout must be B,T or B,C,T")
        if output_layout not in {"B,T,C", "B,C,T"}:
            raise ValueError("output_layout must be B,T,C or B,C,T")

        output_activation = str(payload.get("output_activation", "probability"))
        if output_activation not in {"probability", "logit"}:
            raise ValueError("output_activation must be probability or logit")

        sample_rate = int(payload["sample_rate"])
        hop_length = int(payload["hop_length"])
        threshold = float(payload.get("threshold", 0.5))
        min_gap_ms = float(payload.get("min_gap_ms", 25.0))
        if sample_rate <= 0 or hop_length <= 0:
            raise ValueError("sample_rate and hop_length must be positive")
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be in 0..1")
        if min_gap_ms < 0.0:
            raise ValueError("min_gap_ms must be >= 0")

        velocity_output = (
            str(payload["velocity_output"])
            if payload.get("velocity_output") is not None
            else None
        )
        velocity_encoding = (
            str(payload["velocity_encoding"])
            if payload.get("velocity_encoding") is not None
            else None
        )
        if velocity_output is not None:
            if velocity_encoding not in {"normalized", "midi"}:
                raise ValueError(
                    "velocity_encoding must be declared as 'normalized' or "
                    "'midi' when velocity_output is present"
                )
        elif velocity_encoding is not None:
            raise ValueError(
                "velocity_encoding requires a velocity_output tensor"
            )

        return cls(
            sample_rate=sample_rate,
            hop_length=hop_length,
            labels=labels,
            midi_notes=midi_notes,
            input_name=str(payload["input_name"]),
            onset_output=str(payload["onset_output"]),
            velocity_output=velocity_output,
            velocity_encoding=velocity_encoding,
            input_layout=input_layout,
            output_layout=output_layout,
            output_activation=output_activation,
            threshold=threshold,
            min_gap_ms=min_gap_ms,
        )


def _windowed_sinc_lowpass(
    signal: np.ndarray,
    *,
    source_sr: int,
    target_sr: int,
) -> np.ndarray:
    """Anti-alias filter before downsampling, implemented with NumPy only."""
    if target_sr >= source_sr or signal.size < 3:
        return signal.astype(np.float32, copy=False)

    # Target Nyquist expressed in cycles/source-sample, with transition margin.
    cutoff = 0.5 * (target_sr / source_sr) * 0.94
    if not 0.0 < cutoff < 0.5:
        return signal.astype(np.float32, copy=False)

    # Odd tap count; cap it for short clips so np.convolve(mode='same') keeps
    # the input length. 129 taps is cheap relative to model inference.
    taps = min(129, int(signal.size))
    if taps % 2 == 0:
        taps -= 1
    if taps < 3:
        return signal.astype(np.float32, copy=False)

    half = taps // 2
    n = np.arange(-half, half + 1, dtype=np.float64)
    kernel = 2.0 * cutoff * np.sinc(2.0 * cutoff * n)
    kernel *= np.hanning(taps)
    kernel_sum = float(kernel.sum())
    if abs(kernel_sum) < 1e-12:
        return signal.astype(np.float32, copy=False)
    kernel /= kernel_sum

    return np.convolve(
        signal.astype(np.float64, copy=False),
        kernel,
        mode="same",
    ).astype(np.float32)


def _resample_bandlimited(
    signal: np.ndarray,
    source_sr: int,
    target_sr: int,
) -> np.ndarray:
    if source_sr <= 0 or target_sr <= 0:
        raise ValueError("sample rates must be positive")
    if source_sr == target_sr:
        return signal.astype(np.float32, copy=False)
    if signal.size == 0:
        return signal.astype(np.float32)

    filtered = _windowed_sinc_lowpass(
        signal,
        source_sr=source_sr,
        target_sr=target_sr,
    )
    new_length = max(1, round(len(filtered) * target_sr / source_sr))

    # Endpoint-aware time coordinates avoid an accumulating duration error.
    old_x = np.arange(len(filtered), dtype=np.float64) / source_sr
    new_x = np.arange(new_length, dtype=np.float64) / target_sr
    return np.interp(
        new_x,
        old_x,
        filtered,
        left=float(filtered[0]),
        right=float(filtered[-1]),
    ).astype(np.float32)


def _as_frames_classes(
    tensor: np.ndarray,
    *,
    layout: str,
    class_count: int,
) -> np.ndarray:
    x = np.asarray(tensor)
    if x.ndim == 3:
        if x.shape[0] != 1:
            raise ValueError(f"expected batch size 1, got {x.shape}")
        x = x[0]
    if x.ndim != 2:
        raise ValueError(f"expected 2D/3D model output, got {x.shape}")
    if layout == "B,C,T":
        x = x.T
    if x.shape[1] != class_count:
        raise ValueError(
            f"model output has {x.shape[1]} classes; manifest declares {class_count}"
        )
    return x.astype(np.float32, copy=False)


def _velocity_to_midi(raw_velocity: float, encoding: str) -> int:
    if encoding == "normalized":
        value = round(float(np.clip(raw_velocity, 0.0, 1.0)) * 127.0)
    elif encoding == "midi":
        value = round(float(np.clip(raw_velocity, 0.0, 127.0)))
    else:
        raise ValueError(f"unsupported velocity encoding: {encoding!r}")
    return max(1, min(127, value))


class OnnxDrumTranscriber:
    def __init__(
        self,
        model_path: str | Path,
        manifest_path: str | Path,
        *,
        providers: list[str] | None = None,
    ) -> None:
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise RuntimeError(
                'ONNX support is optional. Install with: pip install -e ".[onnx]"'
            ) from exc

        self.manifest = OnnxDrumManifest.load(manifest_path)
        self.session = ort.InferenceSession(
            str(model_path),
            providers=providers or ["CPUExecutionProvider"],
        )

        available_inputs = {x.name for x in self.session.get_inputs()}
        if self.manifest.input_name not in available_inputs:
            raise ValueError(
                f"manifest input {self.manifest.input_name!r} not found in model"
            )

        available_outputs = {x.name for x in self.session.get_outputs()}
        required_outputs = {self.manifest.onset_output}
        if self.manifest.velocity_output is not None:
            required_outputs.add(self.manifest.velocity_output)
        missing_outputs = required_outputs - available_outputs
        if missing_outputs:
            raise ValueError(
                f"manifest outputs not found in model: {sorted(missing_outputs)}"
            )

    def transcribe(
        self,
        wav_path: str | Path,
        *,
        threshold: float | None = None,
    ) -> list[DrumEvent]:
        signal, source_sr = load_wav_mono(wav_path)
        m = self.manifest
        signal = _resample_bandlimited(signal, source_sr, m.sample_rate)

        if m.input_layout == "B,C,T":
            model_input = signal[None, None, :]
        else:
            model_input = signal[None, :]

        requested = [m.onset_output]
        if m.velocity_output is not None:
            requested.append(m.velocity_output)

        outputs = self.session.run(
            requested,
            {m.input_name: model_input.astype(np.float32, copy=False)},
        )
        onset = _as_frames_classes(
            outputs[0],
            layout=m.output_layout,
            class_count=len(m.labels),
        )
        if m.output_activation == "logit":
            onset = 1.0 / (1.0 + np.exp(-np.clip(onset, -30.0, 30.0)))

        velocity = None
        if m.velocity_output is not None:
            velocity = _as_frames_classes(
                outputs[1],
                layout=m.output_layout,
                class_count=len(m.labels),
            )

        th = float(m.threshold if threshold is None else threshold)
        if not 0.0 <= th <= 1.0:
            raise ValueError("onset threshold must be in 0..1")
        min_gap_frames = max(
            1,
            round((m.min_gap_ms / 1000.0) * m.sample_rate / m.hop_length),
        )

        events: list[DrumEvent] = []
        for class_index, (label, midi_note) in enumerate(
            zip(m.labels, m.midi_notes)
        ):
            score = onset[:, class_index]
            peaks = _pick_peaks(
                score,
                threshold=th,
                min_gap_frames=min_gap_frames,
            )
            for frame in peaks:
                probability = float(score[frame])
                if velocity is None:
                    midi_velocity = max(
                        1,
                        min(127, round(25 + 102 * probability)),
                    )
                else:
                    assert m.velocity_encoding is not None
                    raw_velocity = float(velocity[frame, class_index])
                    midi_velocity = _velocity_to_midi(
                        raw_velocity,
                        m.velocity_encoding,
                    )

                events.append(
                    DrumEvent(
                        time_sec=frame * m.hop_length / m.sample_rate,
                        note=midi_note,
                        velocity=midi_velocity,
                        label=label,
                    )
                )

        return sorted(events, key=lambda e: (e.time_sec, e.note, e.label))
