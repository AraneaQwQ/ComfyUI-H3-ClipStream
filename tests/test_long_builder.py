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
from unittest import mock

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
    """The timeline is the shot number on the card, not the lineage between cards.

    The bin index is newest first, so every case here feeds the cards in reverse on
    purpose: the order the builder produces must come from the shot numbers.
    """

    def setUp(self):
        self.cards = [
            card("clip_c3", "Shot 3", parent="clip_c2", created_at="2026-10-02 10:03:00"),
            card("clip_c1", "Shot 1", parent="", created_at="2026-10-02 10:01:00"),
            card("clip_c2", "Shot 2", parent="clip_c1", created_at="2026-10-02 10:02:00"),
        ]

    def test_cards_are_ordered_by_shot_number(self):
        order, warnings = lb.resolve_shot_order(self.cards)
        self.assertEqual(order, ["clip_c1", "clip_c2", "clip_c3"])
        self.assertEqual(warnings, [])

    def test_shot_12_comes_after_shot_2(self):
        self.cards.insert(0, card("clip_c12", "Shot 12", parent="clip_c3"))
        order, _ = lb.resolve_shot_order(self.cards)
        self.assertEqual(order[-2:], ["clip_c3", "clip_c12"])

    def test_a_project_that_starts_at_shot_4_still_joins(self):
        cards = [card("clip_c5", "Shot 5"), card("clip_c4", "Shot 4")]
        order, warnings = lb.resolve_shot_order(cards)
        self.assertEqual(order, ["clip_c4", "clip_c5"])
        self.assertEqual(warnings, [])

    def test_lineage_does_not_move_a_card(self):
        # A branch or a bad parent id changes which card continued from which; it does
        # not change when the finished film plays each shot.
        for entry in self.cards:
            entry["parent_clip_id"] = "clip_c3"
        order, warnings = lb.resolve_shot_order(self.cards)
        self.assertEqual(order, ["clip_c1", "clip_c2", "clip_c3"])
        self.assertEqual(warnings, [])

    def test_a_card_switched_off_in_the_panel_is_left_out(self):
        order, warnings = lb.resolve_shot_order(self.cards, exclude_text="clip_c2")
        self.assertEqual(order, ["clip_c1", "clip_c3"])
        self.assertEqual(warnings, [])

    def test_exclusion_also_accepts_a_shot_tag(self):
        order, _ = lb.resolve_shot_order(self.cards, exclude_text="Shot 1")
        self.assertEqual(order, ["clip_c2", "clip_c3"])

    def test_excluding_a_card_that_is_not_in_the_bin_is_reported_not_fatal(self):
        order, warnings = lb.resolve_shot_order(self.cards, exclude_text="clip_gone")
        self.assertEqual(order, ["clip_c1", "clip_c2", "clip_c3"])
        self.assertIn("clip_gone", warnings[0])

    def test_unnumbered_tags_follow_the_numbered_ones_in_generation_order(self):
        self.cards.append(card("clip_x", "补拍空镜", created_at="2026-10-02 09:00:00"))
        self.cards.append(card("clip_y", "男主回眸", created_at="2026-10-02 11:00:00"))
        order, _ = lb.resolve_shot_order(self.cards)
        self.assertEqual(order, ["clip_c1", "clip_c2", "clip_c3", "clip_x", "clip_y"])

    def test_the_same_shot_number_falls_back_to_creation_time(self):
        self.cards.append(card("clip_c2b", "Shot 2", created_at="2026-10-02 09:30:00"))
        order, _ = lb.resolve_shot_order(self.cards)
        self.assertEqual(order, ["clip_c1", "clip_c2b", "clip_c2", "clip_c3"])

    def test_empty_bin_says_so(self):
        order, warnings = lb.resolve_shot_order([])
        self.assertEqual(order, [])
        self.assertTrue(warnings)

    def test_switching_off_every_card_leaves_nothing(self):
        order, warnings = lb.resolve_shot_order(self.cards,
                                                exclude_text="Shot 1, Shot 2, Shot 3")
        self.assertEqual(order, [])
        self.assertTrue(any("全被排除" in w for w in warnings))

    def test_shot_number_reads_the_first_number_of_a_tag(self):
        self.assertEqual(lb.shot_number("Shot 12"), 12)
        self.assertEqual(lb.shot_number("第 3 镜 男主回眸"), 3)
        self.assertIsNone(lb.shot_number("远景空镜"))
        self.assertIsNone(lb.shot_number(None))


