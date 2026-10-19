"""The three upstream 0.7.1 experiment nodes and the latent load/save changes.

The node classes are ports, so these tests do not re-derive the algorithms. They
pin the edges a user can actually reach: which frame counts are legal, the
branches that must pass a clip through untouched (and must not pay for a second
sampler), the mistakes worth raising instead of guessing at, and the container
the next node in the graph expects back.

Needs a ComfyUI install for comfy_api. Set COMFYUI_ROOT, or run the suite from
inside custom_nodes where the host root is inferred.
"""

import importlib
import os
import sys
import unittest

import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _support

PKG, PKG_ERROR = _support.load_plugin_package()
SKIP = "the plugin needs a ComfyUI install on sys.path: %s" % PKG_ERROR

SCHEDULE = [1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.0]


def _module(dotted):
    obj = PKG
    for part in dotted.split("."):
        obj = getattr(obj, part)
    return obj


def video(steps=10, height=4, width=6, seed=0):
    generator = torch.Generator().manual_seed(seed)
    return torch.randn(1, 3, steps, height, width, generator=generator)


def sound(frames=40, channels=8, seed=1):
    generator = torch.Generator().manual_seed(seed)
    return torch.randn(1, channels, 2, frames, generator=generator)


def av_latent(steps=10, seed=0):
    """An H3 AV latent in the plain-list form this repo's Load node hands over."""
    return {"samples": [video(steps, seed=seed), sound(seed=seed + 1)]}


@unittest.skipIf(PKG is None, SKIP)
class TestLatentStepCycle(unittest.TestCase):
    def test_the_cycle_matches_the_h3_temporal_compression(self):
        self.assertEqual([_module("motion_context.refine_blend").pixel_frames(t)
                          for t in range(8)], [0, 1, 5, 9, 13, 17, 18, 22])
        self.assertEqual(_module("motion_context.refine_blend").FRAME_PER_TOKEN,
                         _module("motion_context.join_match").FRAME_PER_TOKEN)

    def test_every_pinned_window_length_is_a_whole_number_of_steps(self):
        for frames, steps in ((5, 2), (22, 7), (39, 12), (56, 17)):
            self.assertEqual(_module("motion_context.refine_blend").steps_for_frames(frames), steps)
            self.assertEqual(_module("motion_context.join_match").steps_for_frames(frames), steps)

    def test_a_count_off_the_cycle_has_no_step_count(self):
        self.assertIsNone(_module("motion_context.refine_blend").steps_for_frames(21))
        self.assertIsNone(_module("motion_context.join_match").steps_for_frames(20))

    def test_nearest_valid_offers_only_legal_counts_on_both_sides(self):
        refine = _module("motion_context.refine_blend")
        picks = refine.nearest_valid(20)
        self.assertEqual(picks, [13, 17, 18, 22, 26, 30])
        self.assertTrue(all(refine.steps_for_frames(x) is not None for x in picks))


@unittest.skipIf(PKG is None, SKIP)
class TestRefineBlendWeights(unittest.TestCase):
    def test_the_hold_is_zero_weight_and_the_ramp_stays_in_the_unit_range(self):
        weights = _module("motion_context.refine_blend").weights(12, 22, 22)
        self.assertEqual(len(weights), 12)
        self.assertTrue(all(x == 0.0 for x in weights[:8]))
        self.assertTrue(all(0.0 <= x <= 1.0 for x in weights))
        self.assertEqual(weights, sorted(weights))

    def test_a_blend_that_does_not_land_on_a_step_boundary_still_ramps(self):
        weights = _module("motion_context.refine_blend").weights(12, 22, 9)
        self.assertTrue(any(0.0 < x < 1.0 for x in weights))
        self.assertEqual(weights[-1], 1.0)

    def test_blend_frames_zero_is_a_hard_cut(self):
        weights = _module("motion_context.refine_blend").weights(10, 22, 0)
        self.assertEqual(weights[:7], [0.0] * 7)
        self.assertTrue(all(x == 1.0 for x in weights[7:]))


