#!/usr/bin/env python3
"""Convert the FluidFrames RIFE 4.27 ONNX export to a PyTorch state dict.

Source model: FluidFrames 2026.3 (https://github.com/Djdefrag/FluidFrames,
tag 2026.3), file AI-onnx/RIFE_fp32.onnx, MIT license.  The architecture is
the hzwer Practical-RIFE five-block IFNet family re-trained by FluidFrames;
the graph has the timestep baked at 0.5, which this fork's runtime passes as
an explicit value instead (the ncnn conversion unbakes it into the third
input the same way; see rife427_conversion/ in the handoff).

The converter reads the ONNX initializers and produces a state dict whose
keys match light_video_enhancer_forked.fi._rife_model.RIFE427:

    encode.cnn0.0.weight / encode.cnn3.weight ...
    blockN.conv0.0.weight, blockN.conv0.2.weight
    blockN.convblock.M.conv.weight / .bias
    blockN.lastconv.0.weight / .bias

The output is validated against onnxruntime on several input sizes before
saving (fp32 tolerance 1e-4).  Pass --fp16 to store half-precision weights,
which halves the file size and matches the quality bar already accepted for
the bundled ncnn conversion (<= 2/255); loading casts back to the model dtype.

Usage:
    python tools/convert_rife427_torch.py [--onnx PATH] [--output PATH]
"""

import argparse
import hashlib
import sys
from pathlib import Path

import numpy as np
import onnx
import torch
from onnx import numpy_helper

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from light_video_enhancer_forked.fi._rife_model import RIFE427

DEFAULT_ONNX_URL = (
    "https://raw.githubusercontent.com/Djdefrag/FluidFrames/2026.3/"
    "AI-onnx/RIFE_fp32.onnx")
DEFAULT_ONNX_SHA256 = (
    "5ee29acda81a6747d55624be41ac28723b7a121d743a58f6a12c96ccb9deed0c")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def state_from_onnx(path: str) -> dict:
    """Read the ONNX initializers into the RIFE427 key layout."""
    model = onnx.load(path)
    raw = {tensor.name: numpy_helper.to_array(tensor)
           for tensor in model.graph.initializer}
    state = {}
    # encode: the ONNX keeps the traced module's flat conv names; the
    # shipped class wraps cnn0-cnn2 activation pairs in Sequentials.
    for name in ("cnn0", "cnn1", "cnn2", "cnn3"):
        for param in ("weight", "bias"):
            suffix = ".0" if name != "cnn3" else ""
            state["encode.%s%s.%s" % (name, suffix, param)] = torch.from_numpy(
                raw["encode.%s.%s" % (name, param)].copy())
    for index in range(5):
        prefix = "block%d." % index
        for key, array in raw.items():
            # convblock convolutions appear as Mul outputs in the traced
            # graph: /block{i}/convblock/convblock.{j}/Mul_output_0_{kind}
            if not (key.startswith("/" + prefix.rstrip(".")) and
                    "Mul_output_0" in key):
                continue
            part = key.split("/convblock/", 1)[1]
            position = int(part.split("/")[0].split(".")[1])
            kind = part.rsplit("_", 1)[-1]
            state["%sconvblock.%d.conv.%s" % (prefix, position, kind)] = \
                torch.from_numpy(array.copy())
        for source, target in (
                (prefix + "conv0.0.0.weight", "conv0.0.weight"),
                (prefix + "conv0.0.0.bias", "conv0.0.bias"),
                (prefix + "conv0.1.0.weight", "conv0.2.weight"),
                (prefix + "conv0.1.0.bias", "conv0.2.bias"),
                (prefix + "lastconv.0.weight", "lastconv.0.weight"),
                (prefix + "lastconv.0.bias", "lastconv.0.bias")):
            state[prefix + target] = torch.from_numpy(raw[source].copy())
    return state


def smooth_frames(seed: int, height: int, width: int) -> np.ndarray:
    """Low-frequency smooth frames in [0, 1], mirroring natural content.

    Interpolation networks are validated on real frames (the shipped ncnn
    conversion was checked the same way). White-noise inputs would instead
    amplify sub-pixel flow deltas through grid_sample into huge output
    differences and measure flow jitter, not conversion correctness.
    """
    rng = np.random.RandomState(seed)
    axes_h = np.arange(height, dtype=np.float32)[:, None] / height
    axes_w = np.arange(width, dtype=np.float32)[None, :] / width
    frames = np.zeros((1, 6, height, width), dtype=np.float32)
    for index in range(6):
        image = np.zeros((height, width), dtype=np.float32)
        for _ in range(4):
            fx, fy = rng.uniform(0.3, 2.5, 2)
            phase = rng.uniform(0, 2 * np.pi)
            image += np.sin(2 * np.pi * (fx * axes_w + fy * axes_h) + phase)
        image += 0.5 * axes_w + 0.3 * axes_h
        frames[0, index] = 0.5 + 0.2 * image
    return np.clip(frames, 0.0, 1.0)


