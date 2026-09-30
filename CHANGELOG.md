# Changelog

## Unreleased

## v0.0.3 — Light Video Enhancer-Forked (2026-09-30)

- **RIFE AI (PyTorch) gained the ncnn engine's model menu.** One engine,
  eight models: the bundled `4.27_fluidframes` (the FluidFrames 2026.3
  conversion, shipped as `fi/rife_v4.27_fluidframes.pth`) is the only
  bundled model and the default; the optional 4.20–4.26 hzwer
  Practical-RIFE checkpoints (including the historical `4.25`
  `flownet.pkl`; base and lite variants, about 231 MiB, SHA-256-pinned)
  download on demand from the new `rife-torch-models` pack. `--fi-model`
  selects the model for the `rife` engine exactly as it does for
  `rife_ncnn`, and the GUI Model dropdown replaces the Quality dropdown
  for both engines.
- Six PyTorch architectures were ported for the selectable models
  (four-block 4.20/4.21/4.22 families, 4.22 Lite, FlownetCas five-block
  for 4.25/4.26, 4.25 Lite, and the FluidFrames 4.27 IFNet), each
  validated against the corresponding Practical-RIFE release code, and
  `fi/_rife_model.py` carries them all. The external-Python subprocess
  path learns the architecture with the weights.
- The ncnn-only variants (`4.26 Large`, `4.25 Heavy`, `4.24`, `4.23`)
  remain ncnn-only on purpose: no first-party PyTorch checkpoints were
  ever published for them.
- **The tree is now 0 CJK.** `windows/README.md` was translated to
  English, the inherited upstream `CHANGELOG.md` history was translated
  to English, and the upstream-era Chinese documents (the five
  `docs/RELEASE_NOTES_v0.5-0.8` files, the benchmark research reports,
  and one legacy benchmark record) were removed.

## v0.0.2 — Light Video Enhancer-Forked (2026-09-29)

- The bundled FFmpeg runtime is now **our own minimal FFmpeg 9.0.2 shared
  build** (MSYS2 UCRT64; pinned recipe in `build_ffmpeg.sh`), replacing the
  prebuilt BtbN 8.1 binaries. The full codec menu is unchanged — NVENC, AMF,
  Media Foundation, libx264, libx265, SVT-AV1, libaom-av1, MPEG-4, MJPEG,
  and the FFV1 encoder, now joined by an FFV1 **decoder** so the app can
  re-ingest its own lossless MKV outputs. Runtime size drops from ~150 MB
  to ~58 MB and the backend EXE from ~397 MB to ~339 MB.
- Fixed a decode-loop bug in `ffmpeg_worker.c` that could drop frames on
  B-frame streams (H.264/HEVC inputs): output is now drained before new
  packets are fed, an `EAGAIN` result never discards a packet, and the
  decoder is flushed at end of file. Caught by the round-trip tests when
  moving to FFmpeg 9.
- `tools/fetch_ffmpeg_runtime.py` is now a runtime **verifier**; the BtbN
  downloader is retired (the runtime is built from source, not fetched).

## v0.0.1 — Light Video Enhancer-Forked (2026-09-27)