@unittest.skipIf(PKG is None, SKIP)
class TestRefineBlendNode(unittest.TestCase):
    def node(self):
        return _module("motion_context.refine_blend").MiniMaxH3RefineBlendClipStream

    def test_refine_off_hands_back_the_original_object(self):
        latent = av_latent()
        out = self.node().execute(original=latent, hold_frames=22, blend_frames=22,
                                  audio="original", use_refine=False, clip_index=1,
                                  refined=av_latent(seed=5))
        self.assertIs(out.args[0], latent)

    def test_the_second_sampler_is_only_asked_for_when_refine_is_on(self):
        self.assertEqual(self.node().check_lazy_status(use_refine=False, refined=None), [])
        self.assertEqual(self.node().check_lazy_status(use_refine=True, refined=None), ["refined"])
        self.assertEqual(self.node().check_lazy_status(use_refine=True, refined=av_latent()), [])

    def test_held_frames_come_back_exactly_as_sampled(self):
        original, refined = av_latent(seed=2), av_latent(seed=3)
        out = self.node().execute(original=original, hold_frames=22, blend_frames=0,
                                  audio="original", use_refine=True, clip_index=1,
                                  refined=refined)
        got = out.args[0]["samples"][0]
        self.assertTrue(torch.equal(got[:, :, :7], original["samples"][0][:, :, :7]))
        self.assertTrue(torch.equal(got[:, :, 7:], refined["samples"][0][:, :, 7:]))

    def test_the_first_clip_takes_the_whole_render_from_the_refined_latent(self):
        original, refined = av_latent(seed=2), av_latent(seed=3)
        out = self.node().execute(original=original, hold_frames=22, blend_frames=22,
                                  audio="original", use_refine=True, clip_index=0,
                                  refined=refined)
        self.assertTrue(torch.equal(out.args[0]["samples"][0], refined["samples"][0]))

    def test_a_hold_off_the_step_cycle_is_refused_with_the_nearest_legal_counts(self):
        with self.assertRaises(ValueError) as caught:
            self.node().execute(original=av_latent(), hold_frames=20, blend_frames=22,
                                audio="original", use_refine=True, clip_index=1,
                                refined=av_latent(seed=4))
        message = str(caught.exception)
        self.assertIn("20 frame hold", message)
        self.assertIn("22", message)

    def test_a_hold_longer_than_the_clip_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            self.node().execute(original=av_latent(steps=5), hold_frames=56, blend_frames=0,
                                audio="original", use_refine=True, clip_index=1,
                                refined=av_latent(steps=5, seed=4))
        self.assertIn("only has 5", str(caught.exception))

    def test_two_latents_of_different_shapes_are_refused(self):
        with self.assertRaises(ValueError) as caught:
            self.node().execute(original=av_latent(steps=10), hold_frames=22, blend_frames=0,
                                audio="original", use_refine=True, clip_index=1,
                                refined=av_latent(steps=9, seed=4))
        self.assertIn("different shapes", str(caught.exception))

    def test_audio_defaults_to_the_original_stream(self):
        original, refined = av_latent(seed=2), av_latent(seed=3)
        keep = self.node().execute(original=original, hold_frames=22, blend_frames=0,
                                   audio="original", use_refine=True, clip_index=1,
                                   refined=refined)
        swap = self.node().execute(original=original, hold_frames=22, blend_frames=0,
                                   audio="refined", use_refine=True, clip_index=1,
                                   refined=refined)
        self.assertTrue(torch.equal(keep.args[0]["samples"][1], original["samples"][1]))
        self.assertTrue(torch.equal(swap.args[0]["samples"][1], refined["samples"][1]))

    def test_the_container_kind_is_kept(self):
        out = self.node().execute(original=av_latent(), hold_frames=22, blend_frames=0,
                                  audio="original", use_refine=True, clip_index=1,
                                  refined=av_latent(seed=4))
        self.assertIsInstance(out.args[0]["samples"], list)

    def test_a_nested_latent_stays_nested(self):
        try:
            import comfy.nested_tensor
        except ImportError:
            self.skipTest("this ComfyUI install has no comfy.nested_tensor")
        nested = lambda seed: {"samples": comfy.nested_tensor.NestedTensor(
            (video(10, seed=seed), sound(seed=seed + 1)))}
        out = self.node().execute(original=nested(2), hold_frames=22, blend_frames=0,
                                  audio="original", use_refine=True, clip_index=1,
                                  refined=nested(3))
        self.assertTrue(getattr(out.args[0]["samples"], "is_nested", False))


