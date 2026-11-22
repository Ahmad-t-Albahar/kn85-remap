"""Compare generated reports with the vendor app's captured traffic.

Run: python -m unittest discover -s tests   (from the kn85-remap folder)
"""

import io
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import kn85_protocol as p  # noqa: E402
import remap_store  # noqa: E402

# Frida capture of the vendor app writing both layers (shipped in tests/data).
TRACE = os.path.join(HERE, "data", "trace-fnlayer-app.log")
# The vendor's layout file is not redistributed. To run that test, set
# KN85_LAYOUT_XML to the path of rgb-keyboard.xml from the vendor driver.
LAYOUT = os.environ.get("KN85_LAYOUT_XML") or os.path.join(
    os.path.dirname(ROOT), "black-extracted", "app", "layouts", "rgb-keyboard.xml")


def trace_events():
    """List of ('SET', bytes) and ('ACK', bytes) in order, from the trace."""
    events = []
    with open(TRACE, encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if len(parts) > 3 and parts[1] == "HidD_SetFeature" and parts[2] == "mi_02":
                events.append(("SET", bytes(int(x, 16) for x in parts[3:])))
            elif len(parts) > 4 and parts[1] == "IOCTL-OUT" and parts[3] == "mi_02":
                events.append(("ACK", bytes(int(x, 16) for x in parts[4:])))
    return events


def sequences(events):
    """Split at each 04 18 begin command."""
    seqs = []
    for kind, data in events:
        if kind == "SET" and data[1:3] == b"\x04\x18":
            seqs.append([])
        seqs[-1].append((kind, data))
    return seqs


def generated(layer, remaps):
    t = p.DryRunTransport(out=io.StringIO())
    p.write_layer(t, layer, remaps)
    return t.sent


@unittest.skipUnless(os.path.exists(TRACE), "vendor trace not present")
class TraceMatch(unittest.TestCase):
    def setUp(self):
        self.seqs = sequences(trace_events())
        self.assertEqual(len(self.seqs), 3)

    def sets(self, seq):
        return [d for k, d in seq if k == "SET"]

    def acks(self, seq):
        return [d for k, d in seq if k == "ACK"]

    def test_top_layer_empty_matches_trace(self):
        self.assertEqual(generated(p.LAYER_TOP, {}), self.sets(self.seqs[0]))

    def test_fn_layer_empty_matches_trace(self):
        self.assertEqual(generated(p.LAYER_FN, {}), self.sets(self.seqs[1]))

    def test_fn_right_ctrl_applications_matches_trace(self):
        self.assertEqual(generated(p.LAYER_FN, {98: 0x65}), self.sets(self.seqs[2]))

    def test_checksum_matches_trace_acks(self):
        for seq, remaps in ((self.seqs[0], {}), (self.seqs[1], {}), (self.seqs[2], {98: 0x65})):
            finish = [a for a in self.acks(seq) if a[1:3] == b"\x04\x02"][0]
            self.assertEqual(finish[5] | finish[6] << 8, p.expected_checksum(remaps))

    def test_dry_run_acks_match_trace(self):
        t = p.DryRunTransport(out=io.StringIO())
        acks = []
        orig = t.get_feature
        t.get_feature = lambda r: acks.append(orig(r)) or acks[-1]
        p.write_layer(t, p.LAYER_FN, {98: 0x65})
        self.assertEqual(acks, self.acks(self.seqs[2]))


class Reports(unittest.TestCase):
    def test_every_physical_key_has_a_name(self):
        for idx, name in p.remappable_keys():
            self.assertFalse(name.startswith("Key "), idx)

    def test_report_lengths(self):
        for r in generated(p.LAYER_FN, {98: 0x65, 1: 0x04}):
            self.assertEqual(len(r), 65)
            self.assertEqual(r[0], 0)

    def test_fn_key_cannot_be_remapped(self):
        with self.assertRaises(ValueError):
            p.layer_data({96: 0x04})

    def test_unknown_usage_rejected(self):
        with self.assertRaises(ValueError):
            p.layer_data({1: 0xAF})

    def test_bad_checksum_raises(self):
        t = p.DryRunTransport(out=io.StringIO())
        orig = t.get_feature

        def bad(r):
            a = bytearray(orig(r))
            if r[1:3] == b"\x04\x02":
                a[5] ^= 1
            return bytes(a)
        t.get_feature = bad
        with self.assertRaises(p.ProtocolError):
            p.write_layer(t, p.LAYER_TOP, {})

    def test_nack_raises(self):
        t = p.DryRunTransport(out=io.StringIO())
        t.get_feature = lambda r: bytes(65)
        with self.assertRaises(p.ProtocolError):
            p.write_layer(t, p.LAYER_TOP, {})

    def test_late_ack_is_read_again_not_resent(self):
        t = p.DryRunTransport(out=io.StringIO())
        orig = t.get_feature
        calls = {"n": 0}
        def late(r):
            calls["n"] += 1
            return bytes(65) if calls["n"] == 1 else orig(r)
        t.get_feature = late
        p.write_layer(t, p.LAYER_TOP, {})
        self.assertEqual(sum(1 for r in t.sent if r[1:3] == b""), 1)

    def test_write_all_order(self):
        t = p.DryRunTransport(out=io.StringIO())
        p.write_all(t, {p.LAYER_TOP: {}, p.LAYER_FN: {98: 0x65}})
        cmds = [r[2] for r in t.sent if r[1] == 0x04]
        self.assertEqual(cmds, [0x18, 0x11, 0x02, 0xF0, 0x18, 0x27, 0x02, 0xF0])


@unittest.skipUnless(os.path.exists(LAYOUT), "vendor layout not present")
class LayoutMatch(unittest.TestCase):
    def test_key_table_matches_layout_xml(self):
        root = ET.parse(LAYOUT).getroot()
        keys = [(int(k.get("key_index")), int(k.get("code"), 16)) for k in root.iter("key")]
        self.assertEqual(keys, p.PHYSICAL_KEYS)


class Store(unittest.TestCase):
    def test_seed_when_missing(self):
        with tempfile.TemporaryDirectory() as d:
            rec = remap_store.load(os.path.join(d, "x.json"))
            self.assertEqual(rec[p.LAYER_FN], {98: 0x65})
            self.assertEqual(rec[p.LAYER_TOP], {})

    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.json")
            rec = {p.LAYER_TOP: {55: 0x29}, p.LAYER_FN: {98: 0x65}}
            remap_store.save(path, rec)
            self.assertEqual(remap_store.load(path), rec)

    def test_malformed_files_raise_valueerror(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.json")
            for content in ("[1, 2", "[]", '{"remaps": [{"key_index": 1}]}',
                            '{"remaps": [{"layer": "fn", "key_index": 98, "usage": null}]}',
                            '{"remaps": 5}'):
                with open(path, "w") as f:
                    f.write(content)
                with self.assertRaises(ValueError, msg=content):
                    remap_store.load(path)

    def test_describe(self):
        self.assertEqual(remap_store.describe(p.LAYER_FN, 98, 0x65),
                         "Fn layer: Right Ctrl sends Applications (context menu)")


if __name__ == "__main__":
    unittest.main()
