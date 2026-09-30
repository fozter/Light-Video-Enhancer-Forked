#!/bin/bash
# Build the fork's minimal FFmpeg 9.0.2 shared runtime (MSYS2 UCRT64).
#
# Layout: the FFmpeg source must live at <repo>/../ffmpeg (sibling of this
# repo's root) with the tree directly inside (configure at the top level).
# The runtime is installed to <ffmpeg>/build and consumed by
# light_video_enhancer_forked/ffmpeg_bridge/build_worker.sh.
#
# Component policy — everything the bundled ffmpeg_worker.c uses and the
# codec menu the app offers, nothing else:
#   * decoders: common inputs + ffv1 (so the app can re-ingest its own
#     lossless MKV outputs)
#   * encoders: the full CODEC_CHOICES set from encoding.py (nvenc/amf/mf,
#     libx264, libx265, libsvtav1, libaom-av1, mpeg4, mjpeg) + ffv1
#   * muxers mp4/mov/mkv/webm/avi (worker picks by output extension),
#     demuxers for the common containers, file protocol only
#   * no avfilter, no avdevice, no network, no CLI programs
set -euo pipefail

export MSYSTEM=UCRT64
export PATH="/ucrt64/bin:/usr/bin:$PATH"
export PKG_CONFIG_PATH="/ucrt64/lib/pkgconfig"

SRC="$(cd "$(dirname "$0")/../ffmpeg" && pwd)"
OUT="$SRC/build"
JOBS=$(nproc 2>/dev/null || echo 4)

echo "=== Build minimal FFmpeg runtime (cross-vendor codecs, FFV1 included) ==="
cd "$SRC"
make distclean >/dev/null 2>&1 || true
rm -rf "$OUT"
mkdir -p "$OUT"

./configure \
    --prefix="$OUT" \
    --enable-shared --disable-static --enable-gpl \
    --disable-programs --disable-doc --disable-avdevice --disable-avfilter \
    --disable-network \
    --disable-everything \
    --disable-bzlib --disable-lzma --disable-sdl2 --disable-vaapi \
    --enable-decoder=h264,hevc,av1,libdav1d,vp8,vp9,mpeg4,mpeg2video,mjpeg,png,prores,wmv1,wmv2,wmv3,vc1,theora,ffv1 \
    --enable-encoder=h264_nvenc,hevc_nvenc,av1_nvenc,h264_amf,hevc_amf,av1_amf,h264_mf,hevc_mf,libx264,libx265,libaom_av1,libsvtav1,mpeg4,mjpeg,ffv1 \
    --enable-hwaccel=h264_nvdec,hevc_nvdec,av1_nvdec \
    --enable-parser=h264,hevc,av1,vp8,vp9,mpeg4video,mpegvideo,mjpeg,vc1 \
    --enable-demuxer=mov,matroska,avi,mpegts,mpegvideo,flv,ogg,image2 \
    --enable-muxer=mov,mp4,matroska,avi,webm,null \
    --enable-protocol=file \
    --enable-bsf=h264_mp4toannexb,hevc_mp4toannexb,av1_frame_merge,av1_frame_split,av1_metadata,aac_adtstoasc \
    --enable-nvenc --enable-nvdec --enable-cuvid --enable-ffnvcodec \
    --enable-libx264 --enable-libx265 --enable-libaom --enable-libsvtav1 --enable-libdav1d \
    --enable-mediafoundation \
    --cc=gcc --cxx=g++ \
    --extra-cflags="-I/ucrt64/include" \
    --extra-ldflags="-L/ucrt64/lib"

# Fail early when a component the app needs silently dropped out.
for comp in CONFIG_FFV1_ENCODER CONFIG_FFV1_DECODER CONFIG_LIBX264_ENCODER \
            CONFIG_LIBX265_ENCODER CONFIG_LIBSVTAV1_ENCODER \
            CONFIG_LIBAOM_AV1_ENCODER CONFIG_MPEG4_ENCODER CONFIG_MJPEG_ENCODER \
            CONFIG_H264_NVENC_ENCODER CONFIG_H264_AMF_ENCODER CONFIG_H264_MF_ENCODER \
            CONFIG_HEVC_NVENC_ENCODER CONFIG_HEVC_MF_ENCODER CONFIG_AV1_NVENC_ENCODER \
            CONFIG_AV1_AMF_ENCODER CONFIG_H264_DECODER CONFIG_HEVC_DECODER \
            CONFIG_LIBDAV1D_DECODER CONFIG_MATROSKA_MUXER CONFIG_MATROSKA_DEMUXER \
            CONFIG_MOV_MUXER CONFIG_MP4_MUXER CONFIG_AVI_MUXER CONFIG_MOV_DEMUXER \
            CONFIG_FILE_PROTOCOL; do
    grep -q "^#define $comp 1$" config_components.h || {
        echo "ERROR: $comp is missing from the build" >&2
        exit 1
    }
done

make -j"$JOBS"
make install

cp -v /ucrt64/bin/libgcc_s_seh-1.dll "$OUT/bin/" 2>/dev/null || true
cp -v /ucrt64/bin/libstdc++-6.dll "$OUT/bin/" 2>/dev/null || true
cp -v /ucrt64/bin/libwinpthread-1.dll "$OUT/bin/" 2>/dev/null || true

echo "=== Component check ==="
grep -E "^#define CONFIG_(FFV1|LIBX264|LIBX265|LIBSVTAV1|LIBAOM_AV1|MPEG4|MJPEG|H264_NVENC|H264_AMF|H264_MF|HEVC_NVENC|HEVC_AMF|HEVC_MF|AV1_NVENC|AV1_AMF)_ENCODER 1$" config_components.h \
    | awk '{print $2}' | sort
echo "=== FFmpeg runtime ready: $OUT ==="
ls -la "$OUT/bin/"
