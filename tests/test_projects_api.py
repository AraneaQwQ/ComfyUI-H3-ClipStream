"""The project list behind the Long Builder dropdown.

The panel asks which folder to read instead of making the user type a project name,
so it may only offer bins that actually hold archived video. These tests drive the
real index rebuild against a throwaway media pool and check what gets offered.
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


class TestProjectListing(unittest.TestCase):
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

    def test_only_bins_with_archived_video_are_offered(self):
        self.add_card("Movie", "clip_a", "Shot 1")
        self.add_card("Movie", "clip_b", "Shot 2")
        self.add_card("LatentOnly", "clip_c", "Shot 1", video=None)
        data = api.list_video_projects_api()
        self.assertEqual([p["name"] for p in data["projects"]], ["Movie"])
        self.assertEqual(data["projects"][0]["clips"], 2)
        self.assertEqual(data["projects"][0]["videos"], 2)

    def test_a_card_whose_video_file_was_deleted_is_not_counted(self):
        self.add_card("Movie", "clip_a", "Shot 1")
        os.remove(os.path.join(self.store, "Movie", "clip_a", "video_二采.mp4"))
        self.assertEqual(api.list_video_projects_api()["projects"], [])

    def test_a_video_found_by_scanning_the_card_still_counts(self):
        # Older cards do not always record video_file; the gallery finds the file by
        # name, and the dropdown has to agree with the gallery.
        self.add_card("Movie", "clip_a", "Shot 1", declared=False)
        data = api.list_video_projects_api()
        self.assertEqual([p["name"] for p in data["projects"]], ["Movie"])

    def test_an_empty_pool_offers_nothing(self):
        self.assertEqual(api.list_video_projects_api()["projects"], [])


if __name__ == "__main__":
    unittest.main()
