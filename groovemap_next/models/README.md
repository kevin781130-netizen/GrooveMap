# GrooveMap drum model contract

GrooveMap v3 deliberately does **not** bundle a pretrained drum checkpoint
unless the weight file itself has a clear redistribution license.

## Expected ONNX contract

A model is paired with a JSON manifest. See `manifest-20class.example.json`.

The reference contract accepts mono float32 audio and returns frame-wise onset
probabilities, plus an optional velocity tensor. Both tensors use the same
20-class semantic order defined by the manifest.

Supported input layouts:

- `B,T`
- `B,C,T`

Supported output layouts:

- `B,T,C`
- `B,C,T`

This keeps GrooveMap independent from any specific training framework.

## Why no downloaded checkpoint is committed

A repository's source license does not automatically prove that a separately
stored or privately referenced checkpoint can be redistributed. GrooveMap
therefore requires explicit weight provenance before bundling a model.

ONNX Runtime is used only as an optional inference engine and is MIT licensed.
