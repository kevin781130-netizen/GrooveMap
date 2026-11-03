"""GrooveMap Next RC gate. Offline tests never download AI checkpoints.

Usage:
    python scripts/release_gate.py --offline
    python scripts/release_gate.py --real-stem /path/drums.wav --out /path/rc/song
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def _run(args: list[str]) -> dict:
    result = subprocess.run(
        [sys.executable, *args], cwd=ROOT, capture_output=True,
        text=True, check=False,
    )
    return {
        "command": "python " + " ".join(args),
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-5000:],
        "stderr_tail": result.stderr[-5000:],
    }


def _event_tick(payload: dict, time_sec: float) -> int:
    beats = [float(x) for x in payload["beats_sec"]]
    origin = int(payload["origin_beat_index"])
    ppq = int(payload["ppq"])
    if len(beats) < 2:
        raise ValueError("fewer than 2 beats")
    t = float(time_sec)
    if t <= beats[0]:
        pos = (t - beats[0]) / (beats[1] - beats[0]) - origin
    elif t >= beats[-1]:
        pos = len(beats) - 1 - origin + (t - beats[-1]) / (beats[-1] - beats[-2])
    else:
        i = bisect_right(beats, t) - 1
        pos = i - origin + (t - beats[i]) / (beats[i + 1] - beats[i])
    return max(0, round(pos * ppq) + int(payload["tick_shift"]))


def _midi_notes(path: Path) -> tuple[object, list[tuple[int, int, int, int]]]:
    import mido

    midi = mido.MidiFile(path)
    notes = []
    for track in midi.tracks:
        absolute = 0
        for message in track:
            absolute += message.time
            if message.type == "note_on" and message.velocity:
                notes.append((absolute, message.note, message.velocity, message.channel))
    return midi, sorted(notes)


def _validate_outputs(prefix: Path, *, humanized: bool) -> dict:
    names = ["_tempo.mid", "_drums.mid", "_timing.json"]
    if humanized:
        names += ["_drums_humanized.mid", "_groove.json"]
    paths = {name: prefix.with_name(prefix.name + name) for name in names}
    missing = [name for name, path in paths.items() if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise ValueError(f"missing/empty outputs: {missing}")
    payload = json.loads(paths["_timing.json"].read_text(encoding="utf-8"))
    if payload.get("schema") != "groovemap-next-timing-v2":
        raise ValueError("unexpected timing JSON schema")
    if len(payload["beats_sec"]) < 2 or not payload["tempo_points"]:
        raise ValueError("no valid tempo map")
    if payload.get("beat_source") != "CPJKU/beat_this:minimal":
        raise ValueError("real-stem gate requires real Beat This! analysis")
    events = payload["drum_events"]
    if not events:
        raise ValueError("real stem contains zero detected drum events")
    tempo, _ = _midi_notes(paths["_tempo.mid"])
    drums, notes = _midi_notes(paths["_drums.mid"])
    if tempo.ticks_per_beat != payload["ppq"] or drums.ticks_per_beat != payload["ppq"]:
        raise ValueError("PPQ mismatch")
    if len(notes) != len(events):
        raise ValueError("MIDI note count does not match JSON drum events")
    expected = sorted([
        (_event_tick(payload, event["time_sec"]), event["note"], event["velocity"], 9)
        for event in events
    ])
    if notes != expected:
        raise ValueError("MIDI event/tick/velocity mismatch vs JSON source times")
    # A file can have the expected number of tempo messages while carrying
    # wrong BPMs or wrong tick positions. Verify exact variable-tempo events.
    import mido

    expected_tempo = [(0, mido.bpm2tempo(float(payload["tempo_points"][0]["bpm"])))]
    expected_tempo += [
        (int(payload["tick_shift"]) + int(point["beat_index"]) * int(payload["ppq"]),
         mido.bpm2tempo(float(point["bpm"])))
        for point in payload["tempo_points"]
        if int(payload["tick_shift"]) + int(point["beat_index"]) * int(payload["ppq"]) >= 0
    ]
    expected_tempo.sort(key=lambda item: item[0])

    def validate_tempo(midi):
        tick = 0
        actual = []
        for msg in mido.merge_tracks(midi.tracks):
            tick += msg.time
            if msg.type == "set_tempo":
                actual.append((tick, msg.tempo))
        if actual != expected_tempo:
            raise ValueError("tempo MIDI tick/BPM mismatch vs JSON tempo points")

    validate_tempo(tempo)
    validate_tempo(drums)
    if humanized:
        groove = json.loads(paths["_groove.json"].read_text(encoding="utf-8"))
        if groove.get("schema") != "groovemap-groove-v1":
            raise ValueError("unexpected groove schema")
        humanized_midi, humanized_notes = _midi_notes(paths["_drums_humanized.mid"])
        if len(humanized_notes) != len(payload["humanized_events"] or []):
            raise ValueError("humanized note count mismatch")
        expected_humanized = sorted([
            (_event_tick(payload, event["time_sec"]), event["note"], event["velocity"], 9)
            for event in payload["humanized_events"]
        ])
        if humanized_notes != expected_humanized:
            raise ValueError("humanized event/tick/velocity mismatch vs JSON source times")
        validate_tempo(humanized_midi)
    return {
        "ok": True,
        "mode": "real-stem-structural",
        "detected_events": len(events),
        "tempo_points": len(payload["tempo_points"]),
        "output_files": [str(path) for path in paths.values()],
        "note": "Structural verification only. DAW import, perception, and timing by ear require user machine.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="GrooveMap Next release preflight")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--offline", action="store_true")
    group.add_argument("--real-stem", type=Path, help="real isolated SUNO drums WAV")
    parser.add_argument("--out", type=Path, help="real stem output prefix")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--checkpoint", default="final0")
    parser.add_argument("--drum-model", type=Path)
    parser.add_argument("--drum-manifest", type=Path)
    parser.add_argument("--report-json", type=Path)
    args = parser.parse_args()

    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "offline" if args.offline else "real-stem",
        "checks": [],
    }
    if args.offline:
        report["checks"].append(_run(["-m", "compileall", "-q", "groovemap_next", "tests", "scripts"]))
        report["checks"].append(_run(["-m", "pytest", "-q", "tests"]))
    else:
        if args.out is None:
            parser.error("--out is required with --real-stem")
        if (args.drum_model is None) != (args.drum_manifest is None):
            parser.error("--drum-model and --drum-manifest must be given together")
        wav = args.real_stem.resolve()
        if not wav.is_file():
            parser.error(f"input WAV not found: {wav}")
        out = args.out.resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "-m", "groovemap_next.cli", "suno",
            "--drums", str(wav), "--out", str(out),
            "--device", args.device, "--checkpoint", args.checkpoint,
            "--humanize-source",
        ]
        if args.drum_model is not None:
            cmd += ["--drum-model", str(args.drum_model.resolve())]
            cmd += ["--drum-manifest", str(args.drum_manifest.resolve())]
        executed = _run(cmd)
        report["checks"].append(executed)
        if executed["ok"]:
            try:
                report["checks"].append(_validate_outputs(out, humanized=True))
            except Exception as exc:
                report["checks"].append({"ok": False, "error": str(exc)})

    report["ok"] = bool(report["checks"]) and all(c["ok"] for c in report["checks"])
    if args.report_json:
        args.report_json.resolve().parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
