using System.Text.Json;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace LightVideoEnhancerForked_WinUI;

public sealed partial class MainPage
{
    private bool _emaVfiModelAvailable;
    private bool _flashVsrModelAvailable;
    private string? _flashVsrPython;
    private bool _seedVr2ModelAvailable;
    private string? _seedVr2Python;
    private bool _dloralModelAvailable;
    private string? _dloralPython;
    private bool _osdEnhancerModelAvailable;
    private string? _osdEnhancerPython;
    private bool _sparkVsrModelAvailable;
    private string? _sparkVsrPython;
    private bool _vfiMambaModelAvailable;
    private string? _vfiMambaPython;
    private string[] _rifeNcnnModels = Array.Empty<string>();

    private void UpdateExternalEngineAvailability()
    {
        bool scanned = _environmentsJson is not null;
        bool hasTorch = false;
        bool hasCudaTorch = false;
        bool hasNvVfx = false;
        bool hasFlashVsr = false;
        bool hasSeedVr2 = false;
        bool hasDloral = false;
        bool hasOsdEnhancer = false;
        bool hasSparkVsr = false;
        bool hasVfiMamba = false;

        if (scanned)
        {
            try
            {
                using JsonDocument document = JsonDocument.Parse(_environmentsJson!);
                if (document.RootElement.ValueKind != JsonValueKind.Array)
                {
                    scanned = false;
                }
                else
                {
                    foreach (JsonElement environment in document.RootElement.EnumerateArray())
                    {
                        bool torch = BoolProperty(environment, "torch");
                        bool cuda = BoolProperty(environment, "cuda");
                        hasTorch |= torch;
                        hasCudaTorch |= torch && cuda;
                        hasNvVfx |= torch && cuda && BoolProperty(environment, "nvvfx");
                        hasFlashVsr |= torch && cuda && BoolProperty(environment, "flashvsr");
                        hasSeedVr2 |= torch && cuda && BoolProperty(environment, "seedvr2");
                        hasDloral |= torch && cuda && BoolProperty(environment, "dloral");
                        hasOsdEnhancer |= torch && cuda && BoolProperty(environment, "osdenhancer");
                        hasSparkVsr |= torch && cuda && BoolProperty(environment, "sparkvsr");
                        hasVfiMamba |= torch && cuda && BoolProperty(environment, "vfimamba");
                    }
                }
            }
            catch (JsonException)
            {
                scanned = false;
            }
        }

        string notScanned = "Run the manual Python / PyTorch scan from the Settings tab (Processing Backend card) first.";
        SetExternalEngineState(
            SrEngineBox, NvVfxSrItem, scanned && hasNvVfx,
            scanned ? "No scanned environment provides PyTorch, CUDA, and NVIDIA VFX together." : notScanned);
        SetExternalEngineState(
            SrEngineBox, FlashVsrSrItem,
            scanned && hasFlashVsr && _flashVsrModelAvailable,
            scanned ? "Python 3.11 CUDA, Block-Sparse Attention, and the FlashVSR model pack are required."
                : notScanned);
        SetExternalEngineState(
            SrEngineBox, SeedVr2SrItem,
            scanned && hasSeedVr2 && _seedVr2ModelAvailable,
            scanned ? "A compatible CUDA PyTorch environment and the SeedVR2 3B FP8 model pack are required."
                : notScanned);
        SetExternalEngineState(
            SrEngineBox, DloralSrItem,
            scanned && hasDloral && _dloralModelAvailable,
            scanned ? "A compatible CUDA PyTorch environment and the roughly 8.1 GiB DLoRAL core pack are required; native 4x only."
                : notScanned);
        SetExternalEngineState(
            SrEngineBox, OsdEnhancerSrItem,
            scanned && hasOsdEnhancer && _osdEnhancerModelAvailable,
            scanned ? "The roughly 12.0 GiB model pack, a compatible CUDA PyTorch environment, and at least 80 GB VRAM are required; fixed 4x SR and 2x interpolation."
                : notScanned);
        SetExternalEngineState(
            SrEngineBox, SparkVsrSrItem,
            scanned && hasSparkVsr && _sparkVsrModelAvailable,
            scanned ? "The roughly 39.3 GiB model, a compatible CUDA PyTorch environment, and (below 40 GiB VRAM) at least 56 GiB system RAM are required by the safety gate."
                : notScanned);
        SetExternalEngineState(
            FiEngineBox, RifeFiItem, scanned && hasTorch,
            scanned ? "No usable PyTorch environment was found by the scan." : notScanned);
        SetExternalEngineState(
            FiEngineBox, EmaVfiFiItem,
            scanned && hasCudaTorch && _emaVfiModelAvailable,
            scanned ? "A CUDA PyTorch environment and the EMA-VFI Small model pack are required." : notScanned);
        SetExternalEngineState(
            FiEngineBox, VfiMambaFiItem,
            scanned && hasVfiMamba && _vfiMambaModelAvailable,
            scanned ? "A compatible CUDA PyTorch environment, timm/einops, and the VFIMamba model pack are required." : notScanned);
        SetExternalEngineState(
            FiEngineBox, TorchFlowFiItem, scanned && hasCudaTorch,
            scanned ? "No scanned PyTorch environment has CUDA support." : notScanned);
    }

