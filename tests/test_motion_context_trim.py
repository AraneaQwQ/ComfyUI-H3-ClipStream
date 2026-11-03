import os
import sys
import unittest

import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _support

PKG, PKG_ERROR = _support.load_plugin_package()
SKIP = "the plugin needs a ComfyUI install on sys.path: %s" % PKG_ERROR


def _module(dotted):
    obj = PKG
    for part in dotted.split("."):
        obj = getattr(obj, part)
    return obj


@unittest.skipIf(PKG is None, SKIP)
class TestMotionContextTrimFramesCap(unittest.TestCase):
    def setUp(self):
        self.node = _module("motion_context.nodes").MiniMaxH3MotionContextTrim
        self.images = torch.arange(10).reshape(10, 1, 1, 1)

    def test_cap_limits_video_and_audio_before_head_trim(self):
        waveform = torch.arange(20000).reshape(1, 1, -1)
        out = self.node.execute(
            self.images,
            2,
            audio={"waveform": waveform, "sample_rate": 24000},
            fps=24.0,
            match_tail=True,
            frames_cap=8,
        )
        self.assertTrue(torch.equal(out.args[0], self.images[2:8]))
        self.assertEqual(out.args[0].shape[0], 6)
        self.assertEqual(out.args[1]["waveform"].shape[-1], 6000)
        self.assertTrue(torch.equal(
            out.args[1]["waveform"],
            waveform[..., 2000:8000],
        ))

    def test_zero_and_large_cap_keep_legacy_behavior(self):
        for cap in (0, 20):
            with self.subTest(cap=cap):
                out = self.node.execute(self.images, 2, frames_cap=cap)
                self.assertTrue(torch.equal(out.args[0], self.images[2:]))

    def test_cap_must_leave_a_frame_after_head_trim(self):
        with self.assertRaisesRegex(ValueError, "asked to trim 5 frames from a 5 frame clip"):
            self.node.execute(self.images, 5, frames_cap=5)


if __name__ == "__main__":
    unittest.main()
