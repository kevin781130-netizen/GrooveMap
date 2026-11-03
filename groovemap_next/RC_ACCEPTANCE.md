# GrooveMap Next — RC acceptance gate (2026-11-02)

## Decision and scope

This is **V3 SUNO drums WAV → variable tempo MIDI + drum MIDI + optional
source groove**, with a command-line entry point. It is **not** a claim that
the existing V1 Windows Tkinter GUI / PyInstaller executable has integrated
V3. V1 GUI work lives in PR #1 on a separate branch; V2 and V3 are stacked
PRs #2 / #3, and the release-safety hardening is PR #4.

To minimize time to real-machine validation, freeze the *testable core*
scope at the V3 CLI:

- Real isolated SUNO drum WAV input: 8/16/24/32-bit integer PCM or 32-bit IEEE float (ordinary RIFF and WAVE_FORMAT_EXTENSIBLE). Other formats are explicit errors.
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


## Verified offline acceptance evidence

The original source (13 module files), all original 12 pytest files, and
relevant project metadata were restored byte-for-byte in a Linux Python 3.13
runner. All 30 files matched their GitHub Git blob SHA values at source commit
`dcaad6faa24a40cdbebe0b2dc718c98e4969946e`. Full repository-local
`python scripts/release_gate.py --offline` result: compile PASS, 58/58 pytest
PASS. A pure-Python wheel was built, installed into a separate Python
virtual environment, and its CLI entry points executed. The wheel's 13 Python
modules match the source exactly. Parent environment NumPy/Mido were reused
for the CLI smoke because network egress is restricted. See
`RC_OFFLINE_EVIDENCE_20261102.json` for checksums and limitations.

This establishes **offline pre-machine readiness for the V3 Python CLI** only,
not final product release approval. It does not prove genuine Beat This! model
inference, real SUNO/Cubase musical correctness, Windows installation, or V1 GUI
integration. None of those are included in the 58/58 result.

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
| Failure-safe export patch in PR #4 | **58/58 offline pytest PASS** on Git-blob-identical source |
| Local full pytest / syntax compile | **PASS** — all 12 original test files, 13 original core modules; 30 source files verified byte-for-byte against GitHub |
| Python CLI wheel build + install + CLI help | **PASS** — `groovemap_next-0.2.0-py3-none-any.whl`, SHA-256 recorded in evidence |
| Real SUNO stem inference + model startup | **NOT RUN** |
| DAW import, drift and listening | **NOT RUN** |
| Windows V1 GUI EXE integration with V3 | **NOT IMPLEMENTED** |
| Licensed ONNX 20-class weights | **NOT PROVIDED (optional)** |
| Release/milestone tag and main merge | **NOT PERFORMED** |

**Meaning of 'only real-machine testing left':** For the **V3 Python CLI
baseline**, offline preflight and pure-Python wheel packaging are now verified.
The remaining acceptance is real model/stem operation and DAW/OS behavior.
The unified Windows GUI remains a separate incomplete integration scope.

Do not merge PR #4 or tag a release based only on the presence of this checklist.

## 2026-11-03 independent re-verification (closes the PYTHONPATH gap)

The 2026-11-02 evidence above reused host NumPy/Mido via PYTHONPATH for the
wheel CLI smoke, which is not a genuinely independent install, and recorded
no attempt at real Beat This! checkpoint inference. Both were re-run.

**Independent wheel install — PASS.** Built the wheel from source at
`5c2004cce74e2622394083c8326896893ffd6ca9` and installed it into a brand-new
venv with no editable install, no `PYTHONPATH`, no `PYTHONHOME`, and
`include-system-site-packages = false`. `pip freeze` resolves only the
declared deps (numpy 2.5.4, mido 1.3.3) from the wheel's own metadata;
`pip check` reports no broken requirements. CLI help and the full
installed-wheel core workflow (WAV decode -> DSP transcription -> tempo/drum
MIDI -> timing JSON -> humanize/groove JSON) were run from a directory
outside the checkout; source WAV SHA-256 was confirmed unchanged. The core
workflow run used an **explicit, clearly labeled stub** beat tracker
(`source: "EXPLICIT-STUB-not-real-beat-this"`) to exercise the installed
package's mechanics — this is NOT claimed as real-model evidence.

**Real Beat This! inference — still BLOCKED, now with a precise, reproduced
reason.** The `ai` extra (`beat-this==1.1.0`, `torch==2.15.0`,
`torchaudio==2.11.1`) installs cleanly into the same independent venv — the
dependency itself is not the blocker. `beat_this` 1.1.0's own
`inference.py` resolves checkpoint name `final0` to
`https://cloud.cp.jku.at/public.php/dav/files/7ik4RrBKTS273gp/final0.ckpt`
— the CPJKU paper authors' own hosting, not a third-party mirror. In this
sandbox, that host is denied at the network-policy layer (`cloud.cp.jku.at:443`
-> HTTP 403 on CONNECT; proxy logs `connect_rejected`), reproduced both via
direct `curl` and via `groovemap_next.beat_tracker.BeatThisTracker`, which
correctly raises `ValueError` instead of silently falling back or fabricating
a result. No retry, no alternate/unofficial mirror, and no synthetic
substitute was used in place of real inference. Separately — independent of
that network block — no real, licensed, isolated drum-stem WAV exists in
this sandbox.

Full machine-readable evidence: `rc_evidence/RC_INDEPENDENT_VERIFICATION_20261103.json`,
`rc_evidence/offline-release-report-20261103.json`,
`rc_evidence/core-workflow-structural-report-20261103.json`,
`rc_evidence/wheel-SHA256-20261103.txt`.

**Resume command once a real licensed drum WAV and a network path to
`cloud.cp.jku.at` are both available** (run on a machine with both, not
this sandbox):

```sh
cd groovemap_next
python -m pip install -e ".[ai,dev]"
python scripts/release_gate.py --real-stem "/absolute/path/real_drums.wav" \
  --out "/absolute/path/exports/song01" --device cpu \
  --report-json machine-report.json
```

This remains **BLOCKED**, not PRE_DEVICE_RC_READY: per the acceptance
criteria, the real-material/real-model technical workflow must itself pass,
and it has not — for environment/resource reasons documented above, not a
code defect. No source code changes were required or made in this pass.
