import argparse
import math
import os
import sys
from typing import Optional

from ._logging import get_logger
from .config import EncodeConfig, ProcessConfig
from .encoding import CLI_CODEC_CHOICES, canonical_codec
from .fi.rife import RIFE_TORCH_MODEL_TOKENS
from .fi.rife_ncnn import RIFE_NCNN_MODEL_TOKENS

_log = get_logger(__name__)


def _auto_output(input_path: str, scale: float, fi_engine: str,
                 fi_mult: int, container: str, sr_engine: str = "auto",
                 fps: Optional[float] = None) -> str:
    directory = os.path.dirname(os.path.abspath(input_path))
    base = os.path.splitext(os.path.basename(input_path))[0]
    tags = []
    if sr_engine != "none" and scale != 1.0:
        tags.append("x%s" % ("%.2f" % scale).rstrip("0").rstrip("."))
    if fps:
        tags.append("fps%s" % ("%.3f" % fps).rstrip("0").rstrip("."))
    elif fi_engine != "none":
        tags.append("f%d" % fi_mult)
    safe_container = "".join(char for char in container if char.isalnum()).lower() or "mp4"
    return os.path.join(directory, "%s%s.%s" %
                        (base, "_" + "_".join(tags) if tags else "_enhanced", safe_container))


def _frame_rate(value: str) -> float:
    """Parse a frame rate: a plain number or an exact ratio like 24000/1001."""
    text = value.strip()
    rate = 0.0
    if "/" in text:
        numerator, _, denominator = text.partition("/")
        try:
            rate = float(numerator) / float(denominator)
        except (ValueError, ZeroDivisionError) as exc:
            raise argparse.ArgumentTypeError(
                "Frame rate must be a number or a ratio such as 24000/1001") from exc
    else:
        try:
            rate = float(text)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                "Frame rate must be a number or a ratio such as 24000/1001") from exc
    if not math.isfinite(rate) or rate <= 0:
        raise argparse.ArgumentTypeError(
            "The frame rate must be a positive finite number")
    return rate


def _ncnn_gpu(value: str) -> Optional[int]:
    lowered = value.lower()
    if lowered == "auto":
        return None
    if lowered == "cpu":
        return -1
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "NCNN device must be auto, cpu, or a non-negative GPU index") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("GPU index cannot be negative")
    return parsed


class _HelpFormatter(argparse.ArgumentDefaultsHelpFormatter,
                     argparse.RawDescriptionHelpFormatter):
    """Readable examples plus defaults."""


def _help_epilog(program: str) -> str:
    return """Examples:
  {0} input.mp4
  {0} input.mp4 -o output.mp4 --scale 2 --fi-multiplier 2
  {0} input.mp4 --sr-engine nvvfx --fi-engine rife --codec hevc_nvenc

Standalone commands:
  no arguments / --interactive  open the interactive wizard
  --system-info [--deep]        show system and backend information
  --capabilities-json           print the frontend capability JSON
  --environments-json           list cached Python/PyTorch environments
  --models-json                 show model-pack status

See the bundled CLI_GUIDE.md for the complete guide.""".format(program)


