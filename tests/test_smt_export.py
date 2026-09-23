"""exporter/steinberg_smt.py 單元測試（規格 P1）。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exporter.steinberg_smt import (
    SMT_PPQ,
    TempoEvent,
    build_master_track_xml,
    export_master_track,
)


class TestBuildMasterTrackXml(unittest.TestCase):
    def test_empty_events_raises(self):
        with self.assertRaises(ValueError):
            build_master_track_xml([])

    def test_valid_xml_structure(self):
        xml_str = build_master_track_xml(
            [{"time": 0.0, "bpm": 120.0}, {"time": 1.95, "bpm": 121.0}]
        )
        root = ET.fromstring(xml_str)
        self.assertEqual(root.tag, "MasterTrack")

        roots = root.find("rootObjects").findall("root")
        self.assertEqual(len(roots), 2)
        names = {r.get("name") for r in roots}
        self.assertEqual(names, {"Tempo Track", "Signature Track"})

        # rootObjects 的 ID 必須對應到下面 obj 的 ID
        root_ids = {r.get("name"): r.get("ID") for r in roots}
        objs = root.findall("obj")
        obj_ids = {o.get("class"): o.get("ID") for o in objs}
        self.assertEqual(root_ids["Tempo Track"], obj_ids["MTempoTrackEvent"])
        self.assertEqual(root_ids["Signature Track"], obj_ids["MSignatureTrackEvent"])

    def test_first_tempo_event_at_tick_zero(self):
        xml_str = build_master_track_xml(
            [{"time": 0.0, "bpm": 120.0}, {"time": 1.0, "bpm": 120.0}]
        )
        root = ET.fromstring(xml_str)
        tempo_obj = root.find('obj[@class="MTempoTrackEvent"]')
        events = tempo_obj.find('list[@name="TempoEvent"]').findall("obj")
        self.assertEqual(len(events), 2)

        first_ppq = float(events[0].find('float[@name="PPQ"]').get("value"))
        self.assertAlmostEqual(first_ppq, 0.0)

        first_bpm = float(events[0].find('float[@name="BPM"]').get("value"))
        self.assertAlmostEqual(first_bpm, 120.0)

    def test_tick_accumulation_matches_tempo(self):
        # 120 BPM 持續 1 秒 = 2 拍 = 2 * SMT_PPQ ticks
        xml_str = build_master_track_xml(
            [{"time": 0.0, "bpm": 120.0}, {"time": 1.0, "bpm": 120.0}]
        )
        root = ET.fromstring(xml_str)
        events = root.find('obj[@class="MTempoTrackEvent"]').find(
            'list[@name="TempoEvent"]'
        ).findall("obj")
        second_ppq = float(events[1].find('float[@name="PPQ"]').get("value"))
        self.assertAlmostEqual(second_ppq, 2 * SMT_PPQ)

    def test_ramp_flag_emits_func_element(self):
        xml_str = build_master_track_xml(
            [
                {"time": 0.0, "bpm": 120.0},
                {"time": 1.0, "bpm": 90.0, "ramp": True},
                {"time": 1.5, "bpm": 120.0},
            ]
        )
        root = ET.fromstring(xml_str)
        events = root.find('obj[@class="MTempoTrackEvent"]').find(
            'list[@name="TempoEvent"]'
        ).findall("obj")

        self.assertIsNone(events[0].find('int[@name="Func"]'))
        func_el = events[1].find('int[@name="Func"]')
        self.assertIsNotNone(func_el)
        self.assertEqual(func_el.get("value"), "1")
        self.assertIsNone(events[2].find('int[@name="Func"]'))

    def test_accepts_tempo_event_dataclass(self):
        events = [TempoEvent(time=0.0, bpm=100.0), TempoEvent(time=2.0, bpm=105.0)]
        xml_str = build_master_track_xml(events)
        root = ET.fromstring(xml_str)
        tempo_events = root.find('obj[@class="MTempoTrackEvent"]').find(
            'list[@name="TempoEvent"]'
        ).findall("obj")
        self.assertEqual(len(tempo_events), 2)

    def test_unsorted_input_is_sorted_by_time(self):
        xml_str = build_master_track_xml(
            [{"time": 2.0, "bpm": 130.0}, {"time": 0.0, "bpm": 120.0}]
        )
        root = ET.fromstring(xml_str)
        events = root.find('obj[@class="MTempoTrackEvent"]').find(
            'list[@name="TempoEvent"]'
        ).findall("obj")
        first_bpm = float(events[0].find('float[@name="BPM"]').get("value"))
        self.assertAlmostEqual(first_bpm, 120.0)

    def test_time_signature_event(self):
        xml_str = build_master_track_xml(
            [{"time": 0.0, "bpm": 120.0}], beats_per_bar=3, denominator=4
        )
        root = ET.fromstring(xml_str)
        sig_obj = root.find('obj[@class="MSignatureTrackEvent"]')
        sig_events = sig_obj.find('list[@name="SignatureEvent"]').findall("obj")
        self.assertEqual(len(sig_events), 1)
        num = int(sig_events[0].find('int[@name="Numerator"]').get("value"))
        den = int(sig_events[0].find('int[@name="Denominator"]').get("value"))
        self.assertEqual(num, 3)
        self.assertEqual(den, 4)

    def test_object_ids_are_unique(self):
        xml_str = build_master_track_xml(
            [{"time": 0.0, "bpm": 120.0}, {"time": 1.0, "bpm": 121.0},
             {"time": 2.0, "bpm": 119.0}]
        )
        # <root> 元素的 ID 故意與對應 <obj> 重複（內部參照），只檢查 <obj> 本身要唯一
        root = ET.fromstring(xml_str)
        obj_ids = [el.get("ID") for el in root.iter("obj")]
        self.assertEqual(len(obj_ids), len(set(obj_ids)))


class TestExportMasterTrack(unittest.TestCase):
    def test_writes_utf8_file(self):
        with tempfile.TemporaryDirectory() as d:
            out_path = os.path.join(d, "sub", "Song_MasterTrack.smt")
            result_path = export_master_track(
                [{"time": 0.0, "bpm": 120.0}], out_path
            )
            self.assertEqual(result_path, out_path)
            self.assertTrue(os.path.isfile(out_path))
            with open(out_path, encoding="utf-8") as f:
                content = f.read()
            self.assertTrue(content.startswith('<?xml version="1.0" encoding="utf-8"?>'))
            ET.fromstring(content)  # 必須可被解析


if __name__ == "__main__":
    unittest.main()
