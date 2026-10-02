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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _support

_support.load_clipbin_package()
cbm = _support.load_clipbin_module("clip_bin_manager")
api = _support.load_clipbin_module("clip_bin_api")


class BinFixture(unittest.TestCase):
    """A throwaway media pool plus the card writer both test classes need."""

    def setUp(self):
        self.store = _support.make_temp_dir("cs_projects")
        self._real_base = cbm.get_base_bin_dir
        cbm.get_base_bin_dir = lambda: self.store

    def tearDown(self):
        cbm.get_base_bin_dir = self._real_base
        _support.remove_temp_dir(self.store)

    def add_card(self, project, clip_id, shot, video="video_二采.mp4", declared=True):
        clip_dir = os.path.join(self.store, project, clip_id)
        os.makedirs(clip_dir, exist_ok=True)
        if video:
            with open(os.path.join(clip_dir, video), "wb") as stream:
                stream.write(b"x")
        meta = {"clip_id": clip_id, "project_name": project, "shot_tag": shot}
        if declared and video:
            meta["video_file"] = video
        with open(os.path.join(clip_dir, "meta.json"), "w", encoding="utf-8") as stream:
            json.dump(meta, stream, ensure_ascii=False)

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
        self.assertEqual(api.list_projects_api()["projects"],
                         [{"name": "Default_Project", "clips": 0, "videos": 0}])
        self.assertEqual(api.list_projects_api(videos_only=True)["projects"], [])


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


if __name__ == "__main__":
    unittest.main()
