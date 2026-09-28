"""Command-line entry point for GrooveMap Next."""
from __future__ import annotations
import argparse
from .pipeline import run_suno_drum_pipeline

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="groovemap-next")
    sub = parser.add_subparsers(dest="command", required=True)
    suno = sub.add_parser("suno", help="SUNO drums stem -> drum MIDI + variable tempo map")
    suno.add_argument("--drums", required=True, help="isolated SUNO drums WAV")
    suno.add_argument("--out", required=True, help="output path prefix")
    suno.add_argument("--device", default="cpu", help="Beat This! device, e.g. cpu or cuda")
    suno.add_argument("--checkpoint", default="final0", help="Beat This! checkpoint")
    suno.add_argument("--float16", action="store_true", help="use float16 inference where supported")
    suno.add_argument("--sensitivity", type=float, default=1.0, help="fallback drum detector sensitivity")
    suno.add_argument("--map-json", default=None, help="optional semantic drum keymap JSON")
    suno.add_argument("--ppq", type=int, default=960)
    suno.add_argument("--beats-per-bar", type=int, default=4)
    return parser

def main() -> None:
    args = build_parser().parse_args()
    if args.command == "suno":
        outputs = run_suno_drum_pipeline(
            args.drums, args.out,
            device=args.device,
            checkpoint=args.checkpoint,
            float16=args.float16,
            sensitivity=args.sensitivity,
            mapping_json=args.map_json,
            ppq=args.ppq,
            beats_per_bar=args.beats_per_bar,
        )
        print(f"tempo MIDI : {outputs.tempo_midi}")
        print(f"drum MIDI  : {outputs.drum_midi}")
        print(f"timing JSON: {outputs.timing_json}")

if __name__ == "__main__":
    main()
