"""
RIFE PyTorch model definitions (hzwer Practical-RIFE family + FluidFrames 4.27).

One architecture class per selectable model (see fi/rife.py RIFE_TORCH_MODELS):

- FlownetCas      RIFE v4.25 / v4.26: five-block cascade with the shared
                  16-channel Head (4-channel features), 13-channel block
                  outputs (flow 4 / mask 1 / feat 8), inference scale list
                  [16, 8, 4, 2, 1].  Source: Practical-RIFE V4.25/V4.26
                  train_log/IFNet_HDv3.py (the teacher/caltime training heads
                  are commented out upstream and absent from the weights).
- FlownetCasLite  RIFE v4.25 Lite: block4 at 24 channels and a deeper first
                  scale; inference scale list [32, 16, 8, 4, 1].
- Flownet421      RIFE v4.21 / v4.22: four blocks [256, 192, 96, 48] with the
                  32-channel Head (8-channel features), 13-channel outputs,
                  scale list [8, 4, 2, 1].
- Flownet421Lite  RIFE v4.22 Lite: four blocks [192, 128, 64, 32] with the
                  16-channel Head, scale list [8, 4, 2, 1].
- Flownet420      RIFE v4.20: four blocks [384, 192, 96, 48], 32-channel Head,
                  6-channel block outputs (no feature feedback), scale list
                  [8, 4, 2, 1].
- RIFE427         FluidFrames 2026.3 five-block IFNet (no ResConv beta, no
                  teacher, internal 64-pixel padding).  Converted from
                  AI-onnx/RIFE_fp32.onnx; see tools/convert_rife427_torch.py.

The hzwer-family classes keep the released train_log/flownet.pkl state-dict
key layout unchanged (block0..blockN, encode.cnn0..cnn3, conv0.0.0/conv0.2.0,
convblock.N.conv/beta, lastconv.0), so the official weights load without key
surgery.  Teacher/caltime training heads that exist in the v4.20/v4.21/v4.22
releases are ignored (strict=False).  RIFE427 keeps the key layout produced by
the validated ONNX-initializers conversion.

Shared by fi/rife.py and fi/_rife_infer.py.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F

try:
    from .warplayer import warp
except ImportError:
    from warplayer import warp


def conv(in_planes, out_planes, kernel_size=3, stride=1, padding=1, dilation=1):
    return nn.Sequential(
        nn.Conv2d(in_planes, out_planes, kernel_size=kernel_size, stride=stride,
                  padding=padding, dilation=dilation, bias=True),
        nn.LeakyReLU(0.2, True)
    )


class Head(nn.Module):
    """16-channel encoder with 4-channel full-resolution features (v4.22 lite+)."""

    def __init__(self):
        super(Head, self).__init__()
        self.cnn0 = nn.Conv2d(3, 16, 3, 2, 1)
        self.cnn1 = nn.Conv2d(16, 16, 3, 1, 1)
        self.cnn2 = nn.Conv2d(16, 16, 3, 1, 1)
        self.cnn3 = nn.ConvTranspose2d(16, 4, 4, 2, 1)
        self.relu = nn.LeakyReLU(0.2, True)

    def forward(self, x, feat=False):
        x0 = self.cnn0(x)
        x = self.relu(x0)
        x1 = self.cnn1(x)
        x = self.relu(x1)
        x2 = self.cnn2(x)
        x = self.relu(x2)
        x3 = self.cnn3(x)
        if feat:
            return [x0, x1, x2, x3]
        return x3


class HeadWide(nn.Module):
    """32-channel encoder with 8-channel features (v4.20-v4.22)."""

    def __init__(self):
        super(HeadWide, self).__init__()
        self.cnn0 = nn.Conv2d(3, 32, 3, 2, 1)
        self.cnn1 = nn.Conv2d(32, 32, 3, 1, 1)
        self.cnn2 = nn.Conv2d(32, 32, 3, 1, 1)
        self.cnn3 = nn.ConvTranspose2d(32, 8, 4, 2, 1)
        self.relu = nn.LeakyReLU(0.2, True)

    def forward(self, x, feat=False):
        x0 = self.cnn0(x)
        x = self.relu(x0)
        x1 = self.cnn1(x)
        x = self.relu(x1)
        x2 = self.cnn2(x)
        x = self.relu(x2)
        x3 = self.cnn3(x)
        if feat:
            return [x0, x1, x2, x3]
        return x3


class ResConv(nn.Module):
    """hzwer residual conv with the learnable beta gate."""

    def __init__(self, c, dilation=1):
        super(ResConv, self).__init__()
        self.conv = nn.Conv2d(c, c, 3, 1, dilation, dilation=dilation, groups=1)
        self.beta = nn.Parameter(torch.ones((1, c, 1, 1)), requires_grad=True)
        self.relu = nn.LeakyReLU(0.2, True)

    def forward(self, x):
        return self.relu(self.conv(x) * self.beta + x)


class Flownet(nn.Module):
    """One IFNet block (hzwer IFBlock), generalized over the output channels.

    ``out_channels`` is 13 for the feature-feedback family (flow 4 / mask 1 /
    feat 8) and 6 for RIFE v4.20 (flow 4 / mask 1, no features).
    """

    def __init__(self, in_planes, c=64, out_channels=13):
        super(Flownet, self).__init__()
        self.conv0 = nn.Sequential(
            conv(in_planes, c // 2, 3, 2, 1),
            conv(c // 2, c, 3, 2, 1),
        )
        self.convblock = nn.Sequential(
            ResConv(c), ResConv(c), ResConv(c), ResConv(c),
            ResConv(c), ResConv(c), ResConv(c), ResConv(c),
        )
        self.lastconv = nn.Sequential(
            nn.ConvTranspose2d(c, 4 * out_channels, 4, 2, 1),
            nn.PixelShuffle(2),
        )

    def forward(self, x, flow, scale=1):
        x = F.interpolate(x, scale_factor=1. / scale, mode="bilinear",
                          align_corners=False)
        if flow is not None:
            flow = F.interpolate(flow, scale_factor=1. / scale, mode="bilinear",
                                 align_corners=False) * (1. / scale)
            x = torch.cat((x, flow), 1)
        feat = self.conv0(x)
        feat = self.convblock(feat)
        tmp = self.lastconv(feat)
        tmp = F.interpolate(tmp, scale_factor=scale, mode="bilinear",
                            align_corners=False)
        flow_out = tmp[:, :4] * scale
        mask = tmp[:, 4:5]
        conf = tmp[:, 5:]
        return flow_out, mask, conf


class _HzwerCascade(nn.Module):
    """Shared coarse-to-fine cascade forward for the hzwer IFNet family.

    Subclasses declare the block layout; the state-dict keys stay exactly the
    ones the released train_log/flownet.pkl files use.
    """

    SCALE_LIST = (16, 8, 4, 2, 1)
    FEEDBACK = True

    def __init__(self, head, first_in_planes, rest_in_planes, channels,
                 out_channels=13):
        super(_HzwerCascade, self).__init__()
        self.encode = head
        self.block0 = Flownet(first_in_planes, channels[0], out_channels)
        for index in range(1, len(channels)):
            setattr(self, "block%d" % index,
                    Flownet(rest_in_planes, channels[index], out_channels))

    def _blocks(self):
        count = 1
        while hasattr(self, "block%d" % count):
            count += 1
        return [getattr(self, "block%d" % index) for index in range(count)]

    def forward(self, x, timestep=0.5, scale_list=None):
        channel = x.shape[1] // 2
        img0 = x[:, :channel]
        img1 = x[:, channel:]
        if not torch.is_tensor(timestep):
            timestep = (x[:, :1].clone() * 0 + 1) * timestep
        else:
            timestep = timestep.repeat(1, 1, img0.shape[2], img0.shape[3])
        f0 = self.encode(img0[:, :3])
        f1 = self.encode(img1[:, :3])
        blocks = self._blocks()
        if scale_list is None:
            scale_list = self.SCALE_LIST
        flow = None
        mask = None
        feat = None
        warped_img0 = img0
        warped_img1 = img1
        merged = None
        for index, block in enumerate(blocks):
            if flow is None:
                flow, mask, feat = block(
                    torch.cat((img0[:, :3], img1[:, :3], f0, f1, timestep), 1),
                    None, scale=scale_list[index])
            else:
                inputs = [warped_img0[:, :3], warped_img1[:, :3],
                          warp(f0, flow[:, :2]), warp(f1, flow[:, 2:4]),
                          timestep, mask]
                if self.FEEDBACK:
                    inputs.append(feat)
                delta, mask, feat = block(torch.cat(inputs, 1), flow,
                                          scale=scale_list[index])
                flow = flow + delta
            warped_img0 = warp(img0, flow[:, :2])
            warped_img1 = warp(img1, flow[:, 2:4])
            merged = (warped_img0, warped_img1)
        mask = torch.sigmoid(mask)
        return merged[0] * mask + merged[1] * (1 - mask)

    def inference(self, img0, img1, timestep=0.5, scale=1.0):
        imgs = torch.cat((img0, img1), 1)
        scale_list = [value / scale for value in self.SCALE_LIST]
        return self.forward(imgs, timestep, scale_list)


class FlownetCas(_HzwerCascade):
    """RIFE v4.25 / v4.26 (five-block cascade)."""

    SCALE_LIST = (16, 8, 4, 2, 1)
    FEEDBACK = True

    def __init__(self):
        super(FlownetCas, self).__init__(
            Head(), 7 + 8, 8 + 4 + 8 + 8, (192, 128, 96, 64, 32))


class FlownetCasLite(_HzwerCascade):
    """RIFE v4.25 Lite (block4 at 24 channels, deeper first scale)."""

    SCALE_LIST = (32, 16, 8, 4, 1)
    FEEDBACK = True

    def __init__(self):
        super(FlownetCasLite, self).__init__(
            Head(), 7 + 8, 8 + 4 + 8 + 8, (192, 128, 96, 64, 24))


class Flownet421(_HzwerCascade):
    """RIFE v4.21 / v4.22 (four blocks, wide head, feature feedback)."""

    SCALE_LIST = (8, 4, 2, 1)
    FEEDBACK = True

    def __init__(self):
        super(Flownet421, self).__init__(
            HeadWide(), 7 + 16, 8 + 4 + 16 + 8, (256, 192, 96, 48))


class Flownet421Lite(_HzwerCascade):
    """RIFE v4.22 Lite (four blocks, compact head)."""

    SCALE_LIST = (8, 4, 2, 1)
    FEEDBACK = True

    def __init__(self):
        super(Flownet421Lite, self).__init__(
            Head(), 7 + 8, 8 + 4 + 8 + 8, (192, 128, 64, 32))


class Flownet420(_HzwerCascade):
    """RIFE v4.20 (four blocks, 6-channel outputs, no feature feedback)."""

    SCALE_LIST = (8, 4, 2, 1)
    FEEDBACK = False

    def __init__(self):
        super(Flownet420, self).__init__(
            HeadWide(), 7 + 16, 8 + 4 + 16, (384, 192, 96, 48),
            out_channels=6)


# --------------------------------------------------------------------------
# FluidFrames RIFE 4.27 (converted from AI-onnx/RIFE_fp32.onnx)
# --------------------------------------------------------------------------

_BLOCK_CHANNELS_427 = (192, 128, 96, 64, 32)
_BLOCK_SCALES_427 = (8.0, 4.0, 2.0, 1.0, 1.0)
_BLOCK_INPUT_SCALES_427 = (1.0 / 8, 1.0 / 4, 1.0 / 2, 1.0, 1.0)


class ResConvPlain(nn.Module):
    """FluidFrames residual conv: no beta gate (the ONNX folds it away)."""

    def __init__(self, channels):
        super(ResConvPlain, self).__init__()
        self.conv = nn.Conv2d(channels, channels, 3, 1, 1)

    def forward(self, x):
        return F.leaky_relu(self.conv(x) + x, 0.2)


class IFBlock427(nn.Module):
    def __init__(self, in_channels, out_channels):
        super(IFBlock427, self).__init__()
        self.conv0 = nn.Sequential(
            nn.Conv2d(in_channels, out_channels // 2, 3, 2, 1),
            nn.LeakyReLU(0.2),
            nn.Conv2d(out_channels // 2, out_channels, 3, 2, 1),
            nn.LeakyReLU(0.2))
        self.convblock = nn.ModuleList(
            [ResConvPlain(out_channels) for _ in range(8)])
        self.lastconv = nn.Sequential(
            nn.ConvTranspose2d(out_channels, 52, 4, 2, 1),
            nn.PixelShuffle(2))

    def forward(self, x):
        x = self.conv0(x)
        for module in self.convblock:
            x = module(x)
        return self.lastconv(x)


class EncodeBranch427(nn.Module):
    """Weight-shared per-image encoder (Sequential-wrapped activations)."""

    def __init__(self):
        super(EncodeBranch427, self).__init__()
        self.cnn0 = nn.Sequential(nn.Conv2d(3, 16, 3, 2, 1), nn.LeakyReLU(0.2))
        self.cnn1 = nn.Sequential(nn.Conv2d(16, 16, 3, 1, 1), nn.LeakyReLU(0.2))
        self.cnn2 = nn.Sequential(nn.Conv2d(16, 16, 3, 1, 1), nn.LeakyReLU(0.2))
        self.cnn3 = nn.ConvTranspose2d(16, 4, 4, 2, 1)

    def forward(self, x):
        x = self.cnn0(x)
        x = self.cnn1(x)
        x = self.cnn2(x)
        return self.cnn3(x)


class RIFE427(nn.Module):
    """FluidFrames 2026.3 five-block IFNet.

    The graph pads inputs to 64-pixel multiples internally and crops the
    result back; the timestep enters as a full-resolution map channel.  The
    graph has no scale input, so ``inference`` ignores the engine scale.
    """

    def __init__(self):
        super(RIFE427, self).__init__()
        self.encode = EncodeBranch427()
        self.block0 = IFBlock427(15, 192)
        self.block1 = IFBlock427(28, 128)
        self.block2 = IFBlock427(28, 96)
        self.block3 = IFBlock427(28, 64)
        self.block4 = IFBlock427(28, 32)

    @staticmethod
    def _pad64(img):
        height, width = img.shape[2], img.shape[3]
        pad_h = (height - 1) // 64 * 64 + 64 if height % 64 else height
        pad_w = (width - 1) // 64 * 64 + 64 if width % 64 else width
        if pad_h != height or pad_w != width:
            img = F.pad(img, (0, pad_w - width, 0, pad_h - height))
        return img

    @staticmethod
    def _resize(x, scale):
        if scale == 1.0:
            return x
        return F.interpolate(x, scale_factor=scale, mode="bilinear",
                              align_corners=False)

    def forward(self, img0, img1, timestep):
        height, width = img0.shape[2], img0.shape[3]
        img0 = self._pad64(torch.clamp(img0, 0.0, 1.0))
        img1 = self._pad64(torch.clamp(img1, 0.0, 1.0))
        if not torch.is_tensor(timestep):
            timestep = torch.tensor(float(timestep), dtype=img0.dtype,
                                    device=img0.device)
        tmap = (img0[:, :1] * 0.0 + 1.0) * timestep

        f0 = self.encode(img0)
        f1 = self.encode(img1)

        x = torch.cat([img0, img1, f0, f1, tmap], 1)
        flow = None
        mask = None
        blocks = (self.block0, self.block1, self.block2, self.block3,
                  self.block4)
        for index, block in enumerate(blocks):
            scale = _BLOCK_SCALES_427[index]
            in_scale = _BLOCK_INPUT_SCALES_427[index]
            if index > 0:
                flow_in = self._resize(flow, in_scale) / scale
                y = torch.cat([self._resize(x, in_scale), flow_in], 1)
            else:
                y = self._resize(x, in_scale)
            y = block(y)
            y = self._resize(y, 1.0 / in_scale)
            delta = y[:, 0:4] * scale
            mask = y[:, 4:5]
            feat = y[:, 5:13]
            flow = delta if index == 0 else flow + delta

            wimg0 = warp(img0, flow[:, 0:2])
            wimg1 = warp(img1, flow[:, 2:4])
            wf0 = warp(f0, flow[:, 0:2])
            wf1 = warp(f1, flow[:, 2:4])
            x = torch.cat([wimg0, wimg1, wf0, wf1, tmap, mask, feat], 1)

        wimg0 = warp(img0, flow[:, 0:2])
        wimg1 = warp(img1, flow[:, 2:4])
        merged_mask = torch.sigmoid(mask)
        merged = wimg0 * merged_mask + wimg1 * (1.0 - merged_mask)
        return merged[:, :, :height, :width]

    def inference(self, img0, img1, timestep=0.5, scale=1.0):
        # The FluidFrames graph has no scale input; the argument is accepted
        # for interface compatibility with the other RIFE architectures.
        return self.forward(img0, img1, timestep)


RIFE_TORCH_ARCHITECTURES = {
    "FlownetCas": FlownetCas,
    "FlownetCasLite": FlownetCasLite,
    "Flownet421": Flownet421,
    "Flownet421Lite": Flownet421Lite,
    "Flownet420": Flownet420,
    "RIFE427": RIFE427,
}
