"""The project menu behind both bin panels.

The panels ask which folder to read instead of making the user type a project name,
so the backend has to list what already exists, create a bin on request, and delete one
when a story is abandoned. The
Picker offers every bin - an empty one is where the next shot goes - while the Long
Builder only wants bins that hold archived video. These tests drive the real index
rebuild against a throwaway media pool.
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
api = _support.load_clipbin_module("clip_bin_api")
lb = _support.load_clipbin_module("long_builder")


class BinFixture(unittest.TestCase):
    """A throwaway media pool plus the card writer both test classes need."""

    def setUp(self):
        self.store = _support.make_temp_dir("cs_projects")
        self._real_base = cbm.get_base_bin_dir
        cbm.get_base_bin_dir = lambda: self.store

    def tearDown(self):
        cbm.get_base_bin_dir = self._real_base
        _support.remove_temp_dir(self.store)

    def add_card(self, project, clip_id, shot, video="video_二采.mp4", declared=True,
                 preview=False):
        clip_dir = os.path.join(self.store, project, clip_id)
        os.makedirs(clip_dir, exist_ok=True)
        if video:
            with open(os.path.join(clip_dir, video), "wb") as stream:
                stream.write(b"x")
        if preview:
            with open(os.path.join(clip_dir, "preview.png"), "wb") as stream:
                stream.write(b"png")
        meta = {"clip_id": clip_id, "project_name": project, "shot_tag": shot}
        if declared and video:
            meta["video_file"] = video
        with open(os.path.join(clip_dir, "meta.json"), "w", encoding="utf-8") as stream:
            json.dump(meta, stream, ensure_ascii=False)

    def write_index(self, project, updated, clip_ids):
        path = os.path.join(self.store, project, ".bin_index.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        index = {
            "project_name": project,
            "last_updated": updated,
            "total_clips": len(clip_ids),
            "clips": [{"clip_id": c, "project_name": project} for c in clip_ids],
        }
        with open(path, "w", encoding="utf-8") as stream:
            json.dump(index, stream, ensure_ascii=False)

    def names(self, **kwargs):
        return [p["name"] for p in api.list_projects_api(**kwargs)["projects"]]

    def counts(self, name):
        for item in api.list_projects_api()["projects"]:
            if item["name"] == name:
                return (item["clips"], item["videos"])
        self.fail("project %r is not in the menu" % name)


class TestProjectListing(BinFixture):
    def test_every_bin_is_listed_with_its_card_and_video_counts(self):
        self.add_card("Movie", "clip_a", "Shot 1")
        self.add_card("Movie", "clip_b", "Shot 2", video=None)
        self.add_card("Fresh", "clip_c", "Shot 1", video=None)
        self.assertEqual(self.names(), ["Fresh", "Movie"])
        self.assertEqual(self.counts("Movie"), (2, 1))
        self.assertEqual(self.counts("Fresh"), (1, 0))

    def test_videos_only_offers_bins_that_can_become_a_film(self):
        self.add_card("Movie", "clip_a", "Shot 1")
        self.add_card("Movie", "clip_b", "Shot 2")
        self.add_card("LatentOnly", "clip_c", "Shot 1", video=None)
        data = api.list_projects_api(videos_only=True)
        self.assertEqual([p["name"] for p in data["projects"]], ["Movie"])
        self.assertEqual(data["projects"][0]["clips"], 2)
        self.assertEqual(data["projects"][0]["videos"], 2)

    def test_a_card_whose_video_file_was_deleted_is_not_counted(self):
        self.add_card("Movie", "clip_a", "Shot 1")
        os.remove(os.path.join(self.store, "Movie", "clip_a", "video_二采.mp4"))
        self.assertEqual(api.list_projects_api(videos_only=True)["projects"], [])
        self.assertEqual(self.counts("Movie"), (1, 0))

    def test_a_video_found_by_scanning_the_card_still_counts(self):
        # Older cards do not always record video_file; the gallery finds the file by
        # name, and the dropdown has to agree with the gallery.
        self.add_card("Movie", "clip_a", "Shot 1", declared=False)
        self.assertEqual(self.names(videos_only=True), ["Movie"])

    def test_an_empty_pool_offers_the_default_bin_but_no_film(self):
        empty = api.list_projects_api()["projects"]
        self.assertEqual([(p["name"], p["clips"], p["videos"]) for p in empty],
                         [("Default_Project", 0, 0)])
        self.assertEqual(api.list_projects_api(videos_only=True)["projects"], [])

    def test_the_menu_gets_an_update_time_and_a_cover(self):
        # The card menu draws a cover and "last changed" on each project, so the
        # list endpoint has to carry both without asking for every card again.
        self.add_card("Movie", "clip_a", "Shot 1", preview=True)
        self.write_index("Movie", "2026-10-28 14:32:18", ["clip_a"])
        project = api.list_projects_api()["projects"][0]
        self.assertEqual(project["updated_at"], "2026-10-28 14:32:18")
        self.assertTrue(project["cover_url"].startswith("/view?"))
        self.assertIn("preview.png", project["cover_url"])

    def test_a_bin_without_a_preview_still_lists_without_a_cover(self):
        self.add_card("Movie", "clip_a", "Shot 1")
        project = api.list_projects_api()["projects"][0]
        self.assertEqual(project["cover_url"], "")


class TestProjectRenaming(BinFixture):
    """Renaming a bin moves its folder, so covers and cards follow without a rewrite."""

    def test_renaming_moves_the_folder_and_the_index_name(self):
        self.add_card("Movie", "clip_a", "Shot 1")
        result = cbm.rename_project("Movie", "正片 01")
        self.assertEqual(result, {"old": "Movie", "name": "正片 01", "renamed": True})
        self.assertFalse(os.path.exists(os.path.join(self.store, "Movie")))
        self.assertTrue(os.path.isdir(os.path.join(self.store, "正片 01", "clip_a")))
        with open(os.path.join(self.store, "正片 01", ".bin_index.json"),
                  "r", encoding="utf-8") as stream:
            index = json.load(stream)
        self.assertEqual(index["project_name"], "正片 01")
        self.assertEqual(self.names(), ["正片 01"])
        self.assertEqual(self.counts("正片 01"), (1, 1))

    def test_the_rename_keeps_the_cards_and_the_cover(self):
        self.add_card("Movie", "clip_a", "Shot 1", preview=True)
        cbm.rename_project("Movie", "正片 01")
        project = api.list_projects_api()["projects"][0]
        self.assertEqual(project["name"], "正片 01")
        self.assertIn("preview.png", project["cover_url"])

    def test_an_existing_name_is_never_overwritten(self):
        self.add_card("Movie", "clip_a", "Shot 1")
        self.add_card("Other", "clip_b", "Shot 1")
        with self.assertRaises(ValueError):
            cbm.rename_project("Movie", "Other")
        self.assertTrue(os.path.isdir(os.path.join(self.store, "Movie")))
        self.assertEqual(self.names(), ["Movie", "Other"])

    def test_a_missing_project_is_refused_not_created(self):
        with self.assertRaises(ValueError):
            cbm.rename_project("Ghost", "New")
        self.assertFalse(os.path.exists(os.path.join(self.store, "New")))

    def test_renaming_a_name_to_itself_changes_nothing(self):
        self.add_card("Movie", "clip_a", "Shot 1")
        self.assertEqual(cbm.rename_project("Movie", "Movie"),
                         {"old": "Movie", "name": "Movie", "renamed": False})
        self.assertEqual(self.names(), ["Movie"])

    def test_the_new_name_is_the_folder_name_that_was_written(self):
        self.add_card("Movie", "clip_a", "Shot 1")
        result = cbm.rename_project("Movie", "  我的/项目: 第一集  ")
        self.assertEqual(result["name"], "我的项目 第一集")
        self.assertTrue(os.path.isdir(os.path.join(self.store, "我的项目 第一集")))

    def test_a_name_without_letters_or_digits_is_refused(self):
        self.add_card("Movie", "clip_a", "Shot 1")
        for typed in ("", "   ", "///"):
            with self.assertRaises(ValueError):
                cbm.rename_project("Movie", typed)

    def test_an_overlong_name_is_refused(self):
        self.add_card("Movie", "clip_a", "Shot 1")
        with self.assertRaises(ValueError):
            cbm.rename_project("Movie", "x" * (cbm.MAX_PROJECT_NAME_LENGTH + 1))


class TestProjectCreation(BinFixture):
    def test_a_new_bin_is_created_and_shows_up_in_the_menu(self):
        result = cbm.create_project("科幻短片 01")
        self.assertEqual(result, {"name": "科幻短片 01", "created": True, "clips": 0})
        self.assertTrue(os.path.isdir(os.path.join(self.store, "科幻短片 01")))
        self.assertEqual(self.names(), ["科幻短片 01"])
        self.assertEqual(self.counts("科幻短片 01"), (0, 0))

    def test_a_new_bin_is_not_offered_to_the_long_builder(self):
        cbm.create_project("Fresh")
        self.assertEqual(self.names(videos_only=True), [])
        self.assertEqual(self.names(), ["Fresh"])

    def test_an_existing_name_is_selected_rather_than_duplicated(self):
        self.add_card("Movie", "clip_a", "Shot 1")
        result = cbm.create_project("Movie")
        self.assertEqual(result, {"name": "Movie", "created": False, "clips": 1})
        self.assertEqual(self.names(), ["Movie"])

    def test_the_name_returned_is_the_folder_name_that_was_written(self):
        # The panel writes back what the server answers, so the widget can never hold
        # a name that does not exist on disk.
        result = cbm.create_project("  我的/项目: 第一集  ")
        self.assertEqual(result["name"], "我的项目 第一集")
        self.assertTrue(os.path.isdir(os.path.join(self.store, "我的项目 第一集")))
        self.assertEqual(self.names(), ["我的项目 第一集"])

    def test_a_name_without_letters_or_digits_is_refused(self):
        for typed in ("", "   ", "///", "———"):
            with self.assertRaises(ValueError):
                cbm.create_project(typed)

    def test_an_overlong_name_is_refused(self):
        with self.assertRaises(ValueError):
            cbm.create_project("x" * (cbm.MAX_PROJECT_NAME_LENGTH + 1))


class TestProjectDeletion(BinFixture):
    """Deleting a whole bin, which is the mirror of creating one and just as final."""

    def test_deleting_a_bin_removes_the_folder_and_every_card_in_it(self):
        self.add_card("Movie", "clip_a", "Shot 1")
        self.add_card("Movie", "clip_b", "Shot 2")
        self.add_card("Other", "clip_c", "Shot 1")
        result = cbm.delete_project("Movie", "Movie")
        self.assertEqual(result, {"name": "Movie", "deleted": True, "clips": 2})
        self.assertFalse(os.path.exists(os.path.join(self.store, "Movie")))
        self.assertEqual(self.names(), ["Other"])

    def test_deleting_a_bin_takes_its_videos_out_of_the_long_builder(self):
        self.add_card("Movie", "clip_a", "Shot 1")
        self.assertEqual(self.names(videos_only=True), ["Movie"])
        cbm.delete_project("Movie", "Movie")
        self.assertEqual(self.names(videos_only=True), [])
        self.assertEqual(self.names(), ["Default_Project"])

    def test_the_confirm_name_has_to_match_the_bin_being_deleted(self):
        # A panel left open in another tab must not empty the wrong folder.
        self.add_card("Movie", "clip_a", "Shot 1")
        self.assertRaises(ValueError, cbm.delete_project, "Movie", "Other")
        self.assertRaises(ValueError, cbm.delete_project, "Movie", "")
        self.assertEqual(self.names(), ["Movie"])

    def test_a_name_without_letters_or_digits_is_rejected(self):
        self.assertRaises(ValueError, cbm.delete_project, "  /:*  ", "  /:*  ")

    def test_a_bin_that_is_already_gone_is_reported_not_raised(self):
        # Two panels can both press delete; the second one just learns it is gone.
        self.assertEqual(cbm.delete_project("Ghost", "Ghost"),
                         {"name": "Ghost", "deleted": False, "clips": 0})
        self.assertFalse(os.path.exists(os.path.join(self.store, "Ghost")))

    def test_the_sanitized_name_is_the_one_deleted(self):
        self.add_card("Movie", "clip_a", "Shot 1")
        result = cbm.delete_project("  Movie/  ", "Movie")
        self.assertEqual(result["name"], "Movie")
        self.assertTrue(result["deleted"])
        self.assertEqual(self.names(), ["Default_Project"])


class TestCardVideoProbe(BinFixture):
    """The Long Builder card shows the resolution and duration of the file it joins.

    A card records what a run generated, not what the archived MP4 turned out to be,
    so the panel needs measured numbers. ffprobe runs once per file and the result is
    cached in the card keyed by name, size and mtime; the flat video_* fields are that
    cache re-exported for the front end and are never written back into meta.json.
    Only a request that asks for a measurement pays for it, which is why these tests
    pass want_probe=True the way the Builder panel does.
    """

    def setUp(self):
        super().setUp()
        self.calls = []
        self._real_probe = api.probe_video_streams
        api.probe_video_streams = self._probe

    def tearDown(self):
        api.probe_video_streams = self._real_probe
        super().tearDown()

    def _probe(self, path):
        self.calls.append(path)
        return {"width": 1088, "height": 1920, "fps": 24.0, "frames": 149,
                "duration": 6.208, "frames_estimated": False, "has_audio": True,
                "sample_rate": 32000, "vcodec": "h264", "acodec": "aac"}

    def card(self, project="Proj", variant_policy=""):
        clips = api.get_project_clips_api(project, variant_policy, True)["clips"]
        self.assertEqual(len(clips), 1)
        return clips[0]

    def meta(self, project, clip_id):
        path = os.path.join(self.store, project, clip_id, "meta.json")
        with open(path, "r", encoding="utf-8") as stream:
            return json.load(stream)

    def test_a_card_reports_the_resolution_and_duration_of_its_video(self):
        self.add_card("Proj", "clip_a", "Shot 1")
        card = self.card()
        self.assertEqual((card["video_width"], card["video_height"]), (1088, 1920))
        self.assertAlmostEqual(card["video_duration_seconds"], 6.208)
        self.assertAlmostEqual(card["video_fps"], 24.0)
        self.assertEqual(self.calls,
                         [os.path.join(self.store, "Proj", "clip_a", "video_二采.mp4")])

    def test_the_measurement_is_cached_in_the_card(self):
        self.add_card("Proj", "clip_a", "Shot 1")
        first = self.card()
        second = self.card()
        self.assertEqual(len(self.calls), 1, "ffprobe should run once per file")
        self.assertEqual(second["video_width"], first["video_width"])
        self.assertEqual(self.meta("Proj", "clip_a")["video_probe"]["width"], 1088)

    def test_a_replaced_video_is_measured_again(self):
        self.add_card("Proj", "clip_a", "Shot 1")
        self.card()
        target = os.path.join(self.store, "Proj", "clip_a", "video_二采.mp4")
        with open(target, "wb") as stream:
            stream.write(b"x" * 4096)
        os.utime(target, (1000000, 1000000))
        self.card()
        self.assertEqual(len(self.calls), 2)

    def test_a_card_without_video_reports_nothing_and_caches_nothing(self):
        self.add_card("Proj", "clip_a", "Shot 1", video=None)
        card = self.card()
        self.assertEqual(card["video_width"], 0)
        self.assertEqual(card["video_duration_seconds"], 0.0)
        self.assertEqual(self.calls, [])
        self.assertNotIn("video_probe", self.meta("Proj", "clip_a"))

    def test_the_builder_policy_decides_which_variant_is_measured(self):
        # The numbers on the card have to be the numbers that end up in the film.
        clip_dir = os.path.join(self.store, "Proj", "clip_a")
        os.makedirs(clip_dir, exist_ok=True)
        for name in ("video_一采.mp4", "video_二采.mp4"):
            with open(os.path.join(clip_dir, name), "wb") as stream:
                stream.write(b"x")
        meta = {"clip_id": "clip_a", "project_name": "Proj", "shot_tag": "Shot 1",
                "video_file": "video_一采.mp4",
                "variants": {
                    "一采": {"has_video": True, "video_file": "video_一采.mp4", "frames": 124},
                    "二采": {"has_video": True, "video_file": "video_二采.mp4", "frames": 149}}}
        with open(os.path.join(clip_dir, "meta.json"), "w", encoding="utf-8") as stream:
            json.dump(meta, stream, ensure_ascii=False)

        self.card()
        self.assertTrue(self.calls[-1].endswith("video_一采.mp4"),
                        "the Pickers keep reporting the declared file")
        self.card()  # cached now: no second measurement
        self.assertEqual(len(self.calls), 1)
        self.card(variant_policy=lb.VARIANT_PREFER_UP)
        self.assertTrue(self.calls[-1].endswith("video_二采.mp4"))

    def test_a_picker_request_measures_nothing(self):
        # The Pickers never show these fields and already probe the duration above,
        # so they must not pay for a second ffprobe per card.
        self.add_card("Proj", "clip_a", "Shot 1")
        card = api.get_project_clips_api("Proj")["clips"][0]
        self.assertEqual(self.calls, [])
        self.assertNotIn("video_width", card)
        self.assertNotIn("video_duration_seconds", card)
        self.assertNotIn("video_probe", self.meta("Proj", "clip_a"))


class TestProjectFolderPath(BinFixture):
    def test_an_existing_project_resolves_without_creating(self):
        os.makedirs(os.path.join(self.store, "Movie"), exist_ok=True)
        self.assertEqual(cbm.existing_project_dir("Movie"),
                         os.path.join(self.store, "Movie"))

    def test_a_missing_project_is_refused_and_not_created(self):
        missing = os.path.join(self.store, "Never")
        with self.assertRaises(FileNotFoundError):
            cbm.existing_project_dir("Never")
        self.assertFalse(os.path.exists(missing), "opening a folder must not create a bin")


class TestLocalFolderRaisesExplorer(BinFixture):
    def setUp(self):
        super().setUp()
        self.folder = _support.load_clipbin_module("local_folder")

    def test_it_raises_the_new_explorer_window(self):
        raised = mock.MagicMock()
        windows = [(1, "Documents"), (2, "h3-clipstream"), (3, "Movie")]
        with mock.patch.object(self.folder, "os") as patched_os, \
                mock.patch.object(self.folder.platform, "system", return_value="Windows"), \
                mock.patch.object(self.folder, "_explorer_windows", side_effect=[windows, windows]), \
                mock.patch.object(self.folder, "_raise_explorer", raised):
            patched_os.path.realpath.side_effect = os.path.realpath
            self.folder.open_local_folder(os.path.join(self.store, "Movie"))
        patched_os.startfile.assert_called_once()
        raised.assert_called_once()
        self.assertEqual(raised.call_args.args[1], {1, 2, 3},
                         "only the windows already open are excluded from the lookup")

    def test_a_new_window_wins_over_a_reused_title_match(self):
        with mock.patch.object(self.folder, "_explorer_windows",
                               side_effect=[[(1, "Movie")], [(1, "Movie"), (2, "Other")]]):
            with mock.patch("ctypes.windll", mock.MagicMock(), create=True):
                self.assertTrue(self.folder._raise_explorer(
                    os.path.join(self.store, "Movie"), {1}, timeout=0.5))

    def test_no_window_appearing_is_not_an_error(self):
        with mock.patch.object(self.folder, "_explorer_windows", return_value=[]):
            self.assertFalse(self.folder._raise_explorer(self.store, set(), timeout=0.2))

if __name__ == "__main__":
    unittest.main()
