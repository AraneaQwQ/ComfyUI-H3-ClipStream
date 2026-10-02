"""The node registry and the exact interface every shipped node exposes.

ComfyUI stores a workflow's links by output index and validates combo widgets
against the option strings, so reordering an output or rewording a dropdown
silently rewires or breaks every saved graph. These assertions are the guard
rail for that: change them deliberately, never as a side effect of an edit.

Needs a ComfyUI install for comfy_api. Set COMFYUI_ROOT, or run the suite from
inside custom_nodes where the host root is inferred.
"""

import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _support

PKG, PKG_ERROR = _support.load_plugin_package()

CLIP_CATEGORY = "MiniMaxH3/ClipStream"
CONTEXT_CATEGORY = "conditioning/minimax"

EXPECTED_OUTPUTS = {
    "MiniMaxClipBinSaver": ["clip_id", "preview_image", "bin_path"],
    "MiniMaxClipBinPicker": ["latent", "tail_frame", "first_frame", "prompt", "clip_id", "project_name"],
    "MiniMaxClipBinDualSaver": ["clip_id", "preview_image", "project_name"],
    "MiniMaxClipBinDualPicker": ["latent_一采", "latent_二采", "first_frame", "tail_frame", "clip_id", "project_name", "prompt"],
    "MiniMaxH3MotionContextClipStream": ["conditioning", "trim_frames"],
    "MiniMaxH3MotionContextTrimClipStream": ["images", "audio"],
    "MiniMaxH3MotionContextSaveLatentClipStream": ["latent_path"],
    "MiniMaxH3MotionContextLoadLatentClipStream": ["LATENT"],
    "MiniMaxH3MotionContextChainClipStream": [],
    "MiniMaxH3MotionContextSeamProbeClipStream": ["audio", "report"],
}

# (input id, is_optional) in declaration order. Renaming or reordering one
# breaks graphs that are already saved on disk.
EXPECTED_INPUTS = {
    "MiniMaxClipBinSaver": [("latent", False), ("project_name", False), ("shot_tag", False),
                            ("images", True), ("audio", True), ("prompt", True),
                            ("parent_clip_id", True), ("video_file_name", True), ("save_video", True)],
    "MiniMaxClipBinPicker": [("project_name", False), ("mode", False),
                             ("clip_selection", False), ("custom_clip_path", True)],
    "MiniMaxClipBinDualSaver": [("latent_一采", False), ("latent_二采", True),
                                ("images_一采", True), ("images_二采", True),
                                ("audio_一采", True), ("audio_二采", True),
                                ("project_name", True), ("shot_tag", True), ("prompt", True),
                                ("parent_clip_id", True), ("video_file_一采", True),
                                ("video_file_二采", True), ("save_video", True)],
    "MiniMaxClipBinDualPicker": [("project_name", False), ("mode", False),
                                 ("clip_selection", False), ("custom_clip_path", True)],
    "MiniMaxH3MotionContextClipStream": [("conditioning", False), ("vae", False), ("latent", False),
                                         ("context_length", False), ("audio_context_length", False),
                                         ("context_frames", True), ("context_latent", True),
                                         ("audio_vae", True), ("context_audio", True),
                                         ("enable_audio_context", True)],
    "MiniMaxH3MotionContextTrimClipStream": [("images", False), ("trim_frames", False),
                                             ("audio", True), ("fps", True), ("match_tail", True)],
    "MiniMaxH3MotionContextSaveLatentClipStream": [("latent", False), ("filename_prefix", False),
                                                   ("clip_index", False)],
    "MiniMaxH3MotionContextLoadLatentClipStream": [("latent_path", False), ("clip_index", False)],
    "MiniMaxH3MotionContextChainClipStream": [("segments", False)],
    "MiniMaxH3MotionContextSeamProbeClipStream": [("clip_b_untrimmed", False), ("trim_frames", False),
                                                  ("clip_a_latent", True), ("audio_vae", True),
                                                  ("fps", True), ("window_ms", True), ("search_ms", True)],
}

