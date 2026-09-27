#!/usr/bin/env python3
"""Build a portable Light Video Enhancer-Forked GUI executable.

Use CPython 3.8.10 + PyInstaller 5.13.2 for the Windows 7 package. Use a
64-bit CPython 3.10+ environment + PyInstaller 6 for the Windows 10/11 package.
"""

import argparse
import os
import platform
import re
import subprocess
import sys

from light_video_enhancer_forked.model_manager import model_weight_paths


PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
PACKAGE_NAME = "light_video_enhancer_forked"
PACKAGE_DIR = os.path.join(PROJECT_DIR, PACKAGE_NAME)
LAUNCHER = os.path.join(PROJECT_DIR, "launcher.py")
BACKEND_LAUNCHER = os.path.join(PROJECT_DIR, "backend_launcher.py")
OUTPUT_DIR = os.path.join(PROJECT_DIR, "dist")
MODERN_MANIFEST = os.path.join(PROJECT_DIR, "windows_manifest_win10.xml")
_MODEL_WEIGHT_PATHS = {
    path.replace("\\", "/") for path in model_weight_paths()
}


def _project_version():
    path = os.path.join(PACKAGE_DIR, "__init__.py")
    with open(path, "r", encoding="utf-8") as handle:
        match = re.search(r'^__version__\s*=\s*["\']([^"\']+)', handle.read(), re.MULTILINE)
    if not match:
        raise SystemExit("Could not read the project version.")
    return match.group(1)


def _is_model_weight(path):
    return path.replace("\\", "/") in _MODEL_WEIGHT_PATHS


def _data_files(profile, target):
    relative = [
        "_shared_frames.py",
        "model_manifest.json",
        "_fused_rife_nvvfx_infer.py",
        # The FFmpeg runtime DLLs (BtbN FFmpeg 8.1 GPL shared build with the
        # FFV1 encoder) are collected automatically by PyInstaller's binary
        # dependency analysis because ffmpeg_dlls is on PATH during the build;
        # they end up at the bundle root, which worker.py adds as a DLL
        # search directory in frozen mode.
        os.path.join("ffmpeg_bridge", "ffmpeg_worker.dll"),
        os.path.join("bridge", "dxva_vsr_bridge.dll"),
        os.path.join("fi", "_rife_infer.py"),
        os.path.join("fi", "_rife_model.py"),
        os.path.join("fi", "warplayer.py"),
        os.path.join("fi", "flownet.pkl"),
        os.path.join("fi", "_ema_vfi_infer.py"),
        os.path.join("fi", "_ema_vfi_vendor"),
        os.path.join("fi", "ema_vfi"),
        os.path.join("fi", "_vfimamba_infer.py"),
        os.path.join("sr", "_nvvfx_infer.py"),
        "ncnn",
    ]
    if target == "modern":
        relative.extend([
            os.path.join("sr", "_flashvsr_infer.py"),
            os.path.join("sr", "_seedvr2_infer.py"),
            os.path.join("sr", "_dloral_infer.py"),
            os.path.join("sr", "_osdenhancer_infer.py"),
            os.path.join("sr", "_sparkvsr_infer.py"),
            "external",
        ])
    result = []
    for item in relative:
        source = os.path.join(PACKAGE_DIR, item)
        if not os.path.exists(source):
            continue
        if os.path.isdir(source):
            for root, _, files in os.walk(source):
                for name in files:
                    path = os.path.join(root, name)
                    relative_path = os.path.relpath(path, PACKAGE_DIR)
                    if profile == "light" and _is_model_weight(relative_path):
                        continue
                    target = os.path.join(PACKAGE_NAME, os.path.relpath(root, PACKAGE_DIR))
                    result.extend(["--add-data", path + os.pathsep + target])
        else:
            if profile == "light" and _is_model_weight(item):
                continue
            target = os.path.join(PACKAGE_NAME, os.path.dirname(item))
            result.extend(["--add-data", source + os.pathsep + target])
    return result


def _version_file(version):
    numbers = [int(part) for part in re.findall(r"\d+", version)[:4]]
    numbers.extend([0] * (4 - len(numbers)))
    dotted = ".".join(str(value) for value in numbers)
    comma = ", ".join(str(value) for value in numbers)
    path = os.path.join(PROJECT_DIR, "build", "version_info.txt")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    content = """VSVersionInfo(
  ffi=FixedFileInfo(filevers=({comma}), prodvers=({comma}), mask=0x3f,
    flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('080404b0', [
    StringStruct('CompanyName', 'fozter'),
    StringStruct('FileDescription', 'Light Video Enhancer-Forked'),
    StringStruct('FileVersion', '{dotted}'),
    StringStruct('InternalName', 'LightVideoEnhancerForked'),
    StringStruct('OriginalFilename', 'LightVideoEnhancerForked.exe'),
    StringStruct('ProductName', 'Light Video Enhancer-Forked'),
    StringStruct('ProductVersion', '{dotted}')])]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])])
""".format(comma=comma, dotted=dotted)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


