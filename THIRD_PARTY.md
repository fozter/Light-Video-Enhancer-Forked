# Third-party components and licenses

Light Video Enhancer-Forked bundles, links, or downloads third-party
software, model weights, and documentation. This file lists every
component with its license and upstream source. Each bundled license text
is also shipped in-tree next to the component it covers.

## Project code

| Component | License | Source |
|---|---|---|
| Upstream project (basis of this fork) | MIT © 2026 ZyptusOn | https://github.com/ZyptusOn/light_video_enhancer |
| Fork modifications | MIT © 2026 fozter | this repository |

The upstream MIT license text is preserved verbatim in [LICENSE](LICENSE).

## Bundled runtimes and executables

| Component | License | Source / notes |
|---|---|---|
| **FFmpeg 8.1 shared runtime** (`ffmpeg_dlls/`: avcodec-62, avformat-62, avutil-60, swscale-9, swresample-6) | **GPL-2.0-or-later** (core LGPL-2.1+ with GPL components such as libx264/libx265 enabled) | BtbN `ffmpeg-n8.1-latest-win64-gpl-shared-8.1.zip` — https://github.com/BtbN/FFmpeg-Builds (reproducible builds; FFmpeg source: https://git.ffmpeg.org/ffmpeg.git). **Not committed to this repository** (one DLL exceeds GitHub's 100 MB limit); `tools/fetch_ffmpeg_runtime.py` downloads and SHA-256-verifies them. Shipped binaries embed them. |
| **`ffmpeg_worker.dll`** (our native encode worker, `ffmpeg_bridge/ffmpeg_worker.c`) | **GPL-2.0-or-later** (dynamically linked against the GPL FFmpeg runtime) | Source in this repository; rebuild with the recipe in `build_ffmpeg.sh`. |
| `ncnn/rife/rife-ncnn-vulkan.exe` | MIT | TNTwise's rife-ncnn-vulkan build (fork of nihui's MIT project) — https://github.com/TNTwise/rife-ncnn-vulkan; see the fork note in `light_video_enhancer_forked/ncnn/rife/README.md`. SHA-256 `3105BCBDE7EA38176560EDB217B1605E65DB1D19B7E4E6FC5B9870829B37EAA4`. |
| `ncnn/realcugan/realcugan-ncnn-vulkan.exe`, `ncnn/realesrgan/realesrgan-ncnn-vulkan.exe` | MIT (ports by nihui) | https://github.com/nihui/realcugan-ncnn-vulkan, https://github.com/nihui/realesrgan-ncnn-vulkan; both run on [ncnn](https://github.com/Tencent/ncnn) (BSD-3-Clause). |
| `ncnn/lve_worker/lve-ncnn-worker.exe` | BSD-3-Clause (ncnn) + MIT model code | Built from `native/ncnn_worker/` (IFRNet/SPAN inference sources by nihui/hongyuanyu, MIT/Apache-2.0). |

## Bundled model weights

| Model | Files | License | Source |
|---|---|---|---|
| RIFE 4.27 "FluidFrames" | `ncnn/rife/rife-v4.27/flownet.{param,bin}` | MIT (FluidFrames) | Converted from the ONNX export in https://github.com/Djdefrag/FluidFrames (release 2026.3); derived from hzwer's Practical-RIFE five-block IFNet (MIT). |
| RIFE PyTorch | `fi/flownet.pkl` | MIT | hzwer's Practical-RIFE — https://github.com/hzwer/Practical-RIFE |
| EMA-VFI Small | `fi/ema_vfi/ours_small_t.pkl`, `fi/_ema_vfi_vendor/` | Apache-2.0 | MCG-NJU EMA-VFI — https://github.com/MCG-NJU/EMA-VFI (in-tree `LICENSE.txt`) |
| IFRNet S/Base/L | `ncnn/ifrnet/IFRNet_*` | MIT | nihui's port https://github.com/nihui/ifrnet-ncnn-vulkan; model by ltkong218 — https://github.com/ltkong218/IFRNet (in-tree `LICENSE`) |
| Real-CUGAN | `ncnn/realcugan/models-se/` | MIT (port); weights by Bilibili AI Lab | https://github.com/nihui/realcugan-ncnn-vulkan; model project https://github.com/bilibili/ailab (in-tree `LICENSE`) |
| Real-ESRGAN | `ncnn/realesrgan/models/` | MIT (port); model BSD-3-Clause (Real-ESRGAN) | https://github.com/nihui/realesrgan-ncnn-vulkan; model https://github.com/xinntao/Real-ESRGAN (in-tree `LICENSE`) |
| Classic ESRGAN | `ncnn/realesrgan/models/esrgan-x4.bin` | MIT | Derived from the original ESRGAN research release (Xintao Wang et al.) via nihui's port. |
| SPAN 2×/4× | `ncnn/span/` | Apache-2.0 | hongyuanyu's SPAN — https://github.com/hongyuanyu/SPAN (in-tree `LICENSE.txt`) |