class TestManualCardOrder(unittest.TestCase):
    """Dragging a card on the panel writes clip_order; the film follows it.

    clip_order uses the same references as exclude_clips and is read top to bottom.
    Cards it does not mention are appended by shot number, so a segment generated
    after the last drag still joins the film instead of disappearing, and a reference
    whose card was deleted is reported rather than fatal.
    """

    def setUp(self):
        self.cards = [
            card("clip_c3", "Shot 3", parent="clip_c2", created_at="2026-10-02 10:03:00"),
            card("clip_c1", "Shot 1", parent="", created_at="2026-10-02 10:01:00"),
            card("clip_c2", "Shot 2", parent="clip_c1", created_at="2026-10-02 10:02:00"),
        ]

    def test_the_dragged_order_wins_over_shot_numbers(self):
        order, warnings = lb.resolve_shot_order(self.cards, clip_order="clip_c2,clip_c1,clip_c3")
        self.assertEqual(order, ["clip_c2", "clip_c1", "clip_c3"])
        self.assertEqual(warnings, [])

    def test_a_shot_tag_reference_orders_the_same_card(self):
        order, _ = lb.resolve_shot_order(self.cards, clip_order="Shot 2, Shot 1, Shot 3")
        self.assertEqual(order, ["clip_c2", "clip_c1", "clip_c3"])

    def test_cards_left_out_of_the_order_are_appended_by_shot_number(self):
        # One drag happened, then Shot 4 was generated: the new card must still appear.
        cards = self.cards + [card("clip_c4", "Shot 4", parent="clip_c3",
                                  created_at="2026-10-02 10:04:00")]
        order, _ = lb.resolve_shot_order(cards, clip_order="clip_c3,clip_c1")
        self.assertEqual(order, ["clip_c3", "clip_c1", "clip_c2", "clip_c4"])

    def test_a_reference_that_is_no_longer_in_the_bin_is_reported_not_fatal(self):
        order, warnings = lb.resolve_shot_order(self.cards,
                                               clip_order="clip_gone,clip_c1,clip_c2")
        self.assertEqual(order, ["clip_c1", "clip_c2", "clip_c3"])
        self.assertTrue(any("clip_gone" in w for w in warnings), warnings)

    def test_a_card_listed_twice_joins_once(self):
        order, _ = lb.resolve_shot_order(self.cards, clip_order="clip_c1,clip_c2,clip_c1")
        self.assertEqual(order, ["clip_c1", "clip_c2", "clip_c3"])

    def test_an_excluded_card_stays_out_even_when_it_is_ordered(self):
        order, _ = lb.resolve_shot_order(self.cards,
                                         exclude_text="clip_c2", clip_order="clip_c2,clip_c1")
        self.assertEqual(order, ["clip_c1", "clip_c3"])

    def test_an_empty_order_is_exactly_the_shot_number_order(self):
        self.assertEqual(lb.resolve_shot_order(self.cards, clip_order="")[0],
                         lb.resolve_shot_order(self.cards)[0])

class TestNumberingGaps(unittest.TestCase):
    """A deleted take leaves a hole in the shot numbers; the panel and the log say so."""

    def test_a_deleted_take_is_named(self):
        warnings = lb.numbering_gaps([card("clip_a", "Shot 1"), card("clip_c", "Shot 3")])
        self.assertEqual(len(warnings), 1)
        self.assertIn("Shot 2", warnings[0])

    def test_contiguous_numbers_are_silent(self):
        self.assertEqual(lb.numbering_gaps([card("clip_a", "Shot 1"), card("clip_b", "Shot 2")]),
                         [])

    def test_one_card_is_never_a_gap(self):
        self.assertEqual(lb.numbering_gaps([card("clip_a", "Shot 7")]), [])

    def test_tags_without_numbers_are_not_counted(self):
        self.assertEqual(lb.numbering_gaps([card("clip_a", "空镜"), card("clip_b", "补拍")]),
                         [])

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


    def test_a_first_generation_segment_is_silent_wherever_it_sits(self):
        # A card made with no context has nothing pinned at its head, so equal frame
        # counts are normal even after it was dragged into the middle of the film.
        segments = [{"label": "Shot 2", "latent_frames": 124, "frames": 119},
                    {"label": "Shot 1", "latent_frames": 243, "frames": 243, "is_initial": True},
                    {"label": "Shot 3", "latent_frames": 124, "frames": 119}]
        self.assertEqual(lb.seam_warnings(segments), [])

    def test_a_segment_without_the_initial_marker_is_still_judged(self):
        # Only the marker excuses equal frame counts; an unlabelled middle segment is
        # still read as a continuation whose frames were never cut.
        self.assertEqual(len(lb.seam_warnings([
            {"label": "Shot 1", "latent_frames": 124, "frames": 124},
            {"label": "Shot 2", "latent_frames": 124, "frames": 124, "is_initial": False}])), 1)


