# Windows + Cubase real-machine acceptance

This is the single entry point for real-machine acceptance of the V3 CLI
(`groovemap_next`). It assumes you already have, on the target Windows
machine:

1. A real, properly licensed, isolated drum-stem WAV.
2. A trusted `final0.ckpt` Beat This! checkpoint, obtained yourself from the
   official host documented in `beat_this`'s own source
   (`https://cloud.cp.jku.at/public.php/dav/files/7ik4RrBKTS273gp/final0.ckpt`)
   or any other source you have separately verified and licensed. Record its
   SHA-256 before use.
3. Python 3.11+ and (for the Cubase half) Cubase itself.

Nothing in this script downloads, fabricates, or substitutes a model or
audio file. If step 1 or 2 is missing, stop here — the technical gate is
**NOT_RUN_DEVICE**, not PASS.

## Step 1 — one command: build, install, run the real-stem technical gate

PowerShell, run from OUTSIDE the repo checkout:

```powershell
$Repo = "C:\path\to\GrooveMap\groovemap_next"
$Venv = "C:\gm_accept_venv"
$Wav  = "C:\path\to\real_licensed_drums.wav"
$Ckpt = "C:\path\to\trusted_final0.ckpt"
$Out  = "C:\gm_accept_out\song01"

py -3.11 -m venv $Venv
& "$Venv\Scripts\python.exe" -m pip install --no-cache-dir "${Repo}[ai]"
Get-FileHash $Wav -Algorithm SHA256
Get-FileHash $Ckpt -Algorithm SHA256

$env:PYTHONPATH = $null
$env:PYTHONHOME = $null
& "$Venv\Scripts\python.exe" "$Repo\scripts\release_gate.py" `
  --real-stem $Wav --checkpoint $Ckpt --out $Out --device cpu `
  --report-json "$Out.report.json"
```

`--checkpoint $Ckpt` (an absolute local file path) makes `beat_this` load the
trusted file directly via `torch.load`, with no network download attempted.

## Expected result (technical gate only — not Cubase, not listening)

`"$Out.report.json"` should look like this when it genuinely passed real
inference (field order/exact spacing may differ; the `ok` keys are what
matter):

```json
{
  "mode": "real-stem",
  "checks": [
    { "command": "python -m groovemap_next.cli suno --drums ... --checkpoint ...", "ok": true, "returncode": 0 },
    {
      "ok": true,
      "mode": "real-stem-structural",
      "detected_events": "> 0",
      "tempo_points": "> 0",
      "note": "Structural verification only. DAW import, perception, and timing by ear require user machine."
    }
  ],
  "ok": true
}
```

If `beat_source` in `song01_timing.json` is anything other than
`"CPJKU/beat_this:minimal"`, or if either check's `"ok"` is `false`, this is
**not** a PASS — record the actual error instead.

Outputs to keep as evidence: `song01_tempo.mid`, `song01_drums.mid`,
`song01_timing.json`, `song01_drums_humanized.mid`, `song01_groove.json`,
`song01.report.json`, and the SHA-256 of the input WAV and checkpoint.

## Step 2 — Cubase manual acceptance (cannot be automated; requires a human)

1. Import the exact same WAV from Step 1 into a new Cubase project at its
   native start position (note the project sample rate).
2. Import `song01_tempo.mid` and `song01_drums.mid` into the same project.
3. Check the tempo track follows the drummer through the **entire** song,
   explicitly including the final 30-60 seconds (drift accumulates late).
4. Route the channel-10 drum MIDI to a drum instrument; confirm kick/snare/
   hat land on the right instruments; listen for missed/duplicate hits.
5. Import `song01_drums_humanized.mid`; A/B its timing/velocity against the
   quantized version by ear.
6. Save the Cubase project as your evidence artifact, alongside the Cubase
   version and OS used.

A MIDI file parsing without error is not a Cubase PASS. Only a human,
listening, in Cubase, establishes that.