## Optional downloadable model packs

These weights are **not** bundled with the repository or the Full package;
the app downloads them on demand from the sources below and verifies every
file against a pinned SHA-256 before installing. Mirror downloads are
served from the upstream project's GitHub release assets.

| Pack | Model | License | Official source |
|---|---|---|---|
| `seedvr2-3b-fp8`, `seedvr2-7b-q4`, `seedvr2-7b-sharp-q4` | SeedVR2 (ByteDance Seed) | Apache-2.0 | https://github.com/ByteDance-Seed/SeedVR (community FP8/Q4 repack: HF `numz/SeedVR2_comfyUI`, `cmeka/SeedVR2-GGUF`) |
| `flashvsr-v1.1` | FlashVSR | Apache-2.0 | https://github.com/OpenImagingLab/FlashVSR (HF `JunhaoZhuang/FlashVSR-v1.1`) |
| `dloral-core`, `dloral-prompt` | DLoRAL | MIT | https://github.com/yjsunnn/DLoRAL |
| `osdenhancer-v1` | OSDEnhancer | Apache-2.0 | https://github.com/W-Shuoyan/OSDEnhancer (HF `W-Shuoyan/OSDEnhancer`) |
| `sparkvsr-stage2` | SparkVSR | Apache-2.0 | HF `JiongzeYu/SparkVSR` |
| `vfimamba` | VFIMamba S / Full | Apache-2.0 | https://github.com/MCG-NJU/VFIMamba (HF `MCG-NJU/VFIMamba_ckpts`) |
| `rife-ncnn-models` | RIFE 4.20–4.26 ncnn conversions | MIT | https://github.com/TNTwise/rife-ncnn-vulkan |

Each optional pack's isolated runtime code ships in
`light_video_enhancer_forked/external/*.zip` together with that project's
license file (verified by the unit tests).

## NVIDIA Video Effects (`nvvfx`)

The NVIDIA Video Effects / Maxine super-resolution path uses the separate
`nvvfx` Python package and its models, which are **not** bundled with this
project. They are distributed by NVIDIA under the NVIDIA Video Effects SDK
license (https://developer.nvidia.com/maxine), which users must accept
before installing. No NVIDIA SDK files are committed to this repository.

## Python / .NET dependencies

| Component | License | Use |
|---|---|---|
| NumPy | BSD-3-Clause | Array processing (runtime) |
| OpenCV (`opencv-contrib-python`) | Apache-2.0 | Image/video processing (runtime) |
| PyTorch, torchvision (external environments) | BSD-style (PyTorch license) | Torch engine inference (optional, downloaded runtimes) |
| PyInstaller | GPL-2.0-or-later with special bootloader exception | Build tool only; not part of the shipped binaries' runtime |
| .NET 10 / Windows App SDK / WinUI 3 | MIT | GUI framework (framework-dependent at build time; self-contained when published) |

## GPL notice for distributed binaries

The distributed backend binaries embed the **GPL-2.0-or-later** FFmpeg
shared runtime (BtbN build) and our GPL-linked `ffmpeg_worker.dll`. The
complete corresponding source for the GPL components is:

- FFmpeg: https://github.com/BtbN/FFmpeg-Builds — the exact build recipe
  and source for `ffmpeg-n8.1-latest-win64-gpl-shared-8.1.zip`; upstream
  source: https://git.ffmpeg.org/ffmpeg.git
- `ffmpeg_worker.dll`: `light_video_enhancer_forked/ffmpeg_bridge/ffmpeg_worker.c`
  in this repository (build against the same BtbN headers/libs).

The MIT license of this repository's own code applies to the code itself;
the binary distribution is subject to the GPL terms above for the
embedded FFmpeg components.