@unittest.skipIf(PKG is None, SKIP)
class TestJoinMatchNode(unittest.TestCase):
    def node(self):
        return _module("motion_context.join_match").MiniMaxH3JoinMatchClipStream

    def run_join(self, samples, context_latent, **kwargs):
        args = {"strength": 1.0, "context_length": 22, "min_excess": 1.5,
                "match_spread": True, "min_excess_spread": 1.5, "match_detail": True,
                "min_excess_detail": 1.5, "tuning": "auto"}
        args.update(kwargs)
        return self.node().execute(samples=samples, context_latent=context_latent, **args)

    def test_no_previous_clip_passes_the_clip_through(self):
        latent = av_latent(steps=13, seed=9)
        self.assertIs(self.run_join(latent, None).args[0], latent)

    def test_zero_strength_passes_the_clip_through(self):
        latent = av_latent(steps=13, seed=9)
        out = self.run_join(latent, av_latent(steps=8, seed=7), strength=0.0)
        self.assertIs(out.args[0], latent)

    def test_a_first_clip_with_nothing_pinned_passes_through(self):
        latent = av_latent(steps=13, seed=9)
        out = self.run_join(latent, av_latent(steps=8, seed=7), context_length=0)
        self.assertIs(out.args[0], latent)

    def test_a_context_length_off_the_step_cycle_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            self.run_join(av_latent(steps=13, seed=9), av_latent(steps=8, seed=7),
                          context_length=20)
        self.assertIn("5, 22, 39 or 56", str(caught.exception))

    def test_an_unknown_tuning_mode_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            self.run_join(av_latent(steps=13, seed=9), av_latent(steps=8, seed=7),
                          tuning="aggressive")
        self.assertIn("expected auto or manual", str(caught.exception))

    def test_latents_of_different_frame_sizes_are_refused(self):
        current = {"samples": [video(13, height=4, seed=9), sound(seed=10)]}
        previous = {"samples": [video(8, height=6, seed=7), sound(seed=8)]}
        with self.assertRaises(ValueError) as caught:
            self.run_join(current, previous)
        self.assertIn("share channels and frame size", str(caught.exception))

    def test_a_full_join_keeps_the_shape_and_the_container(self):
        current = av_latent(steps=13, seed=9)
        out = self.run_join(current, av_latent(steps=8, seed=7))
        got = out.args[0]["samples"]
        self.assertIsInstance(got, list)
        self.assertEqual(tuple(got[0].shape), tuple(current["samples"][0].shape))
        self.assertEqual(tuple(got[1].shape), tuple(current["samples"][1].shape))

    def test_shot_motion_needs_a_pair_of_steps(self):
        self.assertIsNone(_module("motion_context.join_match").shot_motion(video(12), 7))

    def test_a_locked_off_shot_scores_as_still(self):
        join = _module("motion_context.join_match")
        still = video(1, seed=4).repeat(1, 1, 13, 1, 1)
        self.assertEqual(join.shot_motion(still, 7), 0.0)

    def test_a_moving_shot_scores_above_the_still_threshold(self):
        join = _module("motion_context.join_match")
        base = video(15, seed=4)
        ramp = 1.0 + torch.arange(15, dtype=torch.float32).reshape(1, 1, 15, 1, 1)
        self.assertGreater(join.shot_motion(base * ramp, 7), join.STILL_MAX)

    def test_the_auto_tuning_threshold_sits_in_the_measured_gap(self):
        join = _module("motion_context.join_match")
        self.assertGreater(join.STILL_MAX, 0.40)
        self.assertLess(join.STILL_MAX, 0.58)
        self.assertLess(join.AUTO_STILL["min_excess_spread"],
                        join.AUTO_MOVING["min_excess_spread"])
        self.assertEqual(join.AUTO_STILL["min_excess"], join.AUTO_MOVING["min_excess"])


