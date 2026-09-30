"""RIFE PyTorch interpolation (in-process or persistent subprocess).

The engine is model-driven like its ncnn sibling: ``--fi-model`` carries a
RIFE model token and the registry below pins, for every selectable model, the
architecture class (fi/_rife_model.py), the weight file name under ``fi/``,
and the display string.  One model ships with the app: v4.27 (the FluidFrames
conversion, ``rife_v4.27_fluidframes.pth``).  The remaining weights — v4.25
(the historical ``flownet.pkl``) down to v4.20 — install from the optional
"rife-torch-models" pack.

Architecture provenance (hzwer Practical-RIFE releases, MIT):

- v4.20        four blocks [384, 192, 96, 48], 32-channel encoder, block
               outputs carry no feature map (6 channels)
- v4.21/v4.22  four blocks [256, 192, 96, 48], 32-channel encoder,
               13-channel block outputs with feature feedback
- v4.22 Lite   four blocks [192, 128, 64, 32], 16-channel encoder
- v4.25/v4.26 five blocks [192, 128, 96, 64, 32], 16-channel encoder
- v4.25 Lite   five blocks with a 24-channel block4 and a deeper scale list
- v4.27        FluidFrames 2026.3 five-block IFNet (see
               tools/convert_rife427_torch.py)
"""

import os
import subprocess
import threading
from typing import Dict, List, Optional, Tuple

import numpy as np

from .base import FrameInterpolationEngine
from ._scene_detect import PAIR_NORMAL, classify_pair, skipped_intermediates
from .._logging import get_logger
from .._paths import get_model_file, get_pkg_file, model_file_exists
from .._shared_frames import (
    SharedNDArray, close_process_pipes, read_framed, write_framed)

_log = get_logger(__name__)

try:
    import torch
    import torch.nn.functional as F
    _TORCH_AVAILABLE = True
except (ImportError, OSError):
    torch = None
    F = None
    _TORCH_AVAILABLE = False

if _TORCH_AVAILABLE:
    from ._rife_model import RIFE_TORCH_ARCHITECTURES


class RIFETorchModel:
    """One selectable RIFE PyTorch model."""

    __slots__ = ("token", "arch", "filename", "display", "bundled")

    def __init__(self, token: str, arch: str, filename: str,
                 display: str, bundled: bool = False):
        self.token = token
        self.arch = arch
        self.filename = filename
        self.display = display
        self.bundled = bool(bundled)

    def weight_file_exists(self) -> bool:
        return model_file_exists("fi", self.filename)

    def weight_path(self) -> str:
        return get_model_file("fi", self.filename)


# token, architecture class name (fi/_rife_model.py), weight file, display,
# bundled flag.  Newest first, mirroring the ncnn registry where the versions
# coincide: the GUI model list, the --fi-model choices, the capability
# report, and the interactive wizard all follow this order.
RIFE_TORCH_MODELS: Dict[str, RIFETorchModel] = {
    token: RIFETorchModel(token, arch, filename, display, bundled)
    for token, arch, filename, display, bundled in (
        ("4.27_fluidframes", "RIFE427", "rife_v4.27_fluidframes.pth",
         "4.27 (FluidFrames)", True),
        ("4.26", "FlownetCas", "rife_v4.26.pth", "4.26", False),
        ("4.25", "FlownetCas", "flownet.pkl", "4.25", False),
        ("4.25-lite", "FlownetCasLite", "rife_v4.25-lite.pth",
         "4.25 Lite", False),
        ("4.22", "Flownet421", "rife_v4.22.pth", "4.22", False),
        ("4.22-lite", "Flownet421Lite", "rife_v4.22-lite.pth",
         "4.22 Lite", False),
        ("4.21", "Flownet421", "rife_v4.21.pth", "4.21", False),
        ("4.20", "Flownet420", "rife_v4.20.pth", "4.20", False),
    )
}
DEFAULT_RIFE_TORCH_MODEL = "4.27_fluidframes"
RIFE_TORCH_MODEL_TOKENS: Tuple[str, ...] = tuple(RIFE_TORCH_MODELS)


