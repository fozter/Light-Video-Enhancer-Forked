from dataclasses import dataclass, field
from typing import Optional


QUALITY_CHOICES = ("ultra", "fast", "balanced", "quality")


@dataclass
class EncodeConfig:
    codec: str = "auto"
    preset: str = "balanced"
    crf: int = 23
    pixel_format: str = "yuv420p"
    container: str = "mp4"
    copy_audio: bool = True
    overwrite: bool = False


@dataclass
class ProcessConfig:
    input_path: str = ""
    output_path: str = ""
    width: int = 0
    height: int = 0
    scale: float = 2.0
    sr_engine: str = "none"
    fi_engine: str = "none"
    sr_quality: str = "quality"
    fi_multiplier: Optional[int] = None
    fi_quality: str = "balanced"
    fi_model: Optional[str] = None
    encode: EncodeConfig = field(default_factory=EncodeConfig)
    fps: Optional[float] = None
    start_time: Optional[float] = None
    duration: Optional[float] = None
    device: str = "auto"
    torch_python: Optional[str] = None
    sr_first: bool = False
    ncnn_gpu: Optional[int] = None
    keep_partial: bool = False
    spark_reference_path: Optional[str] = None
    spark_reference_indices: str = ""
    spark_reference_guidance: float = 1.0

    def validate(self) -> None:
        if not self.input_path:
            raise ValueError("No input file was specified")
        if not self.output_path:
            raise ValueError("No output file was specified")
        if self.scale <= 0:
            raise ValueError("The super-resolution scale must be greater than 0")
        if self.width < 0 or self.height < 0:
            raise ValueError("The output width and height cannot be negative")
        if self.fi_multiplier is not None and not 1 <= self.fi_multiplier <= 8:
            raise ValueError("The interpolation multiplier must be between 1 and 8")
        if self.fps is not None and self.fps <= 0:
            raise ValueError("The output frame rate must be greater than 0")
        if self.start_time is not None and self.start_time < 0:
            raise ValueError("The start time cannot be negative")
        if self.duration is not None and self.duration <= 0:
            raise ValueError("The duration must be greater than 0")
        if not 0 <= self.encode.crf <= 63:
            raise ValueError("The quality value must be between 0 and 63")
        if self.sr_quality not in QUALITY_CHOICES:
            raise ValueError("Unknown super-resolution quality: %s" % self.sr_quality)
        if self.fi_quality not in QUALITY_CHOICES:
            raise ValueError("Unknown interpolation quality: %s" % self.fi_quality)
        if self.fi_model is not None:
            from .fi.rife_ncnn import RIFE_NCNN_MODEL_TOKENS
            if self.fi_model not in RIFE_NCNN_MODEL_TOKENS:
                raise ValueError("Unknown RIFE ncnn model: %s" % self.fi_model)
            if self.fi_engine not in ("rife_ncnn", "rife_ncnn_427"):
                raise ValueError(
                    "The RIFE model selection requires the rife_ncnn engine")
        if not 0.0 <= self.spark_reference_guidance <= 4.0:
            raise ValueError("The SparkVSR reference guidance strength must be between 0 and 4")
