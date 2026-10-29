"""MP4 asset encoding streams bounded chunks while preserving the media contract."""

import os
import shutil
import subprocess
import sys
import unittest
from unittest import mock

import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _support

_support.load_clipbin_package()
cbm = _support.load_clipbin_module("clip_bin_manager")

try:
    import av
    HAS_AV = True
except ImportError:
    HAS_AV = False


class _TrackedStdin:
    def __init__(self, stream, writes):
        self.stream = stream
        self.writes = writes

    def write(self, data):
        self.writes.append(len(data))
        return self.stream.write(data)

    def close(self):
        return self.stream.close()


class _FakeProcess:
    def __init__(self, returncode=0, broken_pipe=False):
        self.returncode = returncode
        self.stdin = mock.Mock()
        self.stdin.write.side_effect = BrokenPipeError("closed") if broken_pipe else None
        self.wait_calls = 0
        self.kill_calls = 0

    def wait(self):
        self.wait_calls += 1
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def poll(self):
        return self.returncode

    def kill(self):
        self.kill_calls += 1
        self.returncode = -9


@unittest.skipUnless(shutil.which("ffmpeg") and HAS_AV, "needs PyAV and ffmpeg on PATH")
class TestMp4Encoding(unittest.TestCase):
    def setUp(self):
        self.tmpdir = _support.make_temp_dir("cs_mp4")

    def tearDown(self):
        _support.remove_temp_dir(self.tmpdir)

    def test_video_is_encoded_in_bounded_chunks(self):
        frames = torch.empty(10, 16, 32, 3, dtype=torch.float32)
        for index in range(10):
            frames[index].fill_((index + 1) / 20.0)
        audio = {"waveform": torch.zeros(1, 1, 24000), "sample_rate": 24000}
        output = os.path.join(self.tmpdir, "preview.mp4")
        writes = []
        real_popen = subprocess.Popen

        def tracked_popen(cmd, **kwargs):
            self.assertEqual(kwargs.get("stdout"), subprocess.DEVNULL)
            self.assertEqual(kwargs.get("stderr"), subprocess.DEVNULL)
            proc = real_popen(cmd, **kwargs)
            proc.stdin = _TrackedStdin(proc.stdin, writes)
            return proc

        with mock.patch.object(cbm.subprocess, "Popen", side_effect=tracked_popen):
            self.assertTrue(cbm.encode_images_to_mp4(frames, output, fps=24, audio_dict=audio))

        frame_bytes = 16 * 32 * 3
        self.assertEqual(writes, [8 * frame_bytes, 2 * frame_bytes])
        with av.open(output) as container:
            self.assertEqual(len(container.streams.audio), 1)
            decoded = [frame.to_ndarray(format="rgb24")
                       for frame in container.decode(video=0)]
        self.assertEqual(len(decoded), 10)
        self.assertAlmostEqual(decoded[0].mean() / 255.0, 0.05, delta=0.03)
        self.assertAlmostEqual(decoded[-1].mean() / 255.0, 0.5, delta=0.03)

    def test_video_frame_count_wins_at_the_audio_rounding_boundary(self):
        """A sub-sample A/V rounding difference must never delete the last frame.

        H3's 22 frames at 24fps span 29333.333 samples at 32kHz.  The real
        decoded audio is rounded to an integer sample count; ``-shortest`` used
        to turn the 29333-sample case into a 21-frame MP4.  Bracket that exact
        boundary so a future ffmpeg-command refactor cannot reintroduce it.
        """
        frame_count = 22
        fps = 24
        sample_rate = 32000
        rounded = round(frame_count / fps * sample_rate)
        frames = torch.linspace(0.05, 0.95, frame_count).view(-1, 1, 1, 1)
        frames = frames.expand(-1, 16, 32, 3).contiguous()

        for sample_count in (rounded - 1, rounded, rounded + 1):
            with self.subTest(sample_count=sample_count):
                output = os.path.join(self.tmpdir, "boundary_%s.mp4" % sample_count)
                audio = {
                    "waveform": torch.zeros(1, 1, sample_count),
                    "sample_rate": sample_rate,
                }
                self.assertTrue(cbm.encode_images_to_mp4(
                    frames, output, fps=fps, audio_dict=audio))
                with av.open(output) as container:
                    self.assertEqual(len(container.streams.audio), 1)
                    decoded = list(container.decode(video=0))
                self.assertEqual(len(decoded), frame_count)

    def test_silent_video_keeps_every_input_frame(self):
        frame_count = 22
        frames = torch.zeros(frame_count, 16, 32, 3, dtype=torch.float32)
        output = os.path.join(self.tmpdir, "silent.mp4")

        self.assertTrue(cbm.encode_images_to_mp4(frames, output, fps=24))
        with av.open(output) as container:
            self.assertEqual(len(container.streams.audio), 0)
            decoded = list(container.decode(video=0))
        self.assertEqual(len(decoded), frame_count)

    def test_seventeen_frame_stereo_clip_survives_both_audio_rounding_sides(self):
        frame_count = 17
        fps = 24
        sample_rate = 32000
        exact_samples = frame_count / fps * sample_rate
        frames = torch.full((frame_count, 16, 32, 3), 0.4, dtype=torch.float32)

        for sample_count in (int(exact_samples), int(exact_samples) + 1):
            with self.subTest(sample_count=sample_count):
                output = os.path.join(self.tmpdir, "stereo17_%s.mp4" % sample_count)
                audio = {
                    "waveform": torch.zeros(1, 2, sample_count),
                    "sample_rate": sample_rate,
                }
                self.assertTrue(cbm.encode_images_to_mp4(
                    frames, output, fps=fps, audio_dict=audio))
                with av.open(output) as container:
                    self.assertEqual(len(container.streams.audio), 1)
                    decoded = list(container.decode(video=0))
                self.assertEqual(len(decoded), frame_count)

    def test_fractional_frame_rate_keeps_the_authoritative_frame_count(self):
        frame_count = 22
        fps = 24000 / 1001
        sample_rate = 32000
        sample_count = round(frame_count / fps * sample_rate)
        frames = torch.full((frame_count, 16, 32, 3), 0.6, dtype=torch.float32)
        audio = {
            "waveform": torch.zeros(1, 1, sample_count),
            "sample_rate": sample_rate,
        }
        output = os.path.join(self.tmpdir, "fractional_fps.mp4")

        self.assertTrue(cbm.encode_images_to_mp4(
            frames, output, fps=fps, audio_dict=audio))
        with av.open(output) as container:
            decoded = list(container.decode(video=0))
        self.assertEqual(len(decoded), frame_count)


class TestMp4FailureCleanup(unittest.TestCase):
    def test_nonzero_ffmpeg_exit_is_a_failed_encode(self):
        proc = _FakeProcess(returncode=1)
        with mock.patch.object(cbm.shutil, "which", return_value="ffmpeg"), \
                mock.patch.object(cbm.subprocess, "Popen", return_value=proc):
            self.assertFalse(cbm.encode_images_to_mp4(
                torch.zeros(1, 2, 2, 3), "unused.mp4", fps=24))
        self.assertEqual(proc.wait_calls, 1)
        self.assertEqual(proc.kill_calls, 0)
        proc.stdin.close.assert_called_once_with()

    def test_broken_pipe_kills_and_reaps_a_stuck_process(self):
        proc = _FakeProcess(returncode=None, broken_pipe=True)
        with mock.patch.object(cbm.shutil, "which", return_value="ffmpeg"), \
                mock.patch.object(cbm.subprocess, "Popen", return_value=proc):
            self.assertFalse(cbm.encode_images_to_mp4(
                torch.zeros(1, 2, 2, 3), "unused.mp4", fps=24))
        self.assertEqual(proc.kill_calls, 1)
        self.assertEqual(proc.wait_calls, 1)
        proc.stdin.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
