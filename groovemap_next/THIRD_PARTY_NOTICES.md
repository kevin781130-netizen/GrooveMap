# Third-party provenance and copy policy

This directory is a new MIT-licensed component inside the existing GrooveMap
repository. The repository root currently carries Apache-2.0; this subdirectory
is intentionally isolated and explicitly licensed under MIT.

## Copy / vendoring policy

- **Direct source copying or vendoring is allowed only from MIT-licensed
  projects**, while preserving copyright and license notices.
- Projects under Apache-2.0, BSD, ISC, GPL, CC, or other licenses are **not
  copied into this source tree**. Public papers, documented behavior and file
  formats may be used as clean-room references.
- Runtime dependencies retain their own upstream licenses and are not
  relicensed by GrooveMap.

## Approved MIT references

### Beat This! — CPJKU/beat_this
- Purpose: beat and downbeat inference for variable-tempo audio.
- Upstream code license: MIT.
- Published model weights: MIT according to upstream README.
- Integration here: optional runtime adapter; no upstream source is vendored
  in this first commit.

### Mido — mido/mido
- Purpose: Standard MIDI File writing.
- License: MIT.
- Integration here: runtime dependency.

### Demucs — facebookresearch/demucs
- Purpose: optional stem separation if GrooveMap later accepts a full mix.
- License: MIT.
- Not needed when SUNO stems are already available.

## Clean-room only references

### Google Magenta / GrooVAE
- License: Apache-2.0.
- No Magenta source code is copied here.
- Groove humanization will be implemented from public descriptions and
  independently written algorithms/models if added later.

### DrumScript
- License: Apache-2.0.
- No DrumScript source code is copied here.
- Drum key mapping and pipeline behavior are implemented independently.

## Held for provenance review

### Teraldan/drums-audio-to-midi
The repository advertises MIT, but it describes its network as a Basic Pitch
fork while Spotify Basic Pitch is Apache-2.0. Until provenance of the relevant
model code/weights is reviewed, GrooveMap does not vendor it. The initial drum
transcriber in this directory is an independent DSP implementation.
