#!/usr/bin/env python3
"""GrooveMap — 入口點（GUI + CLI 雙模式）."""
from __future__ import annotations

import argparse
import logging
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="GrooveMap",
        description="Live Band 錄音 → Cubase Tempo Map / Click / Marker",
    )
    p.add_argument("audio", nargs="?", help="要分析的音檔（省略則開啟 GUI）")
    p.add_argument("-o", "--out", default=None, help="MIDI 輸出資料夾")
    p.add_argument("--bpm", type=float, default=120.0, help="起始 BPM 提示")
    p.add_argument("--beats-per-bar", type=int, default=4,
                   choices=[3, 4, 6, 8, 12], help="每小節拍數")
    p.add_argument("--smooth", type=float, default=0.6, help="平滑強度 0.0–1.0")
    p.add_argument("--smooth-window", type=int, default=5, help="平滑視窗")
    p.add_argument("--demucs", action="store_true", help="啟用 Demucs 鼓軌分離")
    p.add_argument("--device", default=None, help="Demucs 裝置：cpu / cuda")
    return p


def run_gui() -> int:
    try:
        import tkinter  # noqa: F401
    except Exception as exc:
        print(f"[錯誤] 找不到 Tkinter：{exc}")
        print("請改用命令列模式：GrooveMap.exe song.wav")
        return 1
    from gui.window import launch
    launch()
    return 0


def run_cli(args) -> int:
    from core.pipeline import Pipeline
    from exporter.midi import export_cubase_bundle

    if not os.path.isfile(args.audio):
        print(f"[錯誤] 找不到檔案：{args.audio}")
        return 2

    opts = dict(
        start_bpm=args.bpm,
        beats_per_bar=args.beats_per_bar,
        smooth_strength=args.smooth,
        smooth_window=args.smooth_window,
        use_demucs=args.demucs,
        device=args.device,
    )

    def progress(frac, msg):
        bar_len = 28
        filled = int(bar_len * frac)
        bar = "█" * filled + "░" * (bar_len - filled)
        sys.stdout.write(f"\r  [{bar}] {frac * 100:5.1f}%  {msg:<28}")
        sys.stdout.flush()

    print("\nGrooveMap — CLI\n")
    pipe = Pipeline(opts)
    result = pipe.run(args.audio, progress=progress)
    print("\n")

    out_dir = args.out or os.path.dirname(os.path.abspath(args.audio))
    base = os.path.splitext(os.path.basename(args.audio))[0]
    files = export_cubase_bundle(result, out_dir, base)

    print("  ── 分析結果 ─────────────────────────────")
    for k, v in result.summary().items():
        print(f"    {k:10s}: {v}")
    print()
    print("  ── 輸出檔案 ─────────────────────────────")
    for k, v in files.items():
        print(f"    {k:8s} → {v}")
    print("\n  Tempo Track：在 Cubase 匯入 *_MasterTrack.smt")
    print("  Click/Marker：匯入 *_Cubase.mid\n")
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.audio:
        return run_cli(args)
    return run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
