"""Saver-format isolation across storage, galleries and Picker execution."""
import os
import shutil
import sys
import unittest
from unittest import mock
import torch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _support
_support.load_clipbin_package()
cbm = _support.load_clipbin_module("clip_bin_manager")
dual = _support.load_clipbin_module("dual_manager")
api = _support.load_clipbin_module("clip_bin_api")
shared = _support.load_clipbin_module("_shared")
_support.ensure_comfy_on_path()
nodes = _support.load_clipbin_module("nodes")
dual_nodes = _support.load_clipbin_module("dual_nodes")

class IsolationFixture(unittest.TestCase):
    def setUp(self):
        self.store = _support.make_temp_dir("cs_isolation")
        self.patch = mock.patch.object(cbm, "get_base_bin_dir", return_value=self.store)
        self.patch.start()
        self.video = torch.ones(1, 3, 7, 8, 16)
        self.audio = torch.zeros(1, 32, 2, 42)
        self.latent = shared.pack_av_latent(self.video, self.audio)
    def tearDown(self):
        self.patch.stop()
        _support.remove_temp_dir(self.store)
    def single(self, project="Mixed", shot="Single"):
        return cbm.save_clip_asset(self.video, self.audio, None, project_name=project,
                                  shot_tag=shot, save_video=False)
    def dual(self, project="Mixed", pass_b=False, second_only=False):
        return dual.save_dual_clip_asset(
            latent_a=None if second_only else self.latent,
            latent_b=self.latent if pass_b or second_only else None,
            project_name=project, shot_tag="Dual", save_video=False)
    def select(self, kind, project="Mixed", **kwargs):
        cls = nodes.MiniMaxClipBinPickerNode if kind == "single" else dual_nodes.MiniMaxClipBinDualPickerNode
        return cls.execute(project_name=project, **kwargs).args

class TestSaverFormat(IsolationFixture):
    def test_formats_are_detected_without_metadata_migration(self):
        _, one, _ = self.single()
        _, two, _ = self.dual()
        self.assertEqual(cbm.clip_asset_kind(one), "single")
        self.assertEqual(cbm.clip_asset_kind(two), "dual")
        self.assertEqual(cbm.clip_asset_kind(os.path.join(self.store, "missing")), "")
    def test_dual_loader_rejects_ordinary_saved_latent(self):
        meta, _, _ = self.single()
        with self.assertRaisesRegex(ValueError, "Dual Clip Saver"):
            dual.load_dual_clip_asset("Mixed", meta.clip_id)
    def test_single_loader_rejects_first_pass_only_dual(self):
        meta, _, _ = self.dual()
        with self.assertRaisesRegex(ValueError, "普通 Clip Bin Saver"):
            cbm.load_clip_asset("Mixed", meta.clip_id)
    def test_both_loaders_reject_ambiguous_folders(self):
        meta, folder, _ = self.single()
        shutil.copyfile(os.path.join(folder, "latent.safetensors"), os.path.join(folder, "latent_一采.safetensors"))
        self.assertEqual(cbm.clip_asset_kind(folder), "")
        for loader in (cbm.load_clip_asset, dual.load_dual_clip_asset):
            with self.subTest(loader=loader.__name__), self.assertRaises(ValueError):
                loader("Mixed", meta.clip_id)
    def test_second_pass_only_is_still_dual(self):
        meta, folder, _ = self.dual(second_only=True)
        self.assertEqual(cbm.clip_asset_kind(folder), "dual")
        loaded = dual.load_dual_clip_asset("Mixed", meta.clip_id)
        self.assertIsNone(loaded["variants"]["一采"]["latent"])
        self.assertTrue(loaded["variants"]["二采"]["has_latent"])

