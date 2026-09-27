#!/usr/bin/env python3
"""Fetch the FFmpeg 8.1 shared runtime for the backend build.

The BtbN FFmpeg 8.1 GPL shared build provides avcodec-62.dll and friends
that the bundled FFmpeg worker links against. The DLLs are NOT committed to
git: avcodec-62.dll alone is ~119 MB, above GitHub's 100 MB per-file limit.
Run this script once before building the backend executable.

Behavior
--------
* Downloads the current BtbN `latest` rolling release.
* Extracts the five runtime DLLs into light_video_enhancer_forked/ffmpeg_dlls.
* Compares every DLL against the REFERENCE SHA-256 set below — the build
  this project was developed and validated against (2026-09).
* BtbN periodically rebuilds the `latest` assets, so a newer byte-identical
  series build is expected over time: the script then prints a prominent
  WARNING but proceeds (the DLL ABI majors are pinned by the worker:
  62/62/60/9/6). Pass --strict to abort unless the bytes match the
  reference set exactly.
"""

import argparse
import hashlib
import io
import os
import sys
import urllib.error
import urllib.request
import zipfile

URL = ("https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
       "ffmpeg-n8.1-latest-win64-gpl-shared-8.1.zip")
REFERENCE_DLLS = {
    "avcodec-62.dll": ("9BC23DF21E27165938DC8563E2DD5C3E08ECE21A5"
                       "04966024F439ED5C3E3C3CF"),
    "avformat-62.dll": ("8D7B296BD849DE6022867443012B9C4259FFE0348"
                        "378712D0BB5BEA1B1EF8C8"),
    "avutil-60.dll": ("A4BAA4022480B7AE7324E9E969323C709F0F18201"
                      "6A91BEDFE986F003713214"),
    "swresample-6.dll": ("0DDA1B2F6DF504FCDD593F3D24167F43225E210B"
                         "A5F2B7A35288282D19563012"),
    "swscale-9.dll": ("0191A83C4DA9450EF0CC46E2BEAD28D400A04781"
                      "085E9F3A3CCC1AC5452F2673"),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--strict", action="store_true",
                        help="abort when a DLL differs from the reference set")
    args = parser.parse_args()

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dest = os.path.join(repo, "light_video_enhancer_forked", "ffmpeg_dlls")
    os.makedirs(dest, exist_ok=True)

    print("Downloading %s" % URL)
    request = urllib.request.Request(
        URL, headers={"User-Agent": "LightVideoEnhancerForked/0.0.1"})
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read()
    archive_digest = hashlib.sha256(data).hexdigest().upper()
    print("Archive SHA-256: %s (%.1f MiB)"
          % (archive_digest, len(data) / 1048576.0))

    unpinned = 0
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        for name, reference in REFERENCE_DLLS.items():
            members = [m for m in names if m.endswith("/bin/" + name)]
            if not members:
                raise SystemExit("The archive does not contain %s" % name)
            payload = archive.read(members[0])
            if not payload:
                raise SystemExit("%s is empty in the archive" % name)
            actual = hashlib.sha256(payload).hexdigest().upper()
            matches = actual == reference
            if not matches:
                if args.strict:
                    raise SystemExit(
                        "%s SHA-256 %s differs from the reference %s"
                        % (name, actual, reference))
                unpinned += 1
            target = os.path.join(dest, name)
            with open(target, "wb") as handle:
                handle.write(payload)
            print("%s -> %s (%s)"
                  % (name, target, "reference match" if matches else "NEWER BUILD"))
    if unpinned:
        print("\nWARNING: %d of %d DLLs differ from the reference set this "
              "project was validated against (expected: BtbN rebuilt the "
              "'latest' assets). The worker pins the ABI majors "
              "(62/62/60/9/6); run a short FFV1 smoke test after building. "
              "Use --strict to require the exact reference bytes."
              % (unpinned, len(REFERENCE_DLLS)))
    print("FFmpeg runtime ready in %s" % dest)


if __name__ == "__main__":
    try:
        main()
    except (urllib.error.URLError, OSError) as exc:
        print("Download failed: %s" % exc, file=sys.stderr)
        raise SystemExit(2)
