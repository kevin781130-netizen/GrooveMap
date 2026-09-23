"""Optional stem separation via Demucs (規格 3.2)."""
from __future__ import annotations
import logging
import numpy as np

log = logging.getLogger(__name__)


def _pick_device(device=None) -> str:
    import torch
    if device:
        return device
    return "cuda" if torch.cuda.is_available() else "cpu"


def separate_drums(path: str, device=None, model: str = "htdemucs", sr: int = 44100):
    try:
        import torch  # noqa
        from demucs.api import Separator
    except Exception as exc:
        raise RuntimeError(
            "Demucs 未安裝。請執行：pip install -r requirements-demucs.txt"
        ) from exc

    dev = _pick_device(device)
    log.info("Demucs: model=%s device=%s", model, dev)

    separator = Separator(model=model, device=dev, progress=False)
    _origin, stems = separator.separate_audio_file(path)

    drums = stems.get("drums")
    if drums is None:
        raise RuntimeError("Demucs 未回傳 drums stem")

    arr = drums.detach().cpu().numpy()
    mono = arr.mean(axis=0).astype(np.float32)
    return mono, sr


def available() -> bool:
    try:
        import torch  # noqa
        import demucs  # noqa
        return True
    except Exception:
        return False
