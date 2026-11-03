# V3 independent audit, minimal repairs and re-verification

Decision: **CODE_AUDIT_PASS + REAL_MODEL_PENDING**. No unhandled P0/P1 was found in the audited V3 CLI and exercised error modes after these repairs. **PRE_DEVICE_RC_READY is not established**: trusted real weights + licensed real drum material have not been run. Real inference is **NOT_RUN / resource-blocked**, not PASS. Cubase and listening are NOT_RUN. This is not publication approval.

## Source and history

- Only branch: `fix/groovemap-v3-preflight-output-safety-20261102`.
- Fetched starting SHA: `eb445802cb56a3472b6e38c7fc8b195672c6eb0a` (matches supplied last observation).
- Final tested executable source: **`50adca3eb7355f5c1f97e1c2a0c610ff3d2c7c90`**.
- Repairs: `db4577250b2aeefe929a8bd1f4342ed546ba0777`, `54a19fa9d6eea30409b90c9edf954b5c42e31ae2`, `69b1caa` (intermediate decoder dependency declaration), `50adca3` (supersedes that declaration with the shared decoder and official Audio2Beats API; final dependency declarations equal the starting version).
- The commit containing this directory is the **evidence commit**, separate from tested executable source; use `git log -1 --format=%H -- groovemap_next/rc_evidence/audit-20261103` to identify it. This commit changes evidence only.
- Original `/workspace/GrooveMap` remains clean at `21f19b123a023d6a6cc974b978a25a5c4cce3db0`. User-authorized isolated worktree: `/workspace/groovemap-v3-audit`. No AGENTS.md was found in the inspected workspace. No main change, Actions, release, merge, GUI/ONNX integration or unrelated refactor.

## Confirmed defects and smallest final repairs

| Finding | Root cause / final repair | Reproduction / regression |
|---|---|---|
| P1: usable AI install could not read a normal WAV | Upstream File2Beats tries torchaudio (now requires missing TorchCodec), then undeclared SoundFile/madmom. Use official **Audio2Beats** with the existing validated `load_wav_mono` instead. DSP and model now receive the same mono samples, sample rate and seconds origin. No new decoder/model dependency remains. | `upstream-audio-read.log` records actual failure; `audio-contract-before.log` fails 2 tests, after log passes 2. Actual upstream log-mel/resampling passes on 16/44.1/48 kHz and on the installed decoder's WAV. These are preprocessing/API checks, **not inference**. |
| P1: overlapping publishers could mix runs or undo another run | Backups and renames lacked mutual exclusion. Atomic directory creation now locks publication per output prefix; conflict fails loudly without touching the owner lock. | Five-case `regression-before.log` includes interleaving failure; `regression-after.log` passes. |
| P1: rollback failure destroyed the last good backup | TemporaryDirectory cleanup discarded backups even when restore failed. Retain staging, recovery manifest and publication lock on recovery failure; continue restoring other paths, then raise an explicit recovery-required error. | `rollback-before.log` fails; `rollback-after.log` passes. Existing write/rename failure tests and injected KeyboardInterrupt restore prior files. `crash-probe.log` verifies retained backups after abrupt exit and operator restoration. |
| P1: source could collide with an output / stale optional path | WAV content was accepted independently of its filename, allowing a source named like an output to be replaced or pruned. Reject resolved source/output collisions before transcription. | Source sentinel collision fails before repair and passes afterward; installed workflow confirms source SHA256 unchanged. |
| P1: malformed PCM could be silently shortened | Decoder rounded down incomplete samples/channel frames. Reject `data` byte lengths not divisible by the validated block alignment. | Three incomplete frame cases fail before repair and pass afterward; audio matrix verifies supported PCM/FLOAT decode and rejects chunk truncation/nonfinite float data. |
| P1: structural Gate could accept corrupted humanized timing/velocity or extra same-tick tempos | Gate checked humanized count only and converted tempo events to a set/subset. Compare full humanized notes/ticks/velocities/channels and ordered complete tempo sequences across tempo, drum and humanized MIDI. | Two mutation regressions fail before repair, pass afterward; original Gate assertions retained. |
| Supported tempo boundary falsely rejected | Absolute timestamp subtraction made exact 400 BPM slightly greater than 400. Snap only numerical boundary noise within relative `1e-12` to 20/400; genuinely unsupported intervals still fail. | `tempo-boundary-before.log` fails at 400 BPM; after log passes. No output consistency threshold was weakened. |

