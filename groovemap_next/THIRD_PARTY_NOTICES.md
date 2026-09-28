# Third-party provenance and copy policy

This directory is a new MIT-licensed component inside the existing GrooveMap
repository. The repository root currently carries Apache-2.0; this subdirectory
is intentionally isolated and explicitly licensed under MIT.

## Copy / vendoring policy

- Direct source copying or vendoring is allowed only from MIT-licensed projects,
  while preserving required notices.
- Projects under Apache-2.0, BSD, ISC, GPL, CC, or other licenses are not copied
  into this source tree. Public papers, documented behavior, standards and file
  formats may be used as clean-room references.
- A source-code license is not assumed to cover separately hosted, private, or
  otherwise unlicensed model checkpoint files.
- Runtime dependencies retain their own upstream licenses and are not
  relicensed by GrooveMap.

## Approved MIT references / engines

### Beat This! — CPJKU/beat_this
- Purpose: beat and downbeat inference for variable-tempo audio.
- Upstream code license: MIT.
- Published model weights: MIT according to upstream documentation.
- Integration: optional runtime dependency, minimal postprocessing path.

### Mido — mido/mido
- Purpose: Standard MIDI File writing.
- License: MIT.

### ONNX Runtime — microsoft/onnxruntime
- Purpose: optional framework-independent drum-model inference.
- License: MIT.
- GrooveMap does not bundle an ONNX drum checkpoint merely because its runtime
  is MIT; the checkpoint needs its own clear provenance.

### Demucs — facebookresearch/demucs
- Purpose: possible future source separation for full mixes.
- License: MIT.
- Not needed when SUNO stems are already available.

## Clean-room references

### Google Magenta / GrooVAE
- License: Apache-2.0.
- No Magenta source, checkpoints or model implementation is copied here.
- Publicly documented behavior describes humanization as reconstructing
  velocity and microtiming from a quantized drum pattern.
- GrooveMap implements a different statistical source-groove template algorithm
  from scratch.

### DrumScript
- License: Apache-2.0.
- No DrumScript source code is copied.
- Semantic key remapping is independently implemented.

## Held / rejected for bundled weights

### Teraldan/drums-audio-to-midi
The repository advertises MIT, but describes its network as a Basic Pitch fork.
Spotify Basic Pitch is Apache-2.0. No source/model from this project is bundled
without a more complete provenance review.

### mcfredrick/drum-transcription-api
The repository source is MIT and documents multi-class drum transcription, but
its README/configuration refers to checkpoints on the author's local filesystem
rather than distributing those weight files in the repository. GrooveMap does
not treat those private checkpoint references as redistributable MIT weights.

### ADTOF wrappers
MIT-licensed wrappers around ADTOF do not make the underlying ADTOF model/code
MIT. They are not vendored into GrooveMap.
