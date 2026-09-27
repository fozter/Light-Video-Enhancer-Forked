"""IFRNet interpolation through the persistent NCNN/Vulkan worker."""

import os
from typing import List, Optional

import numpy as np

from light_video_enhancer_forked._logging import get_logger
from light_video_enhancer_forked._paths import get_model_dir
from light_video_enhancer_forked.fi.base import FrameInterpolationEngine
from light_video_enhancer_forked.ncnn_contract import NcnnInterpolationStage

_log = get_logger(__name__)


class IFRNetNcnnEngine(FrameInterpolationEngine):
    """Lightweight cross-vendor interpolation without PyTorch.

    IFRNet is intentionally executed only by the shared-memory worker.  A
    per-pair PNG/CLI fallback would hide a severe performance regression and
    is therefore not exposed as a usable backend.
    """

    _MODEL_BY_QUALITY = {
        "fast": "IFRNet_S_Vimeo90K",
        "balanced": "IFRNet_Vimeo90K",
        "quality": "IFRNet_L_Vimeo90K",
        "ultra": "IFRNet_L_Vimeo90K",
    }

    def __init__(self, quality: str = "balanced",
                 gpu_id: Optional[int] = None):
        self._quality = quality if quality in self._MODEL_BY_QUALITY else "balanced"
        self._gpu_id = gpu_id
        self._width = 0
        self._height = 0
        self._multiplier = 2
        self._model_dir = ""

    @property
    def name(self) -> str:
        target = "auto GPU" if self._gpu_id is None else "GPU %d" % self._gpu_id
        tta = ", spatial TTA" if self._quality == "ultra" else ""
        return "IFRNet ncnn-vulkan (%s%s, %s)" % (
            self._quality, tta, target)

    @property
    def supports_batch(self) -> bool:
        return True

    def initialize(self, width: int, height: int, multiplier: int = 2) -> None:
        if multiplier < 2:
            raise ValueError("IFRNet interpolation multiplier must be at least 2")
        if self._gpu_id == -1:
            raise RuntimeError("IFRNet NCNN requires a Vulkan GPU")
        model_name = self._MODEL_BY_QUALITY[self._quality]
        self._model_dir = get_model_dir("ncnn", "ifrnet", model_name)
        required = [
            os.path.join(self._model_dir, "ifrnet.param"),
            os.path.join(self._model_dir, "ifrnet.bin"),
        ]
        missing = [path for path in required if not os.path.isfile(path)]
        if missing:
            raise FileNotFoundError(
                "IFRNet ncnn resources are incomplete: %s" % ", ".join(missing))
        self._width, self._height = int(width), int(height)
        self._multiplier = int(multiplier)
        _log.info("IFRNet ncnn ready: %dx%d, %dx, model=%s",
                  width, height, multiplier, model_name)

    def interpolate(self, frame0: np.ndarray,
                    frame1: np.ndarray) -> List[np.ndarray]:
        raise RuntimeError(
            "IFRNet must run through the native persistent NCNN worker; "
            "verify that lve-ncnn-worker.exe is available and the fast path is not disabled")

    def native_ncnn_stage(self) -> NcnnInterpolationStage:
        return NcnnInterpolationStage(
            model_dir=self._model_dir,
            kind="ifrnet",
            tta=self._quality == "ultra")

    def release(self) -> None:
        pass
