#!/usr/bin/env python3
"""Verify the bundled FFmpeg 9.0.2 runtime in light_video_enhancer_forked/ffmpeg_dlls.

The runtime is our own minimal FFmpeg 9.0.2 shared build (see build_ffmpeg.sh
at the repository root) plus the MSYS2 UCRT64 codec DLLs it links against.
It is NOT downloadable from a binary release anymore: the previous BtbN
8.1 downloader was retired when the project switched to the self-built
runtime. The DLLs ship in the source snapshot and are embedded in every
backend executable; a fresh git clone needs either the snapshot or a
runtime rebuild (MSYS2 UCRT64 + build_ffmpeg.sh + build_worker.sh).

Behavior
--------
* Checks that every DLL the worker's import closure requires is present
  (the exact set is import-verified: nothing outside it is referenced).
* Rejects stale DLLs from the retired BtbN 8.1 runtime (avcodec-62 etc.).
* Prints the SHA-256 of every file so a build can be pinned in docs.
"""

import hashlib
import os
import sys

RUNTIME_DLLS = (
    "avcodec-63.dll",
    "avformat-63.dll",
    "avutil-61.dll",
    "swscale-10.dll",
    "libx264-165.dll",
    "libx265-217.dll",
    "libaom.dll",
    "libdav1d-7.dll",
    "libSvtAv1Enc-4.dll",
    "libiconv-2.dll",
    "zlib1.dll",
    "libgcc_s_seh-1.dll",
    "libstdc++-6.dll",
    "libwinpthread-1.dll",
)

RETIRED_DLLS = (
    "avcodec-62.dll", "avformat-62.dll", "avutil-60.dll",
    "swscale-9.dll", "swresample-6.dll", "swresample-7.dll", "libzstd.dll",
)

EXPECTED_PREFIXES = {
    "avcodec-": ("63",),
    "avformat-": ("63",),
    "avutil-": ("61",),
    "swscale-": ("10",),
}


def main() -> None:
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    runtime = os.path.join(repo, "light_video_enhancer_forked", "ffmpeg_dlls")
    worker = os.path.join(repo, "light_video_enhancer_forked", "ffmpeg_bridge",
                          "ffmpeg_worker.dll")
    failures = 0

    if not os.path.isdir(runtime):
        raise SystemExit("Runtime directory is missing: %s" % runtime)
    present = sorted(name for name in os.listdir(runtime)
                     if name.lower().endswith(".dll"))

    for name in RUNTIME_DLLS:
        path = os.path.join(runtime, name)
        if not os.path.isfile(path):
            print("MISSING  %s" % name)
            failures += 1
            continue
        digest = hashlib.sha256(open(path, "rb").read()).hexdigest().upper()
        print("OK       %-20s %10d bytes  SHA-256 %s" %
              (name, os.path.getsize(path), digest))

    stale = [name for name in present if name in RETIRED_DLLS]
    for name in stale:
        print("STALE    %s (retired runtime; delete it)" % name)
        failures += 1

    for name in present:
        for prefix, majors in EXPECTED_PREFIXES.items():
            if name.startswith(prefix):
                major = name[len(prefix):].split(".")[0]
                if major not in majors:
                    print("WRONG ABI %s (expected major %s)" %
                          (name, "/".join(majors)))
                    failures += 1

    unknown = [name for name in present
               if name not in RUNTIME_DLLS and name not in stale]
    if unknown:
        print("NOTE     extra DLLs present (not in the pinned closure): %s"
              % ", ".join(unknown))

    if not os.path.isfile(worker):
        print("MISSING  ffmpeg_bridge/ffmpeg_worker.dll")
        failures += 1
    else:
        digest = hashlib.sha256(open(worker, "rb").read()).hexdigest().upper()
        print("OK       ffmpeg_worker.dll     %10d bytes  SHA-256 %s" %
              (os.path.getsize(worker), digest))

    if failures:
        print("\n%d problem(s). The backend build must not proceed with an "
              "incomplete runtime - rebuild it with build_ffmpeg.sh + "
              "ffmpeg_bridge/build_worker.sh (MSYS2 UCRT64)." % failures,
              file=sys.stderr)
        raise SystemExit(1)
    print("\nFFmpeg 9.0.2 runtime complete: %d DLLs verified in %s"
          % (len(RUNTIME_DLLS), runtime))


if __name__ == "__main__":
    main()