@unittest.skipIf(PKG is None, SKIP)
class TestSigmasTailNode(unittest.TestCase):
    def node(self):
        return _module("motion_context.sigma_tools").MiniMaxH3SigmasTailClipStream

    def test_strength_zero_returns_the_same_schedule_object(self):
        schedule = list(SCHEDULE)
        self.assertIs(self.node().execute(schedule, 3, 0.0).args[0], schedule)

    def test_only_the_requested_tail_moves_and_the_final_zero_is_kept(self):
        schedule = list(SCHEDULE)
        out = self.node().execute(schedule, 3, 0.5).args[0]
        self.assertEqual(len(out), len(schedule))
        self.assertEqual(out[:5], schedule[:5])
        self.assertEqual(out[-1], 0.0)
        tail = out[5:8]
        self.assertTrue(all(x > y for x, y in zip(tail, tail[1:])))
        self.assertTrue(all(0.0 < x < schedule[4] for x in tail))

    def test_positive_strength_lifts_the_tail_and_negative_lowers_it(self):
        up = self.node().execute(list(SCHEDULE), 3, 0.5).args[0][5:8]
        down = self.node().execute(list(SCHEDULE), 3, -0.5).args[0][5:8]
        self.assertTrue(all(x > y for x, y in zip(up, SCHEDULE[5:8])))
        self.assertTrue(all(x < y for x, y in zip(down, SCHEDULE[5:8])))

    def test_a_flat_stretch_is_forced_back_down(self):
        out = self.node().execute([1.0, 0.8, 0.8, 0.8, 0.0], 3, 0.5).args[0]
        self.assertTrue(all(x > y for x, y in zip(out[:4], out[1:5])))

    def test_a_schedule_shorter_than_the_tail_passes_through(self):
        schedule = [1.0, 0.0]
        self.assertIs(self.node().execute(schedule, 3, 0.5).args[0], schedule)

    def test_a_tensor_schedule_comes_back_as_a_tensor(self):
        out = self.node().execute(torch.tensor(SCHEDULE), 3, 0.5).args[0]
        self.assertIsInstance(out, torch.Tensor)
        self.assertEqual(out.shape, torch.tensor(SCHEDULE).shape)
        self.assertAlmostEqual(float(out[-1]), 0.0)

    def test_same_kind_keeps_a_list_and_uses_new_tensor_otherwise(self):
        class Fake:
            def new_tensor(self, values):
                return ("new", values)

        sigma_tools = _module("motion_context.sigma_tools")
        self.assertEqual(sigma_tools.same_kind([1.0, 0.0], [1.0, 0.0]), [1.0, 0.0])
        self.assertEqual(sigma_tools.same_kind([1.0], Fake())[0], "new")


