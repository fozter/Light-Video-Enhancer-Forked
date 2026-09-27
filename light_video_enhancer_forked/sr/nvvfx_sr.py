"""NVIDIA Video Effects super-resolution backend with isolated inference."""

import os
import subprocess
import sys
import threading
from typing import List, Optional

import numpy as np

from .base import SuperResolutionEngine
from .._logging import get_logger
from .._shared_frames import (
    FramedPipeReader, SharedNDArray, close_process_pipes, write_framed)

_log = get_logger(__name__)

_NVVFX_QUALITY_LEVELS = {
    "LOW": 1, "MEDIUM": 2, "HIGH": 3, "ULTRA": 4,
    "DENOISE_LOW": 8, "DENOISE_MEDIUM": 9,
    "DENOISE_HIGH": 10, "DENOISE_ULTRA": 11,
    "DEBLUR_LOW": 12, "DEBLUR_MEDIUM": 13,
    "DEBLUR_HIGH": 14, "DEBLUR_ULTRA": 15,
}

_GUI_QUALITY_LEVELS = {
    "fast": "LOW",
    "balanced": "MEDIUM",
    "quality": "HIGH",
    "ultra": "ULTRA",
}


def _pack_array(value: np.ndarray) -> dict:
    array = np.ascontiguousarray(value)
    return {
        "__lve_array__": 1,
        "shape": tuple(int(part) for part in array.shape),
        "dtype": array.dtype.str,
        "data": array.tobytes(order="C"),
    }


def _unpack_array(value) -> np.ndarray:
    if not isinstance(value, dict) or value.get("__lve_array__") != 1:
        raise TypeError("Invalid NV-VFX array message")
    shape = tuple(int(part) for part in value["shape"])
    result = np.frombuffer(value["data"], dtype=np.dtype(value["dtype"]))
    expected = int(np.prod(shape, dtype=np.int64))
    if result.size != expected:
        raise ValueError("NV-VFX array message length mismatch")
    return result.reshape(shape).copy()


class NVVFX_SR_Engine(SuperResolutionEngine):
    def __init__(self, quality: str = "HIGH", torch_python: Optional[str] = None):
        requested = str(quality or "quality")
        self._quality_name = _GUI_QUALITY_LEVELS.get(requested.lower(), requested.upper())
        if self._quality_name not in _NVVFX_QUALITY_LEVELS:
            self._quality_name = "HIGH"
        self._quality_value = _NVVFX_QUALITY_LEVELS[self._quality_name]
        self._torch_python = torch_python
        self._proc = None
        self._reader = None
        self._stderr_thread = None
        self._stderr_lines: List[str] = []
        self._shared_input = None
        self._shared_output = None
        self._src_w = self._src_h = 0
        self._dst_w = self._dst_h = 0

    @property
    def name(self) -> str:
        mode = "isolated-shm" if self._shared_input is not None else "isolated"
        return "NVIDIA Video Effects VSR (%s, %s)" % (self._quality_name, mode)

    def initialize(self, src_width: int, src_height: int,
                   dst_width: int, dst_height: int) -> None:
        self._src_w, self._src_h = src_width, src_height
        self._dst_w, self._dst_h = dst_width, dst_height
        if getattr(sys, "frozen", False) and not self._torch_python:
            raise RuntimeError("The packaged build requires an external CUDA Python environment to be selected before using NV-VFX")
        self._init_subprocess()

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
        from .._paths import get_pkg_dir

        python_executable = self._torch_python or sys.executable
        infer_script = os.path.join(get_pkg_dir(), "sr", "_nvvfx_infer.py")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        shared_args = {}
        try:
            self._shared_input = SharedNDArray.create((self._src_h, self._src_w, 3))
            self._shared_output = SharedNDArray.create((self._dst_h, self._dst_w, 3))
            shared_args = {
                "ipc": "shared_v1",
                "shared_input": self._shared_input.descriptor(),
                "shared_output": self._shared_output.descriptor(),
            }
        except (OSError, RuntimeError, ValueError):
            self._release_shared()
            _log.warning("NV-VFX shared memory is unavailable; falling back to pipe transport", exc_info=True)

        self._proc = subprocess.Popen(
            [python_executable, "-u", infer_script],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=creationflags)
        self._reader = FramedPipeReader(self._proc.stdout, "lve-nvvfx-read")
        self._stderr_thread = threading.Thread(
            target=self._read_stderr, args=(self._proc.stderr,), daemon=True)
        self._stderr_thread.start()
        arguments = {
            "src_w": self._src_w, "src_h": self._src_h,
            "dst_w": self._dst_w, "dst_h": self._dst_h,
            "quality": self._quality_value,
        }
        arguments.update(shared_args)
        self._write(arguments)
        result = self._read(timeout=90.0)
        if isinstance(result, dict) and "error" in result:
            error = result["error"]
            self.release()
            raise RuntimeError("NV-VFX initialization failed: %s" % error)
        _log.info("NV-VFX VSR ready: %dx%d -> %dx%d (%s, %s)",
                  self._src_w, self._src_h, self._dst_w, self._dst_h,
                  self._quality_name,
                  "shared-memory" if self._shared_input is not None else "pipe")

    def process(self, frame: np.ndarray) -> np.ndarray:
        if not self._proc:
            raise RuntimeError("NV-VFX is not initialized")
        if self._shared_input is not None and self._shared_output is not None:
            np.copyto(self._shared_input.array, frame)
            self._write({"protocol": 2, "command": "process"})
        else:
            self._write(_pack_array(frame))
        result = self._read(timeout=30.0)
        if isinstance(result, dict) and "error" in result:
            raise RuntimeError("NV-VFX inference failed: %s" % result["error"])
        if self._shared_output is not None and isinstance(result, dict) and result.get("shared"):
            return self._shared_output.array.copy()
        try:
            return _unpack_array(result)
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("NV-VFX returned invalid data: %s" % exc) from exc

    def release(self) -> None:
        process, self._proc = self._proc, None
        if process is not None:
            try:
                if process.stdin:
                    process.stdin.close()
                process.wait(timeout=3)
            except (subprocess.TimeoutExpired, OSError):
                process.kill()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
        if self._reader is not None:
            self._reader.join(timeout=1)
            self._reader = None
        if self._stderr_thread and self._stderr_thread.is_alive():
            self._stderr_thread.join(timeout=1)
        close_process_pipes(process)
        self._release_shared()

    def _release_shared(self) -> None:
        for name in ("_shared_input", "_shared_output"):
            value = getattr(self, name, None)
            if value is not None:
                try:
                    value.close()
                except Exception:
                    pass
                setattr(self, name, None)

    def _write(self, obj) -> None:
        if not self._proc or not self._proc.stdin:
            raise RuntimeError("The NV-VFX subprocess is not running")
        try:
            write_framed(self._proc.stdin, obj)
        except (BrokenPipeError, OSError) as exc:
            raise RuntimeError("The NV-VFX subprocess exited\n%s" % self._stderr_text()) from exc

    def _read(self, timeout: float):
        if self._reader is None:
            raise RuntimeError("The NV-VFX subprocess is not running")
        try:
            return self._reader.read(timeout)
        except TimeoutError as exc:
            self.release()
            raise TimeoutError(
                "NV-VFX did not respond within %.0f seconds; update the NVIDIA driver/SDK or use D3D11 VSR instead" % timeout
            ) from exc
        except EOFError as exc:
            raise RuntimeError("NV-VFX subprocess communication failed: %s\n%s" % (
                exc, self._stderr_text())) from exc
