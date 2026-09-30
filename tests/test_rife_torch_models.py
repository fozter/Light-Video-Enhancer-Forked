"""Tests for the RIFE PyTorch model registry and its plumbing (GPU-free).

The heavy validation (every architecture against hzwer's released reference
code, and the bundled 4.27 conversion against onnxruntime) ran while the
architectures were ported; see tools/convert_rife427_torch.py for the 4.27
conversion recipe.  These tests pin the registry, the CLI/config plumbing,
the model pack, and the shipped 4.27 artifact.
"""

import os
import unittest
from unittest import mock

from light_video_enhancer_forked.capabilities import quick_capabilities
from light_video_enhancer_forked.config import ProcessConfig
from light_video_enhancer_forked.fi import create_fi_engine
from light_video_enhancer_forked.fi.rife import (
    DEFAULT_RIFE_TORCH_MODEL, RIFE_TORCH_MODELS, RIFE_TORCH_MODEL_TOKENS,
    RIFETorchModel, RIFEEngine)
from light_video_enhancer_forked.fi.rife_ncnn import RIFE_NCNN_MODEL_TOKENS
from light_video_enhancer_forked.model_manager import MODEL_PACKS

try:
    import torch
except ImportError:
    torch = None


class RifeTorchRegistryTest(unittest.TestCase):
    def test_registry_tokens_and_weight_files(self):
        self.assertEqual(RIFE_TORCH_MODEL_TOKENS, (
            "4.27_fluidframes", "4.26", "4.25", "4.25-lite",
            "4.22", "4.22-lite", "4.21", "4.20"))
        for token, model in RIFE_TORCH_MODELS.items():
            self.assertEqual(model.token, token)
            if token == "4.27_fluidframes":
                expected = "rife_v4.27_fluidframes.pth"
            elif token == "4.25":
                expected = "flownet.pkl"
            else:
                expected = "rife_v%s.pth" % token
            self.assertEqual(model.filename, expected)
        self.assertEqual(RIFE_TORCH_MODELS["4.27_fluidframes"].display,
                         "4.27 (FluidFrames)")

    def test_default_model_is_bundled_427(self):
        self.assertEqual(DEFAULT_RIFE_TORCH_MODEL, "4.27_fluidframes")
        self.assertTrue(RIFE_TORCH_MODELS["4.27_fluidframes"].bundled)
        for token in ("4.26", "4.25", "4.25-lite", "4.22", "4.22-lite",
                      "4.21", "4.20"):
            self.assertFalse(RIFE_TORCH_MODELS[token].bundled)

    def test_architectures_are_registered(self):
        from light_video_enhancer_forked.fi._rife_model import (
            RIFE_TORCH_ARCHITECTURES)
        for model in RIFE_TORCH_MODELS.values():
            self.assertIn(model.arch, RIFE_TORCH_ARCHITECTURES)

    def test_tokens_exist_on_the_ncnn_side_too(self):
        # The GUI reuses one Model dropdown for both RIFE engines, so every
        # torch token must also be a valid ncnn token.
        self.assertTrue(
            set(RIFE_TORCH_MODEL_TOKENS) <= set(RIFE_NCNN_MODEL_TOKENS))


class RifeTorchEngineTest(unittest.TestCase):
    def test_token_selects_model(self):
        engine = create_fi_engine("rife", quality="4.26")
        self.assertIsInstance(engine, RIFEEngine)
        self.assertEqual(engine._model_def.token, "4.26")
        self.assertIn("4.26", engine.name)

    def test_legacy_tier_falls_back_to_default_model(self):
        engine = create_fi_engine("rife", quality="ultra")
        self.assertEqual(engine._model_def.token, DEFAULT_RIFE_TORCH_MODEL)
        self.assertIn("4.27 (FluidFrames)", engine.name)

    def test_missing_weights_error_points_at_the_pack(self):
        engine = create_fi_engine("rife", quality="4.26")
        with mock.patch.object(
                RIFETorchModel, "weight_path",
                return_value=os.path.join("Z:", "missing", "rife_v4.26.pth")):
            with self.assertRaises(FileNotFoundError) as ctx:
                engine.initialize(1920, 1080, 2)
        self.assertIn("4.26", str(ctx.exception))
        self.assertIn("rife-torch-models", str(ctx.exception))


class RifeTorchConfigTest(unittest.TestCase):
    def _config(self, **kwargs):
        base = dict(input_path="in.mp4", output_path="out.mp4",
                    fi_engine="rife", fi_model="4.26")
        base.update(kwargs)
        return ProcessConfig(**base)

    def test_model_token_accepted(self):
        self._config().validate()

    def test_unknown_model_rejected(self):
        with self.assertRaises(ValueError):
            self._config(fi_model="4.99").validate()

    def test_ncnn_only_model_rejected(self):
        with self.assertRaises(ValueError):
            self._config(fi_model="4.23").validate()

    def test_model_requires_a_rife_engine(self):
        with self.assertRaises(ValueError):
            self._config(fi_engine="dis").validate()