class TestInitialGenerationMarker(unittest.TestCase):
    """Both Pickers leave a no-context generation in the parent field."""

    def test_dual_picker_initial_tag_is_recognised(self):
        self.assertTrue(lb.is_initial_generation("[INITIAL]"))

    def test_clip_bin_picker_initial_tag_is_recognised(self):
        self.assertTrue(lb.is_initial_generation("[INITIAL_GENERATION]"))

    def test_spaces_and_case_do_not_hide_the_tag(self):
        self.assertTrue(lb.is_initial_generation("  [initial]  "))

    def test_a_real_parent_is_not_initial(self):
        self.assertFalse(lb.is_initial_generation("clip_20261004_022730_609522_Shot1"))

    def test_a_missing_parent_is_not_treated_as_initial(self):
        # An unwired lineage says nothing, so the seam check keeps its teeth.
        self.assertFalse(lb.is_initial_generation(""))
        self.assertFalse(lb.is_initial_generation(None))


class TestConcatList(unittest.TestCase):
    def test_paths_are_forward_slashed_and_quote_escaped(self):
        text = lb.concat_list_text([r"C:\out\it's a shot.mp4", "/tmp/plain.mp4"])
        self.assertIn("file 'C:/out/it'\\''s a shot.mp4'", text)
        self.assertIn("file '/tmp/plain.mp4'", text)
        self.assertTrue(text.startswith("ffconcat version 1.0"))


