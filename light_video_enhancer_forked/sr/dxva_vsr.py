import os
import ctypes
import cv2
import numpy as np

from ._dxva_convert import bgr_to_nv12
from .base import SuperResolutionEngine
from .._paths import get_data_file


def _bgr_to_nv12(bgr: np.ndarray, align_w: int = 0, align_h: int = 0) -> np.ndarray:
    """BGR24 -> NV12 (YUV444 conversion + 2x2 average, unambiguous layout)

    align_w/align_h: when > 0 the output is aligned to this size (zero-padded
    on the right/bottom) to match the alignSrcW x alignSrcH expected by the bridge DLL.
    """
    h, w = bgr.shape[:2]
    yuv = cv2.cvtColor(bgr, cv2.COLOR_BGR2YUV)

    y = yuv[:, :, 0].ravel()

    h2, w2 = h // 2, w // 2
    u = yuv[:, :, 1].reshape(h2, 2, w2, 2).mean(axis=(1, 3)).astype(np.uint8).ravel()
    v = yuv[:, :, 2].reshape(h2, 2, w2, 2).mean(axis=(1, 3)).astype(np.uint8).ravel()

    uv = np.empty(len(u) * 2, dtype=np.uint8)
    uv[0::2] = u
    uv[1::2] = v
    nv12 = np.concatenate([y, uv])

    # Align to alignSrcW x alignSrcH (the size the bridge expects)
    if align_w > 0 and align_h > 0 and (align_w != w or align_h != h):
        aligned = np.zeros(align_w * align_h * 3 // 2, dtype=np.uint8)
        # Y plane: bulk copy via numpy slicing (instead of a per-row Python loop)
        y_plane = y.reshape(h, w)
        aligned_y = aligned[:align_h * align_w].reshape(align_h, align_w)
        aligned_y[:h, :w] = y_plane
        # UV plane: bulk copy via numpy slicing
        y_off = align_w * align_h
        uv_src = nv12[h * w:].reshape(h2, w)
        uv_dst = aligned[y_off:].reshape(h2, align_w)
        uv_dst[:h2, :w] = uv_src
        return aligned

    return nv12


class DXVA_VSR_Engine(SuperResolutionEngine):
    """
    Invokes the NVIDIA driver's RTX Video Super Resolution through the Direct3D 11
    Video Processor API.

    How it works:
    NVIDIA RTX VSR intercepts D3D11 VideoProcessorBlt calls at the driver level
    and automatically applies AI super resolution when video content is detected.
    This engine mimics a media player:
    1. Create the D3D11Device + D3D11VideoDevice + D3D11VideoProcessor
    2. Feed each frame into the VideoProcessor as an NV12 texture
    3. Read back the driver-enhanced (super-resolved) frame

    Prerequisites:
    - An NVIDIA RTX 30/40-series GPU
    - NVIDIA Control Panel -> Adjust video image settings -> enable RTX video enhancement
    - A compiled dxva_vsr_bridge.dll (see the bridge/ directory)
    """

    def __init__(self):
        self._dll = None
        self._handle = None
        self._src_width = 0
        self._src_height = 0
        self._dst_width = 0
        self._dst_height = 0
        self._initialized = False

    @property
    def name(self) -> str:
        return "NVIDIA RTX VSR (D3D11 Video Processor)"

    def _load_dll(self) -> ctypes.CDLL:
        if self._dll is not None:
            return self._dll
        dll_path = get_data_file("bridge", "dxva_vsr_bridge.dll")
        if not os.path.exists(dll_path):
            raise FileNotFoundError(
                f"{dll_path} was not found. Build it by running build.sh in the bridge/ directory."
            )
        self._dll = ctypes.CDLL(dll_path)

        self._dll.dxva_vsr_create.argtypes = []
        self._dll.dxva_vsr_create.restype = ctypes.c_void_p

        self._dll.dxva_vsr_initialize.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int,
        ]
        self._dll.dxva_vsr_initialize.restype = ctypes.c_int

        self._dll.dxva_vsr_process.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ]
        self._dll.dxva_vsr_process.restype = ctypes.c_int

        self._dll.dxva_vsr_get_output.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_int,
        ]
        self._dll.dxva_vsr_get_output.restype = ctypes.c_int

        self._dll.dxva_vsr_release.argtypes = [ctypes.c_void_p]
        self._dll.dxva_vsr_release.restype = None

        self._dll.dxva_vsr_get_output_size.argtypes = [ctypes.c_void_p]
        self._dll.dxva_vsr_get_output_size.restype = ctypes.c_int

        return self._dll

    def initialize(self, src_width: int, src_height: int,
                   dst_width: int, dst_height: int) -> None:
        if self._initialized:
            if (src_width != self._src_width or src_height != self._src_height or
                    dst_width != self._dst_width or dst_height != self._dst_height):
                raise ValueError(
                    f"The DXVA VSR engine was initialized at "
                    f"{self._src_width}x{self._src_height}->{self._dst_width}x{self._dst_height}; "
                    f"re-specifying dimensions ({src_width}x{src_height}->{dst_width}x{dst_height}) is not supported."
                )
            return
        self._src_width = src_width
        self._src_height = src_height
        self._dst_width = dst_width
        self._dst_height = dst_height

        dll = self._load_dll()
        print(f"[dxva_vsr] Creating the D3D11 device + Video Processor ({src_width}x{src_height}->{dst_width}x{dst_height}) ...")
        self._handle = dll.dxva_vsr_create()
        result = dll.dxva_vsr_initialize(
            self._handle, src_width, src_height, dst_width, dst_height
        )
        if result != 0:
            err_map = {-1: "D3D11CreateDevice", -2: "CreateVideoProcessor", -3: "CreateTextures"}
            self.release()
            step = err_map.get(result, f"code={result}")
            raise RuntimeError(
                f"D3D11 Video Processor initialization failed ({step}).\n"
                "Make sure that:\n"
                "1. An NVIDIA RTX 30/40/50-series GPU is installed\n"
                "2. RTX video enhancement is enabled in the NVIDIA Control Panel (Video section)\n"
                "3. The driver is up to date (Game Ready or Studio)\n"
                "If the bridge DLL cannot be built, use --sr-engine nvvfx instead."
            )
        print("[dxva_vsr] D3D11 Video Processor initialization complete")
        self._initialized = True

    def process(self, frame: np.ndarray) -> np.ndarray:
        if not self._initialized:
            raise RuntimeError("The engine is not initialized; call initialize() first")
        dll = self._dll

        h, w = frame.shape[:2]
        if w != self._src_width or h != self._src_height:
            raise ValueError(
                f"Input frame size {w}x{h} does not match the initialized size {self._src_width}x{self._src_height}"
            )
        frame_bgr = frame if frame.shape[2] == 3 else frame[:, :, :3]

        align_w = ((self._src_width + 1) // 2) * 2
        align_h = ((self._src_height + 1) // 2) * 2
        nv12 = bgr_to_nv12(frame_bgr, align_w=align_w, align_h=align_h)
        nv12 = np.ascontiguousarray(nv12)

        in_ptr = nv12.ctypes.data_as(ctypes.POINTER(ctypes.c_ubyte))
        result = dll.dxva_vsr_process(self._handle, in_ptr, w, h, 0)
        if result != 0:
            raise RuntimeError(f"VideoProcessor processing failed (error code: {result})")

        out_size = dll.dxva_vsr_get_output_size(self._handle)
        out_buf = (ctypes.c_ubyte * out_size)()
        result = dll.dxva_vsr_get_output(self._handle, out_buf, out_size)
        if result != 0:
            raise RuntimeError(f"Reading the output frame failed (error code: {result})")

        bgra = np.ctypeslib.as_array(out_buf).reshape(
            self._dst_height, self._dst_width, 4
        )
        return np.ascontiguousarray(bgra[:, :, :3])

    def release(self) -> None:
        if self._handle and self._dll:
            self._dll.dxva_vsr_release(self._handle)
        self._handle = None
        self._initialized = False
