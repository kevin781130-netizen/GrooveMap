"""Command-line entry point for GrooveMap Next."""
from __future__ import annotations
import argparse

from .midi_humanize import humanize_midi_file
from .pipeline import run_suno_drum_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="groovemap-next")
    sub = parser.add_subparsers(dest="command", required=True)

    suno = sub.add_parser(
        "suno",
        help="SUNO drums stem -> drum MIDI + variable tempo + optional groove",
    )
    suno.add_argument("--drums", required=True, help="isolated SUNO drums WAV")
    suno.add_argument("--out", required=True, help="output path prefix")
    suno.add_argument("--device", default="cpu", help="Beat This! device: cpu/cuda")
    suno.add_argument("--checkpoint", default="final0", help="Beat This! checkpoint")
    suno.add_argument("--float16", action="store_true", help="float16 beat inference")
    suno.add_argument(
        "--sensitivity",
        type=float,
        default=1.0,
        help="DSP fallback sensitivity",
    )
    suno.add_argument("--map-json", default=None, help="semantic AD2/SD3 keymap JSON")
    suno.add_argument("--ppq", type=int, default=960)
    suno.add_argument("--beats-per-bar", type=int, default=4)

    model = suno.add_argument_group("optional ONNX drum model")
    model.add_argument("--drum-model", default=None, help="licensed ONNX model path")
    model.add_argument(
        "--drum-manifest",
        default=None,
        help="GrooveMap model manifest JSON",
    )
    model.add_argument("--onnx-threshold", type=float, default=None)

    groove = suno.add_argument_group("clean-room groove reconstruction")
    groove.add_argument(
        "--humanize-source",
        action="store_true",
        help="learn source microtiming/velocity then reapply it to the quantized skeleton",
    )
    groove.add_argument("--timing-strength", type=float, default=1.0)
    groove.add_argument("--velocity-strength", type=float, default=1.0)
    groove.add_argument("--pattern-bars", type=int, default=2)

    hm = sub.add_parser(
        "humanize-midi",
        help="apply a saved GrooveMap groove to an external GM drum MIDI skeleton",
    )
    hm.add_argument("--midi", required=True, help="input drum MIDI skeleton")
    hm.add_argument("--timing", required=True, help="GrooveMap *_timing.json")
    hm.add_argument("--groove", required=True, help="GrooveMap *_groove.json")
    hm.add_argument("--out", required=True, help="output humanized MIDI")
    hm.add_argument("--map-json", default=None, help="optional final AD2/SD3 map")
    hm.add_argument("--timing-strength", type=float, default=1.0)
    hm.add_argument("--velocity-strength", type=float, default=1.0)
    hm.add_argument(
        "--input-has-groovemap-preroll",
        action="store_true",
        help="set only when the input MIDI was previously exported by GrooveMap",
    )

    return parser


def main() -> None:
    args = build_parser().parse_args()

    if args.command == "suno":
        outputs = run_suno_drum_pipeline(
            args.drums,
            args.out,
            device=args.device,
            checkpoint=args.checkpoint,
            float16=args.float16,
            sensitivity=args.sensitivity,
            mapping_json=args.map_json,
            ppq=args.ppq,
            beats_per_bar=args.beats_per_bar,
            drum_model=args.drum_model,
            drum_manifest=args.drum_manifest,
            onnx_threshold=args.onnx_threshold,
            humanize_source=args.humanize_source,
            timing_strength=args.timing_strength,
            velocity_strength=args.velocity_strength,
            pattern_bars=args.pattern_bars,
        )
        print(f"tempo MIDI     : {outputs.tempo_midi}")
        print(f"drum MIDI      : {outputs.drum_midi}")
        print(f"timing JSON    : {outputs.timing_json}")
        if outputs.humanized_midi is not None:
            print(f"humanized MIDI : {outputs.humanized_midi}")
        if outputs.groove_json is not None:
            print(f"groove template: {outputs.groove_json}")
        return

    if args.command == "humanize-midi":
        output = humanize_midi_file(
            args.midi,
            args.timing,
            args.groove,
            args.out,
            timing_strength=args.timing_strength,
            velocity_strength=args.velocity_strength,
            mapping_json=args.map_json,
            input_has_groovemap_preroll=args.input_has_groovemap_preroll,
        )
        print(f"humanized MIDI : {output}")
        return

    raise RuntimeError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    main()