def _pickle_write(pipe, obj) -> None:
    write_framed(pipe, obj)


def _pickle_read(pipe):
    return read_framed(pipe)


def _pack_array(value: np.ndarray) -> dict:
    array = np.ascontiguousarray(value)
    return {"__lve_array__": 1, "shape": tuple(int(part) for part in array.shape),
            "dtype": array.dtype.str, "data": array.tobytes(order="C")}


def _unpack_array(value) -> np.ndarray:
    if not isinstance(value, dict) or value.get("__lve_array__") != 1:
        raise TypeError("Invalid RIFE array message")
    shape = tuple(int(part) for part in value["shape"])
    result = np.frombuffer(value["data"], dtype=np.dtype(value["dtype"]))
    expected = int(np.prod(shape, dtype=np.int64))
    if result.size != expected:
        raise ValueError("RIFE array message length mismatch")
    return result.reshape(shape).copy()


def _clean_state_dict(state: dict) -> dict:
    if isinstance(state, dict) and "state_dict" in state:
        state = state["state_dict"]
    if any(key.startswith("module.") for key in state):
        state = {key.replace("module.", "", 1): value
                 for key, value in state.items()}
    return state


class RIFEEngine(FrameInterpolationEngine):
    """RIFE PyTorch interpolation with a selectable model.

    ``model`` selects the architecture and weights when it carries a RIFE
    model token (``4.20`` ... ``4.27_fluidframes``); the classic quality
    tiers are no longer interpreted by this engine and fall back to the
    default model.
    """

    def __init__(self, device: str = "auto", torch_python: Optional[str] = None,
                 model: Optional[str] = None):
        self._requested_device = device
        self._torch_python = torch_python
        self._model_def = RIFE_TORCH_MODELS.get(
            model, RIFE_TORCH_MODELS[DEFAULT_RIFE_TORCH_MODEL])
        self._use_subprocess = False
        self._subproc = None
        self._stderr_thread = None
        self._stderr_lines: List[str] = []
        self._model = None
        self._device = None
        self._fp16 = False
        self._scale = 1.0
        self._multiplier = 2
        self._width = self._height = 0
        self._pad_w = self._pad_h = 0
        self._model_path: Optional[str] = None
        self._shared_input = None
        self._shared_output = None

    @property
    def name(self) -> str:
        precision = "FP16" if self._fp16 else "FP32"
        if self._shared_input is not None:
            mode = "subprocess-shm"
        else:
            mode = "subprocess" if self._use_subprocess else "in-process"
        return "RIFE %s (%s, %s)" % (self._model_def.display, precision, mode)

    def initialize(self, src_width: int, src_height: int, multiplier: int = 2) -> None:
        if multiplier < 2:
            raise ValueError("RIFE interpolation multiplier must be at least 2")
        self._width, self._height = src_width, src_height
        self._multiplier = multiplier
        area = src_width * src_height
        self._scale = 0.25 if area > 3840 * 2160 else (0.5 if area > 1920 * 1080 * 2 else 1.0)
        alignment = max(128, int(128 / self._scale))
        self._pad_w = ((src_width + alignment - 1) // alignment) * alignment - src_width
        self._pad_h = ((src_height + alignment - 1) // alignment) * alignment - src_height
        self._model_path = self._model_def.weight_path()
        if not os.path.isfile(self._model_path):
            hint = "" if self._model_def.bundled else (
                " (download it with --download-model rife-torch-models)")
            raise FileNotFoundError(
                "RIFE %s weights are missing: light_video_enhancer_forked/fi/%s%s"
                % (self._model_def.display, self._model_def.filename, hint))

        current_cuda = bool(_TORCH_AVAILABLE and torch.cuda.is_available())
        allow_cpu = self._requested_device == "cpu"
        if _TORCH_AVAILABLE and (current_cuda or allow_cpu):
            self._init_inprocess(use_cuda=current_cuda and not allow_cpu)
        elif self._torch_python:
            self._init_subprocess()
        else:
            raise RuntimeError("RIFE requires CUDA PyTorch; RIFE ncnn-vulkan is an alternative")
        _log.info("RIFE ready: %dx%d, %dx, scale=%.2f", src_width, src_height,
                  multiplier, self._scale)

    def _init_inprocess(self, use_cuda: bool) -> None:
        self._device = torch.device("cuda" if use_cuda else "cpu")
        self._fp16 = use_cuda
        torch.set_grad_enabled(False)
        if use_cuda:
            # Avoid a multi-second algorithm search before the first frame.
            torch.backends.cudnn.benchmark = False
        arch = RIFE_TORCH_ARCHITECTURES[self._model_def.arch]
        self._model = arch().to(self._device).eval()
        state = _clean_state_dict(
            torch.load(self._model_path, map_location=self._device))
        missing, unexpected = self._model.load_state_dict(state, strict=False)
        if missing:
            raise RuntimeError(
                "The RIFE %s weights do not match the architecture "
                "(%d missing keys): %s" % (self._model_def.display, len(missing),
                                           ", ".join(missing[:4])))
        if unexpected:
            # The hzwer releases carry the training-only teacher/caltime
            # heads; they are never used at inference.
            _log.debug("RIFE %s weights carry %d training-only keys",
                       self._model_def.display, len(unexpected))
        if self._fp16:
            self._model.half()

    def _read_stderr(self, pipe) -> None:
        try:
            for line in pipe:
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    self._stderr_lines.append(text)
        except Exception:
            pass

    def _stderr_text(self) -> str:
        return "\n".join(self._stderr_lines[-20:])

    def _init_subprocess(self) -> None:
        script = get_pkg_file("fi", "_rife_infer.py")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        shared_args = {}
        try:
            self._shared_input = SharedNDArray.create((2, self._height, self._width, 3))
            self._shared_output = SharedNDArray.create(
                (self._multiplier - 1, self._height, self._width, 3))
            shared_args = {
                "ipc": "shared_v1",
                "shared_input": self._shared_input.descriptor(),
                "shared_output": self._shared_output.descriptor(),
            }
        except (OSError, RuntimeError, ValueError):
            self._release_shared()
            _log.warning("RIFE shared memory is unavailable; falling back to pipe transport", exc_info=True)

        self._subproc = subprocess.Popen(
            [self._torch_python, "-u", script], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=flags)
        self._stderr_thread = threading.Thread(
            target=self._read_stderr, args=(self._subproc.stderr,), daemon=True)
        self._stderr_thread.start()
        arguments = {"arch": self._model_def.arch,
                     "model_path": self._model_path, "fp16": True}
        arguments.update(shared_args)
        _pickle_write(self._subproc.stdin, arguments)
        _pickle_write(self._subproc.stdin, [])
        try:
            reply = _pickle_read(self._subproc.stdout)
        except EOFError as exc:
            self.release()
            raise RuntimeError("RIFE subprocess failed to start\n%s" % self._stderr_text()) from exc
        if isinstance(reply, dict) and "error" in reply:
            error = reply["error"]
            self.release()
            raise RuntimeError("RIFE subprocess failed to start: %s" % error)
        self._use_subprocess = True
        self._fp16 = True

    def interpolate(self, frame0: np.ndarray, frame1: np.ndarray) -> List[np.ndarray]:
        if frame0.shape != frame1.shape:
            raise ValueError("RIFE input frame dimensions do not match")
        pair_mode = classify_pair(frame0, frame1)
        if pair_mode != PAIR_NORMAL:
            return skipped_intermediates(
                frame0, frame1, self._multiplier, pair_mode)
        if self._use_subprocess:
            return self._interpolate_subprocess(frame0, frame1)
        return self._interpolate_inprocess(frame0, frame1)

    def _to_tensor(self, bgr: np.ndarray):
        rgb = np.ascontiguousarray(bgr[:, :, ::-1])
        tensor = torch.from_numpy(rgb).to(self._device, non_blocking=True)
        tensor = tensor.permute(2, 0, 1).unsqueeze(0)
        return tensor.half().div_(255.0) if self._fp16 else tensor.float().div_(255.0)

    def _interpolate_inprocess(self, frame0, frame1) -> List[np.ndarray]:
        i0, i1 = self._to_tensor(frame0), self._to_tensor(frame1)
        i0 = F.pad(i0, (0, self._pad_w, 0, self._pad_h))
        i1 = F.pad(i1, (0, self._pad_w, 0, self._pad_h))
        output = []
        with torch.inference_mode():
            for index in range(1, self._multiplier):
                pred = self._model.inference(i0, i1, index / self._multiplier, self._scale)
                pred = pred[0, :, :self._height, :self._width]
                rgb = pred.float().permute(1, 2, 0).clamp_(0, 1).mul_(255).byte().cpu().numpy()
                output.append(np.ascontiguousarray(rgb[:, :, ::-1]))
        return output

    def _interpolate_subprocess(self, frame0, frame1) -> List[np.ndarray]:
        if self._subproc is None or self._subproc.poll() is not None:
            raise RuntimeError("RIFE subprocess exited\n%s" % self._stderr_text())
        if self._shared_input is not None and self._shared_output is not None:
            np.copyto(self._shared_input.array[0], frame0)
            np.copyto(self._shared_input.array[1], frame1)
            request = {
                "protocol": 3,
                "timesteps": [i / self._multiplier for i in range(1, self._multiplier)],
                "pad_w": self._pad_w,
                "pad_h": self._pad_h,
                "scale": self._scale,
            }
        else:
            request = {
                "protocol": 2,
                "frame0": _pack_array(frame0),
                "frame1": _pack_array(frame1),
                "timesteps": [i / self._multiplier for i in range(1, self._multiplier)],
                "pad_w": self._pad_w,
                "pad_h": self._pad_h,
                "scale": self._scale,
            }
        try:
            _pickle_write(self._subproc.stdin, request)
            result = _pickle_read(self._subproc.stdout)
        except (EOFError, BrokenPipeError) as exc:
            raise RuntimeError("RIFE subprocess communication failed:\n%s" % self._stderr_text()) from exc
        if isinstance(result, dict) and "error" in result:
            raise RuntimeError("RIFE inference failed: %s" % result["error"])
        if self._shared_output is not None and isinstance(result, dict) and result.get("shared"):
            count = int(result.get("count", 0))
            return [self._shared_output.array[index].copy() for index in range(count)]
        try:
            return [_unpack_array(frame) for frame in result]
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("RIFE subprocess returned invalid data: %s" % exc) from exc

    def release(self) -> None:
        process, self._subproc = self._subproc, None
        if process is not None:
            try:
                if process.stdin:
                    process.stdin.close()
                process.wait(timeout=5)
            except Exception:
                process.kill()
                try:
                    process.wait(timeout=2)
                except Exception:
                    pass
        if self._stderr_thread and self._stderr_thread.is_alive():
            self._stderr_thread.join(timeout=1)
        close_process_pipes(process)
        self._release_shared()
        self._model = None
        if _TORCH_AVAILABLE and torch.cuda.is_available():
            torch.cuda.empty_cache()

    def _release_shared(self) -> None:
        for name in ("_shared_input", "_shared_output"):
            value = getattr(self, name, None)
            if value is not None:
                try:
                    value.close()
                except Exception:
                    pass
                setattr(self, name, None)
