"""Frame-grid maths: the H3 temporal cycle and the run-length snap-down.

These numbers decide how many frames a chain hands over and how much of a
render the pinned head costs, so a silent change here shows up as a seam in
every clip. Locked against the current implementation.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _support

shared = _support.load_standalone(os.path.join("clipbin", "_shared.py"), "clipbin_shared")
mc, MC_ERROR = _support.try_import("motion_context.nodes")


class TestPixelLatentCycle(unittest.TestCase):
    def test_step_spans_are_the_documented_cycle(self):
        self.assertEqual(shared.FRAME_PER_TOKEN, (1, 4, 4, 4, 4))
        self.assertEqual(shared.latent_steps_to_pixel_frames(0), 0)
        self.assertEqual(shared.latent_steps_to_pixel_frames(1), 1)
        self.assertEqual(shared.latent_steps_to_pixel_frames(2), 5)
        self.assertEqual(shared.latent_steps_to_pixel_frames(7), 22)
        self.assertEqual(shared.latent_steps_to_pixel_frames(12), 39)
        self.assertEqual(shared.latent_steps_to_pixel_frames(17), 56)

    def test_non_positive_input_is_zero(self):
        self.assertEqual(shared.latent_steps_to_pixel_frames(-3), 0)
        self.assertEqual(shared.pixel_frames_to_latent_steps(0), 0)
        self.assertEqual(shared.pixel_frames_to_latent_steps(-5), 0)

    def test_frame_to_step_rounds_up_but_never_by_a_whole_step(self):
        for frames in range(1, 125):
            steps = shared.pixel_frames_to_latent_steps(frames)
            covered = shared.latent_steps_to_pixel_frames(steps)
            self.assertGreaterEqual(covered, frames, "%d frames covered only %d" % (frames, covered))
            self.assertLess(covered - frames, 4, "%d frames over-covered by %d" % (frames, covered - frames))

    def test_step_count_never_decreases_as_frames_grow(self):
        previous = 0
        for frames in range(1, 125):
            steps = shared.pixel_frames_to_latent_steps(frames)
            self.assertGreaterEqual(steps, previous)
            previous = steps


@unittest.skipIf(mc is None, "motion_context needs a ComfyUI install on sys.path: %s" % MC_ERROR)
class TestMotionContextGrid(unittest.TestCase):
    def test_offered_context_lengths_land_on_whole_latent_steps(self):
        for frames, steps in ((5, 2), (22, 7), (39, 12), (56, 17)):
            self.assertEqual(mc._steps_for_frames(frames), steps, "%d frames" % frames)

    def test_off_grid_runs_have_no_whole_step_cover(self):
        for frames in (2, 6, 7, 8, 21, 23, 40):
            self.assertIsNone(mc._steps_for_frames(frames), "%d frames" % frames)

    def test_every_run_grid_point_is_reachable(self):
        for frames in mc.VIDEO_RUN_GRID:
            self.assertIsNotNone(mc._steps_for_frames(frames), "%d frames" % frames)

    def test_pixel_frames_matches_the_clipbin_helper(self):
        for steps in range(0, 20):
            self.assertEqual(mc._pixel_frames(steps), shared.latent_steps_to_pixel_frames(steps))

    def test_step_offsets_are_cumulative(self):
        self.assertEqual(mc._step_offsets(1), [0])
        self.assertEqual(mc._step_offsets(3), [0, 1, 5])
        self.assertEqual(mc._step_offsets(6), [0, 1, 5, 9, 13, 17])


if __name__ == "__main__":
    unittest.main()
