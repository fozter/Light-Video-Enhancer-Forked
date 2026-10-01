"""RIFE ncnn-vulkan using the executable's efficient directory batch mode.

The engine is model-driven: ``--fi-quality`` carries either a classic quality
tier (used by the other interpolation engines) or a RIFE model token such as
``4.26``.  The model table below pins, for every supported RIFE ncnn model:

* the model directory name under ``ncnn/rife/``;
* the tile alignment the network needs.  The bundled executable tiles every
  job to 32-pixel multiples internally; the five-block family (4.25 and
  newer) needs 64 (128 for 4.25 Lite), so those frames are zero-padded in
  Python before the executable sees them and the outputs are cropped back.
  This mirrors the reference implementations, which zero-pad to the same
  multiples;
* whether the legacy half-resolution UHD mode may be used.  It matches the
  four-block family (4.20-4.24); the five-block family always runs at full
  resolution.

The bundled executable is the TNTwise rife-ncnn-vulkan build (a fork of
nihui's MIT-licensed project, also MIT-licensed).  It keeps the exact CLI of
the original, runs every model in the table, and produces byte-identical
results to the original build for models the original could load.
"""

import os
import subprocess
import tempfile
from typing import Dict, List, Optional, Tuple

import numpy as np

from light_video_enhancer_forked.fi.base import FrameInterpolationEngine
from light_video_enhancer_forked._image_batch import (
    make_directory, ncnn_jobs, read_frames, validate_outputs, write_frames)
from light_video_enhancer_forked._logging import get_logger
from light_video_enhancer_forked._paths import (
    get_model_dir, get_pkg_dir, model_file_exists)
from light_video_enhancer_forked.ncnn_contract import NcnnInterpolationStage
from light_video_enhancer_forked.fi._scene_detect import (
    PAIR_NORMAL, classify_pair, skipped_intermediates)

_log = get_logger(__name__)


class RIFEModel:
    """One selectable RIFE ncnn model."""

    __slots__ = ("token", "directory", "display", "tile", "uhd", "bundled")

    def __init__(self, token: str, directory: str, display: str,
                 tile: int = 0, uhd: bool = False, bundled: bool = False):
        self.token = token
        self.directory = directory
        self.display = display
        self.tile = int(tile)
        self.uhd = bool(uhd)
        self.bundled = bool(bundled)

    def model_file_exists(self) -> bool:
        return all(model_file_exists("ncnn", "rife", self.directory, name)
                   for name in ("flownet.param", "flownet.bin"))


# token, model directory, dropdown display, python tile padding, uhd mode
# (newest first: the GUI model list, the --fi-model choices, the capability
# report, and the interactive wizard all follow this order)
RIFE_NCNN_MODELS: Dict[str, RIFEModel] = {
    token: RIFEModel(token, directory, display, tile, uhd, bundled)
    for token, directory, display, tile, uhd, bundled in (
        ("4.27_fluidframes", "rife-v4.27", "4.27 (FluidFrames)", 64, False, True),
        ("4.26", "rife-v4.26", "4.26", 64, False, False),
        ("4.26-large", "rife-v4.26-large", "4.26 Large", 64, False, False),
        ("4.25", "rife-v4.25", "4.25", 64, False, False),
        ("4.25-heavy", "rife-v4.25-heavy", "4.25 Heavy", 64, False, False),
        ("4.25-lite", "rife-v4.25-lite", "4.25 Lite", 128, False, False),
        ("4.24", "rife-v4.24", "4.24", 0, True, False),
        ("4.23", "rife-v4.23", "4.23", 0, True, False),
        ("4.22", "rife-v4.22", "4.22", 0, True, False),
        ("4.22-lite", "rife-v4.22-lite", "4.22 Lite", 0, True, False),
        ("4.21", "rife-v4.21", "4.21", 0, True, False),
        ("4.20", "rife-v4.20", "4.20", 0, True, False),
    )
}
DEFAULT_RIFE_NCNN_MODEL = "4.27_fluidframes"
RIFE_NCNN_MODEL_TOKENS: Tuple[str, ...] = tuple(RIFE_NCNN_MODELS)


def _no_window_flag() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