def _build_target(pyinstaller_version):
    if platform.architecture()[0] != "64bit":
        raise SystemExit("Release packages must be built with 64-bit Python.")
    if sys.version_info[:2] == (3, 8):
        if pyinstaller_version != "5.13.2":
            raise SystemExit("Windows 7 builds must use PyInstaller 5.13.2.")
        return "win7", "LightVideoEnhancerForked-Win7-x64"
    if sys.version_info >= (3, 10):
        major = int(pyinstaller_version.split(".", 1)[0])
        if major < 6:
            raise SystemExit("Windows 10/11 builds must use PyInstaller 6 or newer.")
        return "modern", "LightVideoEnhancerForked-Win10-11-x64"
    raise SystemExit("Use Python 3.8.10 for the Win7 build, or 64-bit Python 3.10+ for the Win10/11 build.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Light Video Enhancer-Forked executables")
    parser.add_argument("--backend", action="store_true", help="build the console backend invoked by the WinUI 3 frontend")
    parser.add_argument("--profile", choices=("full", "light"), default="full",
                        help="control whether model weights are embedded in the backend")
    args = parser.parse_args()
    try:
        import PyInstaller
    except ImportError:
        raise SystemExit("PyInstaller is missing. Install the build dependencies first.")
    if not os.path.isdir(PACKAGE_DIR):
        raise SystemExit("The package directory was not found: %s" % PACKAGE_DIR)

    target, executable_name = _build_target(PyInstaller.__version__)
    if args.backend and target != "modern":
        raise SystemExit("The WinUI backend must be built with 64-bit Python 3.10+ and PyInstaller 6+.")
    if target == "modern" and not args.backend:
        raise SystemExit(
            "The Windows 10/11 Tk GUI is no longer published; run windows/build_winui.ps1 to build the WinUI package.")
    if target == "win7" and args.profile != "full":
        raise SystemExit("The Windows 7 Tk GUI is only published as a full build containing all weights.")
    if args.backend:
        executable_name = "LightVideoEnhancerForked-Backend-" + ("Lite" if args.profile == "light" else "Full")
    version = _project_version()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    hidden = [
        PACKAGE_NAME + ".native_ncnn",
        PACKAGE_NAME + ".executor", PACKAGE_NAME + ".ncnn_contract",
        PACKAGE_NAME + ".fused_rife_nvvfx",
        PACKAGE_NAME, PACKAGE_NAME + ".pipeline", PACKAGE_NAME + ".config",
        PACKAGE_NAME + ".cli", PACKAGE_NAME + ".capabilities",
        PACKAGE_NAME + ".sr", PACKAGE_NAME + ".sr.dxva_vsr",
        PACKAGE_NAME + ".sr.nvvfx_sr", PACKAGE_NAME + ".sr.realcugan_ncnn",
        PACKAGE_NAME + ".sr.realesrgan_ncnn", PACKAGE_NAME + ".sr.span_ncnn",
        PACKAGE_NAME + ".sr.flashvsr", PACKAGE_NAME + ".sr.seedvr2",
        PACKAGE_NAME + ".sr.dloral", PACKAGE_NAME + ".sr.osdenhancer",
        PACKAGE_NAME + ".sr.sparkvsr",
        PACKAGE_NAME + ".fi", PACKAGE_NAME + ".fi.rife",
        PACKAGE_NAME + ".fi.rife_ncnn", PACKAGE_NAME + ".fi.ifrnet_ncnn",
        PACKAGE_NAME + ".fi.ema_vfi",
        PACKAGE_NAME + ".fi.vfimamba",
        PACKAGE_NAME + ".fi.optical_flow", PACKAGE_NAME + ".fi.dis_flow",
        PACKAGE_NAME + ".fi.blend", PACKAGE_NAME + ".ffmpeg_bridge",
        PACKAGE_NAME + ".model_manager", PACKAGE_NAME + ".frontend_protocol",
        PACKAGE_NAME + ".backend_main", PACKAGE_NAME + ".cli_app",
        PACKAGE_NAME + "._paths",
    ]
    if not args.backend:
        hidden.append(PACKAGE_NAME + ".gui")
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
        "--console" if args.backend else "--windowed",
        "--name", executable_name, "--distpath", OUTPUT_DIR,
        "--workpath", os.path.join(PROJECT_DIR, "build", "pyinstaller"),
        "--specpath", os.path.join(PROJECT_DIR, "build"), "--noupx",
        "--version-file", _version_file(version),
    ]
    if target == "modern":
        command.extend(["--manifest", MODERN_MANIFEST])
    icon = os.path.join(PROJECT_DIR, "assets", "branding", "AppIcon.ico")
    if os.path.isfile(icon):
        command.extend(["--icon", icon])
    for module in hidden:
        command.extend(["--hidden-import", module])
    excluded = [
        "torch", "torchvision", "torchaudio", "nvvfx", "tensorflow",
        "pandas", "matplotlib", "jupyter", "scipy",
    ]
    if args.backend:
        excluded.extend([PACKAGE_NAME + ".gui", "tkinter", "_tkinter", "idlelib", "turtle"])
    for module in excluded:
        command.extend(["--exclude-module", module])
    command.extend(_data_files(args.profile, target))
    command.append(BACKEND_LAUNCHER if args.backend else LAUNCHER)
    build_env = dict(os.environ)
    build_env["PYTHONNOUSERSITE"] = "1"
    ffmpeg_dll_dir = os.path.join(PACKAGE_DIR, "ffmpeg_dlls")
    build_env["PATH"] = ffmpeg_dll_dir + os.pathsep + build_env.get("PATH", "")
    print("Build target: %s%s | Python %s | PyInstaller %s | project %s" % (
        "Windows 7" if target == "win7" else "Windows 10/11",
        (" WinUI backend (%s)" % args.profile) if args.backend else " GUI",
        platform.python_version(), PyInstaller.__version__, version))
    subprocess.run(command, check=True, cwd=PROJECT_DIR, env=build_env)
    executable = os.path.join(OUTPUT_DIR, executable_name + ".exe")
    if not os.path.isfile(executable):
        raise SystemExit("The build finished without producing an executable.")
    print("Completed: %s (%.1f MB)" % (executable, os.path.getsize(executable) / 1024 / 1024))


if __name__ == "__main__":
    main()
