"""Path safety for the gallery HTTP API and cache-busting preview URLs.

The delete route takes a project name and a clip id straight from the browser, so
the containment checks in checked_asset_dir are what stop a request from deleting
outside the media pool. The versioned preview URL is what stops a re-saved card
from showing a stale thumbnail.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _support

ap = _support.load_standalone(os.path.join("clipbin", "asset_paths.py"), "clipbin_asset_paths")


class TestCheckedAssetDir(unittest.TestCase):
    def setUp(self):
        self.base = _support.make_temp_dir("cs_paths")
        self.project = os.path.join(self.base, "My Project")
        self.asset = os.path.join(self.project, "clip_20261002_Shot1")
        os.makedirs(self.asset)

    def tearDown(self):
        _support.remove_temp_dir(self.base)

    def test_accepts_a_card_directly_inside_the_project(self):
        self.assertEqual(
            os.path.normcase(ap.checked_asset_dir(self.base, self.project, "clip_20261002_Shot1")),
            os.path.normcase(self.asset))

    def test_rejects_ids_that_cannot_be_a_single_directory(self):
        for bad in ("", ".", "..", "a/b", "a\\b", "a:b", "x\x00", "sub/clip"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                ap.checked_asset_dir(self.base, self.project, bad)

    def test_rejects_a_project_nested_below_the_store(self):
        nested = os.path.join(self.project, "deeper")
        os.makedirs(nested)
        with self.assertRaises(ValueError):
            ap.checked_asset_dir(self.base, nested, "clip_1")

    def test_rejects_a_card_that_is_a_link(self):
        target = os.path.join(self.base, "outside_card")
        os.makedirs(target)
        link = os.path.join(self.project, "linked_card")
        try:
            os.symlink(target, link, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("cannot create a directory link here: %s" % exc)
        with self.assertRaises(ValueError):
            ap.checked_asset_dir(self.base, self.project, "linked_card")


class TestPreviewUrl(unittest.TestCase):
    def setUp(self):
        self.dir = _support.make_temp_dir("cs_url")
        self.card = os.path.join(self.dir, "preview.png")
        with open(self.card, "wb") as handle:
            handle.write(b"first")

    def tearDown(self):
        _support.remove_temp_dir(self.dir)

    def test_is_a_view_request_for_the_output_folder(self):
        url = ap.preview_url(self.card, "h3-clipstream/Proj")
        self.assertTrue(url.startswith("/view?"))
        self.assertIn("filename=preview.png", url)
        self.assertIn("subfolder=h3-clipstream%2FProj", url)

    def test_version_changes_when_the_card_is_rewritten(self):
        before = ap.preview_url(self.card, "")
        with open(self.card, "wb") as handle:
            handle.write(b"a different and longer card")
        after = ap.preview_url(self.card, "")
        self.assertNotEqual(before, after)
        self.assertIn("v=", after)


if __name__ == "__main__":
    unittest.main()