class RifeTorchCliTest(unittest.TestCase):
    def test_model_argument(self):
        from light_video_enhancer_forked.cli import parse_args
        cfg = parse_args(["in.mp4", "--fi-engine", "rife",
                          "--fi-model", "4.25-lite"])
        self.assertEqual(cfg.fi_model, "4.25-lite")
        self.assertEqual(cfg.fi_quality, "balanced")

    def test_ncnn_engine_still_selects_ncnn_models(self):
        from light_video_enhancer_forked.cli import parse_args
        cfg = parse_args(["in.mp4", "--fi-engine", "rife_ncnn",
                          "--fi-model", "4.23"])
        self.assertEqual(cfg.fi_model, "4.23")

    def test_unknown_token_rejected_by_argparse(self):
        from light_video_enhancer_forked.cli import parse_args
        with self.assertRaises(SystemExit):
            parse_args(["in.mp4", "--fi-engine", "rife",
                        "--fi-model", "4.99"])


class RifeTorchPackTest(unittest.TestCase):
    def test_bundled_pack_carries_only_427(self):
        pack = next(p for p in MODEL_PACKS if p["id"] == "rife-pytorch")
        self.assertEqual(list(pack["files"]),
                         ["fi/rife_v4.27_fluidframes.pth"])

    def test_optional_pack_matches_registry(self):
        pack = next(p for p in MODEL_PACKS if p["id"] == "rife-torch-models")
        optional = sorted("fi/%s" % RIFE_TORCH_MODELS[token].filename
                          for token in RIFE_TORCH_MODEL_TOKENS
                          if not RIFE_TORCH_MODELS[token].bundled)
        self.assertEqual(sorted(pack["files"]), optional)
        self.assertEqual(len(pack["remote_hashes"]), len(optional))
        self.assertEqual(set(pack["remote_hashes"]), set(pack["files"]))
        # v4.25 keeps its historical file name; it downloads with the rest.
        self.assertIn("fi/flownet.pkl", pack["files"])
        self.assertGreater(pack["remote_download_size"], 230 * 1024 * 1024)

    def test_capability_reports_available_models(self):
        caps = quick_capabilities()
        self.assertTrue(caps["rife_model"])
        models = caps["rife_torch_models"]
        self.assertIn("4.27_fluidframes", models)
        self.assertTrue(set(models) <= set(RIFE_TORCH_MODEL_TOKENS))


def _smooth_frames(seed, height, width):
    """Low-frequency frames in [0, 1] (see tools/convert_rife427_torch.py)."""
    import numpy as np
    rng = np.random.RandomState(seed)
    axes_h = np.arange(height, dtype=np.float32)[:, None] / height
    axes_w = np.arange(width, dtype=np.float32)[None, :] / width
    frames = np.zeros((1, 6, height, width), dtype=np.float32)
    for index in range(6):
        image = np.zeros((height, width), dtype=np.float32)
        for _ in range(4):
            fx, fy = rng.uniform(0.3, 2.5, 2)
            phase = rng.uniform(0, 2 * np.pi)
            image += np.sin(2 * np.pi * (fx * axes_w + fy * axes_h) + phase)
        image += 0.5 * axes_w + 0.3 * axes_h
        frames[0, index] = 0.5 + 0.2 * image
    return np.clip(frames, 0.0, 1.0)


@unittest.skipIf(torch is None, "PyTorch is not installed")
class Rife427BundledWeightsTest(unittest.TestCase):
    """The shipped 4.27 conversion must load strictly and behave."""

    def _load(self):
        from light_video_enhancer_forked.fi._rife_model import RIFE427
        model = RIFE427().eval()
        state = torch.load(
            RIFE_TORCH_MODELS["4.27_fluidframes"].weight_path(),
            map_location="cpu")
        if isinstance(state, dict) and "state_dict" in state:
            state = state["state_dict"]
        # The file stores fp16 weights; loading casts them to the model
        # dtype exactly the way the engine does.
        model.load_state_dict(state, strict=True)
        return model

    def test_bundled_weights_load_strictly(self):
        model = self._load()
        self.assertGreater(
            sum(parameter.numel() for parameter in model.parameters()), 0)

    def test_output_shape_matches_unaligned_input(self):
        import numpy as np
        model = self._load()
        frames = _smooth_frames(11, 70, 100)
        img0 = torch.from_numpy(frames[:, 0:3])
        img1 = torch.from_numpy(frames[:, 3:6])
        with torch.no_grad():
            output = model(img0, img1, 0.5)
        self.assertEqual(tuple(output.shape), (1, 3, 70, 100))

    def test_zero_inputs_merge_to_zero(self):
        import numpy as np
        model = self._load()
        zeros = torch.zeros((1, 3, 64, 64))
        with torch.no_grad():
            output = model(zeros, zeros, 0.5)
        # The merged result is a convex combination of the two warped
        # (zero) images, so it must be exactly zero whatever the flow is.
        self.assertEqual(float(output.abs().max()), 0.0)

    def test_timestep_conditioning_changes_the_output(self):
        import numpy as np
        model = self._load()
        frames = _smooth_frames(5, 128, 128)
        img0 = torch.from_numpy(frames[:, 0:3])
        img1 = torch.from_numpy(frames[:, 3:6])
        with torch.no_grad():
            near_start = model(img0, img1, 0.25)
            near_end = model(img0, img1, 0.75)
        difference = float((near_start - near_end).abs().max())
        self.assertGreater(difference, 1.0 / 255.0)


if __name__ == "__main__":
    unittest.main()