class RIFENcnnEngine(FrameInterpolationEngine):
    """Portable Vulkan RIFE with directory-to-directory chaining support.

    ``quality`` selects the model when it carries a RIFE model token
    (``4.20`` ... ``4.27_fluidframes``); classic quality tiers fall back to the default
    model.  Spatial/temporal TTA is not offered: the upstream conversions
    deprecate it for the five-block family and no ensemble exports exist for
    the models in the table.
    """

    def __init__(self, quality: str = "balanced", gpu_id: Optional[int] = None):
        self._model = RIFE_NCNN_MODELS.get(
            quality, RIFE_NCNN_MODELS[DEFAULT_RIFE_NCNN_MODEL])
        self._gpu_id = gpu_id
        self._width = 0
        self._height = 0
        self._multiplier = 2
        self._exe = ""
        self._model_dir = ""
        self._pad_width = 0
        self._pad_height = 0

    @property
    def name(self) -> str:
        target = "auto GPU" if self._gpu_id is None else (
            "CPU" if self._gpu_id < 0 else "GPU %d" % self._gpu_id)
        return "RIFE ncnn-vulkan (%s, %s)" % (self._model.display, target)

    @property
    def supports_batch(self) -> bool:
        return True

    @property
    def supports_directory_batch(self) -> bool:
        return True

    def initialize(self, width: int, height: int, multiplier: int = 2) -> None:
        if multiplier < 2:
            raise ValueError("RIFE interpolation multiplier must be at least 2")
        base = os.path.join(get_pkg_dir(), "ncnn", "rife")
        self._exe = os.path.join(base, "rife-ncnn-vulkan.exe")
        self._model_dir = get_model_dir("ncnn", "rife", self._model.directory)
        required = [self._exe, os.path.join(self._model_dir, "flownet.param"),
                    os.path.join(self._model_dir, "flownet.bin")]
        missing = [path for path in required if not os.path.isfile(path)]
        if missing:
            hint = ""
            if not self._model.bundled:
                hint = " (download it with --download-model rife-ncnn-models)"
            raise FileNotFoundError(
                "RIFE ncnn resources are incomplete: %s%s" % (
                    ", ".join(missing), hint))
        self._width, self._height = width, height
        self._multiplier = multiplier
        tile = self._model.tile
        self._pad_width = (tile - width % tile) % tile if tile else 0
        self._pad_height = (tile - height % tile) % tile if tile else 0
        if self._pad_width or self._pad_height:
            _log.info("RIFE ncnn (%s) batch processing ready: %dx%d (+%dx%d padding), %dx",
                      self._model.display, width, height,
                      self._pad_width, self._pad_height, multiplier)
        else:
            _log.info("RIFE ncnn (%s) batch processing ready: %dx%d, %dx",
                      self._model.display, width, height, multiplier)

    def _tile_size(self) -> tuple:
        """Padded (width, height) expected by read_frames."""
        return (self._width + self._pad_width,
                self._height + self._pad_height)

    def _pad_frame(self, frame: np.ndarray) -> np.ndarray:
        if not self._pad_width and not self._pad_height:
            return frame
        return np.pad(frame, ((0, self._pad_height), (0, self._pad_width), (0, 0)))

    def _crop_frame(self, frame: np.ndarray) -> np.ndarray:
        if not self._pad_width and not self._pad_height:
            return frame
        return np.ascontiguousarray(frame[:self._height, :self._width])

    def _needs_padding(self) -> bool:
        return bool(self._pad_width or self._pad_height)

    def interpolate(self, frame0: np.ndarray, frame1: np.ndarray) -> List[np.ndarray]:
        if frame0.shape != frame1.shape:
            raise ValueError("RIFE ncnn input frame dimensions do not match")
        pair_mode = classify_pair(frame0, frame1)
        if pair_mode != PAIR_NORMAL:
            return skipped_intermediates(
                frame0, frame1, self._multiplier, pair_mode)
        sequence = self._batch_interpolate([frame0, frame1])
        return sequence[1:-1]

    def _batch_interpolate(self, frames: List[np.ndarray]) -> List[np.ndarray]:
        """Internal batch processing without scene detection."""
        target_count = (len(frames) - 1) * self._multiplier + 1
        with tempfile.TemporaryDirectory(prefix="lve_rife_") as work:
            input_dir = os.path.join(work, "input")
            output_dir = os.path.join(work, "output")
            write_frames((self._pad_frame(f) for f in frames), input_dir,
                         "RIFE ncnn")
            self._run_batch(input_dir, output_dir, len(frames))
            padded = read_frames(output_dir, target_count, self._tile_size(),
                                 "RIFE ncnn")
            return [self._crop_frame(f) for f in padded]

    def interpolate_batch(self, frames: List[np.ndarray]) -> List[np.ndarray]:
        if not frames:
            return []
        if len(frames) == 1:
            return [frames[0].copy()]
        pair_modes = [classify_pair(f0, f1)
                      for f0, f1 in zip(frames, frames[1:])]
        # Fast path: all pairs are normal, use the batch executable directly.
        if all(mode == PAIR_NORMAL for mode in pair_modes):
            return self._batch_interpolate(frames)
        # Scene detection fallback: process consecutive normal pairs as
        # segments and use skipped-interpolation for static/scene-cut pairs.
        output: List[np.ndarray] = [frames[0].copy()]
        index = 0
        while index < len(frames) - 1:
            # Find the longest segment of consecutive normal pairs.
            end = index
            while end < len(frames) - 1 and pair_modes[end] == PAIR_NORMAL:
                end += 1
            if end > index:
                segment = frames[index:end + 1]
                result = self._batch_interpolate(segment)
                # Skip the first frame of the segment (already in output).
                output.extend(result[1:])
                index = end
            else:
                mode = pair_modes[index]
                output.extend(skipped_intermediates(
                    frames[index], frames[index + 1],
                    self._multiplier, mode))
                output.append(frames[index + 1].copy())
                index += 1
        return output

    def _run_batch(self, input_dir: str, output_dir: str,
                   input_count: int) -> int:
        """Run one directory job; caller owns the frame files."""
        target_count = (input_count - 1) * self._multiplier + 1
        make_directory(output_dir)
        padded_w = self._width + self._pad_width
        padded_h = self._height + self._pad_height
        command = [
            self._exe, "-i", input_dir.replace("\\", "/"),
            "-o", output_dir.replace("\\", "/"),
            "-n", str(target_count), "-m", self._model_dir.replace("\\", "/"),
            "-j", ncnn_jobs(padded_w, padded_h, engine="rife"),
            "-f", "%08d.png",
        ]
        if self._gpu_id is not None:
            command.extend(["-g", str(self._gpu_id)])
        if self._model.uhd and self._width * self._height > 1920 * 1080:
            command.append("-u")
        result = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=max(120, input_count * 30), creationflags=_no_window_flag())
        if result.returncode != 0:
            error = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError("RIFE ncnn batch processing failed: %s" %
                               (error or result.returncode))
        validate_outputs(output_dir, target_count, "RIFE ncnn")
        return target_count

    def process_directory(self, input_dir: str, output_dir: str,
                          input_count: int) -> int:
        """Run one directory job at native size (padded transparently)."""
        if input_count < 2:
            raise ValueError("RIFE ncnn directory batching needs at least 2 frames")
        make_directory(output_dir)
        frames = read_frames(input_dir, input_count, (self._width, self._height),
                             "RIFE ncnn")
        pair_modes = [classify_pair(f0, f1)
                      for f0, f1 in zip(frames, frames[1:])]
        target_count = (input_count - 1) * self._multiplier + 1
        if all(mode == PAIR_NORMAL for mode in pair_modes):
            if not self._needs_padding():
                self._run_batch(input_dir, output_dir, input_count)
                return target_count
            with tempfile.TemporaryDirectory(prefix="lve_rife_pad_") as work:
                padded_dir = os.path.join(work, "padded")
                result_dir = os.path.join(work, "result")
                write_frames((self._pad_frame(f) for f in frames), padded_dir,
                             "RIFE ncnn")
                self._run_batch(padded_dir, result_dir, input_count)
                padded = read_frames(result_dir, target_count, self._tile_size(),
                                     "RIFE ncnn")
                write_frames((self._crop_frame(f) for f in padded), output_dir,
                             "RIFE ncnn")
            return target_count
        result = self.interpolate_batch(frames)
        write_frames(result, output_dir, "RIFE ncnn")
        return target_count

    def native_ncnn_stage(self) -> NcnnInterpolationStage:
        """The fused worker tiles to 32 only, so it cannot run these models."""
        raise NotImplementedError(
            "The fused worker does not tile the %s model" % self._model.display)

    def release(self) -> None:
        pass
