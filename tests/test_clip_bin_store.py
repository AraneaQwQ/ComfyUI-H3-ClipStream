"""Clip Bin storage round-trips: single card, dual card, index rebuild, deletion.

Everything the gallery shows is rebuilt from these files, so the tests drive the
real manager code against a throwaway media pool and check that a saved clip
comes back bit-identical and stays listed.
"""

import json
import os
import sys
import unittest

import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _support

_support.load_clipbin_package()
cbm = _support.load_clipbin_module("clip_bin_manager")
dual = _support.load_clipbin_module("dual_manager")
shared = _support.load_standalone(os.path.join("clipbin", "_shared.py"), "clipbin_shared")


def make_latent(seed=0, steps=7):
    v = torch.arange(1 * 3 * steps * 8 * 16, dtype=torch.float32).reshape(1, 3, steps, 8, 16) + seed
    a = torch.zeros(1, 32, 2, steps * 6, dtype=torch.float32) + seed
    return v, a, shared.pack_av_latent(v, a)


class StoreTestCase(unittest.TestCase):
    def setUp(self):
        self.store = _support.make_temp_dir("cs_store")
        self._real_base = cbm.get_base_bin_dir
        cbm.get_base_bin_dir = lambda: self.store

    def tearDown(self):
        cbm.get_base_bin_dir = self._real_base
        _support.remove_temp_dir(self.store)

    def save_one(self, project="Proj A", shot="Shot 1", seed=0, **kwargs):
        v, a, _ = make_latent(seed=seed)
        return cbm.save_clip_asset(v, a, None, project_name=project, shot_tag=shot,
                                   prompt="a prompt", save_video=False, **kwargs)


class TestSingleClipRoundTrip(StoreTestCase):
    def test_saved_clip_loads_back_identical(self):
        v, a, _ = make_latent()
        meta, clip_dir, preview = self.save_one()
        self.assertTrue(os.path.isfile(os.path.join(clip_dir, "latent.safetensors")))
        self.assertTrue(os.path.isfile(os.path.join(clip_dir, "meta.json")))
        self.assertTrue(os.path.isfile(os.path.join(clip_dir, "preview.png")))
        self.assertGreater(preview.size[0], 0)
        self.assertGreater(preview.size[1], 0)

        video, audio, tail, first, loaded_meta = cbm.load_clip_asset("Proj A", meta.clip_id)
        self.assertTrue(torch.equal(video, v))
        self.assertTrue(torch.equal(audio, a))
        self.assertEqual(loaded_meta["clip_id"], meta.clip_id)
        self.assertEqual(loaded_meta["shot_tag"], "Shot 1")
        self.assertEqual(loaded_meta["prompt"], "a prompt")

    def test_missing_card_is_reported_clearly(self):
        self.save_one()
        with self.assertRaises(FileNotFoundError):
            cbm.load_clip_asset("Proj A", "clip_not_in_the_bin")

    def test_frame_count_and_duration_follow_the_latent_grid(self):
        meta, _, _ = self.save_one()
        self.assertEqual(meta.frames, 22)
        self.assertEqual(meta.duration_seconds, round(22 / 24.0, 2))
        self.assertEqual(meta.duration_source, "computed")
        self.assertEqual(meta.resolution, [128, 64])
        self.assertFalse(meta.has_video)

    def test_project_index_lists_the_newest_first(self):
        first, _, _ = self.save_one(shot="Shot 1", seed=0)
        second, _, _ = self.save_one(shot="Shot 2", seed=1)
        index = cbm.load_project_index("Proj A")
        self.assertEqual(index["total_clips"], 2)
        self.assertEqual([c["clip_id"] for c in index["clips"]], [second.clip_id, first.clip_id])
        self.assertIn("Proj A", cbm.list_projects())

    def test_index_rebuilds_from_disk_when_it_is_lost(self):
        self.save_one()
        self.save_one(shot="Shot 2")
        index_path = cbm._get_index_path("Proj A")
        os.remove(index_path)
        rebuilt = cbm.load_project_index("Proj A")
        self.assertEqual(rebuilt["total_clips"], 2)
        self.assertTrue(os.path.isfile(index_path))

    def test_deleting_removes_the_card_and_the_entry(self):
        meta, clip_dir, _ = self.save_one()
        self.assertTrue(cbm.delete_clip_asset("Proj A", meta.clip_id))
        self.assertFalse(os.path.isdir(clip_dir))
        self.assertEqual(cbm.load_project_index("Proj A")["total_clips"], 0)

    def test_deleting_an_unknown_clip_reports_false_and_keeps_the_card(self):
        meta, clip_dir, _ = self.save_one()
        self.assertFalse(cbm.delete_clip_asset("Proj A", "clip_that_does_not_exist"))
        self.assertTrue(os.path.isdir(clip_dir))

    def test_shot_tags_are_sluged_into_the_card_id_and_stay_unique(self):
        first, first_dir, _ = self.save_one(shot="男主 回眸!")
        second, second_dir, _ = self.save_one(shot="男主 回眸!")
        self.assertEqual(os.path.basename(first_dir), first.clip_id)
        self.assertIn("_", first.clip_id)
        self.assertNotIn("!", first.clip_id)
        self.assertNotIn(" ", first.clip_id)
        self.assertNotEqual(first.clip_id, second.clip_id)
        self.assertEqual(first.shot_tag, "男主 回眸!")

    def test_meta_on_disk_matches_the_returned_meta(self):
        meta, clip_dir, _ = self.save_one()
        with open(os.path.join(clip_dir, "meta.json"), "r", encoding="utf-8") as handle:
            on_disk = json.load(handle)
        self.assertEqual(on_disk["clip_id"], meta.clip_id)
        self.assertEqual(on_disk["frames"], meta.frames)


