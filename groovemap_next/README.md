# GrooveMap Next — SUNO MIDI, Variable Tempo & Groove

This is an isolated **MIT-licensed** next-generation core inside the existing
GrooveMap repository.

## Pipeline

```text
SUNO drums.wav
   |
   +--> drum transcription
   |      |- clean-room DSP fallback (kick/snare/closed-hat)
   |      `- optional licensed ONNX model (20-class contract)
   |
   +--> Beat This! (MIT)
   |      -> beats + downbeats in seconds
   |
   +--> exact variable tempo map
   |      BPM[i] = 60 / (beat[i+1] - beat[i])
   |
   +--> optional clean-room source-groove reconstruction
   |      -> 16th-grid microtiming offsets + velocity template
   |
   +--> semantic key remap
          -> GM / user AD2 / user SD3 map
```

Outputs can include:

- `*_tempo.mid`
- `*_drums.mid`
- `*_drums_humanized.mid`
- `*_timing.json`
- `*_groove.json`

## Install

Core + Beat This!:

```bash
cd groovemap_next
pip install -e ".[ai]"
```

Core + Beat This! + optional ONNX inference:

```bash
pip install -e ".[full]"
```

## Basic SUNO -> MIDI + tempo

```bash
groovemap-next suno \
  --drums "drums.wav" \
  --out "exports/song01" \
  --device cpu
```

## Reconstruct the source groove

```bash
groovemap-next suno \
  --drums "drums.wav" \
  --out "exports/song01" \
  --humanize-source \
  --timing-strength 1.0 \
  --velocity-strength 1.0 \
  --pattern-bars 2
```

This does not add random jitter. GrooveMap first derives the variable tempo
curve, quantizes each detected hit to a 16th-note skeleton, learns the source
performance's offset/velocity pattern, and then reconstructs that feel on the
tempo-aware grid.

Microtiming is stored as a fraction of a subdivision rather than milliseconds,
so the groove follows tempo drift instead of accumulating alignment error.

## Humanize a different drum MIDI skeleton

Once a SUNO performance has produced `*_timing.json` and `*_groove.json`,
the same feel can be transferred to another GM drum MIDI pattern:

```bash
groovemap-next humanize-midi \
  --midi "basic_pattern.mid" \
  --timing "song01_timing.json" \
  --groove "song01_groove.json" \
  --out "basic_pattern_humanized.mid" \
  --timing-strength 1.0 \
  --velocity-strength 1.0
```

This is the clean-room replacement for the "quantized rhythm backbone ->
humanized performance" stage: the score can come from another generator or
from hand-programmed MIDI, while the feel comes from the SUNO performance.

## Optional 20-class ONNX model

No pretrained checkpoint is bundled until the weight file itself has clear
redistribution provenance.

GrooveMap defines a framework-independent ONNX contract in:

`models/manifest-20class.example.json`

The semantic classes are:

kick, snare, sidestick, clap, closed/pedal/open hi-hat, six tom/floor-tom
positions, crash 1/2, ride, china, ride bell, splash, and cowbell.

Usage once you have an appropriately licensed compatible model:

```bash
groovemap-next suno \
  --drums "drums.wav" \
  --out "exports/song01" \
  --drum-model "drumnet.onnx" \
  --drum-manifest "models/my-drumnet.json" \
  --humanize-source
```

ONNX Runtime is optional and MIT licensed.

## AD2 / SD3 mapping

Vendor maps can differ by preset, kit, articulation configuration, and user
MIDI settings. GrooveMap therefore maps by semantic label, not by assuming one
universal vendor note table.

Example:

```json
{
  "kick": 36,
  "snare": 38,
  "closed_hat": 42,
  "open_hat": 46,
  "ride": 51
}
```

Use it with:

```bash
groovemap-next suno --drums drums.wav --out song --map-json my_sd3_map.json
```

## Licensing boundary

See `THIRD_PARTY_NOTICES.md`.

- Beat This!: MIT; approved.
- Mido: MIT; approved.
- ONNX Runtime: MIT; approved optional inference engine.
- Magenta / GrooVAE: Apache-2.0; no source/model copied. GrooveMap's groove
  implementation is independently written from public behavioral descriptions.
- DrumScript: Apache-2.0; no source copied.
- Repositories that say MIT but reference external/private model checkpoints
  are not treated as proof that those weights can be redistributed.

The repository root still carries Apache-2.0. The `groovemap_next/` component
has its own MIT license so the new implementation stays auditable.
