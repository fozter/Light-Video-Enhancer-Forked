import os
import tempfile
import unittest

import numpy as np

from light_video_enhancer_forked.ffmpeg_bridge import (
    FFmpegVideoDecoder,
    FFmpegVideoEncoder,
    encoder_is_available,
    worker_is_loadable,
)


@unittest.skipUnless(os.name == "nt", "the bundled worker is Windows-only")
class FFmpegBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not worker_is_loadable():
            raise unittest.SkipTest("bundled FFmpeg worker cannot be loaded")

    def _round_trip(self, codec):
        with tempfile.TemporaryDirectory(prefix="lve-test-") as directory:
            safe_name = codec.replace("-", "_")
            path = os.path.join(directory, safe_name + ".mp4")
            encoder = FFmpegVideoEncoder(
                path, 64, 64, 10.0, codec=codec, preset="fast", crf=28
            )
            encoder.open()
            for index in range(6):
                frame = np.zeros((64, 64, 3), dtype=np.uint8)
                frame[:, :, 0] = index * 30
                frame[8:24, 8 + index:24 + index, 1] = 255
                encoder.encode(frame)
            encoder.close()
            with FFmpegVideoDecoder(path, hardware="cpu") as decoder:
                self.assertAlmostEqual(decoder.fps, 10.0, places=3)
                self.assertEqual(decoder.total_frames, 6)
                frames = list(decoder)
            self.assertEqual(len(frames), 6)
            self.assertTrue(all(frame.shape == (64, 64, 3) for frame in frames))

    def test_bundled_software_codec_round_trips(self):
        for codec in ("libx264", "libx265", "libsvtav1", "libaom-av1"):
            with self.subTest(codec=codec):
                self.assertTrue(encoder_is_available(codec), codec)
                self._round_trip(codec)

    def test_mpeg4_round_trip_is_frame_accurate(self):
        self._round_trip("mpeg4")

    def test_media_foundation_round_trip_is_frame_accurate(self):
        if not encoder_is_available("h264_mf"):
            self.skipTest("Media Foundation H.264 is unavailable")
        self._round_trip("h264_mf")

    def test_probe_reports_stream_basics(self):
        from light_video_enhancer_forked.frontend_protocol import probe_video_payload

        with tempfile.TemporaryDirectory(prefix="lve-probe-") as directory:
            path = os.path.join(directory, "probe.mp4")
            encoder = FFmpegVideoEncoder(
                path, 64, 48, 10.0, codec="libx264", preset="fast", crf=28
            )
            encoder.open()
            for index in range(6):
                frame = np.zeros((48, 64, 3), dtype=np.uint8)
                frame[:, :, 2] = index * 40
                encoder.encode(frame)
            encoder.close()
            payload = probe_video_payload(path)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["protocol_version"], 1)
            self.assertEqual(payload["width"], 64)
            self.assertEqual(payload["height"], 48)
            self.assertAlmostEqual(payload["fps"], 10.0, places=3)
            self.assertEqual(payload["frames"], 6)

    def test_probe_reports_missing_file(self):
        from light_video_enhancer_forked.frontend_protocol import probe_video_payload

        payload = probe_video_payload(
            os.path.join("Z:", "__no_such_input__.mp4"))
        self.assertFalse(payload["ok"])
        self.assertIn("does not exist", payload["error"])


if __name__ == "__main__":
    unittest.main()
