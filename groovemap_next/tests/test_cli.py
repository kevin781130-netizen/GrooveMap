from groovemap_next.cli import build_parser


def test_suno_parser_exposes_model_and_humanize_options():
    args = build_parser().parse_args([
        "suno",
        "--drums", "drums.wav",
        "--out", "song",
        "--drum-model", "model.onnx",
        "--drum-manifest", "model.json",
        "--humanize-source",
        "--timing-strength", "0.8",
        "--velocity-strength", "1.1",
    ])
    assert args.command == "suno"
    assert args.drum_model == "model.onnx"
    assert args.drum_manifest == "model.json"
    assert args.humanize_source is True
    assert args.timing_strength == 0.8
    assert args.velocity_strength == 1.1


def test_humanize_midi_parser_defaults_to_external_no_preroll():
    args = build_parser().parse_args([
        "humanize-midi",
        "--midi", "pattern.mid",
        "--timing", "song_timing.json",
        "--groove", "song_groove.json",
        "--out", "pattern_humanized.mid",
    ])
    assert args.command == "humanize-midi"
    assert args.input_has_groovemap_preroll is False


def test_humanize_midi_parser_can_mark_groovemap_preroll():
    args = build_parser().parse_args([
        "humanize-midi",
        "--midi", "groovemap.mid",
        "--timing", "song_timing.json",
        "--groove", "song_groove.json",
        "--out", "humanized.mid",
        "--input-has-groovemap-preroll",
    ])
    assert args.input_has_groovemap_preroll is True
