"""Exact overlap restoration, untouched future/audio, and wiring mistakes."""

import os
import sys
import unittest

import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _support

PKG, ERROR = _support.load_plugin_package()


def clip(steps=22, seed=1):
    generator = torch.Generator().manual_seed(seed)
    video = torch.randn(1, 24, steps, 3, 4, generator=generator)
    audio = torch.randn(1, 32, 2, 40, generator=generator)
    return {"samples": [video, audio], "noise_mask": torch.ones(1), "tag": "retained"}


@unittest.skipIf(PKG is None, f"ComfyUI import failed: {ERROR}")
class TestOverlapRestore(unittest.TestCase):
    def setUp(self):
        self.module = PKG.motion_context.overlap_restore
        self.restore = self.module.restore_overlap

    def test_all_context_windows_copy_exact_tail_only(self):
        for frames, steps in ((5, 2), (22, 7), (39, 12), (56, 17)):
            with self.subTest(frames=frames):
                parent, child = clip(seed=1), clip(seed=2)
                old_parent, old_child = parent["samples"][0].clone(), child["samples"][0].clone()
                out = self.restore(child, frames, context_latent=parent)
                video = out["samples"][0]
                self.assertTrue(torch.equal(video[:, :, :steps], old_parent[:, :, -steps:]))
                self.assertTrue(torch.equal(video[:, :, steps:], old_child[:, :, steps:]))
                self.assertTrue(torch.equal(parent["samples"][0], old_parent))
                self.assertTrue(torch.equal(child["samples"][0], old_child))
                self.assertIs(out["samples"][1], child["samples"][1])
                self.assertIs(out["noise_mask"], child["noise_mask"])
                self.assertEqual(out["tag"], "retained")
                self.assertNotEqual(video.data_ptr(), child["samples"][0].data_ptr())

    def test_first_clip_and_disabled_are_identity_pass_through(self):
        child = clip()
        self.assertIs(self.restore(child, 0), child)
        self.assertIs(self.restore(child, 22, enabled=False), child)

    def test_missing_parent_is_an_error_when_continuing(self):
        with self.assertRaisesRegex(ValueError, "context_latent is empty"):
            self.restore(clip(), 22)

    def test_invalid_windows_are_rejected(self):
        for count in (-1, 1, 18, 21, 23, 57):
            with self.subTest(count=count), self.assertRaises(ValueError):
                self.restore(clip(), count, context_latent=clip())

    def test_temporal_phase_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "temporal cycle"):
            self.restore(clip(), 22, context_latent=clip(steps=23))

    def test_short_parent_and_no_new_content_are_rejected(self):
        for parent, child in ((clip(steps=2), clip()), (clip(), clip(steps=7))):
            with self.assertRaisesRegex(ValueError, "new content"):
                self.restore(child, 22, context_latent=parent)

    def test_pass_one_resolution_and_batch_mismatch_are_rejected(self):
        for axis in (0, 3, 4):
            parent = clip()
            shape = list(parent["samples"][0].shape)
            shape[axis] += 1
            parent["samples"][0] = torch.zeros(shape)
            with self.subTest(axis=axis), self.assertRaisesRegex(ValueError, "resolution"):
                self.restore(clip(), 22, context_latent=parent)

    def test_dtype_mismatch_is_not_silently_quantized(self):
        parent = clip()
        parent["samples"][0] = parent["samples"][0].half()
        with self.assertRaisesRegex(ValueError, "dtype mismatch"):
            self.restore(clip(), 22, context_latent=parent)

    def test_nested_tuple_and_video_only_containers(self):
        import comfy.nested_tensor
        for kind in ("nested", "tuple", "tensor"):
            child, parent = clip(seed=2), clip()
            audio = child["samples"][1]
            if kind == "nested":
                child["samples"] = comfy.nested_tensor.NestedTensor(child["samples"])
                parent["samples"] = comfy.nested_tensor.NestedTensor(parent["samples"])
            elif kind == "tuple":
                child["samples"] = tuple(child["samples"])
            else:
                child["samples"] = child["samples"][0]
                parent["samples"] = parent["samples"][0]
            out = self.restore(child, 22, context_latent=parent)
            self.assertIs(type(out["samples"]), type(child["samples"]))
            parts = self.module.video_stream(out, "out")[2]
            if kind != "tensor":
                self.assertIs(parts[1], audio)

    def test_unbatched_video_keeps_its_rank(self):
        child, parent = clip(seed=2), clip()
        child["samples"][0] = child["samples"][0][0]
        parent["samples"][0] = parent["samples"][0][0]
        out = self.restore(child, 22, context_latent=parent)
        self.assertEqual(out["samples"][0].ndim, 4)
        self.assertTrue(torch.equal(out["samples"][0][:, :7], parent["samples"][0][:, -7:]))

    def test_ordinary_image_latent_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "H3 video"):
            self.restore({"samples": torch.zeros(1, 4, 8, 8)}, 22, context_latent=clip())

    def test_execute_returns_comfy_latent_and_requires_trim_wire(self):
        node = self.module.MiniMaxH3OverlapRestoreClipStream
        out = node.execute(clip(seed=2), 22, context_latent=clip())
        self.assertIsInstance(out.args[0], dict)
        schema = node.define_schema()
        self.assertTrue(schema.inputs[1].force_input)


if __name__ == "__main__":
    unittest.main()
