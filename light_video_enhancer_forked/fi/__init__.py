from typing import Optional

from .base import FrameInterpolationEngine


def create_fi_engine(engine_name: str, device: str = "auto",
                     quality: str = "balanced",
                     torch_python: Optional[str] = None,
                     ncnn_gpu: Optional[int] = None) -> FrameInterpolationEngine:
    if engine_name == "rife":
        from .rife import RIFEEngine, RIFE_TORCH_MODELS
        # The token selects the architecture and weights; the classic
        # quality tiers are not interpreted by the PyTorch engine.
        model = quality if quality in RIFE_TORCH_MODELS else None
        return RIFEEngine(device=device, torch_python=torch_python, model=model)
    if engine_name == "ema_vfi":
        from .ema_vfi import EMAVFIEngine
        return EMAVFIEngine(device=device, quality=quality, torch_python=torch_python)
    if engine_name == "vfimamba":
        from .vfimamba import VFIMambaEngine
        return VFIMambaEngine(device=device, quality=quality, torch_python=torch_python)
    if engine_name == "rife_ncnn":
        from .rife_ncnn import RIFENcnnEngine
        return RIFENcnnEngine(quality=quality, gpu_id=ncnn_gpu)
    if engine_name == "rife_ncnn_427":
        # Deprecated alias: the merged engine selects the model via its
        # token.  Respect an explicit token, default to 4.27_fluidframes otherwise.
        from .rife_ncnn import (DEFAULT_RIFE_NCNN_MODEL, RIFE_NCNN_MODELS,
                                RIFENcnnEngine)
        token = quality if quality in RIFE_NCNN_MODELS else DEFAULT_RIFE_NCNN_MODEL
        return RIFENcnnEngine(quality=token, gpu_id=ncnn_gpu)
    if engine_name == "ifrnet_ncnn":
        from .ifrnet_ncnn import IFRNetNcnnEngine
        return IFRNetNcnnEngine(quality=quality, gpu_id=ncnn_gpu)
    if engine_name == "dis":
        from .dis_flow import DISFlowEngine
        return DISFlowEngine(quality=quality)
    if engine_name == "optical_flow":
        from .optical_flow import OpticalFlowEngine
        return OpticalFlowEngine(quality=quality)
    if engine_name == "torch_flow":
        from .torch_flow import TorchFlowEngine
        return TorchFlowEngine(quality=quality)
    if engine_name == "blend":
        from .blend import BlendFIEngine
        return BlendFIEngine(device=device, quality=quality)
    raise ValueError("Unknown interpolation engine: %s" % engine_name)


__all__ = ["FrameInterpolationEngine", "create_fi_engine"]