def build_parser() -> argparse.ArgumentParser:
    program = (os.path.basename(sys.executable)
               if getattr(sys, "frozen", False) else "lve")
    parser = argparse.ArgumentParser(
        prog=program,
        description="Light Video Enhancer-Forked - video super resolution, interpolation, and transcoding for Windows",
        epilog="Launch the backend EXE without arguments for the interactive wizard.",
        formatter_class=_HelpFormatter)
    parser.epilog = _help_epilog(program)
    parser._positionals.title = "Input"
    parser._optionals.title = "Processing and encoding options"
    parser.add_argument("input", help="input video path")
    parser.add_argument("-o", "--output", help="output video path")
    parser.add_argument("-s", "--scale", type=float, default=2.0,
                        help="super-resolution scale")
    parser.add_argument("-W", "--width", type=int, default=0,
                        help="explicit output width")
    parser.add_argument("-H", "--height", type=int, default=0,
                        help="explicit output height")
    parser.add_argument("--sr-engine", default="none", choices=[
        "dxva_vsr", "nvvfx", "span", "flashvsr", "seedvr2", "dloral", "osdenhancer", "sparkvsr",
        "realcugan", "realesrgan", "esrgan",
        "bicubic", "lanczos", "none"], help="super-resolution engine")
    parser.add_argument("--fi-engine", default="none", choices=[
        "rife", "ema_vfi", "vfimamba", "rife_ncnn", "rife_ncnn_427", "ifrnet_ncnn", "dis", "optical_flow",
        "torch_flow", "blend", "none"], help="interpolation engine")
    parser.add_argument("--sr-quality", default="quality",
                        choices=["fast", "balanced", "quality", "ultra"],
                        help="super-resolution quality")
    parser.add_argument("--fi-quality", default="balanced",
                        choices=["ultra", "fast", "balanced", "quality"],
                        help="interpolation quality")
    parser.add_argument("--fi-model", default=None,
                        choices=list(RIFE_TORCH_MODEL_TOKENS) + [
                            token for token in RIFE_NCNN_MODEL_TOKENS
                            if token not in RIFE_TORCH_MODEL_TOKENS],
                        help="RIFE model, used when the interpolation engine "
                             "is rife (PyTorch) or rife_ncnn "
                             "(4.20 ... 4.27_fluidframes; the valid set "
                             "depends on the engine)")
    parser.add_argument("--fi-multiplier", type=int, default=None,
                        help="interpolation multiplier (default: 2, or the smallest "
                             "grid that covers --fps)")
    parser.add_argument("--sr-first", action="store_true",
                        help="run super resolution before interpolation (more VRAM and compute)")
    parser.add_argument("--codec", default="auto", choices=CLI_CODEC_CHOICES,
                        help="video encoder")
    parser.add_argument("--preset", default="balanced",
                        help="encoder speed/quality preset")
    parser.add_argument("--crf", type=int, default=23,
                        help="CQ/CRF quality value (lower is better, 0-63)")
    parser.add_argument("--container", default="mp4", choices=["mp4", "mkv", "mov"],
                        help="output container")
    parser.add_argument("--fps", type=_frame_rate,
                        help="target output frame rate; accepts numbers or exact "
                             "ratios like 24000/1001 (an interpolation engine runs on "
                             "the smallest grid that covers it, then frames are "
                             "added/dropped to preserve duration; the grid is "
                             "capped at 8x the source rate)")
    parser.add_argument("--start", type=float, help="start time in seconds")
    parser.add_argument("--duration", type=float, help="duration to process in seconds")
    parser.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"],
                        help="PyTorch device")
    parser.add_argument("--torch-python",
                        help="python.exe from an external CUDA PyTorch environment")
    parser.add_argument("--spark-reference",
                        help="SparkVSR HQ reference image or image directory")
    parser.add_argument("--spark-reference-indices", default="",
                        help="source-frame indices for SparkVSR references, e.g. 0,48")
    parser.add_argument("--spark-reference-guidance", type=float, default=1.0,
                        help="SparkVSR reference guidance strength (0-4)")
    parser.add_argument("--ncnn-gpu", type=_ncnn_gpu, default=None,
                        metavar="auto|cpu|INDEX", help="NCNN Vulkan device")
    parser.add_argument("--no-audio", action="store_true", help="do not copy source audio")
    parser.add_argument("-y", "--overwrite", action="store_true", help="overwrite existing output")
    parser.add_argument("--keep-partial", action="store_true",
                        help="keep partial output on failure or cancellation")
    parser.add_argument("--ssim-identical", type=float, default=None,
                        help="SSIM score above which two frames are treated as identical")
    parser.add_argument("--ssim-scene-cut", type=float, default=None,
                        help="SSIM score below which a scene cut is detected")
    return parser


def parse_args(argv=None) -> ProcessConfig:
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.device == "cpu" and (args.sr_engine == "nvvfx" or args.fi_engine == "torch_flow"):
        parser.error("NVIDIA VFX and CUDA optical flow cannot use --device cpu")
    if args.fi_engine == "ifrnet_ncnn" and args.ncnn_gpu == -1:
        parser.error("IFRNet NCNN requires a Vulkan GPU")
    if args.sr_engine == "span" and args.ncnn_gpu == -1:
        parser.error("SPAN NCNN requires a Vulkan GPU")
    if args.fi_engine == "rife_ncnn_427":
        # Deprecated alias: the merged engine selects the model via --fi-model.
        args.fi_engine = "rife_ncnn"
        if args.fi_model is None:
            args.fi_model = "4.27_fluidframes"
    output = args.output or _auto_output(
        args.input, args.scale, args.fi_engine, args.fi_multiplier or 2,
        args.container, args.sr_engine, fps=args.fps)
    container = os.path.splitext(output)[1].lstrip(".").lower() or args.container
    codec = canonical_codec(args.codec)
    if codec == "ffv1":
        if container != "mkv":
            parser.error("FFV1 can only be written to the MKV container")
    encode = EncodeConfig(
        codec=codec, preset=args.preset, crf=args.crf,
        pixel_format="yuv420p", container=container,
        copy_audio=not args.no_audio, overwrite=args.overwrite)
    if args.ssim_identical is not None or args.ssim_scene_cut is not None:
        from light_video_enhancer_forked.fi import _scene_detect as _scene_detect_module
        for flag, value in (("--ssim-identical", args.ssim_identical),
                            ("--ssim-scene-cut", args.ssim_scene_cut)):
            if value is not None and not math.isfinite(value):
                parser.error("%s must be a finite number in the 0-1 range" % flag)
        if args.ssim_identical is not None:
            _scene_detect_module.SSIM_IDENTICAL = args.ssim_identical
        if args.ssim_scene_cut is not None:
            _scene_detect_module.SSIM_SCENE_CUT = args.ssim_scene_cut
    return ProcessConfig(
        input_path=args.input, output_path=output, width=args.width, height=args.height,
        scale=args.scale, sr_engine=args.sr_engine, fi_engine=args.fi_engine,
        sr_quality=args.sr_quality, fi_multiplier=args.fi_multiplier,
        fi_quality=args.fi_quality, fi_model=args.fi_model,
        encode=encode, fps=args.fps, start_time=args.start, duration=args.duration,
        device=args.device, torch_python=args.torch_python, sr_first=args.sr_first,
        ncnn_gpu=args.ncnn_gpu, keep_partial=args.keep_partial,
        spark_reference_path=args.spark_reference,
        spark_reference_indices=args.spark_reference_indices,
        spark_reference_guidance=args.spark_reference_guidance)
