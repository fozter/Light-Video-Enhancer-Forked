# Light Video Enhancer-Forked

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A Windows 10/11 desktop application and standalone CLI backend for video
super-resolution, frame interpolation, re-timing, and transcoding — built on
a composable pipeline of vendor-neutral and GPU-accelerated engines.

This repository is a fork of
[ZyptusOn/light_video_enhancer](https://github.com/ZyptusOn/light_video_enhancer)
(versions restart at 0.0.1). All fork work is English-only, both in the UI
and in the code. See [THIRD_PARTY.md](THIRD_PARTY.md) for every bundled and
downloadable component and its license, and
[DISCLAIMER.md](DISCLAIMER.md) for the no-warranty terms.

> **Provenance & copyright.** The original Light Video Enhancer code by
> **ZyptusOn** was generated with DeepSeek V4Pro + TRAE Work; this fork's
> code was generated with **GLM 5.3 + Muse Spark 1.3**. Copyright © 2026
> ZyptusOn (original project) and © 2026 fozter (fork) — see
> [LICENSE](LICENSE) for the MIT license text.

## Highlights

- **WinUI 3 desktop app + a fully standalone CLI backend.** The
  `LightVideoEnhancerForked-Backend.exe` console binary runs everything the
  GUI can run, without the GUI, Python, or .NET installed.
- **RIFE ncnn-vulkan, one engine, twelve models.** The bundled
  `4.27_fluidframes` (converted from the [FluidFrames](https://github.com/Djdefrag/FluidFrames)
  2026.3 ONNX export, validated against the reference) is the default;
  4.20–4.26 (with lite/heavy/large variants) download on demand. Select the
  model in the GUI dropdown or with `--fi-model`.
- **RIFE AI (PyTorch), one engine, eight models.** The CUDA engine gained
  the same model menu: the bundled `4.27_fluidframes` conversion ships
  with the app, and the optional 4.20–4.26 hzwer Practical-RIFE
  checkpoints (including `4.25`; about 231 MiB) download on demand.
- **Frame-rate targeting, exactly.** Multiply the source rate (×2/×3/×4) or
  set an exact output rate — including NTSC rationals such as
  `60000/1001` (`59.94`) — and frames are added or dropped while duration is
  preserved.
- **No automatic engine selection.** Nothing is ever chosen "for you":
  defaults are No Resolution Change / No Interpolation, and every engine is
  an explicit choice.
- **FFV1 lossless output** on the bundled minimal FFmpeg 9.0.2 runtime (MKV
  container), alongside NVENC/AMF/Media Foundation/software H.264, HEVC,
  AV1, and MPEG-4 encoders.
- **Scene & static-frame detection** with SSIM thresholds you can tune
  (`--ssim-identical`, `--ssim-scene-cut`).
- **A model manager that verifies everything.** Every download is
  SHA-256-pinned, resumable, and stall-proof; installed packs can be
  re-verified and repaired file-by-file; packs can also be imported from
  local ZIP archives.
- **Optional generative upscalers** — SeedVR2, FlashVSR, DLoRAL,
  OSDEnhancer, SparkVSR, VFIMamba — download on demand and run in isolated
  runtimes so a failed environment never breaks the app.

## Installation

1. Download `LightVideoEnhancerForked-WinUI3-Full-Win10-11-x64.zip` from
   the [Releases](https://github.com/fozter/Light-Video-Enhancer-Forked/releases)
   page.
2. Extract the ZIP to any folder and run `LightVideoEnhancerForked.WinUI.exe`.
   Requirements: Windows 10 1809 or newer, x64. No other dependencies.
3. The Full package bundles the standard ncnn model packs. The optional
   generative models (several GiB each) download on demand from the
   **Models & Downloads** tab.

The CLI backend sits next to the GUI in the same folder and also works
standalone — see the bundled `CLI_GUIDE.md`.

## Quick start (GUI)

1. **Process** tab: pick an input video, then choose an engine pair
   (super resolution and/or interpolation), a codec, and a container.
2. Pick a Frame Rate: a multiplier (Source ×2/×3/×4) or an exact output
   rate.
3. Press **Start**. The task log shows backend progress; when the run
   completes, the output path appears in the summary banner.

For lossless archiving, choose the **FFV1 (Lossless)** codec — the output
container is forced to MKV automatically.

## Quick start (CLI)

```powershell
# Interactive wizard
.\LightVideoEnhancerForked-Backend.exe

# Pure transcode
.\LightVideoEnhancerForked-Backend.exe input.mp4 -o output.mp4

# RIFE ncnn 2x interpolation at an exact NTSC frame rate
.\LightVideoEnhancerForked-Backend.exe input.mp4 -o output.mp4 `
  --sr-engine none --fi-engine rife_ncnn --fi-model 4.26 --fps 24000/1001

# Lossless FFV1
.\LightVideoEnhancerForked-Backend.exe input.mp4 -o lossless.mkv `
  --sr-engine none --fi-engine none --codec ffv1 --container mkv
```

Run `--help` for every option, and see `CLI_GUIDE.md` for the full guide.

## Engines

| Stage | Engines |
|---|---|
| Super resolution | `nvvfx` (NVIDIA Video Effects), `dxva_vsr` (driver-level VSR), `span`, `realcugan`, `realesrgan`, `esrgan`, `flashvsr`, `seedvr2`, `dloral`, `osdenhancer`, `sparkvsr`, `bicubic`, `lanczos`, `none` |
| Interpolation | `rife` (PyTorch), `rife_ncnn` (Vulkan), `ema_vfi`, `vfimamba`, `ifrnet_ncnn`, `dis`, `optical_flow`, `torch_flow`, `blend`, `none` |
| Encoders | NVENC (H.264/HEVC/AV1), AMD AMF, Media Foundation, libx264/libx265, SVT-AV1, libaom, MPEG-4, FFV1 (lossless) |

Optional generative models are fetched on demand (per-file SHA-256
verification) and run in isolated Python runtimes.

## Building from source

Prerequisites: 64-bit Python 3.10+ (3.14 used for the shipped build), .NET
SDK 10, and Git. The minimal FFmpeg 9.0.2 runtime DLLs ship in
`light_video_enhancer_forked/ffmpeg_dlls/` (they are excluded from git by
`.gitignore` but present in the source snapshot); verify them with
`python tools\fetch_ffmpeg_runtime.py`. Rebuilding the runtime is only
needed after changing its codec set — it requires MSYS2 (UCRT64 toolchain
plus the `x264`, `x265`, `aom`, `svt-av1`, `dav1d`, `ffnvcodec-headers`,
and `amf-headers` packages) and the pinned recipe
`build_ffmpeg.sh` + `light_video_enhancer_forked/ffmpeg_bridge/build_worker.sh`
(FFmpeg source at `<repo>/../ffmpeg`, FFmpeg 9.0.2 from https://ffmpeg.org).

```powershell
python -m pip install -r requirements.txt pyinstaller>=6
python tools\fetch_ffmpeg_runtime.py        # verify the bundled runtime DLLs

# Backend EXE (dist\LightVideoEnhancerForked-Backend-Full.exe)
python build_exe.py --backend --profile full

# WinUI package (dist\LightVideoEnhancerForked-WinUI3-Full-Win10-11-x64.zip)
powershell -ExecutionPolicy Bypass -File .\windows\build_winui.ps1 -Profile Full -SkipBackend

# Tests (133 pass, 1 environment-conditional skip)
python -m unittest discover -s tests
```

GUI-only development: `dotnet run --project
windows\LightVideoEnhancerForked.WinUI\LightVideoEnhancerForked.WinUI.csproj
-p:Platform=x64` (the GUI falls back to a Python "development backend"
automatically).

## Repository layout

| Path | Contents |
|---|---|
| `light_video_enhancer_forked/` | Python backend package (pipeline, engines, encoders, model manager) |
| `windows/LightVideoEnhancerForked.WinUI/` | WinUI 3 frontend |
| `native/ncnn_worker/` | Sources for the fused NCNN Vulkan worker |
| `tools/` | Build helpers, including the FFmpeg runtime verifier |
| `tests/` | Unit test suite |
| `docs/` | Architecture notes and upstream release history |
| `benchmarks/` | Pipeline benchmarks and engineering reports |
| `CLI_GUIDE.md` | The full CLI reference |

## Data locations

Downloaded models and environment scans live under
`%LOCALAPPDATA%\LightVideoEnhancerForked` (models: `...\models`,
environment cache: `...\environment-cache.json`, 24 h TTL). Removing the
program directory never deletes your models.

## Credits

- Upstream project: [ZyptusOn/light_video_enhancer](https://github.com/ZyptusOn/light_video_enhancer)
- Engine, model, and runtime authors — RIFE (hzwer), FluidFrames
  (Djdefrag), TNTwise, nihui (rife/realcugan/realesrgan/ifrnet ncnn
  ports), Real-ESRGAN (Xintao Wang), SPAN, EMA-VFI / VFIMamba (MCG-NJU),
  SeedVR2 (ByteDance Seed), FlashVSR, DLoRAL, OSDEnhancer, SparkVSR,
  ncnn (Tencent), FFmpeg, NumPy, OpenCV, and NVIDIA.
  The full attribution table with licenses is in
  [THIRD_PARTY.md](THIRD_PARTY.md).

## License

This project is licensed under the [MIT License](LICENSE), continuing the
upstream project's license. Fork modifications © 2026 fozter.

Distributed binaries contain third-party components under their own
licenses — most notably the **GPL-2.0-or-later** FFmpeg runtime and the
GPL-linked `ffmpeg_worker.dll` (source: `light_video_enhancer_forked/ffmpeg_bridge/ffmpeg_worker.c`
in this repository). Read [THIRD_PARTY.md](THIRD_PARTY.md) before
redistributing binaries.