@unittest.skipIf(PKG is None, SKIP)
class TestLatentFolders(unittest.TestCase):
    """The output/input folder switch that came with upstream 0.7.1."""

    def setUp(self):
        self.nodes = _module("motion_context.nodes")
        self.root = os.path.realpath(_support.make_temp_dir("mc_latents"))
        self.output = os.path.join(self.root, "output")
        self.input_dir = os.path.join(self.root, "input")
        os.mkdir(self.output)
        os.mkdir(self.input_dir)
        self.folder_paths = importlib.import_module("folder_paths")
        self.real_output = self.folder_paths.get_output_directory
        self.real_input = self.folder_paths.get_input_directory
        self.folder_paths.get_output_directory = lambda: self.output
        self.folder_paths.get_input_directory = lambda: self.input_dir

    def tearDown(self):
        self.folder_paths.get_output_directory = self.real_output
        self.folder_paths.get_input_directory = self.real_input
        _support.remove_temp_dir(self.root)

    def require_safetensors(self):
        if self.nodes._st_save is None or self.nodes._st_load is None:
            self.skipTest("safetensors is not available in this environment")

    def write_slot(self, folder, index, seed=0):
        path = os.path.join(self.output, folder, "%s_%05d.safetensors" % (folder, index))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.nodes._write_safetensors(path, {"video": video(3, seed=seed),
                                             "audio": sound(8, seed=seed)})
        return path

    def test_relative_paths_stay_inside_the_root_and_escapes_are_refused(self):
        under = self.nodes._under_root
        self.assertEqual(under(self.output, "h3_context"),
                         os.path.join(self.output, "h3_context"))
        self.assertEqual(under(self.output, "", "h3_context"),
                         os.path.join(self.output, "h3_context"))
        self.assertIsNone(under(self.output, ""))
        self.assertEqual(under(self.output, self.output), self.output)
        self.assertIsNone(under(self.output, "../outside"))
        self.assertIsNone(under(self.output, self.root))

    def test_the_root_is_compared_case_insensitively_where_the_filesystem_is(self):
        target = os.path.join(self.root, "Chain")
        os.mkdir(target)
        flipped = "".join(c.lower() if c.isupper() else c.upper() for c in target)
        if os.path.normcase(flipped) == flipped:
            self.skipTest("this filesystem does not fold case")
        got = self.nodes._under_root(target, flipped)
        self.assertIsNotNone(got)
        self.assertEqual(os.path.normcase(got), os.path.normcase(os.path.realpath(target)))

    def test_input_mode_reads_one_file_from_the_input_folder(self):
        path = os.path.join(self.input_dir, "uploaded.safetensors")
        with open(path, "wb") as handle:
            handle.write(b"x")
        self.assertEqual(self.nodes._resolve_latent_path("uploaded.safetensors", 1, "input"),
                         os.path.realpath(path))
        with self.assertRaises(FileNotFoundError):
            self.nodes._resolve_latent_path("missing.safetensors", 1, "input")
        with self.assertRaises(FileNotFoundError):
            self.nodes._resolve_latent_path("../output/whatever.safetensors", 1, "input")

    def test_an_unknown_folder_is_an_error_rather_than_a_silent_output_read(self):
        with self.assertRaises(ValueError) as caught:
            self.nodes._resolve_latent_path("h3_context", 1, "models")
        self.assertIn("folder must be one of output, input", str(caught.exception))

    def test_numbered_slots_are_matched_by_the_natural_name_only(self):
        written = self.write_slot("chain", 2)
        self.assertEqual(os.path.realpath(self.nodes._resolve_latent_path("chain", 2)),
                         os.path.realpath(written))
        auto = os.path.join(self.output, "auto", "auto_00003_.safetensors")
        os.makedirs(os.path.dirname(auto), exist_ok=True)
        self.require_safetensors()
        self.nodes._write_safetensors(auto, {"video": video(3), "audio": sound(8)})
        with self.assertRaises(FileNotFoundError) as caught:
            self.nodes._resolve_latent_path("auto", 3)
        self.assertIn("auto-numbered", str(caught.exception))

    def test_clip_zero_loads_nothing(self):
        out = self.nodes.MiniMaxH3MotionContextLoadLatent.execute(latent_path="chain",
                                                                  clip_index=0)
        self.assertIsNone(out.args[0])

    def test_the_default_output_is_the_plain_list_only_context_latent_accepts(self):
        self.require_safetensors()
        self.write_slot("chain", 1)
        out = self.nodes.MiniMaxH3MotionContextLoadLatent.execute(latent_path="chain",
                                                                  clip_index=1)
        samples = out.args[0]["samples"]
        self.assertIsInstance(samples, list)
        self.assertEqual(tuple(samples[0].shape), tuple(video(3).shape))

    def test_stock_format_hands_stock_nodes_a_nested_av_latent(self):
        self.require_safetensors()
        self.write_slot("chain", 1)
        out = self.nodes.MiniMaxH3MotionContextLoadLatent.execute(
            latent_path="chain", clip_index=1, stock_format=True)
        self.assertTrue(getattr(out.args[0]["samples"], "is_nested", False))

    def test_a_latent_from_the_input_folder_loads_the_same_way(self):
        self.require_safetensors()
        path = os.path.join(self.input_dir, "uploaded.safetensors")
        self.nodes._write_safetensors(path, {"video": video(3, seed=5),
                                             "audio": sound(8, seed=5)})
        out = self.nodes.MiniMaxH3MotionContextLoadLatent.execute(
            latent_path="uploaded.safetensors", clip_index=4, folder="input")
        self.assertEqual(tuple(out.args[0]["samples"][0].shape), tuple(video(3).shape))

    def test_the_fingerprint_caches_on_the_file_and_the_format_flag(self):
        self.require_safetensors()
        self.write_slot("chain", 1)
        node = self.nodes.MiniMaxH3MotionContextLoadLatent
        plain = node.fingerprint_inputs("chain", 1)
        stock = node.fingerprint_inputs("chain", 1, stock_format=True)
        self.assertIn(":owned", plain)
        self.assertTrue(stock.startswith(plain))
        self.assertTrue(stock.endswith(":stock"))
        self.assertEqual(node.fingerprint_inputs("chain", 0), "disabled")

    def test_the_fingerprint_refuses_to_cache_an_unreadable_slot(self):
        nan = self.nodes.MiniMaxH3MotionContextLoadLatent.fingerprint_inputs("missing", 3)
        self.assertNotEqual(nan, nan)

    def test_save_reports_the_file_the_way_stock_save_latent_does(self):
        self.require_safetensors()
        out = self.nodes.MiniMaxH3MotionContextSaveLatent.execute(
            latent=av_latent(), filename_prefix="mc_chain", clip_index=2)
        path = out.args[0]
        self.assertTrue(os.path.isfile(path))
        self.assertEqual(os.path.basename(path), "mc_chain_00002.safetensors")
# A plain dict, exactly like stock Save Latent: an HTTP client reads it
        # out of /history and fetches the file through /view.
        reported = out.ui["latents"][0]
        self.assertEqual(reported["filename"], "mc_chain_00002.safetensors")
        self.assertEqual(reported["subfolder"], "")
        self.assertEqual(reported["type"], "output")


if __name__ == "__main__":
    unittest.main()
