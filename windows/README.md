# Light Video Enhancer-Forked · WinUI 3

This is the modern Windows 10/11 frontend. It implements no video
algorithms itself; it drives the standalone Python/C++ backend over a
versioned stdio JSON protocol.

## Supported systems

- Minimum: Windows 10 1809 (build 17763) x64
- Recommended: Windows 11 x64
- Windows 7: the frozen Tk LTS full package
- UI: WinUI 3 / Windows App SDK 2.3.1
- Deployment: unpackaged and self-contained; the target machine needs no
  .NET or Windows App Runtime preinstalled

## Running from source

Requires the .NET 10 SDK. Debug builds walk up the tree for
`pyproject.toml`, then run `python -m light_video_enhancer_forked`.

```powershell
dotnet run --project windows\LightVideoEnhancerForked.WinUI\LightVideoEnhancerForked.WinUI.csproj -p:Platform=x64
```

Environment variables:

- `LVE_BACKEND`: point the frontend at a specific backend EXE
- `LVE_PYTHON`: explicit interpreter for source-debug runs
- `LVE_MODEL_DIR`: override the user model directory
- `LVE_LANG`: `zh-CN` or `en-US`

## Building the Full / Lite portable packages

The current Python environment needs the project build requirements and
PyInstaller 6+:

```powershell
python -m pip install -r requirements-build.txt
powershell -ExecutionPolicy Bypass -File windows\build_winui.ps1
```

By default this produces both profiles:

```text
dist\LightVideoEnhancerForked-WinUI3-Full-Win10-11-x64\
dist\LightVideoEnhancerForked-WinUI3-Full-Win10-11-x64.zip
dist\LightVideoEnhancerForked-WinUI3-Lite-Win10-11-x64\
dist\LightVideoEnhancerForked-WinUI3-Lite-Win10-11-x64.zip
```

Pass `-Profile Full` or `-Profile Lite` to build one profile. Add
`-SkipBackend` when the backend already exists.

Both directories contain exactly three files:
`LightVideoEnhancerForked.WinUI.exe`,
`LightVideoEnhancerForked-Backend.exe`, and `CLI_GUIDE.md`. The frontend
uses the self-contained single-file publishing supported by the Windows
App SDK and keeps only the satellite localization resources; the .NET
and WinUI runtimes unpack into the system cache on first launch instead
of scattering through the program directory.

The Full and Lite frontends are byte-identical; only the backend —
uniformly renamed `LightVideoEnhancerForked-Backend.exe` — differs. Lite
keeps the FFmpeg worker, the Vulkan executables, and all classic
algorithms; it only drops model weights.

## Standalone backend CLI

`LightVideoEnhancerForked-Backend.exe` is the complete console program
that does not depend on the GUI; the archives contain no Tkinter,
Tcl/Tk, IDLE, or the old GUI modules. Launching by double-click or
without arguments enters the interactive wizard; full arguments work
directly in PowerShell:

```powershell
.\LightVideoEnhancerForked-Backend.exe --help
.\LightVideoEnhancerForked-Backend.exe --system-info
.\LightVideoEnhancerForked-Backend.exe input.mp4 -o output.mp4 --scale 2 --fi-multiplier 2 --codec auto --overwrite
```

The CLI wizard, help, processing log, and errors stay English. All JSON
queries for the frontend keep standard output clean; diagnostics go to
standard error. Full reference: the bundled `CLI_GUIDE.md`.

## External environment gating

The WinUI app does not scan for external Python at startup. Before a
scan, NVIDIA Video Effects VSR, RIFE PyTorch, and CUDA optical flow stay
disabled; a manual scan unlocks them only when the results confirm
`PyTorch + CUDA + NV-VFX`, `PyTorch`, or `PyTorch + CUDA` respectively.
NCNN, D3D11 VSR, and the classic CPU algorithms are unaffected.

## Size and deployment trade-offs

In the current verified build, the self-contained WinUI frontend dropped
from about 85.6 MiB to about 42.4 MiB, and the Lite backend is about
96.9 MiB. The frontend still carries .NET and the Windows App SDK, so
the target machine needs no extra non-system runtime, and the
single-file payload unpacks to the system cache on first launch.

The size cut is not simple DLL deletion. The build excludes the unused
Windows App SDK AI/ML, DirectML, ONNX Runtime, Widgets, NPU detection,
and workload manifests, then enables controlled `partial` trimming with
WinUI, WinRT, the Windows SDK projections, and the app assembly pinned
as trimming roots. The step-by-step results:

| Experiment | Frontend size | Result |
|---|---:|---|
| Original self-contained single file | ~85.6 MiB | Works |
| Unused workloads excluded | ~68.1 MiB | Works |
| Aggressive trimming without roots | ~34.1 MiB | WinUI init crash |
| Controlled trimming with the needed roots | ~42.4 MiB | Pages, themes, localization, the model list, and the backend protocol verified live |

Framework-dependent builds can be smaller still, but they require the
user to install matching .NET and Windows App Runtime versions, which
defeats the portable "extract and run" goal. The Windows App SDK /
WinRT still produces IL2104 trimming analysis warnings, so every SDK
upgrade needs a fresh GUI regression — launch, page navigation, and the
backend protocol — and compiling cleanly alone is not shippable.

## Model packs

Run:

```powershell
python tools\build_model_packs.py
```

This builds the ten standard model ZIPs in `dist\model-packs` and
refreshes the archive and per-file SHA-256 entries in
`light_video_enhancer_forked\model_manifest.json`. The multi-GiB
generative weights (FlashVSR, SeedVR2, and friends) and the two
optional RIFE model sets — `rife-ncnn-models` for the ncnn 4.20-4.26
variants and `rife-torch-models` for the PyTorch 4.20-4.26 weights —
stay download-on-demand with pinned per-file SHA-256 manifests. Upload
the standard ZIPs to the GitHub release `models-v1` and the GUI's
GitHub/mirror sources work out of the box; custom base URLs,
`{archive}` templates, and local ZIP import remain available at any
time.

## Process protocol

- `--capabilities-json`: quick hardware, model, and encoder
  capabilities, including the `ncnn_rife_models` and
  `rife_torch_models` lists that gate the per-engine model dropdowns
- `--environments-json --force`: on-demand Python / PyTorch / CUDA
  environment scan
- `--models-json`: model sources, paths, sizes, and install state
- `--download-model` / `--install-model-pack` / `--remove-model` /
  `--repair-model`: model management
- `--progress-json`: emits progress JSON lines prefixed
  `__LVE_PROGRESS__`
- `--control-stdin`: receives `cancel` on standard input

Protocol version and compatibility rules:
[`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md).
