# GrooveMap Next — RC acceptance gate (2026-11-02)

## Decision and scope

This is **V3 SUNO drums WAV → variable tempo MIDI + drum MIDI + optional
source groove**, with a command-line entry point. It is **not** a claim that
the existing V1 Windows Tkinter GUI / PyInstaller executable has integrated
V3. V1 GUI work lives in PR #1 on a separate branch; V2 and V3 are stacked
PRs #2 / #3, and the release-safety hardening is PR #4.

To minimize time to real-machine validation, freeze the *testable core*
scope at the V3 CLI:

- Real isolated SUNO drum PCM WAV input.
- Beat This! variable-tempo estimation.
- Three-class offline clean-room DSP fallback: kick, snare, closed hi-hat.
- Export `*_tempo.mid`, `*_drums.mid`, `*_timing.json`.
- Optional source-groove `*_drums_humanized.mid` and `*_groove.json`.
- Cubase import via MIDI.
- Optional 20-class inference **requires a separately licensed and compatible
  ONNX model**. **Not in baseline V3 RC.**

No checkpoint or licensed third-party model is embedded in this repository.

## Offline preflight — no hardware, no AI model, no GitHub Actions

Use a clean Python >=3.11 environment and install dependencies.

macOS / Linux:

```sh
cd groovemap_next
python3 -m pip install -e ".[dev]"
python3 scripts/release_gate.py --offline --report-json offline-release-report.json
```

Windows PowerShell:

```powershell
cd groovemap_next
py -3 -m pip install -e ".[dev]"
py -3 scripts/release_gate.py --offline --report-json offline-release-report.json
```

PASS requires both source compilation and all bundled pytest cases to return
0. Any failure or missing dependency is **BLOCKED**. Results must be observed
on a real runner; committed test source alone does not establish PASS.

## Real-machine structural acceptance

Install optional Beat This! dependency (model download/cache availability
may require internet):

```sh
python -m pip install -e ".[ai,dev]"
python scripts/release_gate.py --real-stem "/absolute/path/drums.wav" --out "/absolute/path/exports/song01" --device cpu --report-json machine-report.json
```

The real-stem gate executes actual Beat This! inference and clean-room drum
transcription. It checks output existence, nonempty drum detection, all MIDI
note times/velocities against source event seconds, PPQ, variable tempo events,
and groove JSON. No source events are silently fabricated. A successful
structural gate does **not** prove musical quality or Cubase correctness.

## Cubase real-machine user acceptance (manual)

1. Import the exact test WAV into Cubase, preserving its starting position;
   import `song01_tempo.mid` and `song01_drums.mid` into the same project.
2. Verify tempo changes and downbeat origin/pre-roll; align against the WAV
   throughout, **including the final minute** for longer stems.
3. Route channel-10 drum MIDI to a drum instrument; confirm kick/snare/hat
   mapping and listen for missed/duplicate hits.
4. Import `song01_drums_humanized.mid` and compare its timing and velocity
   against the unhumanized file. Save a project as evidence.
5. On Windows, package and launch the *separate V1 GUI* from PR #1 only
   if GUI compatibility is part of the release; V3 is not yet inside that EXE.

Record OS, Python, Beat This! version/checkpoint, stem source details,
project sample rate, report JSON, and Cubase version.

## Release truth table

| Gate | Status as of 2026-11-02 |
|---|---|
| V3 functionality present in PR #3 | **Source verified** |
| Failure-safe export patch in PR #4 | **Committed; unexecuted** |
| Local full pytest / syntax compile | **NOT RUN in assistant environment** |
| Real SUNO stem inference + model startup | **NOT RUN** |
| DAW import, drift and listening | **NOT RUN** |
| Windows V1 GUI EXE integration with V3 | **NOT IMPLEMENTED** |
| Licensed ONNX 20-class weights | **NOT PROVIDED (optional)** |
| Release/milestone tag and main merge | **NOT PERFORMED** |

**Meaning of 'only real-machine testing left':** it can only be said for the
*V3 CLI* after offline preflight has actually passed. The unified Windows GUI
is a separate, currently incomplete packaging/integration scope.

Do not merge PR #4 or tag a release based only on the presence of this checklist.
