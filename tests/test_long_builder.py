"""Shot order, variant choice and the join pre-check for the long-video builder.

The builder reads files written by an earlier run, so what matters is the
decisions it makes before ffmpeg runs: which cards to join and in which order,
which variant of a card to use, whether the pieces can be stream-copied, and when
a seam still carries the overlap frames. ffmpeg and ffprobe are replaced here; the
real ones are exercised by the manual run.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _support

_support.load_clipbin_package()
cbm = _support.load_clipbin_module("clip_bin_manager")
lb = _support.load_clipbin_module("long_builder")


def card(clip_id, shot, parent="", **extra):
    entry = {"clip_id": clip_id, "shot_tag": shot, "parent_clip_id": parent}
    entry.update(extra)
    return entry


def variant(video=None, frames=0):
    return {"has_video": bool(video), "video_file": video, "frames": frames}


def probe(width=1280, height=720, fps=24.0, frames=124, duration=5.166,
          has_audio=True, sample_rate=32000, frames_estimated=False):
    return {"width": width, "height": height, "fps": fps, "frames": frames,
            "duration": duration, "frames_estimated": frames_estimated,
            "has_audio": has_audio, "sample_rate": sample_rate,
            "vcodec": "h264", "acodec": "aac" if has_audio else ""}


class TestShotOrder(unittest.TestCase):
    """The bin is indexed newest first; the join order is the reverse of the lineage."""

    def setUp(self):
        self.cards = [
            card("clip_c3", "Shot 3", parent="clip_c2"),
            card("clip_c2", "Shot 2", parent="clip_c1"),
            card("clip_c1", "Shot 1", parent=""),
        ]

    def test_lineage_is_walked_backwards_then_reversed(self):
        order, warnings = lb.resolve_shot_order(self.cards)
        self.assertEqual(order, ["clip_c1", "clip_c2", "clip_c3"])
        self.assertEqual(warnings, [])

    def test_initial_marker_ends_the_chain(self):
        self.cards[1]["parent_clip_id"] = "[INITIAL]"
        order, warnings = lb.resolve_shot_order(self.cards)
        self.assertEqual(order, ["clip_c2", "clip_c3"])
        self.assertEqual(warnings, [])

    def test_start_clip_limits_the_chain(self):
        order, warnings = lb.resolve_shot_order(self.cards, start_ref="clip_c2")
        self.assertEqual(order, ["clip_c2", "clip_c3"])

    def test_end_clip_can_be_named_by_shot_tag(self):
        order, _ = lb.resolve_shot_order(self.cards, end_ref="Shot 2")
        self.assertEqual(order, ["clip_c1", "clip_c2"])

    def test_deleted_parent_warns_and_truncates(self):
        self.cards[1]["parent_clip_id"] = "clip_gone"
        order, warnings = lb.resolve_shot_order(self.cards)
        self.assertEqual(order, ["clip_c2", "clip_c3"])
        self.assertEqual(len(warnings), 1)
        self.assertIn("clip_gone", warnings[0])

    def test_cycle_in_lineage_is_broken_with_a_warning(self):
        self.cards[2]["parent_clip_id"] = "clip_c3"
        order, warnings = lb.resolve_shot_order(self.cards)
        self.assertEqual(order, ["clip_c1", "clip_c2", "clip_c3"])
        self.assertTrue(any("循环" in w for w in warnings))

    def test_hand_written_sequence_wins_over_lineage(self):
        order, warnings = lb.resolve_shot_order(
            self.cards, sequence_text="clip_c1, Shot 3\nclip_c2")
        self.assertEqual(order, ["clip_c1", "clip_c3", "clip_c2"])
        self.assertEqual(warnings, [])

    def test_unknown_reference_in_a_sequence_is_reported_not_fatal(self):
        order, warnings = lb.resolve_shot_order(self.cards, sequence_text="clip_c1,clip_missing")
        self.assertEqual(order, ["clip_c1"])
        self.assertIn("clip_missing", warnings[0])

    def test_empty_bin_says_so(self):
        order, warnings = lb.resolve_shot_order([])
        self.assertEqual(order, [])
        self.assertTrue(warnings)


class TestVariantChoice(unittest.TestCase):
    def test_second_pass_is_preferred_when_it_has_a_video(self):
        meta = {"variants": {"一采": variant("video_一采.mp4", 124),
                             "二采": variant("video_二采.mp4", 124)}}
        self.assertEqual(lb.pick_variant(meta, lb.VARIANT_PREFER_UP)[:2], ("二采", "video_二采.mp4"))

    def test_falls_back_to_first_pass_when_second_has_no_video(self):
        meta = {"variants": {"一采": variant("video_一采.mp4", 124),
                             "二采": variant(None, 124)}}
        self.assertEqual(lb.pick_variant(meta, lb.VARIANT_PREFER_UP)[:2], ("一采", "video_一采.mp4"))

    def test_forced_policy_does_not_fall_back(self):
        meta = {"variants": {"一采": variant("video_一采.mp4", 124),
                             "二采": variant(None, 124)}}
        self.assertEqual(lb.pick_variant(meta, lb.VARIANT_ONLY_UP), ("", "", {}))

    def test_single_variant_cards_ignore_the_policy(self):
        meta = {"has_video": True, "video_file": "video.mp4"}
        self.assertEqual(lb.pick_variant(meta, lb.VARIANT_ONLY_UP)[:2], ("", "video.mp4"))

    def test_card_without_video_selects_nothing(self):
        self.assertEqual(lb.pick_variant({"has_video": False}, lb.VARIANT_PREFER_UP), ("", "", {}))


class TestProbeParsing(unittest.TestCase):
    def test_container_frame_count_is_used_when_present(self):
        payload = {"streams": [{"codec_type": "video", "codec_name": "h264", "width": 1280,
                                "height": 720, "avg_frame_rate": "24/1", "nb_frames": "124",
                                "duration": "5.166667"},
                               {"codec_type": "audio", "codec_name": "aac", "sample_rate": "32000"}],
                   "format": {"duration": "5.166667"}}
        got = lb.parse_probe_json(payload)
        self.assertEqual((got["width"], got["height"], got["frames"]), (1280, 720, 124))
        self.assertFalse(got["frames_estimated"])
        self.assertEqual(got["sample_rate"], 32000)

    def test_missing_frame_count_falls_back_to_duration_and_is_flagged(self):
        payload = {"streams": [{"codec_type": "video", "codec_name": "h264", "width": 1280,
                                "height": 720, "avg_frame_rate": "24/1", "nb_frames": "N/A"}],
                   "format": {"duration": "5.166667"}}
        got = lb.parse_probe_json(payload)
        self.assertEqual(got["frames"], 124)
        self.assertTrue(got["frames_estimated"])

    def test_fractional_frame_rates_are_computed(self):
        payload = {"streams": [{"codec_type": "video", "codec_name": "h264",
                                "avg_frame_rate": "30000/1001", "nb_frames": "1"}], "format": {}}
        self.assertAlmostEqual(lb.parse_probe_json(payload)["fps"], 29.97002997, places=5)

    def test_silent_video_reports_no_audio(self):
        payload = {"streams": [{"codec_type": "video", "codec_name": "h264", "avg_frame_rate": "24/1",
                                "nb_frames": "1"}], "format": {}}
        got = lb.parse_probe_json(payload)
        self.assertFalse(got["has_audio"])
        self.assertEqual(got["sample_rate"], 0)


class TestJoinDecision(unittest.TestCase):
    def test_identical_parameters_allow_a_stream_copy(self):
        can_copy, reasons = lb.classify_join([probe(), probe()])
        self.assertTrue(can_copy)
        self.assertEqual(reasons, [])

    def test_resolution_difference_is_named(self):
        can_copy, reasons = lb.classify_join([probe(), probe(width=1920, height=1080)])
        self.assertFalse(can_copy)
        self.assertIn("1920x1080", reasons[0])

    def test_frame_rate_difference_is_named(self):
        can_copy, reasons = lb.classify_join([probe(), probe(fps=25.0)])
        self.assertFalse(can_copy)
        self.assertIn("帧率", reasons[0])

    def test_mixed_audio_presence_forces_a_reencode(self):
        can_copy, reasons = lb.classify_join([probe(), probe(has_audio=False)])
        self.assertFalse(can_copy)
        self.assertIn("音轨", reasons[0])

    def test_sample_rate_difference_is_named(self):
        can_copy, reasons = lb.classify_join([probe(), probe(sample_rate=44100)])
        self.assertFalse(can_copy)
        self.assertIn("44100", reasons[0])

    def test_a_single_segment_never_needs_reencoding(self):
        self.assertEqual(lb.classify_join([probe()]), (True, []))


class TestSeamWarnings(unittest.TestCase):
    """Equal latent and video frame counts means the pinned frames were never cut."""

    def test_untrimmed_segment_is_flagged(self):
        segments = [{"label": "Shot 1", "latent_frames": 124, "frames": 124},
                    {"label": "Shot 2", "latent_frames": 124, "frames": 124}]
        warnings = lb.seam_warnings(segments)
        self.assertEqual(len(warnings), 1)
        self.assertIn("Shot 2", warnings[0])
        self.assertIn("Trim", warnings[0])

    def test_first_segment_is_never_flagged(self):
        self.assertEqual(lb.seam_warnings([{"label": "Shot 1", "latent_frames": 124, "frames": 124}]), [])

    def test_trimmed_segment_is_silent(self):
        segments = [{"label": "Shot 1", "latent_frames": 124, "frames": 124},
                    {"label": "Shot 2", "latent_frames": 124, "frames": 119}]
        self.assertEqual(lb.seam_warnings(segments), [])

    def test_estimated_frame_counts_are_not_judged(self):
        segments = [{"label": "Shot 1", "latent_frames": 124, "frames": 124},
                    {"label": "Shot 2", "latent_frames": 124, "frames": 124, "frames_estimated": True}]
        self.assertEqual(lb.seam_warnings(segments), [])


class TestConcatList(unittest.TestCase):
    def test_paths_are_forward_slashed_and_quote_escaped(self):
        text = lb.concat_list_text([r"C:\out\it's a shot.mp4", "/tmp/plain.mp4"])
        self.assertIn("file 'C:/out/it'\\''s a shot.mp4'", text)
        self.assertIn("file '/tmp/plain.mp4'", text)
        self.assertTrue(text.startswith("ffconcat version 1.0"))


class BuildTestCase(unittest.TestCase):
    """Drives build_long_video against a throwaway bin with ffmpeg and ffprobe faked."""

    def setUp(self):
        self.store = _support.make_temp_dir("cs_long")
        self.out = _support.make_temp_dir("cs_long_out")
        self._real_base = cbm.get_base_bin_dir
        self._real_root = lb.get_output_root
        self._real_probe = lb.probe_video_streams
        self._real_concat = lb.concat_videos
        cbm.get_base_bin_dir = lambda: self.store
        lb.get_output_root = lambda: self.out
        self.probes = {}
        # Keyed by full path: every card stores its video under the same file name.
        lb.probe_video_streams = lambda path: self.probes.get(path)
        self.calls = []

        def fake_concat(paths, output_path, mode, fps=24.0, has_audio=False):
            self.calls.append({"paths": paths, "mode": mode, "fps": fps, "has_audio": has_audio})
            with open(output_path, "wb") as stream:
                stream.write(b"fake")
            return ("copy" if mode == lb.JOIN_COPY else "reencode"), ""

        lb.concat_videos = fake_concat

    def tearDown(self):
        cbm.get_base_bin_dir = self._real_base
        lb.get_output_root = self._real_root
        lb.probe_video_streams = self._real_probe
        lb.concat_videos = self._real_concat
        _support.remove_temp_dir(self.store)
        _support.remove_temp_dir(self.out)

    def add_card(self, project, clip_id, shot, parent, video="video_二采.mp4", frames=124,
                 probed_frames=None, **probe_overrides):
        # A normally archived segment has the pinned frames cut, so the file is shorter
        # than the latent. Tests that want the untrimmed case pass probed_frames.
        if probed_frames is None:
            probed_frames = frames - 5
        clip_dir = os.path.join(self.store, project, clip_id)
        os.makedirs(clip_dir, exist_ok=True)
        if video:
            with open(os.path.join(clip_dir, video), "wb") as stream:
                stream.write(b"x")
            self.probes[os.path.join(clip_dir, video)] = probe(frames=probed_frames or frames, **probe_overrides)
        meta = {"clip_id": clip_id, "project_name": project, "shot_tag": shot,
                "parent_clip_id": parent,
                "variants": {"二采": variant(video, frames), "一采": variant(None, frames)}}
        with open(os.path.join(clip_dir, "meta.json"), "w", encoding="utf-8") as stream:
            json.dump(meta, stream, ensure_ascii=False)

    def test_three_shots_become_one_file_in_shot_order(self):
        self.add_card("Proj", "clip_a", "Shot 1", "")
        self.add_card("Proj", "clip_b", "Shot 2", "clip_a")
        self.add_card("Proj", "clip_c", "Shot 3", "clip_b")
        result = lb.build_long_video("Proj")
        self.assertEqual([os.path.basename(s["video_path"]) for s in result["segments"]],
                         ["video_二采.mp4"] * 3)
        self.assertEqual(len(self.calls[0]["paths"]), 3)
        self.assertTrue(self.calls[0]["paths"][0].replace("\\", "/").find("clip_a") > 0)
        self.assertEqual(self.calls[0]["mode"], lb.JOIN_COPY)
        self.assertEqual(result["total_frames"], 357)
        self.assertEqual(result["join_method"], "copy")
        self.assertEqual(result["warnings"], [])
        self.assertIn(os.path.join("h3_long", "Proj"), result["path"])
        self.assertTrue(os.path.isfile(result["path"]))
        self.assertIn("3 段", result["report"])

    def test_mismatched_segments_are_reencoded_and_reported(self):
        self.add_card("Proj", "clip_a", "Shot 1", "")
        self.add_card("Proj", "clip_b", "Shot 2", "clip_a", width=1920, height=1080)
        result = lb.build_long_video("Proj")
        self.assertEqual(self.calls[0]["mode"], lb.JOIN_REENCODE)
        self.assertEqual(result["join_method"], "reencode")
        self.assertTrue(any("1920x1080" in w for w in result["warnings"]))

    def test_copy_mode_refuses_mismatched_segments(self):
        self.add_card("Proj", "clip_a", "Shot 1", "")
        self.add_card("Proj", "clip_b", "Shot 2", "clip_a", fps=25.0)
        with self.assertRaises(ValueError) as caught:
            lb.build_long_video("Proj", join_mode=lb.JOIN_COPY)
        self.assertIn("帧率", str(caught.exception))

    def test_missing_video_is_fatal_unless_skipping_is_allowed(self):
        self.add_card("Proj", "clip_a", "Shot 1", "")
        self.add_card("Proj", "clip_b", "Shot 2", "clip_a", video=None)
        with self.assertRaises(ValueError) as caught:
            lb.build_long_video("Proj")
        self.assertIn("Shot 2", str(caught.exception))
        result = lb.build_long_video("Proj", skip_missing=True)
        self.assertEqual(len(result["segments"]), 1)
        self.assertTrue(any("跳过" in w for w in result["warnings"]))

    def test_untrimmed_middle_segment_is_reported_in_the_report(self):
        self.add_card("Proj", "clip_a", "Shot 1", "")
        self.add_card("Proj", "clip_b", "Shot 2", "clip_a", probed_frames=124)
        result = lb.build_long_video("Proj")
        self.assertTrue(any("Shot 2" in w and "Trim" in w for w in result["warnings"]))
        self.assertIn("注意：", result["report"])

    def test_empty_project_fails_clearly(self):
        with self.assertRaises(ValueError) as caught:
            lb.build_long_video("Proj")
        self.assertIn("没有可拼接的镜头", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
