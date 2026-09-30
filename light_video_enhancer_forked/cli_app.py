"""Interactive console entry point for the standalone backend executable."""

import ctypes
import os
import sys
from typing import Iterable, Optional

from . import __version__
from .encoding import CLI_CODEC_CHOICES
from .fi.rife import RIFE_TORCH_MODEL_TOKENS
from .fi.rife_ncnn import RIFE_NCNN_MODEL_TOKENS


_SR_ENGINES = (
    "dxva_vsr", "nvvfx", "span", "flashvsr", "seedvr2", "dloral", "osdenhancer", "sparkvsr",
    "realcugan", "realesrgan", "esrgan", "bicubic", "lanczos", "none",
)
_FI_ENGINES = (
    "rife", "ema_vfi", "vfimamba", "rife_ncnn",
    "ifrnet_ncnn", "dis", "optical_flow", "torch_flow", "blend", "none",
)
_QUALITIES = ("fast", "balanced", "quality", "ultra")


def _console_title() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.kernel32.SetConsoleTitleW(
            "Light Video Enhancer-Forked CLI %s" % __version__)
    except (AttributeError, OSError):
        pass


def _read(prompt: str) -> Optional[str]:
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None


def _path(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"\"", "'"}:
        return value[1:-1]
    return value


def _choice(label: str, values: Iterable[str], default: str) -> Optional[str]:
    choices = tuple(values)
    while True:
        value = _read("%s [%s] (%s): " % (label, default, "/".join(choices)))
        if value is None:
            return None
        value = value or default
        if value in choices:
            return value
        print("Enter one of the listed values.")


def _number(label: str, default: str,
            minimum: float, maximum: float) -> Optional[str]:
    while True:
        value = _read("%s [%s]: " % (label, default))
        if value is None:
            return None
        value = value or default
        try:
            parsed = float(value)
        except ValueError:
            parsed = minimum - 1
        if minimum <= parsed <= maximum:
            return value
        print("Enter a number between %.1f and %.1f." % (minimum, maximum))


def _yes_no(label: str, default: bool) -> Optional[bool]:
    marker = "Y/n" if default else "y/N"
    while True:
        value = _read("%s [%s]: " % (label, marker))
        if value is None:
            return None
        if not value:
            return default
        lowered = value.lower()
        if lowered in {"y", "yes"}:
            return True
        if lowered in {"n", "no"}:
            return False
        print("Enter y or n.")


def interactive_arguments() -> Optional[list]:
    """Collect a common processing configuration without hiding advanced CLI flags."""
    _console_title()
    executable = os.path.basename(sys.executable if getattr(sys, "frozen", False) else sys.argv[0])
    print("=" * 68)
    print("Light Video Enhancer-Forked CLI %s" % __version__)
    print("Language: English (system default)")
    print("This is the complete standalone command-line backend. The wizard covers common options;")
    print("run %s --help for every advanced option." % executable)
    print("You can drag a video file into this window.")
    print("=" * 68)

    while True:
        raw_input = _read("Input video (q to quit): ")
        if raw_input is None or raw_input.lower() in {"q", "quit", "exit"}:
            return None
        input_path = _path(raw_input)
        if os.path.isfile(input_path):
            break
        print("The file does not exist. Try again.")

    raw_output = _read("Output file (blank for automatic name): ")
    if raw_output is None:
        return None
    output_path = _path(raw_output)
    scale = _number("Super-resolution scale", "2", 1.0, 8.0)
    if scale is None:
        return None
    sr_engine = _choice("Super-resolution engine", _SR_ENGINES, "none")
    if sr_engine is None:
        return None
    fi_engine = _choice("Interpolation engine", _FI_ENGINES, "none")
    if fi_engine is None:
        return None
    frame_rate = None
    fi_multiplier = None
    while frame_rate is None:
        raw_rate = _read("Target frame rate (number or 24000/1001, blank for multiplier): ")
        if raw_rate is None:
            return None
        raw_rate = raw_rate.strip()
        if not raw_rate:
            frame_rate = ""
            break
        try:
            from .cli import _frame_rate
            _frame_rate(raw_rate)
            frame_rate = raw_rate
        except Exception:
            print("Enter a number or an exact ratio such as 24000/1001, or leave blank.")
    if not frame_rate:
        fi_multiplier = _number("Interpolation multiplier", "2", 1.0, 4.0)
        if fi_multiplier is None:
            return None
    fi_model = None
    fi_quality = None
    if fi_engine == "rife":
        print("Optional RIFE PyTorch models 4.20-4.26 download with: --download-model rife-torch-models")
        fi_model = _choice("RIFE PyTorch model", RIFE_TORCH_MODEL_TOKENS, "4.27_fluidframes")
        if fi_model is None:
            return None
    elif fi_engine == "rife_ncnn":
        print("Optional RIFE models 4.20-4.26 download with: --download-model rife-ncnn-models")
        fi_model = _choice("RIFE ncnn model", RIFE_NCNN_MODEL_TOKENS, "4.27_fluidframes")
        if fi_model is None:
            return None
    else:
        fi_quality = _choice("Interpolation quality", _QUALITIES, "balanced")
        if fi_quality is None:
            return None
    sr_quality = _choice("Super-resolution quality", _QUALITIES, "quality")
    if sr_quality is None:
        return None
    codec = _choice("Encoder", CLI_CODEC_CHOICES, "auto")
    if codec is None:
        return None
    overwrite = _yes_no("Overwrite an existing output", False)
    if overwrite is None:
        return None

    arguments = [
        input_path,
        "--scale", scale,
        "--sr-engine", sr_engine,
        "--fi-engine", fi_engine,
        "--sr-quality", sr_quality,
        "--codec", codec,
    ]
    if frame_rate:
        arguments.extend(["--fps", frame_rate])
    else:
        arguments.extend(["--fi-multiplier", str(int(float(fi_multiplier)))])
    if fi_model is not None:
        arguments.extend(["--fi-model", fi_model])
    else:
        arguments.extend(["--fi-quality", fi_quality])
    if output_path:
        arguments.extend(["--output", output_path])
    if overwrite:
        arguments.append("--overwrite")
    print()
    print("Processing will start. Press Ctrl+C to cancel.")
    confirmed = _yes_no("Continue", True)
    return arguments if confirmed else None