class TestPlaybackSpeed(unittest.TestCase):
    def test_presets_match_the_cutting_nodes(self):
        self.assertEqual(lb.parse_playback_speed("1.0x"), 1.0)
        self.assertEqual(lb.parse_playback_speed("0.75x"), 0.75)
        self.assertEqual(lb.parse_playback_speed("0.5x"), 0.5)

    def test_custom_uses_the_same_one_decimal_rule(self):
        self.assertEqual(lb.parse_playback_speed("custom", 0.62), 0.6)
        for bad in (0, -0.5, 1.1, "fast"):
            with self.assertRaises(ValueError):
                lb.parse_playback_speed("custom", bad)

    def test_output_frame_rate_preserves_rendered_frames(self):
        self.assertEqual(lb.output_frame_rate(24, 1.0), 24.0)
        self.assertEqual(lb.output_frame_rate(24, 0.5), 48.0)
        self.assertEqual(lb.output_frame_rate(24, 0.75), 32.0)
        self.assertEqual(lb.output_frame_rate(24, 0.1), 240.0)

    def test_tempo_chain_keeps_every_stage_in_the_portable_range(self):
        chain = lb.atempo_filter(10.0)
        stages = [float(item.split("=")[1]) for item in chain.split(",")]
        self.assertTrue(all(0.5 <= stage <= 2.0 for stage in stages))
        product = 1.0
        for stage in stages:
            product *= stage
        self.assertAlmostEqual(product, 10.0)

    def test_reencode_command_retimes_video_and_audio_together(self):
        out_dir = _support.make_temp_dir("cs_long_cmd")
        output_path = os.path.join(out_dir, "film.mp4")
        completed = mock.Mock(returncode=0, stderr="")

        def fake_run(cmd, **kwargs):
            with open(cmd[-1], "wb") as stream:
                stream.write(b"fake")
            return completed

        try:
            with mock.patch.object(lb.shutil, "which", return_value="ffmpeg"), \
                    mock.patch.object(lb.subprocess, "run", side_effect=fake_run) as run:
                method, _ = lb.concat_videos(
                    [os.path.join(out_dir, "part.mp4")], output_path, lb.JOIN_REENCODE,
                    fps=48.0, has_audio=True, output_speed=2.0)
            command = run.call_args[0][0]
            self.assertEqual(method, "reencode")
            self.assertIn("setpts=(PTS-STARTPTS)/2.00000000,fps=48.0", command)
            self.assertIn("atempo=2.000000", command)
            self.assertNotIn("-r", command)
        finally:
            _support.remove_temp_dir(out_dir)


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

        def fake_concat(paths, output_path, mode, fps=24.0, has_audio=False, output_speed=1.0):
            self.calls.append({"paths": paths, "mode": mode, "fps": fps,
                               "has_audio": has_audio, "output_speed": output_speed})
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
        self.assertEqual(self.calls[0]["output_speed"], 1.0)
        self.assertEqual(self.calls[0]["fps"], 24.0)
        self.assertEqual(result["output_fps"], 24.0)
        self.assertEqual(result["total_frames"], 357)
        self.assertEqual(result["join_method"], "copy")
        self.assertEqual(result["warnings"], [])
        self.assertIn(os.path.join("h3_long", "Proj"), result["path"])
        self.assertTrue(os.path.isfile(result["path"]))
        self.assertIn("3 段", result["report"])

    def test_existing_complete_probe_cache_avoids_remeasuring_segments(self):
        self.add_card("Proj", "clip_a", "Shot 1", "")
        clip_dir = os.path.join(self.store, "Proj", "clip_a")
        video_path = os.path.join(clip_dir, "video_二采.mp4")
        measured = self.probes.pop(video_path)
        stat = os.stat(video_path)
        meta_path = os.path.join(clip_dir, "meta.json")
        with open(meta_path, "r", encoding="utf-8") as stream:
            meta = json.load(stream)
        meta["video_probe"] = dict(measured, file="video_二采.mp4",
                                   size=int(stat.st_size), mtime=int(stat.st_mtime))
        with open(meta_path, "w", encoding="utf-8") as stream:
            json.dump(meta, stream, ensure_ascii=False)

        result = lb.build_long_video("Proj")

        self.assertEqual(result["segments"][0]["width"], measured["width"])
        self.assertEqual(result["segments"][0]["sample_rate"], measured["sample_rate"])
        self.assertEqual(self.calls[0]["mode"], lb.JOIN_COPY)

    def test_slowed_cutting_project_is_restored_while_joining(self):
        self.add_card("Proj", "clip_a", "Shot 1", "", duration=119 / 24.0)
        result = lb.build_long_video("Proj", playback_speed="0.5x")
        self.assertEqual(self.calls[0]["mode"], lb.JOIN_REENCODE)
        self.assertEqual(self.calls[0]["output_speed"], 2.0)
        self.assertEqual(self.calls[0]["fps"], 48.0)
        self.assertEqual(result["playback_speed"], 0.5)
        self.assertEqual(result["output_speed"], 2.0)
        self.assertEqual(result["output_fps"], 48.0)
        self.assertEqual(result["total_frames"], 119)
        self.assertAlmostEqual(result["duration_seconds"], (119 / 24.0) / 2, places=3)
        self.assertIn("原速恢复：切片 0.50x → 成片 2.0000x", result["report"])
        self.assertIn("基准 24.000fps ÷ 切片 0.50x = 48.000fps", result["report"])

    def test_copy_mode_rejects_speed_restoration(self):
        self.add_card("Proj", "clip_a", "Shot 1", "")
        with self.assertRaises(ValueError) as caught:
            lb.build_long_video("Proj", join_mode=lb.JOIN_COPY, playback_speed="0.75x")
        self.assertIn("恢复原速", str(caught.exception))
        self.assertEqual(self.calls, [])

    def test_the_dragged_card_order_is_the_order_that_is_joined(self):
        self.add_card("Proj", "clip_a", "Shot 1", "")
        self.add_card("Proj", "clip_b", "Shot 2", "clip_a")
        self.add_card("Proj", "clip_c", "Shot 3", "clip_b")
        result = lb.build_long_video("Proj", clip_order="clip_b,clip_a,clip_c")
        self.assertEqual([s["clip_id"] for s in result["segments"]],
                         ["clip_b", "clip_a", "clip_c"])
        paths = [p.replace("\\", "/") for p in self.calls[0]["paths"]]
        self.assertEqual([p.split("/")[-2] for p in paths], ["clip_b", "clip_a", "clip_c"])

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

    def test_a_card_without_archived_video_is_skipped_and_named(self):
        self.add_card("Proj", "clip_a", "Shot 1", "")
        self.add_card("Proj", "clip_b", "Shot 2", "clip_a", video=None)
        result = lb.build_long_video("Proj")
        self.assertEqual(len(result["segments"]), 1)
        self.assertTrue(any("Shot 2" in w and "跳过" in w for w in result["warnings"]))

    def test_a_card_switched_off_in_the_panel_is_not_joined(self):
        self.add_card("Proj", "clip_a", "Shot 1", "")
        self.add_card("Proj", "clip_b", "Shot 2", "clip_a")
        self.add_card("Proj", "clip_c", "Shot 3", "clip_b")
        result = lb.build_long_video("Proj", exclude_clips="clip_b")
        self.assertEqual(len(self.calls[0]["paths"]), 2)
        self.assertFalse(any("clip_b" in path for path in self.calls[0]["paths"]))
        self.assertEqual([s["clip_id"] for s in result["segments"]], ["clip_a", "clip_c"])
        # Leaving a take out on purpose is not a hole in the shot numbers.
        self.assertFalse(any("库里没有" in w for w in result["warnings"]))

    def test_a_deleted_take_leaves_a_warning_about_the_numbering(self):
        self.add_card("Proj", "clip_a", "Shot 1", "")
        self.add_card("Proj", "clip_c", "Shot 3", "clip_a")
        result = lb.build_long_video("Proj")
        self.assertEqual(len(result["segments"]), 2)
        self.assertTrue(any("库里没有 Shot 2" in w for w in result["warnings"]))

    def test_the_result_is_addressable_by_the_inline_preview(self):
        # ui.PreviewVideo needs filename + subfolder under ComfyUI's output folder,
        # which is what replaced the filename/total_frames/duration sockets.
        self.add_card("Proj", "clip_a", "Shot 1", "")
        result = lb.build_long_video("Proj")
        self.assertEqual(result["subfolder"].replace("\\", "/"), "h3_long/Proj")
        self.assertTrue(result["filename"].endswith(".mp4"))
        self.assertEqual(os.path.join(self.out, result["subfolder"].replace("/", os.sep),
                                      result["filename"]), result["path"])

    def test_untrimmed_middle_segment_is_reported_in_the_report(self):
        self.add_card("Proj", "clip_a", "Shot 1", "")
        self.add_card("Proj", "clip_b", "Shot 2", "clip_a", probed_frames=124)
        result = lb.build_long_video("Proj")
        self.assertTrue(any("Shot 2" in w and "Trim" in w for w in result["warnings"]))
        self.assertIn("注意：", result["report"])

    def test_a_first_generation_card_moved_into_the_film_is_not_warned(self):
        # The real shape of the complaint: Shot 1 was made with no context, so its
        # video is exactly as long as its latent, and that is correct wherever it is
        # joined - it must not be reported as an untrimmed seam.
        self.add_card("Proj", "clip_a", "Shot 1", "[INITIAL]", frames=243, probed_frames=243)
        self.add_card("Proj", "clip_b", "Shot 2", "clip_a")
        self.add_card("Proj", "clip_c", "Shot 3", "clip_b")
        result = lb.build_long_video("Proj", clip_order="clip_b,clip_a,clip_c")
        self.assertEqual([s["clip_id"] for s in result["segments"]], ["clip_b", "clip_a", "clip_c"])
        self.assertTrue(result["segments"][1]["is_initial"])
        self.assertFalse(any("Trim" in w for w in result["warnings"]))

    def test_empty_project_fails_clearly(self):
        with self.assertRaises(ValueError) as caught:
            lb.build_long_video("Proj")
        self.assertIn("没有可拼接的镜头", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