First release of the fork; version numbers restart at 0.0.1. Based on
[ZyptusOn/light_video_enhancer](https://github.com/ZyptusOn/light_video_enhancer).
See `THIRD_PARTY.md` for the licenses of every bundled and downloadable
component, and `DISCLAIMER.md` for the no-warranty terms.

- Full fork rebrand: `LightVideoEnhancerForked.WinUI.exe` /
  `LightVideoEnhancerForked-Backend.exe`, window title and About name
  "Light Video Enhancer-Forked", Python package renamed to
  `light_video_enhancer_forked`. The About page shows the WinUI and backend
  versions on separate lines (`WinUI 3:` / `Backend:`).
- One merged RIFE ncnn-vulkan engine with a 12-model dropdown: the bundled
  `4.27_fluidframes` (displayed as "4.27 (FluidFrames)", converted from the
  FluidFrames 2026.3 ONNX export) plus optional 4.20-4.26 models from the
  `rife-ncnn-models` pack; `--fi-model` selects the model, and the old 4.6
  model is gone.
- Frame-rate targeting: `--fps` accepts plain numbers or exact ratios such
  as `24000/1001`; the GUI Frame Rate selector offers `Source x2/x3/x4` or
  exact output rates (NTSC rationals included).
- No automatic engine selection anywhere: unset engines mean `none` (GUI
  defaults: No Resolution Change / No Interpolation).
- FFV1 lossless encoding via the bundled FFmpeg 8.1 runtime (MKV container),
  with the MKV header now declaring the true average frame rate.
- Scene & static-frame detection with SSIM thresholds
  (`--ssim-identical` / `--ssim-scene-cut`).
- Stall-safe, resumable, SHA-256-pinned model downloads with per-file
  Repair, archive-pack import, and Google Drive/custom sources.
- Python environment scans cached for 24 h under
  `%LOCALAPPDATA%\LightVideoEnhancerForked`.
- English-only UI, CLI, and task logs; log level defaults to INFO
  (`LVE_LOG_DEBUG=1` restores verbose output).

## v0.8.0 — Heavy-model interfaces and the latest stable components

- Added the DLoRAL, OSDEnhancer, and SparkVSR super-resolution interfaces
  and the VFIMamba S/Full interpolation interface; the large weights
  download on demand, and a failing isolated runtime never takes down the
  GUI or the main processing pipeline.
- SeedVR2 gained 7B Q4 and 7B Sharp Q4 tiers; the model manager gained
  resumable downloads, Google Drive sources, and more complete per-file
  verification.
- WinUI was upgraded from Windows App SDK 1.8.6 to the then-current stable
  2.3.1; still .NET SDK 10.0.302 and Windows SDK BuildTools
  10.0.28000.2270, with the Windows 10 1809 minimum unchanged.
- v0.8.0 rebuilt all three assets — WinUI Full/Lite and the Windows 7 Tk
  LTS; the Full/Lite frontends are byte-identical and bundle 10/0 standard
  model packs with an empty user model directory.
- The portable backend became a fully standalone console CLI: the
  no-argument interactive wizard, grouped bilingual `--help`, system info,
  capability/environment/model protocol queries, and full video processing
  all work without the GUI.
- The backend PyInstaller entry no longer imports Tkinter, Tcl/Tk, IDLE,
  the old Tk GUI, or `light_video_enhancer.gui`; the Windows 7 Tk LTS
  source keeps sharing the stable processing configuration and core
  modules with the backend.
- The wizard, help, processing log, and main errors of the CLI and the
  backend EXE picked Chinese or English from the Windows UI language by
  default, with a `--language` override; protocol JSON keeps standard
  output clean and diagnostic logs moved to standard error.
- The WinUI language options displayed the fixed autonyms for Chinese and
  English; dynamic English localization was completed for the models page,
  the environments page, the processing page, and collapsed pages on first
  visit.
- The self-contained single-file WinUI build dropped from about 85.6 MiB
  to about 42.4 MiB by excluding the unused AI/ML, ONNX, DirectML,
  Widgets, and NPU workloads and applying controlled partial trimming
  with explicit trimming roots.
- The Chinese and English pages, all 12 model packs, the backend
  capability protocol, and the standalone CLI were verified live; the
  34.1 MiB experimental build without trimming roots was explicitly
  rejected because WinUI initialization crashed.
- Fixed the packaged standalone CLI failing to start `RIFE -> NV-VFX`
  without the GUI's environment cache: CUDA PyTorch / nvvfx environments
  are scanned on demand only when explicitly needed, an explicit
  `--torch-python` works directly, and errors and unexpected exceptions
  stay visible in the interactive window for the user to read.
- The v0.7.0 Full/Lite assets were replaced in place with builds
  containing the fixes from commit `9cd9088`; the Windows 7 assets were
  unchanged.

## v0.7.0 — New-generation algorithms, smart auto-selection, and model runtimes

- Reworked auto-selection into a context scorer: after video probing it
  decides from the GPU, the models, the scanned Python/CUDA/NV-VFX
  capabilities, target pixels, quality tier, multipliers, and processing
  order; the fast tier prefers low-latency backends, high-pixel
  "super-res first, then interpolate" avoids the expensive RIFE, D3D11 VSR
  respects its 4K cap, invalid 1x stages are skipped, and the log explains
  every choice.
- Fixed Real-ESRGAN `quality` still running the x4plus 4x inference and
  downscaling on 2x/3x jobs; it now uses the native AnimeVideo-v3 model
  for the target multiplier, while `ultra` keeps the explicit 4x
  oversampling + TTA path.
- Added IFRNet S / Base / L NCNN/Vulkan interpolation, wired into the
  persistent native worker, model downloads, the GUI, the CLI, and the
  bilingual capability descriptions.
- Added SPAN 2x/4x (48/52-channel) NCNN/Vulkan super resolution; the
  conversion tool verifies the PNNX/NCNN numeric cross-check and the
  runtime uses FP32 to avoid Vulkan half-precision drift.
- Added EMA-VFI Small CUDA interpolation with a persistent isolated
  process, shared memory, and multi-timestep feature reuse, supporting
  2x-4x.
- Added the optional experimental Win10/11 backend FlashVSR v1.1: a pinned
  runtime, a 29-frame causal window, a dedicated Python 3.11 CUDA
  capability gate, and Hugging Face / mirror downloads.
- Added the optional heavy-restoration backend SeedVR2 3B FP8 for
  Win10/11: the low-VRAM community runtime with tiled VAE, CPU offload,
  block swap, and 4n+1 temporal batching.
- All FlashVSR and SeedVR2 remote weights gained per-file SHA-256
  verification; neither takes part in auto-selection and neither is
  bundled in the Full package.
- The temporal super-resolution preference window is now converted to the
  source batch size when interpolating first, so 2x interpolation no
  longer inflates the 29-frame window into 57 frames.
- The environment scan cache was upgraded and explicitly versioned, and
  old caches invalidate themselves; the GUI only enables a heavy backend
  after a scan confirms its Python/CUDA dependencies.
- Fixed the Full/Lite packaging manifests: Lite now excludes exactly all
  weights per model directory, the modern backend includes EMA-VFI and the
  pinned heavy runtimes, and the Windows 7 package excludes the
  Win10/11-only runtimes.
- Fixed the all-black videos caused by SPAN NCNN casting its [0,1] float
  output straight to bytes and getting the BGR/RGB order wrong; added an
  optional real-Vulkan smoke test.
- Measured on 2 seconds of usable `YUKI_Z.mp4` output: IFRNet S alone
  took 3.70 s for 60 to 119 frames, SPAN x2 alone 12.92 s, and the
  combination 19.34 s. SPAN dominated the combination, so automatic
  super-resolution prefers Real-ESRGAN when its models are present and
  falls back to SPAN.

## v0.6.0 — Persistent NCNN/Vulkan worker and the backend executor refactor

### Performance and architecture

- Added the persistent native `lve-ncnn-worker.exe`, which runs RIFE NCNN
  plus Real-CUGAN, Real-ESRGAN, or ESRGAN in one Vulkan process.
- BGR24 frames travel through Windows named shared memory, eliminating
  per-batch process launches, PNG encode/decode, and disk round-trips;
  initialization failures fall back to the compatible directory pipeline
  automatically.
- Added a dual-workspace three-stage pipeline so decoding, NCNN directory
  jobs, and encoding can overlap.
- Added the unified `FrameBatchExecutor` and an immutable NCNN stage
  contract; the pipeline no longer reads engine-private fields.
- Real-ESRGAN 2x/3x fast and balanced tiers now use the native
  AnimeVideo-v3 multipliers instead of running 4x inference and
  downscaling.
- RIFE PyTorch, the fused RIFE + NV-VFX path, and the external RIFE
  worker skip the repeated cuDNN shape search, cutting startup overhead on
  short videos.
- The native worker reuses models, Vulkan pipelines, and intermediate
  buffers, with per-batch error isolation, BGR/RGB correction, and explicit
  resource ownership.

### UI and compatibility

- The WinUI light/dark themes now reach the window's root visual tree,
  Mica, the navigation pane, and the title bar, fixing the black backdrop
  that survived a switch to light mode.
- The GUI and CLI keep depending only on `ProcessConfig` and the stable
  protocol; adding or replacing a backend no longer means copying frontend
  decision logic.
- The native worker builds with `_WIN32_WINNT=0x0601` and the static MSVC
  runtime, and ships `vcomp140.dll` alongside.
- The `LVE_DISABLE_FUSED_NCNN=1` compatibility switch remains available to
  force the legacy CLI/PNG path.

### Performance results

- RIFE NCNN + Real-CUGAN: 1.50 to 4.99 input fps, a 3.32x speedup.
- RIFE NCNN + Real-ESRGAN AnimeVideo-v3: 1.85 to 8.18 input fps, a 4.42x
  speedup.
- RIFE NCNN + ESRGAN classic: 0.14 to 0.33 input fps, a 2.33x speedup.
- The same-machine RIFE PyTorch + NVIDIA VFX baseline was 8.01 input fps.

### Verification and release

- 35 Python unit and integration tests passed; the real-video smoke run
  and image regression comparisons passed.
- The WinUI Release x64 build had 0 warnings and 0 errors; Full and Lite
  both kept exactly two EXEs and zero subdirectories.
- The Full and Lite backends both reported protocol version 1 and program
  version 0.6.0, with model states matching the bundled / on-demand
  expectations.
- The Windows 7 Full GUI was rebuilt with Python 3.8.10 and PyInstaller
  5.13.2 and passed the launch survival test.

## v0.5.2 — WinUI usability and slim-publish fixes

### UI

- The main window starts as a regular 1280x900 window again instead of
  forcing maximized; all pages moved to a centered content viewport.
- Removed the "Encoding, device, and clip" Expander sub-level in favor of
  the unified card layout.
- The InfoBar stays collapsed by default and appears only when the title
  or body is non-empty, fixing the empty notification bar at the top of
  the home page.
- Model-page JSON transport became code-page agnostic, so Chinese names
  and descriptions no longer garble.
- "Hardware & capabilities" refreshes immediately after a Python
  environment scan, showing the PyTorch, CUDA, and NVIDIA VFX environment
  counts.
- NV-VFX, RIFE PyTorch, and CUDA optical flow stay disabled on launch and
  on scan failure; they unlock only after a manual scan confirms the
  environment.
- Theme switching was raised to the window's root visual tree, so the
  Mica backdrop, navigation pane, pages, and title bar all switch
  light/dark together.

### Release

- The WinUI frontend moved to self-contained single-file publishing; the
  Full and Lite extract directories shrank from hundreds of runtime files
  to two EXEs.
- Satellite resources were limited to `zh-CN` and `en-US`, so unrelated
  language directories are no longer produced.
- Backend lookup now supports both the host EXE directory and the
  self-extracting runtime directory.
- The backend no longer packages Tk/Tcl and dropped the duplicated FFmpeg
  DLLs, keeping only the dynamic libraries the runtime needs.
- Full and Lite keep sharing the same frontend EXE; only the bundled
  backend weights differ.

### Verification

- 28 Python unit and integration tests passed.
- The WinUI Release x64 single-file publish passed, with the frontend at
  about 85.6 MiB.
- The Full and Lite directories both verified as 2 files and 0
  subdirectories; final sizes were about 305.0 MiB and 168.6 MiB.
- Verified live: regular window launch, centered pages, Chinese model
  text, the disappearing empty notification bar, and the capability bar
  and algorithm options updating after an environment scan.

## v0.5.0 — WinUI dual packages, model downloads, and a stable frontend/backend protocol

### Distribution and models

- The Windows 10/11 distribution split into Full and Lite; both share the
  same WinUI 3 frontend.
- Full bundles every RIFE, Real-CUGAN, Real-ESRGAN, and ESRGAN weight;
  Lite keeps only the core runtime files.
- Added the model download page with GitHub, proxy mirrors, custom URL
  templates, and local ZIP import.
- Downloads and imports verify the archive SHA-256, per-file SHA-256, the
  exact file list, and safe paths.
- External models install to `%LOCALAPPDATA%\LightVideoEnhancer\models` by
  default, and app upgrades never clear them.

### Architecture and UI

- WinUI and the backend talk over the version-1 JSON/JSONL protocol, so
  model-state, environment, and capability queries no longer depend on
  Python internals.
- Added system-language plus Chinese/English switching; the CLI gained
  `--language` / `-L`.
- Added the app logo, ICO, and full WinUI icon set, and upgraded to
  Windows App SDK 1.8.
- The Windows 10/11 Tk edition stopped shipping; the Windows 7 Tk edition
  remains as a frozen LTS with only the Full weights.

### Verification

- 28 Python unit and integration tests passed.
- The WinUI Release x64 build had 0 warnings and 0 errors.
- All 336 frontend files other than the backend files are SHA-256
  identical between Full and Lite.
- Full, Lite, and the Windows 7 GUI all passed the launch smoke test.

## v0.4.5 — Dual-platform releases, the fast NCNN pipeline, and ESRGAN

This release was the full rework that took the project from an early
NVIDIA-only prototype to a composable, cross-vendor video enhancement
tool. It kept the core idea of driving the driver's video enhancement
through the D3D11 Video Processor and added the portable NCNN path,
external PyTorch, software fallbacks, modern encoding, and the Windows 7
release chain.

### Main changes

- The project and Python package were renamed from `nvidia_video_enhancer`
  to `light_video_enhancer`, and the CLI entry from `nve` to `lve`.
- Two single-file GUIs ship: Windows 10/11 x64 and Windows 7 SP1 x64.
- Added Real-ESRGAN AnimeVideo-v3 2x/3x/4x, x4plus, x4plus-anime, and the
  classic ESRGAN x4 perceptual model.
- Real-CUGAN, Real-ESRGAN, classic ESRGAN, and RIFE NCNN all moved to
  directory batching.
- RIFE NCNN and the NCNN super-resolution engines support safe bidirectional
  directory chaining, removing the repeated reads and writes of
  intermediate frames in Python.
- Batch sizes are computed from the input, the target, and the model's
  native size; the encode queue grows dynamically and temporary
  directories are cleaned up in the background.
- The Windows 10/11 `RIFE PyTorch -> NV-VFX` path gained a fused CUDA
  worker, cutting GPU/CPU round-trips and repeated color conversions.
- Standalone RIFE and NV-VFX modes use preallocated shared memory; the
  cross-environment protocol no longer serializes NumPy objects.

### Codecs

- Decoding supports CUDA, D3D11VA, dav1d, and a software fallback.
- H.264: NVENC, AMF, Media Foundation, x264.
- H.265/HEVC: NVENC, AMF, Media Foundation, x265.
- AV1: NVENC, AMF, SVT-AV1, libaom.
- When the requested encoder is unavailable, the format is kept first and
  then degraded AV1 -> HEVC -> H.264 -> MPEG-4.
- Fixed the lost final encode frame, wrong frame rates, dropped decode
  packets, audio clip timestamps, and encoder flushing.

### GUI and environments

- Super-resolution and interpolation quality split apart, and controls
  enable only when the chosen backend supports them.
- Added the NCNN Vulkan GPU selector, encoding presets, clip processing,
  audio copy, and overwrite options.
- GUI startup only does the quick capability check; Python/PyTorch/CUDA
  scans became manual, parallel, and cached.
- Environment discovery covers PATH, the Python Launcher, the Windows
  registry, Conda, uv, pyenv, Poetry, and the common virtual-environment
  directories.
- NVIDIA Video Effects initializes and infers in an isolated subprocess,
  with timeouts and automatic fallback.

### Performance

On the 720p, 33-frame synthetic benchmark, the old Python
intermediate-frame path took 22.256 s and the v0.4.5 NCNN directory
chaining took 15.425 s: about `1.443x` higher throughput and about
`30.7%` less total time. Real gains vary with GPU, model, resolution,
disk, and encoder.

### Fixes

- Fixed `No module named 'numpy._core'` when the external Python has a
  different NumPy version.
- Fixed the environment scan missing some Python/Conda installations.
- Fixed the NCNN GPU being hardcoded and quality options disagreeing with
  the model's actual behavior.
- Fixed the model's native 4x output feeding straight into the 2x
  interpolation stage, which cost extra computation and changed the
  meaning of the scale.
- Fixed RIFE static-frame/scene-cut handling and the warp grid cache
  pinning VRAM.
- Fixed partial-file handling in cancel, failure, and overwrite scenarios.

### Verification

- Python 3.13: 24 tests passed.
- Python 3.8.10: 24 tests passed.
- Real encode-decode round trips passed for x264, x265, SVT-AV1, libaom,
  Media Foundation, and MPEG-4.
- `RIFE NCNN -> Real-CUGAN -> AV1 NVENC` passed end to end.
- The reverse `Real-CUGAN -> RIFE NCNN` directory chaining passed.
- Both single-file programs create and respond to a GUI window; the Win7
  package builds with Python 3.8.10 and PyInstaller 5.13.2.

### Upgrade notes

- Change old `nvidia_video_enhancer` imports to `light_video_enhancer`.
- Change the old `nve` command to `lve`.
- Re-check the GUI's quality tiers, encoding preset, and NCNN GPU after
  upgrading.
- First launch and first model load can be slower because of single-file
  unpacking, antivirus scans, and Vulkan cache building.

### Downloads

- `LightVideoEnhancer-Win10-11-x64.exe`: for 64-bit Windows 10/11.
- `LightVideoEnhancer-Win7-x64.exe`: for the 64-bit Windows 7 SP1
  compatibility target.

Full usage instructions, checksums, and known limitations are in
[README.md](README.md).