## Executed checks

- Baseline formal offline Gate: compile + **58/58** PASS, return codes 0.
- Final formal offline Gate: compile + **71/71** PASS, no skips/xfails, return codes 0; raw `final-gate.json` and log retained.
- New non-editable Wheel installed into new `/workspace/gm-candidate-venv`; no PYTHONPATH/PYTHONHOME or system-site-packages. Tests and exact Gate script/manifest fixture copied unchanged outside checkout. Installed imports resolve to site-packages. **71/71** installed tests PASS. `pip check` PASS.
- Final Wheel contains 13 Python modules byte-identical to tested source (`wheel-source-match.json`). Candidate base/dev install uses original cached package wheels, not copied site-packages. SHA256 of every dependency wheel matched the original cached TLS-fetched PyPI index (`offline-dependency-provenance.json`).
- Installed console entry script actually executed from `/workspace/gm-artifacts/candidate-run`: real WAV decode + actual DSP + MIDI/JSON/groove export, with **EXPLICIT-STUB-not-real-beat-this** beat source. Full postchecks completed and produced `candidate-installed-report.json`: independent mido integration verifies event seconds, notes, channel 10, velocities and balanced note-offs against both regular/humanized JSON; source hash unchanged. Real `humanize-midi` subprocess succeeds. Real `suno` subprocess without AI fails loudly and preserves all prior outputs.
- Independent mido tests exercise unequal 20..400 BPM intervals, leading silence/downbeat pre-roll, tail extrapolation and a two-hour beat map. MIDI microseconds/quarter-note and integer tick rounding remain format limits; no new timing precision or meter claim is made.
- Installed audio matrix: 30 combinations of mono/stereo, 16/44.1/48 kHz, PCM8/16/24/32 and FLOAT32; NaN/+Inf/-Inf rejected; empty/short/silent audio creates no fabricated DSP events; truncated chunk rejected. Existing tests cover extensible PCM/FLOAT.
- Final Wheel ai extra resolves successfully in the separately isolated AI venv; pip check PASS. Official package versions: beat-this 1.1.0, torch 2.15.0, torchaudio 2.11.1. The real upstream CPU preprocessing executes. **No model was instantiated with untrusted/random weights, and no inference was run.**
- Checkpoint API source: Audio2Beats uses upstream `load_checkpoint`, which first tries local `torch.load` with map_location/device and weights_only, then named/URL download and torch hub cache. A trusted **existing absolute local checkpoint** takes the local path and needs no forced download. This path is source-audited, not a claim of successful real checkpoint loading. Default `final0` URL is `https://cloud.cp.jku.at/public.php/dav/files/7ik4RrBKTS273gp/final0.ckpt`; cache is normally `torch.hub.get_dir()/checkpoints/beat_this-final0.ckpt`. Errors propagate; no production stub/fixed-beat fallback exists.

Harness issues are explicitly recorded in `audit-report.json`: initial copied tests lacked their script namespace / manifest fixture; those were restored and unchanged tests rerun. Initial console-script SystemExit ended the inspection driver before postchecks; missing report detected it, the driver was corrected, and `candidate-validation-complete.log` plus `candidate-installed-report.json` record completion. An API-inspection typo was corrected. None was hidden or treated as a product PASS.

## Original evidence review

