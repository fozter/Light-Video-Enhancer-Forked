"""Tests for the merged RIFE ncnn engine and its model registry (GPU-free)."""

import os
import unittest
from unittest import mock

import numpy as np

import light_video_enhancer_forked.fi.rife_ncnn as rife_ncnn_module
from light_video_enhancer_forked.capabilities import quick_capabilities
from light_video_enhancer_forked.config import ProcessConfig
from light_video_enhancer_forked.fi import create_fi_engine
from light_video_enhancer_forked.fi.rife_ncnn import (
    DEFAULT_RIFE_NCNN_MODEL, RIFE_NCNN_MODELS, RIFE_NCNN_MODEL_TOKENS,
    RIFENcnnEngine)
from light_video_enhancer_forked.model_manager import MODEL_PACKS


def initialize_engine(engine, width, height, multiplier=2):
    """Initialize against the bundled 4.27 files so optional models can be
    exercised without downloading the model pack (only existence is
    checked at this stage; nothing is loaded)."""
    bundled = os.path.join(
        rife_ncnn_module.get_pkg_dir(), "ncnn", "rife", "rife-v4.27")
    with mock.patch.object(rife_ncnn_module, "get_model_dir",
                           return_value=bundled):
        engine.initialize(width, height, multiplier)


class RifeNcnnRegistryTest(unittest.TestCase):
    def test_registry_tokens_and_directories(self):
        self.assertEqual(RIFE_NCNN_MODEL_TOKENS, (
            "4.27_fluidframes", "4.26", "4.26-large", "4.25", "4.25-heavy", "4.25-lite",
            "4.24", "4.23", "4.22", "4.22-lite", "4.21", "4.20"))
        for token, model in RIFE_NCNN_MODELS.items():
            self.assertEqual(model.token, token)
            # The bundled FluidFrames model keeps the plain version directory.
            version = "4.27" if token == "4.27_fluidframes" else token
            self.assertEqual(model.directory, "rife-v%s" % version)
        self.assertEqual(RIFE_NCNN_MODELS["4.27_fluidframes"].display,
                         "4.27 (FluidFrames)")

    def test_tile_alignment_per_family(self):
        # Four-block family: the executable tiles to 32 by itself and the
        # legacy half-resolution UHD mode is allowed.
        for token in ("4.20", "4.21", "4.22", "4.22-lite", "4.23", "4.24"):
            self.assertEqual(RIFE_NCNN_MODELS[token].tile, 0)
            self.assertTrue(RIFE_NCNN_MODELS[token].uhd)
        # Five-block family: padded in Python, always full resolution.
        for token in ("4.25", "4.25-heavy", "4.26", "4.26-large", "4.27_fluidframes"):
            self.assertEqual(RIFE_NCNN_MODELS[token].tile, 64)
            self.assertFalse(RIFE_NCNN_MODELS[token].uhd)
        self.assertEqual(RIFE_NCNN_MODELS["4.25-lite"].tile, 128)
        self.assertFalse(RIFE_NCNN_MODELS["4.25-lite"].uhd)

    def test_default_model_is_bundled_427(self):
        self.assertEqual(DEFAULT_RIFE_NCNN_MODEL, "4.27_fluidframes")
        self.assertTrue(RIFE_NCNN_MODELS["4.27_fluidframes"].bundled)
        self.assertFalse(RIFE_NCNN_MODELS["4.26"].bundled)


