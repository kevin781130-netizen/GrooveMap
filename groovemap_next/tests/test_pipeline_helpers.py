import pytest

from groovemap_next.pipeline import (
    _clear_optional_outputs,
    _optional_output_paths,
    _validate_strength,
)


def test_clear_optional_outputs_removes_stale_humanize_artifacts(tmp_path):
    prefix = tmp_path / "song"
    humanized, groove = _optional_output_paths(prefix)
    humanized.write_bytes(b"old midi")
    groove.write_text("old groove", encoding="utf-8")

    returned = _clear_optional_outputs(prefix)

    assert returned == (humanized, groove)
    assert not humanized.exists()
    assert not groove.exists()


@pytest.mark.parametrize("value", [0.0, 1.0, 1.5])
def test_pipeline_strength_validation_accepts_recordable_values(value):
    assert _validate_strength(value, "timing_strength") == value


@pytest.mark.parametrize("value", [-0.1, 1.5001, 5.0])
def test_pipeline_strength_validation_rejects_unrecordable_values(value):
    with pytest.raises(ValueError, match="0.0..1.5"):
        _validate_strength(value, "timing_strength")