class TestDualClipRoundTrip(StoreTestCase):
    def save_dual(self, project="Dual A", shot="Auto", with_b=True, seed=0):
        _, _, latent_a = make_latent(seed=seed)
        _, _, latent_b = make_latent(seed=seed + 1) if with_b else (None, None, None)
        return dual.save_dual_clip_asset(latent_a=latent_a, latent_b=latent_b,
                                        project_name=project, shot_tag=shot, save_video=False)

    def test_one_pass_card_reports_only_the_first_variant(self):
        meta, clip_dir, _ = self.save_dual(with_b=False)
        self.assertEqual(meta.variant_labels, ["一采"])
        self.assertFalse(os.path.isfile(os.path.join(clip_dir, "latent_二采.safetensors")))
        loaded = dual.load_dual_clip_asset("Dual A", meta.clip_id)
        self.assertTrue(loaded["variants"]["一采"]["has_latent"])
        self.assertIsNotNone(loaded["variants"]["一采"]["latent"])
        self.assertFalse(loaded["variants"]["二采"]["has_latent"])
        self.assertIsNone(loaded["variants"]["二采"]["latent"])

    def test_two_pass_card_returns_both_latents(self):
        meta, _, _ = self.save_dual(with_b=True)
        self.assertEqual(sorted(meta.variant_labels), ["一采", "二采"])
        loaded = dual.load_dual_clip_asset("Dual A", meta.clip_id)
        for variant in ("一采", "二采"):
            self.assertTrue(loaded["variants"][variant]["has_latent"], variant)
            video, audio = shared._unpack_latent(loaded["variants"][variant]["latent"])
            self.assertEqual(tuple(video.shape), (1, 3, 7, 8, 16), variant)
            self.assertEqual(tuple(audio.shape), (1, 32, 2, 42), variant)

    def test_variant_frames_are_recorded_per_pass(self):
        meta, _, _ = self.save_dual(with_b=True)
        for label in ("一采", "二采"):
            self.assertEqual(meta.variants[label].frames, 22)
            self.assertEqual(meta.variants[label].resolution, [128, 64])

    def test_a_card_needs_at_least_one_variant(self):
        with self.assertRaises(ValueError):
            dual.save_dual_clip_asset(latent_a=None, latent_b=None, project_name="Dual A")

    def test_auto_shot_tags_increment_per_project(self):
        first, _, _ = self.save_dual(shot="Auto (自动编号)")
        second, _, _ = self.save_dual(shot="Auto (自动编号)")
        other, _, _ = self.save_dual(project="Dual B", shot="Auto (自动编号)")
        self.assertEqual(first.shot_tag, "Shot 1")
        self.assertEqual(second.shot_tag, "Shot 2")
        self.assertEqual(other.shot_tag, "Shot 1")

    def test_dual_cards_share_the_project_index_with_single_cards(self):
        single, _, _ = self.save_one(project="Mixed")
        dual_meta, _, _ = self.save_dual(project="Mixed", with_b=False)
        ids = [c["clip_id"] for c in cbm.load_project_index("Mixed")["clips"]]
        self.assertEqual(sorted(ids), sorted([single.clip_id, dual_meta.clip_id]))


if __name__ == "__main__":
    unittest.main()