class RifeNcnnEngineTest(unittest.TestCase):
    def test_token_selects_model(self):
        engine = create_fi_engine("rife_ncnn", quality="4.26-large")
        self.assertIsInstance(engine, RIFENcnnEngine)
        self.assertIn("4.26 Large", engine.name)

    def test_legacy_tier_falls_back_to_default_model(self):
        engine = create_fi_engine("rife_ncnn", quality="ultra")
        self.assertEqual(engine._model.token, DEFAULT_RIFE_NCNN_MODEL)
        self.assertIn("4.27 (FluidFrames)", engine.name)

    def test_deprecated_alias_selects_427(self):
        engine = create_fi_engine("rife_ncnn_427")
        self.assertEqual(engine._model.token, "4.27_fluidframes")
        engine = create_fi_engine("rife_ncnn_427", quality="4.26")
        self.assertEqual(engine._model.token, "4.26")

    def test_initialize_computes_64_tiling(self):
        engine = create_fi_engine("rife_ncnn", quality="4.27_fluidframes")
        initialize_engine(engine, 1920, 818, 2)
        self.assertEqual((engine._width, engine._height), (1920, 818))
        self.assertEqual((engine._pad_width, engine._pad_height), (0, 14))
        initialize_engine(engine, 200, 136, 2)
        self.assertEqual((engine._pad_width, engine._pad_height), (56, 56))
        initialize_engine(engine, 1920, 1080, 2)
        self.assertEqual((engine._pad_width, engine._pad_height), (0, 8))
        initialize_engine(engine, 1920, 1024, 2)
        self.assertEqual((engine._pad_width, engine._pad_height), (0, 0))

    def test_128_tiling_for_425_lite(self):
        engine = create_fi_engine("rife_ncnn", quality="4.25-lite")
        initialize_engine(engine, 480, 270, 2)
        self.assertEqual((engine._pad_width, engine._pad_height), (32, 114))

    def test_four_block_family_needs_no_padding(self):
        engine = create_fi_engine("rife_ncnn", quality="4.24")
        initialize_engine(engine, 480, 270, 2)
        self.assertEqual((engine._pad_width, engine._pad_height), (0, 0))
        initialize_engine(engine, 200, 136, 2)
        self.assertEqual((engine._pad_width, engine._pad_height), (0, 0))

    def test_pad_crop_roundtrip(self):
        engine = create_fi_engine("rife_ncnn", quality="4.25")
        initialize_engine(engine, 100, 70, 2)
        frame = np.full((70, 100, 3), 7, dtype=np.uint8)
        padded = engine._pad_frame(frame)
        self.assertEqual(padded.shape, (128, 128, 3))
        self.assertTrue((padded[:70, :100] == 7).all())
        self.assertTrue((padded[70:] == 0).all())
        self.assertTrue((padded[:, 100:] == 0).all())
        cropped = engine._crop_frame(padded)
        self.assertEqual(cropped.shape, (70, 100, 3))
        self.assertTrue((cropped == 7).all())

    def test_aligned_sizes_are_untouched(self):
        engine = create_fi_engine("rife_ncnn", quality="4.26")
        initialize_engine(engine, 256, 256, 2)
        frame = np.full((256, 256, 3), 9, dtype=np.uint8)
        self.assertIs(engine._pad_frame(frame), frame)
        self.assertIs(engine._crop_frame(frame), frame)

    def test_native_stage_not_offered_for_any_model(self):
        for token in RIFE_NCNN_MODEL_TOKENS:
            engine = create_fi_engine("rife_ncnn", quality=token)
            with self.assertRaises(NotImplementedError):
                engine.native_ncnn_stage()

    def test_directory_batching_contract(self):
        engine = create_fi_engine("rife_ncnn", quality="4.24")
        self.assertTrue(engine.supports_batch)
        self.assertTrue(engine.supports_directory_batch)
        with self.assertRaises(ValueError):
            engine.process_directory("nope", "nada", 1)


class RifeModelConfigTest(unittest.TestCase):
    def _config(self, **kwargs):
        base = dict(input_path="in.mp4", output_path="out.mp4",
                    fi_engine="rife_ncnn", fi_model="4.26")
        base.update(kwargs)
        return ProcessConfig(**base)

    def test_model_token_accepted(self):
        self._config().validate()

    def test_unknown_model_rejected(self):
        with self.assertRaises(ValueError):
            self._config(fi_model="4.99").validate()

    def test_model_requires_rife_engine(self):
        with self.assertRaises(ValueError):
            self._config(fi_engine="dis").validate()


class RifeModelCliTest(unittest.TestCase):
    def test_alias_maps_to_default_model(self):
        from light_video_enhancer_forked.cli import parse_args
        cfg = parse_args(["in.mp4", "--fi-engine", "rife_ncnn_427"])
        self.assertEqual(cfg.fi_engine, "rife_ncnn")
        self.assertEqual(cfg.fi_model, "4.27_fluidframes")

    def test_alias_respects_explicit_model(self):
        from light_video_enhancer_forked.cli import parse_args
        cfg = parse_args(["in.mp4", "--fi-engine", "rife_ncnn_427",
                          "--fi-model", "4.26"])
        self.assertEqual(cfg.fi_engine, "rife_ncnn")
        self.assertEqual(cfg.fi_model, "4.26")

    def test_model_argument(self):
        from light_video_enhancer_forked.cli import parse_args
        cfg = parse_args(["in.mp4", "--fi-engine", "rife_ncnn",
                          "--fi-model", "4.25-heavy"])
        self.assertEqual(cfg.fi_model, "4.25-heavy")
        self.assertEqual(cfg.fi_quality, "balanced")


class RifeNcnnPackTest(unittest.TestCase):
    def test_bundled_pack_carries_only_427(self):
        pack = next(p for p in MODEL_PACKS if p["id"] == "rife-ncnn")
        self.assertEqual(list(pack["files"]), [
            "ncnn/rife/rife-v4.27/flownet.param",
            "ncnn/rife/rife-v4.27/flownet.bin"])

    def test_optional_pack_matches_registry(self):
        pack = next(p for p in MODEL_PACKS if p["id"] == "rife-ncnn-models")
        self.assertEqual(len(pack["files"]), 22)
        optional = [t for t in RIFE_NCNN_MODEL_TOKENS if t != "4.27_fluidframes"]
        expected = sorted(
            "ncnn/rife/%s/flownet.%s" % (RIFE_NCNN_MODELS[t].directory, ext)
            for t in optional for ext in ("param", "bin"))
        self.assertEqual(sorted(pack["files"]), expected)
        self.assertEqual(len(pack["remote_hashes"]), 22)
        self.assertEqual(set(pack["remote_hashes"]), set(pack["files"]))
        self.assertGreater(pack["remote_download_size"], 150 * 1024 * 1024)

    def test_capability_reports_available_models(self):
        caps = quick_capabilities()
        self.assertNotIn("ncnn_rife_427", caps)
        self.assertTrue(caps["ncnn_rife"])
        models = caps["ncnn_rife_models"]
        self.assertIn("4.27_fluidframes", models)
        self.assertTrue(set(models) <= set(RIFE_NCNN_MODEL_TOKENS))


if __name__ == "__main__":
    unittest.main()
