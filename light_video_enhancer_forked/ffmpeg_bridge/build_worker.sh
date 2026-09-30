#!/bin/bash
# Build the Windows 7-compatible FFmpeg worker from an MSYS2 UCRT64 shell.
set -e

export MSYSTEM=UCRT64
export PATH="/ucrt64/bin:/usr/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
FFMPEG_BUILD="${FFMPEG_BUILD:-$PROJECT_DIR/../ffmpeg/build}"
FFMPEG_DLLS="$SCRIPT_DIR/../ffmpeg_dlls"

echo "============================================"
echo "  Build FFmpeg Worker DLL"
echo "============================================"

gcc -shared -O2 \
    -o "$SCRIPT_DIR/ffmpeg_worker.dll" \
    "$SCRIPT_DIR/ffmpeg_worker.c" \
    -I"$FFMPEG_BUILD/include" \
    -L"$FFMPEG_BUILD/lib" \
    -L"$FFMPEG_BUILD/bin" \
    -lavformat -lavcodec -lavutil -lswscale \
    -lmfplat -lmfuuid -lole32 -luuid \
    -static-libgcc

echo "  Copy FFmpeg runtime DLLs to $FFMPEG_DLLS"
mkdir -p "$FFMPEG_DLLS"
rm -f "$FFMPEG_DLLS"/*.dll
# FFmpeg ABI majors are pinned by the worker link line; wildcards keep the
# script valid across a version bump. swresample is NOT shipped: nothing in
# the closure imports it (worker links avformat/avcodec/avutil/swscale only).
for runtime in \
    "$FFMPEG_BUILD/bin/avcodec-"*.dll \
    "$FFMPEG_BUILD/bin/avformat-"*.dll \
    "$FFMPEG_BUILD/bin/avutil-"*.dll \
    "$FFMPEG_BUILD/bin/swscale-"*.dll \
    /ucrt64/bin/libx264-*.dll \
    /ucrt64/bin/libx265-*.dll \
    /ucrt64/bin/libaom.dll \
    /ucrt64/bin/libdav1d-*.dll \
    /ucrt64/bin/libSvtAv1Enc-*.dll \
    /ucrt64/bin/libiconv-2.dll \
    /ucrt64/bin/zlib1.dll \
    /ucrt64/bin/libgcc_s_seh-1.dll \
    /ucrt64/bin/libstdc++-6.dll \
    /ucrt64/bin/libwinpthread-1.dll; do
    [ -f "$runtime" ] && cp -v "$runtime" "$FFMPEG_DLLS/"
done

echo "Worker: $SCRIPT_DIR/ffmpeg_worker.dll"
echo "FFmpeg: $FFMPEG_DLLS"