    private void UpdateBuiltInEngineAvailability(JsonElement capabilities)
    {
        _emaVfiModelAvailable = BoolProperty(capabilities, "ema_vfi_model");
        _flashVsrModelAvailable = BoolProperty(capabilities, "flashvsr_model");
        _seedVr2ModelAvailable = BoolProperty(capabilities, "seedvr2_model");
        _dloralModelAvailable = BoolProperty(capabilities, "dloral_model");
        _osdEnhancerModelAvailable = BoolProperty(capabilities, "osdenhancer_model");
        _sparkVsrModelAvailable = BoolProperty(capabilities, "sparkvsr_model");
        _vfiMambaModelAvailable = BoolProperty(capabilities, "vfimamba_model");
        bool ifrnet = BoolProperty(capabilities, "ncnn_ifrnet");
        bool span = BoolProperty(capabilities, "ncnn_span");
        if (capabilities.TryGetProperty("ncnn_rife_models", out JsonElement rifeModels) &&
            rifeModels.ValueKind == JsonValueKind.Array)
        {
            _rifeNcnnModels = rifeModels.EnumerateArray()
                .Where(element => element.ValueKind == JsonValueKind.String)
                .Select(element => element.GetString() ?? string.Empty)
                .Where(token => token.Length > 0)
                .ToArray();
        }
        else
        {
            _rifeNcnnModels = Array.Empty<string>();
        }
        UpdateRifeModelItemStates();
        SetExternalEngineState(
            SrEngineBox, SpanSrItem, span,
            "The SPAN native worker or models are unavailable. Install the SPAN model pack on Models & downloads.");
        SetExternalEngineState(
            FiEngineBox, IfrNetFiItem, ifrnet,
            "The IFRNet native worker or all three model presets are unavailable. Install the IFRNet model pack on Models & downloads.");
        SetExternalEngineState(
            FiEngineBox, RifeNcnnFiItem, BoolProperty(capabilities, "ncnn_rife"),
            "The RIFE ncnn-vulkan runtime or the bundled 4.27 model are unavailable. Reinstall the app.");
        SetExternalEngineState(
            SrEngineBox, RealCuganSrItem, BoolProperty(capabilities, "ncnn_cugan"),
            "The Real-CUGAN ncnn worker or models are unavailable. Install the Real-CUGAN model pack on Models & downloads.");
        SetExternalEngineState(
            SrEngineBox, RealesrganSrItem, BoolProperty(capabilities, "ncnn_esrgan"),
            "The Real-ESRGAN ncnn worker or models are unavailable. Install the Real-ESRGAN model pack on Models & downloads.");
        SetExternalEngineState(
            SrEngineBox, EsrganSrItem, BoolProperty(capabilities, "ncnn_classic_esrgan"),
            "The ESRGAN Classic ncnn worker or models are unavailable. Install the ESRGAN Classic model pack on Models & downloads.");
    }

