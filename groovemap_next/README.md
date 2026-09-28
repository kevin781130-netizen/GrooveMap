# GrooveMap Next — SUNO MIDI + Variable Tempo

This is an isolated **MIT-licensed** next-generation core inside the existing
GrooveMap repository.

## Goal

SUNO stems are often not perfectly locked to one BPM. GrooveMap Next therefore
does **not** estimate one global tempo and stretch everything to it.

Pipeline:

```text
SUNO drums.wav
   |
   +--> clean-room drum transient transcription
   |      -> raw DrumEvent(time_sec, note, velocity)
   |
   +--> Beat This! (MIT code + published MIT model weights)
          -> beat[] + downbeat[] in seconds
                |
                v
       exact per-beat tempo map
       BPM[i] = 60 / (beat[i+1] - beat[i])
                |
                +--> *_tempo.mid
                +--> *_drums.mid (tempo track + GM drums)
                +--> *_timing.json
```

The important implementation detail is that drum hits stay in **seconds**
until the beat map is known. Their final MIDI tick position is then computed
inside the variable-tempo grid, so the original SUNO microtiming is preserved.

## Install

Python 3.11+:

```bash
cd groovemap_next
pip install -e ".[ai]"
```

Beat This! downloads/loads its published checkpoint through its normal
upstream mechanism.

## Run

```bash
groovemap-next suno \
  --drums "drums.wav" \
  --out "exports/song01" \
  --device cpu
```

For a CUDA system:

```bash
groovemap-next suno \
  --drums "drums.wav" \
  --out "exports/song01" \
  --device cuda \
  --float16
```

Outputs:

- `song01_tempo.mid` — tempo/time-signature/marker track for DAW import.
- `song01_drums.mid` — the same tempo track plus GM channel-10 drum notes.
- `song01_timing.json` — raw beats, downbeats, BPM per beat, origin, PPQ and
  time-domain drum events for debugging or a future GUI.

## Why "MIDI first, tempo second" is represented this way

The first stage does create the **musical events first**, but it keeps them as
time-domain MIDI-like events in seconds. A Standard MIDI File ultimately needs
ticks, and ticks only become meaningful after the tempo map exists. Serializing
the final .mid therefore happens after beat tracking; this avoids quantizing
the source performance too early.

## Drum transcription status

The included transcriber is an independently written DSP fallback for isolated
drum stems. It currently emits:

- kick -> GM 36
- snare -> GM 38
- closed hi-hat -> GM 42

It handles 16/24/32-bit PCM WAV and derives velocity from transient strength.
This is intentionally conservative and is **not** presented as a replacement
for a trained 20-class drum model.

A future MIT-provenance DrumNet adapter can replace this stage without changing
the tempo-map or MIDI-export layers.

## AD2 / SD3 key mapping

Do not assume one hard-coded vendor map. Supply a semantic JSON profile:

```json
{
  "kick": 36,
  "snare": 38,
  "closed_hat": 42
}
```

Then:

```bash
groovemap-next suno --drums drums.wav --out song --map-json my_sd3_map.json
```

This is the clean-room equivalent of the mapping stage you wanted from
DrumScript, while staying independent of DrumScript's Apache-2.0 source.

## Licensing boundary

See `THIRD_PARTY_NOTICES.md`.

- Beat This!: MIT — approved integration.
- Mido: MIT — approved dependency.
- Magenta / GrooVAE: Apache-2.0 — no source copied; future humanization must be
  clean-room.
- DrumScript: Apache-2.0 — no source copied.
- Teraldan/drums-audio-to-midi: repo says MIT, but its model is described as a
  Basic Pitch fork. It is held out of this branch until provenance is reviewed.

The repository root currently has an Apache-2.0 LICENSE. This directory has its
own explicit MIT LICENSE so it can be reviewed independently before any
repo-wide relicensing decision.

## Next implementation layer

After this SUNO -> MIDI -> tempo core is validated on real stems:

1. replace/augment the 3-class DSP transcriber with an MIT-provenance trained
   drum model;
2. add clean-room groove humanization (microtiming + velocity) for quantized
   input, inspired by public GrooVAE behavior but without copying Magenta code;
3. add reusable AD2/SD3 mapping presets supplied as user-editable profiles;
4. package the Python stack into the existing Windows GrooveMap distribution.
