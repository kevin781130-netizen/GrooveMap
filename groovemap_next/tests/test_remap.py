from groovemap_next.models import DrumEvent
from groovemap_next.remap import remap_events

def test_semantic_mapping_changes_note_not_timing_or_velocity():
    source = [DrumEvent(1.25, 38, 91, "snare")]
    mapped = remap_events(source, {"snare": 40})
    assert mapped[0].note == 40
    assert mapped[0].time_sec == 1.25
    assert mapped[0].velocity == 91