Prior `rc_evidence` reports were read, including source `5c2004cce74e2622394083c8326896893ffd6ca9`, 58-test Gate return codes, and claimed Wheel SHA256 `7924dee7c4001e01c2d27fd45fe0f98c288af0c0115e2abf599e56da65bb211b`. There are no executable module/manifest changes between that source and fetched `eb44580`. The original Wheel path `/tmp/claude-0/round3/dist/...` and full historical install logs do not exist in this environment, so their artifact hash / raw installation history cannot independently be reverified here. New source, Wheel, raw logs and independent installation supersede those limitations. The prior installed core workflow explicitly used a stub; ai dependency installation and correct load-failure handling never establish inference PASS.

## Artifacts and resource limits

Candidate `groovemap_next-0.2.0-py3-none-any.whl` is included here (29,141 bytes), SHA256:

`bb745c3ac13506a0704692cf33b4d8f2e5054e7d418ce0ad3da5342d90831e8d`

Raw inputs/outputs, cached dependency wheels and the portable evidence bundle are under `/workspace/gm-delivery` and `/workspace/gm-delivery.tar.gz` in this session. The input is a labeled synthetic fixture, **not a licensed real drum stem and not a model acceptance substitute**. The offline dependency wheelhouse is specific to Linux x86_64 Python 3.12; install normal platform dependencies on Windows/macOS. `SHA256SUMS` in this evidence directory and the delivery directory exclude themselves and are verified. No credentials or model weights are included.

`cloud.cp.jku.at` was rechecked exactly once: CONNECT **403**, curl exit **56** (`host-check.txt`). No mirror/bypass/repeated model request was attempted. No trusted checkpoint or licensed real isolated drum WAV was provided. A temporary automatic approval service usage-limit failure stopped the attempted SoundFile installation; the command did not execute. Final shared-decoder repair removed that requirement. Later allowed fetch succeeded after service availability returned.

## One real acceptance command

Prerequisites: a fresh venv with this exact candidate Wheel `[ai,dev]` installed; a legally usable isolated drum WAV; a trusted official `final0.ckpt` (record its source, license and SHA256, and the WAV SHA256). Use absolute paths. `--checkpoint` below avoids reliance on the blocked download host. Save stdout/stderr and preserve the Gate exit code when capturing logs.

```sh
env -u PYTHONPATH -u PYTHONHOME PYTHONSAFEPATH=1 /absolute/venv/bin/python /absolute/GrooveMap/groovemap_next/scripts/release_gate.py --real-stem "/absolute/licensed/drums.wav" --checkpoint "/absolute/trusted/final0.ckpt" --out "/absolute/exports/song01" --device cpu --report-json "/absolute/exports/real-report.json"
```

`PYTHONSAFEPATH=1` ensures Gate subprocesses resolve the installed Wheel rather than importing checkout source; this import isolation was exercised (`real-gate-import-isolation.log`). Do not use editable install or system-site-packages. The command itself is **NOT_RUN** for real resources here. Retain model/input identity, Gate JSON/log, produced MIDI/JSON and their SHA256 before claiming real inference PASS.

## Publication/recovery limits and remaining manual acceptance

Each normal failure or KeyboardInterrupt rolls back prior outputs; persistent rollback failure leaves a visible recovery-required error, lock and backup manifest. Abrupt termination can expose a partly published set until recovery: fixed filenames are **not a multi-file atomic filesystem transaction**. Never remove a publication lock automatically. Confirm no live owner; preserve the whole staging directory, follow `backup/recovery.json` (destination -> old backup; null means originally absent), restore any remaining old backups/remove originally absent destinations, then remove the lock only after successful recovery. A failed real run is never a success report.

After real technical Gate PASS, only then consider PRE_DEVICE_RC_READY. Minimum target-machine checks: import the exact WAV + tempo/drum MIDI into Cubase with correct pre-roll/origin; verify full-song alignment including first attacks and final minute; route channel 10 and verify GM kick/snare/hat; compare humanized timing/velocity and listen for missed/duplicate hits; save Cubase version, project sample rate and project evidence. No Windows/Cubase/listening claim is made here.

Reusable environment `install_script` and `start_skill` were saved and the offline install repeated successfully. Draft saving is not publication or new-task restoration validation. Review/save in environment settings and publish only when intended; no publication was performed by this task.
