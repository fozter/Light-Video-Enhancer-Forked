# Light Video Enhancer-Forked CLI

`LightVideoEnhancerForked-Backend.exe` is a complete standalone console application.
It does not require the WinUI frontend, Python, .NET, or Tkinter on the target
computer.

This copy documents backend version 0.0.1, part of the Light Video Enhancer-Forked
WinUI 3 package (GUI 0.0.1). Run `--help` on your exact build for the
authoritative option list and defaults.

## Quick start

Double-click the EXE or run it without arguments to open the interactive wizard:

```powershell
.\LightVideoEnhancerForked-Backend.exe
```

Process with automatic encoder selection and no processing engines (a pure
transcode):

```powershell
.\LightVideoEnhancerForked-Backend.exe input.mp4
```

Engines are never chosen automatically; without explicit flags the input is
only transcoded. Enable what you need explicitly:

```powershell
.\LightVideoEnhancerForked-Backend.exe input.mp4 -o output.mp4 `
  --scale 2 --sr-engine nvvfx --sr-quality quality `
  --fi-engine rife --fi-multiplier 2 --fi-quality balanced `
  --codec hevc_nvenc --preset balanced --crf 23
```

Lossless FFV1 output (see the FFV1 note below for the requirements):

```powershell
.\LightVideoEnhancerForked-Backend.exe input.mp4 -o lossless.mkv `
  --sr-engine none --fi-engine none `
  --codec ffv1 --container mkv
```

## Help and diagnostics

```powershell
# Concise processing help
.\LightVideoEnhancerForked-Backend.exe --help

# Hardware, encoders, and built-in engines
.\LightVideoEnhancerForked-Backend.exe --system-info

# Include slower environment checks
.\LightVideoEnhancerForked-Backend.exe --system-info --deep

# Machine-readable frontend protocol
.\LightVideoEnhancerForked-Backend.exe --capabilities-json
.\LightVideoEnhancerForked-Backend.exe --environments-json
.\LightVideoEnhancerForked-Backend.exe --models-json

# Force a fresh environment rescan and refresh the cache
.\LightVideoEnhancerForked-Backend.exe --environments-json --force
```

## Common choices

- Super resolution: `dxva_vsr`, `nvvfx`, `span`, `flashvsr`,
  `seedvr2`, `dloral`, `osdenhancer`, `sparkvsr`, `realcugan`,
  `realesrgan`, `esrgan`, `bicubic`, `lanczos`, `none` (`none` keeps the
  source resolution; any `--scale` / explicit size is ignored with a
  warning; unset means `none`)
- Interpolation: `rife`, `ema_vfi`, `vfimamba`, `rife_ncnn`,
  `rife_ncnn_427` (deprecated alias for `rife_ncnn` with `--fi-model 4.27_fluidframes`),
  `ifrnet_ncnn`, `dis`, `optical_flow`, `torch_flow`, `blend`, `none`
  (unset means `none`)
- Codecs: `auto`, `h264_nvenc`, `h264_amf`, `h264_mf`, `libx264` (`x264`,
  `h264`), `hevc_nvenc`, `hevc_amf`, `hevc_mf`, `libx265` (`x265`,
  `h265`), `av1_nvenc`, `av1_amf`, `libsvtav1` (`svt-av1`),
  `libaom-av1` (`aom`), `mpeg4`, and `ffv1` (lossless; requires an MKV
  container)
- Quality: `fast`, `balanced`, `quality`, `ultra` (the `rife_ncnn` engine
  ignores these tiers and uses `--fi-model` instead)
- Container: `mp4`, `mkv`, `mov`
- NCNN device: `auto`, `cpu`, or a Vulkan GPU index (`0`, `1`, …).
  `span` and `ifrnet_ncnn` require a Vulkan GPU and reject `cpu`.

## RIFE ncnn-vulkan models

The `rife_ncnn` engine picks its network with `--fi-model`:

```powershell
.\LightVideoEnhancerForked-Backend.exe input.mp4 -o output.mp4 `
  --sr-engine none --fi-engine rife_ncnn --fi-model 4.26 --fi-multiplier 2
```

- `4.27_fluidframes` is bundled (the FluidFrames 2026.3 conversion, shown
  as `4.27 (FluidFrames)` in the GUI) and is the default
  when no model is specified.
- The optional models (TNTwise ncnn conversions of the Practical-RIFE
  weights, listed newest first) download with
  `--download-model rife-ncnn-models` (about 188 MiB) or from the
  Models & Downloads tab of the WinUI frontend: `4.26`, `4.26 Large`,
  `4.25`, `4.25 Heavy`, `4.25 Lite`, `4.24`, `4.23`, `4.22`, `4.22 Lite`,
  `4.21`, and `4.20`.