    private static void SetExternalEngineState(
        ComboBox owner, ComboBoxItem item, bool enabled, string unavailableReason)
    {
        item.IsEnabled = enabled;
        ToolTipService.SetToolTip(item, enabled ? null : unavailableReason);
        if (!enabled && ReferenceEquals(owner.SelectedItem, item))
        {
            // Fall back to the no-op engine, which is always available.
            for (int index = 0; index < owner.Items.Count; index++)
            {
                if (owner.Items[index] is ComboBoxItem fallback &&
                    fallback.Tag?.ToString() == "none")
                {
                    owner.SelectedItem = fallback;
                    break;
                }
            }
        }
    }

    private void ValidateExternalEngineSelection(string srEngine, string fiEngine,
        string? rifeModel = null)
    {
        if (srEngine == "nvvfx" && !NvVfxSrItem.IsEnabled)
        {
            throw new ArgumentException("NVIDIA Video Effects VSR has not been enabled by a manual environment scan.");
        }
        if (srEngine == "flashvsr" && !FlashVsrSrItem.IsEnabled)
        {
            throw new ArgumentException("FlashVSR has not passed the environment and model checks.");
        }
        if (srEngine == "seedvr2" && !SeedVr2SrItem.IsEnabled)
        {
            throw new ArgumentException("SeedVR2 has not passed the environment and model checks.");
        }
        if (srEngine == "dloral" && !DloralSrItem.IsEnabled)
        {
            throw new ArgumentException("DLoRAL has not passed the environment and model checks.");
        }
        if (srEngine == "osdenhancer" && !OsdEnhancerSrItem.IsEnabled)
        {
            throw new ArgumentException("OSDEnhancer has not passed the environment, model, and VRAM checks.");
        }
        if (srEngine == "sparkvsr" && !SparkVsrSrItem.IsEnabled)
        {
            throw new ArgumentException("SparkVSR has not passed the environment, model, and memory-safety checks.");
        }
        if (srEngine == "realcugan" && !RealCuganSrItem.IsEnabled)
        {
            throw new ArgumentException("Real-CUGAN ncnn is unavailable; install its model pack on Models & downloads.");
        }
        if (srEngine == "realesrgan" && !RealesrganSrItem.IsEnabled)
        {
            throw new ArgumentException("Real-ESRGAN ncnn is unavailable; install its model pack on Models & downloads.");
        }
        if (srEngine == "esrgan" && !EsrganSrItem.IsEnabled)
        {
            throw new ArgumentException("ESRGAN Classic ncnn is unavailable; install its model pack on Models & downloads.");
        }
        if (fiEngine == "rife" && !RifeFiItem.IsEnabled)
        {
            throw new ArgumentException("RIFE AI has not been enabled by a manual PyTorch environment scan.");
        }
        if (fiEngine == "ema_vfi" && !EmaVfiFiItem.IsEnabled)
        {
            throw new ArgumentException("EMA-VFI Small has not passed the environment and model checks.");
        }
        if (fiEngine == "rife_ncnn" && !RifeNcnnFiItem.IsEnabled)
        {
            throw new ArgumentException("RIFE ncnn is unavailable; install its model pack on Models & downloads.");
        }
        if (fiEngine == "rife_ncnn" && rifeModel is not null &&
            !_rifeNcnnModels.Contains(rifeModel))
        {
            throw new ArgumentException(
                $"The RIFE ncnn-vulkan model {rifeModel} is not installed. Download the optional model pack on Models & downloads or pick another model.");
        }
        if (fiEngine == "vfimamba" && !VfiMambaFiItem.IsEnabled)
        {
            throw new ArgumentException("VFIMamba has not passed the environment and model checks.");
        }
        if (fiEngine == "torch_flow" && !TorchFlowFiItem.IsEnabled)
        {
            throw new ArgumentException("CUDA optical flow has not been enabled by a manual CUDA PyTorch environment scan.");
        }
    }
}