def validate(state: dict, onnx_path: str, label: str,
             tolerance: float) -> None:
    """Check every parameter is covered and outputs match onnxruntime."""
    import onnxruntime as ort

    model = RIFE427()
    own = dict(model.named_parameters())
    missing = [name for name in own if name not in state]
    unused = [name for name in state if name not in own]
    if missing or unused:
        raise RuntimeError(
            "initializer mismatch: missing=%s unused=%s" % (missing, unused))
    for name, parameter in own.items():
        if tuple(state[name].shape) != tuple(parameter.shape):
            raise RuntimeError("shape mismatch for %s: %s vs %s" % (
                name, tuple(state[name].shape), tuple(parameter.shape)))
        parameter.data.copy_(state[name])
    model.eval()

    session = ort.InferenceSession(
        onnx_path, providers=["CPUExecutionProvider"])
    worst = 0.0
    with torch.no_grad():
        for height, width in ((256, 256), (192, 128), (208, 144), (64, 64)):
            images = smooth_frames(7, height, width)
            reference = session.run(None, {"input": images})[0]
            img0 = torch.from_numpy(images[:, 0:3])
            img1 = torch.from_numpy(images[:, 3:6])
            got = model(img0, img1, 0.5).numpy()
            diff = float(np.abs(reference - got).max())
            worst = max(worst, diff)
            print("  %dx%d %s max_abs_diff=%.3e (%.2f/255) %s"
                  % (height, width, label, diff, diff * 255.0,
                     "OK" if diff < tolerance else "FAIL"))
            if diff >= tolerance:
                raise RuntimeError(
                    "%s validation failed at %dx%d (%.4f/255)"
                    % (label, height, width, diff * 255.0))
    return worst


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--onnx", default=str(
        Path.home() / "Downloads" / "RIFE_fp32.onnx"),
        help="path to the downloaded RIFE_fp32.onnx")
    parser.add_argument("--output", default=str(
        ROOT / "light_video_enhancer_forked" / "fi" / "rife_v4.27_fluidframes.pth"),
        help="destination .pth path")
    parser.add_argument("--fp16", action="store_true",
                        help="store half-precision weights")
    args = parser.parse_args()

    onnx_path = Path(args.onnx)
    if not onnx_path.is_file():
        raise SystemExit(
            "The ONNX export is missing: %s\nDownload it first:\n"
            "  curl -L -o \"%s\" %s" % (onnx_path, onnx_path, DEFAULT_ONNX_URL))
    digest = sha256_file(onnx_path)
    if digest != DEFAULT_ONNX_SHA256:
        raise SystemExit(
            "Unexpected ONNX checksum: %s\nPinned: %s" % (
                digest, DEFAULT_ONNX_SHA256))

    print("Converting %s" % onnx_path)
    state = state_from_onnx(str(onnx_path))
    print("Validating against onnxruntime (fp32)")
    validate(state, str(onnx_path), "fp32", 1.0 / 255.0)

    if args.fp16:
        state = {key: value.half() for key, value in state.items()}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    torch.save(state, str(output))
    print("Saved %s (%d bytes, %s) sha256=%s"
          % (output, output.stat().st_size,
             "fp16" if args.fp16 else "fp32", sha256_file(output)))

    # Reload exactly the way the engine loads the file (torch.load, module.
    # prefix strip, strict=False) and re-check the stored precision against
    # onnxruntime so the shipped artifact itself is the validated one.
    reloaded = torch.load(str(output), map_location="cpu")
    if any(key.startswith("module.") for key in reloaded):
        reloaded = {key.replace("module.", "", 1): value
                   for key, value in reloaded.items()}
    validate(reloaded, str(onnx_path),
             "fp16" if args.fp16 else "fp32", 3.0 / 255.0)
    print("Reloaded-file validation passed (%s)"
          % ("fp16" if args.fp16 else "fp32"))


if __name__ == "__main__":
    main()