- Tile alignment is handled automatically: the five-block family
  (4.25, 4.25 Heavy, 4.25 Lite, 4.26, 4.26 Large, 4.27) is padded to
  64-pixel multiples (4.25 Lite: 128) before inference, matching the
  reference implementations.
- Spatial/temporal TTA and ensemble models are not offered: the upstream
  conversions deprecate TTA for the five-block family and no ensemble
  exports exist for these versions.
- The WinUI frontend exposes the same list in the Model dropdown that
  replaces the Quality dropdown while the RIFE ncnn-vulkan engine is
  selected.

## Target frame rate

`--fps` sets the output frame rate directly. With an interpolation engine
selected, the backend interpolates on the smallest integer grid that covers
the rate (for example 3x for 23.976 -> 60) and then resamples that dense
grid to the exact target clock, adding or dropping frames to preserve
duration:

```powershell
.\LightVideoEnhancerForked-Backend.exe input.mp4 -o output.mp4 `
  --sr-engine none --fi-engine rife_ncnn --fi-model 4.26 --fps 60
```

- Exact ratios are accepted, so NTSC rates stay exact: `--fps 24000/1001`
  (23.976), `--fps 30000/1001` (29.97), `--fps 48000/1001` (47.952),
  `--fps 60000/1001` (59.94).
- A target at or below the source rate disables interpolation and only
  resamples (frames are dropped).
- An explicit `--fi-multiplier` overrides the derived grid and keeps the
  classic behavior: that multiplier's grid is resampled by duplication or
  dropping.
- Rates that would need more than an 8x grid are rejected (for example
  480 fps from a 23.976 fps source).
- The WinUI frontend combines both choices in one Frame Rate dropdown:
  the Source ×2 / ×3 / ×4 multipliers or the common rates (15 ... 480).

## FFV1 lossless encoding

`ffv1` encodes losslessly using the FFV1 encoder built into the bundled
FFmpeg runtime. The output container must be MKV, so use `--container mkv`
or an `.mkv` output path (the backend rejects FFV1 with any other
container). The WinUI frontend enforces the same rule: choosing FFV1
automatically rewrites the output to `.mkv`.

## Scene and static-frame detection

Interpolation pipelines use an SSIM-based detector to skip duplicate (static)
frames and to detect scene cuts. Two optional flags tune it:

```powershell
# Frames with SSIM above this value are treated as identical / static.
.\LightVideoEnhancerForked-Backend.exe input.mp4 -o output.mp4 `
  --sr-engine none --fi-engine rife --fi-multiplier 2 `
  --ssim-identical 0.9995

# Frames with SSIM below this value are treated as a scene cut.
.\LightVideoEnhancerForked-Backend.exe input.mp4 -o output.mp4 `
  --sr-engine none --fi-engine rife --fi-multiplier 2 `
  --ssim-scene-cut 0.2
```

- `--ssim-identical VALUE` — treat two consecutive frames as identical when
  their SSIM score is above VALUE (default threshold 0.996). Higher values
  detect more static frames and can skip more interpolation work; extreme
  values can incorrectly merge frames that are merely similar.
- `--ssim-scene-cut VALUE` — detect a scene cut when the SSIM score drops
  below VALUE (default threshold 0.20). Lower values suppress cuts and let
  similar-looking scenes flow together; higher values split more
  aggressively.
- Values are finite decimals in the 0–1 range written with a dot, e.g.
  `0.9995` / `0.2`; non-finite values (`NaN`, `inf`) are rejected. These
  flags only affect pipelines whose interpolation engine
  consumes the scene detector (RIFE and friends); check `--help` and the
  processing log to see whether the active engine applies them.
- The WinUI frontend exposes the same thresholds as the Static Frame
  Threshold and Scene Cut Threshold controls (defaults 0.9995 / 0.2) and
  passes them to the backend automatically.

## Environment cache

`--environments-json` lists Python / PyTorch / CUDA environments that are
cached on disk (`%LOCALAPPDATA%\LightVideoEnhancerForked\environment-cache.json`,
24-hour freshness). By default the GUI loads this cache automatically at
startup, so environment results are available without clicking Scan;
`--environments-json --force` (or the GUI Scan button) performs a full rescan
and refreshes the cache.

Run `--help` on the exact build you are using for the authoritative codec list
and defaults. Hardware encoders are selected only when the current machine
reports them as available.
