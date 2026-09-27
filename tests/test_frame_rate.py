"""Target frame rate behavior: parsing, grid derivation, and resampling."""

import argparse
import unittest

import numpy as np

from light_video_enhancer_forked.cli import _auto_output, _frame_rate, parse_args
from light_video_enhancer_forked.pipeline import (
    _FrameRateResampler, derived_frame_rate_multiplier)


class FrameRateParseTest(unittest.TestCase):
    def test_plain_number(self):
        self.assertEqual(_frame_rate("60"), 60.0)
        self.assertEqual(_frame_rate("23.976"), 23.976)

    def test_exact_ntsc_ratios(self):
        self.assertAlmostEqual(_frame_rate("24000/1001"), 24000 / 1001, places=12)
        self.assertAlmostEqual(_frame_rate("30000/1001"), 30000 / 1001, places=12)
        self.assertAlmostEqual(_frame_rate("48000/1001"), 48000 / 1001, places=12)
        self.assertAlmostEqual(_frame_rate("60000/1001"), 60000 / 1001, places=12)

    def test_rejects_garbage(self):
        for bad in ("abc", "", "1/0", "-5", "24/", "/25"):
            with self.assertRaises(argparse.ArgumentTypeError):
                _frame_rate(bad)

    def test_cli_accepts_ratio_and_keeps_multiplier_auto(self):
        cfg = parse_args(["in.mp4", "--fps", "24000/1001"])
        self.assertAlmostEqual(cfg.fps, 24000 / 1001, places=12)
        self.assertIsNone(cfg.fi_multiplier)

    def test_cli_explicit_multiplier_wins(self):
        cfg = parse_args(["in.mp4", "--fps", "60", "--fi-multiplier", "4"])
        self.assertEqual(cfg.fps, 60.0)
        self.assertEqual(cfg.fi_multiplier, 4)

    def test_engines_default_to_none(self):
        cfg = parse_args(["in.mp4"])
        self.assertEqual(cfg.sr_engine, "none")
        self.assertEqual(cfg.fi_engine, "none")

    def test_auto_engines_are_gone(self):
        for flag in ("--sr-engine", "--fi-engine"):
            with self.assertRaises(SystemExit):
                parse_args(["in.mp4", flag, "auto"])

    def test_auto_output_prefers_the_rate_tag(self):
        self.assertTrue(_auto_output(
            "clip.mp4", 2.0, "rife_ncnn", 3, "mp4", "none",
            fps=60000 / 1001).endswith("clip_fps59.94.mp4"))
        self.assertTrue(_auto_output(
            "clip.mp4", 2.0, "rife_ncnn", 3, "mp4", "none").endswith("clip_f3.mp4"))


class MultiplierDerivationTest(unittest.TestCase):
    def test_two_and_a_half_needs_three(self):
        self.assertEqual(derived_frame_rate_multiplier(24000 / 1001, 60), 3)
        self.assertEqual(derived_frame_rate_multiplier(24000 / 1001, 60000 / 1001), 3)
        self.assertEqual(derived_frame_rate_multiplier(24, 60), 3)

    def test_exact_double_needs_two(self):
        self.assertEqual(derived_frame_rate_multiplier(24000 / 1001, 48000 / 1001), 2)
        self.assertEqual(derived_frame_rate_multiplier(25, 50), 2)
        self.assertEqual(derived_frame_rate_multiplier(30, 60), 2)

    def test_at_or_below_source_needs_none(self):
        self.assertIsNone(derived_frame_rate_multiplier(30, 15))
        self.assertIsNone(derived_frame_rate_multiplier(24000 / 1001, 24000 / 1001))
        self.assertIsNone(derived_frame_rate_multiplier(60, 59.94))

    def test_unreachable_rate_is_rejected(self):
        with self.assertRaises(ValueError):
            derived_frame_rate_multiplier(24000 / 1001, 480)

    def test_float_noise_around_an_exact_ratio(self):
        # 48000/1001 over 24000/1001 is exactly 2; float noise must not
        # pay for a third interpolation pass.
        dense = 24000 / 1001
        self.assertEqual(derived_frame_rate_multiplier(dense, dense * 2.0000000001), 2)


class FrameRateResamplerTest(unittest.TestCase):
    def _run(self, natural, target, count):
        resampler = _FrameRateResampler(natural, target)
        emitted = []
        for index in range(count):
            frame = np.array([index], dtype=np.int32)
            emitted.extend(int(value[0]) for value in resampler.feed(frame))
        return emitted

    def test_downsampling_drops_frames(self):
        emitted = self._run(72.0, 60.0, 5 * 72)
        self.assertEqual(len(emitted), 5 * 60)
        self.assertEqual(emitted[0], 0)
        self.assertTrue(all(a < b for a, b in zip(emitted, emitted[1:])))
        self.assertEqual(emitted[-1], 5 * 72 - 1)

    def test_duration_is_preserved_from_ntsc_dense_grid(self):
        dense = 24000 / 1001 * 3
        emitted = self._run(dense, 60.0, 240)
        self.assertAlmostEqual(
            len(emitted) / 60.0, 240 / dense, delta=1.05)

    def test_upsampling_duplicates_frames(self):
        # Legacy mode: an explicit 2x grid resampled to 60 fps duplicates.
        emitted = self._run(48.0, 60.0, 48)
        self.assertEqual(len(emitted), 60)

    def test_identical_rates_pass_through(self):
        resampler = _FrameRateResampler(30.0, 30.0)
        frames = [np.zeros((1,), dtype=np.uint8) for _ in range(4)]
        out = [f for frame in frames for f in resampler.feed(frame)]
        self.assertEqual(len(out), 4)


if __name__ == "__main__":
    unittest.main()
