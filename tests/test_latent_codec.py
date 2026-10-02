"""AV latent packing/unpacking and the input-shape normalisers the Saver relies on.

The Saver accepts whatever a neighbouring graph hands it: a NestedTensor AV pair,
a bare tuple, a video-only latent, an IMAGE tensor in any of three layouts, or an
AUDIO dict that is sometimes a bare waveform. Each branch is a crash the user
would otherwise hit at queue time.
"""

import os
import sys
import unittest

import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _support

shared = _support.load_standalone(os.path.join("clipbin", "_shared.py"), "clipbin_shared")


def video(batch=1, steps=7, height=10, width=20):
    return torch.arange(batch * 3 * steps * height * width, dtype=torch.float32).reshape(
        batch, 3, steps, height, width)


def audio(batch=1, channels=32, frames=40):
    return torch.zeros(batch, channels, 2, frames, dtype=torch.float32)


class TestUnpackLatent(unittest.TestCase):
    def test_none_and_empty_dicts(self):
        self.assertEqual(shared._unpack_latent(None), (None, None))
        self.assertEqual(shared._unpack_latent({}), (None, None))
        self.assertEqual(shared._unpack_latent({"samples": None}), (None, None))

    def test_batched_video_tensor_round_trips(self):
        v, a = shared._unpack_latent({"samples": video()})
        self.assertEqual(tuple(v.shape), (1, 3, 7, 10, 20))
        self.assertIsNone(a)

    def test_unbatched_bare_tensor_is_split_on_its_channel_axis(self):
        # torch.Tensor has .unbind, so the plain-tensor branch in _unpack_latent is
        # unreachable: an unbatched [C, T, H, W] latent is split along C, and the
        # second slice is then mistaken for an audio stream and gains a batch axis.
        # Batched latents (the shape ComfyUI actually passes) are unaffected. Locked
        # as-is so a future fix has to change it on purpose.
        v, a = shared._unpack_latent({"samples": video()[0]})
        self.assertEqual(tuple(v.shape), (7, 10, 20))
        self.assertEqual(tuple(a.shape), (1, 7, 10, 20))

    def test_tuple_pair(self):
        v, a = shared._unpack_latent({"samples": (video(), audio())})
        self.assertEqual(v.shape, video().shape)
        self.assertEqual(a.shape, audio().shape)

    def test_list_pair_with_unbatched_streams(self):
        v, a = shared._unpack_latent({"samples": (video()[0], audio()[0])})
        self.assertEqual(v.shape, video().shape)
        self.assertEqual(a.shape, audio().shape)

    def test_unknown_container_is_ignored(self):
        self.assertEqual(shared._unpack_latent({"samples": object()}), (None, None))


class TestPackLatent(unittest.TestCase):
    def test_video_only_round_trip(self):
        packed = shared.pack_av_latent(video())
        v, a = shared._unpack_latent(packed)
        self.assertTrue(torch.equal(v, video()))
        self.assertIsNone(a)

    def test_av_round_trip_keeps_both_streams(self):
        packed = shared.pack_av_latent(video(), audio())
        v, a = shared._unpack_latent(packed)
        self.assertTrue(torch.equal(v, video()))
        self.assertTrue(torch.equal(a, audio()))

    def test_original_dict_keys_are_preserved(self):
        packed = shared.pack_av_latent(video(), audio(), {"batch_index": [0]})
        self.assertEqual(packed.get("batch_index"), [0])

    def test_packing_does_not_mutate_the_source_dict(self):
        original = {"samples": video()}
        shared.pack_av_latent(video(), audio(), original)
        self.assertTrue(torch.equal(original["samples"], video()))


class TestStandardizeImageTensor(unittest.TestCase):
    def test_none_and_non_tensors_pass_through(self):
        self.assertIsNone(shared._standardize_image_tensor(None))
        self.assertEqual(shared._standardize_image_tensor("not a tensor"), "not a tensor")

    def test_leading_batch_with_trailing_channels(self):
        out = shared._standardize_image_tensor(torch.zeros(1, 5, 8, 12, 3))
        self.assertEqual(tuple(out.shape), (5, 8, 12, 3))

    def test_channel_first_single_batch(self):
        out = shared._standardize_image_tensor(torch.zeros(1, 3, 5, 8, 12))
        self.assertEqual(tuple(out.shape), (5, 8, 12, 3))

    def test_channel_first_batched_flattens_into_frames(self):
        out = shared._standardize_image_tensor(torch.zeros(2, 3, 5, 8, 12))
        self.assertEqual(tuple(out.shape), (10, 8, 12, 3))

    def test_single_frame_gains_a_frame_axis(self):
        out = shared._standardize_image_tensor(torch.zeros(8, 12, 3))
        self.assertEqual(tuple(out.shape), (1, 8, 12, 3))

    def test_already_canonical_is_unchanged(self):
        out = shared._standardize_image_tensor(torch.zeros(5, 8, 12, 3))
        self.assertEqual(tuple(out.shape), (5, 8, 12, 3))


class TestStandardizeAudioDict(unittest.TestCase):
    def test_canonical_dict_is_returned_as_is(self):
        source = {"waveform": torch.zeros(1, 2, 100), "sample_rate": 44100}
        self.assertIs(shared._standardize_audio_dict(source), source)

    def test_bare_waveform_becomes_a_dict(self):
        out = shared._standardize_audio_dict(torch.zeros(100))
        self.assertEqual(tuple(out["waveform"].shape), (1, 1, 100))
        self.assertEqual(out["sample_rate"], 32000)

    def test_two_dimensional_waveform_gains_a_batch_axis(self):
        out = shared._standardize_audio_dict(torch.zeros(2, 100))
        self.assertEqual(tuple(out["waveform"].shape), (1, 2, 100))

    def test_wrapped_in_a_list_is_unwrapped(self):
        out = shared._standardize_audio_dict([{"waveform": torch.zeros(1, 2, 50), "sample_rate": 16000}])
        self.assertEqual(out["sample_rate"], 16000)

    def test_unusable_input_is_dropped(self):
        self.assertIsNone(shared._standardize_audio_dict(None))
        self.assertIsNone(shared._standardize_audio_dict("silence"))
        self.assertIsNone(shared._standardize_audio_dict([]))


if __name__ == "__main__":
    unittest.main()