class TestFilteredLists(IsolationFixture):
    def test_galleries_and_shared_index(self):
        one, _, _ = self.single()
        two, _, _ = self.dual()
        for kind, expected in (("single", [one.clip_id]), ("dual", [two.clip_id])):
            result = api.get_project_clips_api("Mixed", asset_kind=kind)
            self.assertEqual([c["clip_id"] for c in result["clips"]], expected)
            self.assertEqual(result["total_clips"], 1)
        self.assertEqual(api.get_project_clips_api("Mixed")["total_clips"], 2)
        self.assertEqual(cbm.load_project_index("Mixed")["total_clips"], 2)
    def test_project_counts_and_covers(self):
        _, single_dir, _ = self.single()
        _, dual_dir, _ = self.dual()
        for kind, expected in (("single", single_dir), ("dual", dual_dir)):
            listing = api.list_projects_api(asset_kind=kind)["projects"]
            project = next(p for p in listing if p["name"] == "Mixed")
            self.assertEqual(project["clips"], 1)
            self.assertEqual(project["total_clips"], 2)
            self.assertIn(os.path.basename(expected), project["cover_url"])
    def test_foreign_only_project_stays_selectable_but_empty(self):
        self.dual(project="DualOnly")
        project = api.list_projects_api(asset_kind="single")["projects"][0]
        self.assertEqual(project["name"], "DualOnly")
        self.assertEqual(project["clips"], 0)
        self.assertEqual(project["cover_url"], "")
    def test_rebuilt_index_keeps_isolation_and_existing_files(self):
        one, folder, _ = self.single()
        two, _, _ = self.dual()
        before = sorted(os.listdir(folder))
        os.remove(cbm._get_index_path("Mixed"))
        self.assertEqual(api.get_project_clips_api("Mixed", asset_kind="single")["clips"][0]["clip_id"], one.clip_id)
        self.assertEqual(api.get_project_clips_api("Mixed", asset_kind="dual")["clips"][0]["clip_id"], two.clip_id)
        self.assertEqual(sorted(os.listdir(folder)), before)
    def test_invalid_filter_does_not_expose_all_cards(self):
        self.single()
        with self.assertRaises(ValueError):
            api.get_project_clips_api("Mixed", asset_kind="typo")

class TestPickerExecution(IsolationFixture):
    def test_single_latest_skips_newer_dual(self):
        one, _, _ = self.single()
        self.dual()
        self.assertEqual(self.select("single")[4], one.clip_id)
    def test_dual_latest_skips_newer_single(self):
        two, _, _ = self.dual()
        self.single()
        self.assertEqual(self.select("dual")[4], two.clip_id)
    def test_auto_uses_initial_if_only_foreign_cards_exist(self):
        self.dual(project="DualOnly")
        self.single(project="SingleOnly")
        self.assertIsNone(self.select("single", project="DualOnly")[0])
        result = self.select("dual", project="SingleOnly")
        self.assertIsNone(result[0])
        self.assertIsNone(result[1])
    def test_strict_rejects_foreign_only_projects(self):
        self.dual(project="DualOnly")
        self.single(project="SingleOnly")
        for kind, project in (("single", "DualOnly"), ("dual", "SingleOnly")):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.select(kind, project=project, mode="Strict Chaining")
    def test_explicit_foreign_id_cannot_bypass_filter(self):
        one, _, _ = self.single()
        two, _, _ = self.dual()
        for kind, foreign in (("single", two.clip_id), ("dual", one.clip_id)):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.select(kind, clip_selection=foreign)
    def test_explicit_foreign_id_in_foreign_only_project_is_not_initial(self):
        one, _, _ = self.single(project="SingleOnly")
        two, _, _ = self.dual(project="DualOnly")
        for kind, project, clip_id in (("single", "DualOnly", two.clip_id),
                                       ("dual", "SingleOnly", one.clip_id)):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.select(kind, project=project, clip_selection=clip_id)
    def test_legacy_path_values_cannot_override_project_selection(self):
        one, single_dir, _ = self.single(project="SingleOnly")
        two, dual_dir, _ = self.dual(project="DualOnly")
        self.assertEqual(self.select("single", project="SingleOnly", custom_clip_path=dual_dir)[4], one.clip_id)
        self.assertEqual(self.select("dual", project="DualOnly", custom_clip_path=single_dir)[4], two.clip_id)
    def test_absolute_paths_in_selection_are_not_loaded(self):
        _, single_dir, _ = self.single()
        _, dual_dir, _ = self.dual()
        for kind, path in (("single", single_dir), ("dual", dual_dir)):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.select(kind, clip_selection=path)
    def test_legacy_path_does_not_override_force_initial(self):
        _, single_dir, _ = self.single()
        _, dual_dir, _ = self.dual()
        for kind, path in (("single", single_dir), ("dual", dual_dir)):
            self.assertIsNone(self.select(kind, mode="Force Initial", custom_clip_path=path)[0])
    def test_dual_disk_scan_does_not_reintroduce_single(self):
        self.single()
        with mock.patch.object(dual_nodes, "load_project_index", side_effect=OSError("index unavailable")):
            self.assertIsNone(self.select("dual")[0])
    def test_dual_disk_scan_selects_dual_only(self):
        two, _, _ = self.dual()
        self.single()
        with mock.patch.object(dual_nodes, "load_project_index", side_effect=OSError("index unavailable")):
            self.assertEqual(self.select("dual")[4], two.clip_id)
    def test_force_initial_reads_neither_format(self):
        self.single()
        self.dual()
        for kind in ("single", "dual"):
            self.assertIsNone(self.select(kind, mode="Force Initial")[0])

if __name__ == "__main__":
    unittest.main()