PICKER_MODES = ['Auto (首段全新 / 后续自动接续)', 'Force Initial (强制新建首段，无上下文)', 'Strict Chaining (必须接续指定或最新镜头)']
DUAL_PICKER_MODES = ['Auto (首段全新 / 后续自动接续)', 'Force Initial (强制首段，无上下文)', 'Strict Chaining (严格接续，空库报错)']
CONTEXT_LENGTHS = ['22', '5', '39', '56']


def _module(dotted):
    obj = PKG
    for part in dotted.split("."):
        obj = getattr(obj, part)
    return obj


def _schemas():
    schemas = {}
    for module_name in ("clipbin.nodes", "clipbin.dual_nodes", "motion_context.nodes", "motion_context.probe_node"):
        for node_class in _module(module_name).NODE_LIST:
            schema = node_class.define_schema()
            schemas[schema.node_id] = schema
    return schemas


@unittest.skipIf(PKG is None, "the plugin needs a ComfyUI install on sys.path: %s" % PKG_ERROR)
class TestNodeRegistry(unittest.TestCase):
    def test_exactly_the_documented_ten_nodes_are_registered(self):
        self.assertEqual(sorted(_schemas().keys()), sorted(EXPECTED_OUTPUTS.keys()))

    def test_no_node_class_is_registered_twice(self):
        classes = []
        for module_name in ("clipbin.nodes", "clipbin.dual_nodes", "motion_context.nodes", "motion_context.probe_node"):
            classes.extend(_module(module_name).NODE_LIST)
        self.assertEqual(len(classes), len(set(classes)))

    def test_extension_serves_the_same_ten_nodes(self):
        served = asyncio.run(PKG.H3ClipStreamExtension().get_node_list())
        self.assertEqual(sorted(cls.define_schema().node_id for cls in served), sorted(EXPECTED_OUTPUTS.keys()))

    def test_motion_context_ids_keep_the_clipstream_suffix(self):
        for node_id in _schemas():
            if node_id.startswith("MiniMaxH3MotionContext"):
                self.assertTrue(node_id.endswith("ClipStream"), node_id)

    def test_categories_are_unchanged(self):
        for node_id, schema in _schemas().items():
            expected = CONTEXT_CATEGORY if node_id.startswith("MiniMaxH3MotionContext") else CLIP_CATEGORY
            self.assertEqual(schema.category, expected, node_id)


@unittest.skipIf(PKG is None, "the plugin needs a ComfyUI install on sys.path: %s" % PKG_ERROR)
class TestNodeInterfaces(unittest.TestCase):
    def test_output_names_and_order(self):
        for node_id, expected in EXPECTED_OUTPUTS.items():
            got = [out.display_name for out in _schemas()[node_id].outputs]
            self.assertEqual(got, expected, node_id)

    def test_input_names_and_required_state(self):
        for node_id, expected in EXPECTED_INPUTS.items():
            got = [(item.id, bool(item.optional)) for item in _schemas()[node_id].inputs]
            self.assertEqual(got, expected, node_id)

    def test_context_length_offers_only_whole_latent_steps(self):
        combo = _schemas()["MiniMaxH3MotionContextClipStream"].inputs[3]
        self.assertEqual(list(combo.options), CONTEXT_LENGTHS)

    def test_picker_mode_strings_are_unchanged(self):
        single = _schemas()["MiniMaxClipBinPicker"].inputs[1]
        self.assertEqual(list(single.options), PICKER_MODES)
        dual = _schemas()["MiniMaxClipBinDualPicker"].inputs[1]
        self.assertEqual(list(dual.options), DUAL_PICKER_MODES)

    def test_graph_terminal_nodes_are_marked_as_output_nodes(self):
        schemas = _schemas()
        for node_id in ("MiniMaxClipBinSaver", "MiniMaxClipBinDualSaver",
                        "MiniMaxH3MotionContextChainClipStream", "MiniMaxH3MotionContextSeamProbeClipStream"):
            self.assertTrue(schemas[node_id].is_output_node, node_id)
        for node_id in ("MiniMaxClipBinPicker", "MiniMaxClipBinDualPicker", "MiniMaxH3MotionContextClipStream"):
            self.assertFalse(schemas[node_id].is_output_node, node_id)


if __name__ == "__main__":
    unittest.main()
