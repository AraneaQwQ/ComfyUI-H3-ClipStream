"""Real ffmpeg regression for frame-exact Clip Bin archiving and A/V-safe joining."""

import json
import os
import shutil
import subprocess
import sys
import unittest

import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _support

_support.load_clipbin_package()
cbm = _support.load_clipbin_module("clip_bin_manager")
lb = _support.load_clipbin_module("long_builder")


def _stream_probe(path):
    proc = subprocess.run(
        [
            shutil.which("ffprobe"), "-v", "error", "-count_frames",
            "-show_entries",
            "stream=codec_type,start_time,duration,nb_read_frames",
            "-of", "json", path,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    streams = json.loads(proc.stdout or "{}").get("streams", [])
    return {stream.get("codec_type"): stream for stream in streams}


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                     "needs ffmpeg and ffprobe on PATH")
class TestAvTimingRegression(unittest.TestCase):
    def setUp(self):
        self.tmpdir = _support.make_temp_dir("cs_av_timing")

    def tearDown(self):
        _support.remove_temp_dir(self.tmpdir)

    def _make_clip(self, name, frame_count, level):
        fps = 24
        sample_rate = 32000
        frames = torch.full((frame_count, 16, 32, 3), level, dtype=torch.float32)
        samples = round(frame_count / fps * sample_rate)
        audio = {
            "waveform": torch.zeros(1, 1, samples),
            "sample_rate": sample_rate,
        }
        output = os.path.join(self.tmpdir, name)
        self.assertTrue(cbm.encode_images_to_mp4(
            frames, output, fps=fps, audio_dict=audio))
        return output

    def test_first_auto_strict_shape_joins_to_56_frames_at_zero_based_av(self):
        paths = [
            self._make_clip("shot1.mp4", 22, 0.2),
            self._make_clip("shot2.mp4", 17, 0.5),
            self._make_clip("shot3.mp4", 17, 0.8),
        ]
        output = os.path.join(self.tmpdir, "long.mp4")

        method, _ = lb.concat_videos(
            paths, output, lb.JOIN_COPY, fps=24.0, has_audio=True)
        streams = _stream_probe(output)

        self.assertEqual(method, "video_copy_audio_reencode")
        self.assertEqual(int(streams["video"]["nb_read_frames"]), 56)
        self.assertAlmostEqual(float(streams["video"]["start_time"]), 0.0, delta=0.001)
        self.assertAlmostEqual(float(streams["audio"]["start_time"]), 0.0, delta=0.001)


if __name__ == "__main__":
    unittest.main()
