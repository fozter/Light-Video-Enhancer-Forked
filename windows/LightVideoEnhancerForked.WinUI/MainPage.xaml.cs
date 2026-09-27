using System.Collections.ObjectModel;
using System.Diagnostics;
using System.Globalization;
using System.Text;
using System.Text.Json;
using LightVideoEnhancerForked_WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Windows.ApplicationModel.DataTransfer;
using Windows.Storage;
using Windows.Storage.Pickers;
using Windows.Globalization.NumberFormatting;
using WinRT.Interop;

namespace LightVideoEnhancerForked_WinUI;

public sealed class ModelPackViewModel
{
    public required string Id { get; init; }
    public required string DisplayName { get; init; }
    public required string Description { get; init; }
    public required string StatusText { get; init; }
    public required string ImportText { get; init; }
    public required string RemoveText { get; init; }
    public required string DownloadText { get; init; }
    public required string RepairText { get; init; }
    public bool CanDownload { get; init; }
    public bool CanRemove { get; init; }
    public bool CanRepair { get; init; }
    public long InstalledBytes { get; init; }
    public long DownloadBytes { get; init; }
}

public sealed partial class MainPage : Page
{
    private readonly BackendProcess _backend = new();
    private readonly StringBuilder _logText = new();
    private string _lastSuggestedOutput = string.Empty;
    private string? _capabilitiesJson;
    private string? _environmentsJson;
    private bool _loaded;
    private readonly ObservableCollection<ModelPackViewModel> _modelPacks = [];
    private bool _modelOperation;
    private double _previousScale = double.NaN;
    private ScrollViewer? _logScroller;

    // Mirrors the backend RIFE ncnn model registry (fi/rife_ncnn.py);
    // newest first, the regular model before its variants.
    private static readonly (string Token, string Display)[] RifeNcnnModels =
    [
        ("4.27_fluidframes", "4.27 (FluidFrames)"),
        ("4.26", "4.26"),
        ("4.26-large", "4.26 Large"),
        ("4.25", "4.25"),
        ("4.25-heavy", "4.25 Heavy"),
        ("4.25-lite", "4.25 Lite"),
        ("4.24", "4.24"),
        ("4.23", "4.23"),
        ("4.22", "4.22"),
        ("4.22-lite", "4.22 Lite"),
        ("4.21", "4.21"),
        ("4.20", "4.20"),
    ];
    private const string DefaultRifeNcnnModel = "4.27_fluidframes";
    private bool _fiQualityShowsModels;
    private int _fiQualityTierIndex = 2;
    private string _rifeModelSelection = DefaultRifeNcnnModel;

    public MainPage()
    {
        InitializeComponent();
        // XBF compiles XAML number literals as float32, which shifts 0.9995/0.2
        // into display artifacts such as 0.999500036 and 0.200000003. Reassign
        // exact doubles and pin a 4-fraction-digit formatter on both SSIM edits
        // so they render as 0,9995 / 0,2000.
        SsimIdenticalBox.Value = 0.9995;
        SsimSceneCutBox.Value = 0.2;
        DecimalFormatter ssimFormatter = new() { FractionDigits = 4 };
        SsimIdenticalBox.NumberFormatter = ssimFormatter;
        SsimSceneCutBox.NumberFormatter = ssimFormatter;
        ModelPacksList.ItemsSource = _modelPacks;
        // Bring-into-view requests raised inside the log (caret moves, text
        // updates) must never drag the page: they escaped the log's inner
        // scroller and pulled the whole Process tab back down to the Task
        // section while log lines streamed, making the page impossible to
        // scroll up during processing. The inner scroller runs before this
        // handler in the bubble chain, so the log still scrolls itself.
        LogBox.BringIntoViewRequested += (_, e) => e.Handled = true;
        _backend.OutputReceived += Backend_OutputReceived;
        _backend.ProgressReceived += Backend_ProgressReceived;
        Loaded += MainPage_Loaded;
        Unloaded += (_, _) => _backend.Dispose();
    }

    private async void MainPage_Loaded(object sender, RoutedEventArgs e)
    {
        if (_loaded)
        {
            return;
        }
        _loaded = true;
        UpdateExternalEngineAvailability();
        RenderBackendPath();
        await RefreshCapabilitiesAsync();
        await ScanEnvironmentsAsync(force: false);
        await RefreshModelsAsync();
    }

    private void MainNavigation_SelectionChanged(NavigationView sender, NavigationViewSelectionChangedEventArgs args)
    {
        string tag = (args.SelectedItem as NavigationViewItem)?.Tag?.ToString() ?? "process";
        ProcessView.Visibility = tag == "process" ? Visibility.Visible : Visibility.Collapsed;
        ModelsView.Visibility = tag == "models" ? Visibility.Visible : Visibility.Collapsed;
        SettingsView.Visibility = tag == "settings" ? Visibility.Visible : Visibility.Collapsed;
        AboutView.Visibility = tag == "about" ? Visibility.Visible : Visibility.Collapsed;
    }

    private async void BrowseInput_Click(object sender, RoutedEventArgs e)
    {
        FileOpenPicker picker = CreateOpenPicker("Choose input video", ".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".ts");
        StorageFile? file = await picker.PickSingleFileAsync();
        if (file is not null)
        {
            InputPathBox.Text = file.Path;
            SuggestOutputPath();
        }
    }

    private async void BrowseOutput_Click(object sender, RoutedEventArgs e)
    {
        string container = SelectedTag(ContainerBox, "mp4");
        string suggestedFileName = string.IsNullOrWhiteSpace(OutputPathBox.Text)
            ? SuggestedStem()
            : Path.GetFileNameWithoutExtension(OutputPathBox.Text);
        FileSavePicker picker = new()
        {
            SuggestedStartLocation = PickerLocationId.VideosLibrary,
            SuggestedFileName = suggestedFileName,
        };
        picker.FileTypeChoices.Add(container.ToUpperInvariant(), ["." + container]);
        InitializeWithWindow.Initialize(picker, MainWindowHandle());
        StorageFile? file = await picker.PickSaveFileAsync();
        if (file is not null)
        {
            OutputPathBox.Text = file.Path;
            // Deliberately NOT updating _lastSuggestedOutput here: an explicit
            // Save-As pick is user-authored output, not a suggestion. Marking
            // it as the tracker made the next suggestion trigger (container
            // change, input change, engine change) regenerate the path and
            // wipe both the picked name and directory.
            RemovePickerPlaceholder(file.Path);
        }
    }

    private static void RemovePickerPlaceholder(string path)
    {
        // The WinRT save picker creates a 0-byte file the moment the user
        // confirms the dialog. That placeholder must not survive: with
        // Overwrite off, the backend would refuse to start ("output already
        // exists"), and no output file may exist before Start. Only a file
        // that is both empty AND freshly created is removed, so a
        // pre-existing 0-byte file the user picked deliberately is left
        // untouched for the overwrite rule.
        try
        {
            var info = new FileInfo(path);
            if (info.Exists && info.Length == 0 &&
                (DateTime.UtcNow - info.CreationTimeUtc) < TimeSpan.FromMinutes(10))
            {
                info.Delete();
            }
        }
        catch (Exception)
        {
            // Best effort: if deletion fails, the backend's overwrite check
            // still guards the Start path.
        }
    }

    private async void BrowseTorchPython_Click(object sender, RoutedEventArgs e)
    {
        FileOpenPicker picker = CreateOpenPicker("Choose python.exe from a PyTorch environment", ".exe");
        StorageFile? file = await picker.PickSingleFileAsync();
        if (file is not null)
        {
            TorchPythonBox.Text = file.Path;
        }
    }

    private async void BrowseSparkReference_Click(object sender, RoutedEventArgs e)
    {
        FolderPicker picker = new()
        {
            SuggestedStartLocation = PickerLocationId.PicturesLibrary,
            ViewMode = PickerViewMode.Thumbnail,
        };
        picker.FileTypeFilter.Add("*");
        InitializeWithWindow.Initialize(picker, MainWindowHandle());
        StorageFolder? folder = await picker.PickSingleFolderAsync();
        if (folder is not null)
        {
            SparkReferencePathBox.Text = folder.Path;
        }
    }

    private void InputCard_DragOver(object sender, DragEventArgs e)
    {
        e.AcceptedOperation = DataPackageOperation.Copy;
        e.DragUIOverride.Caption = "Use this video";
        e.DragUIOverride.IsCaptionVisible = true;
    }

    private async void InputCard_Drop(object sender, DragEventArgs e)
    {
        if (!e.DataView.Contains(StandardDataFormats.StorageItems))
        {
            return;
        }
        IReadOnlyList<IStorageItem> items = await e.DataView.GetStorageItemsAsync();
        StorageFile? file = items.OfType<StorageFile>().FirstOrDefault();
        if (file is not null)
        {
            InputPathBox.Text = file.Path;
            SuggestOutputPath();
        }
    }

    private void InputPathBox_TextChanged(object sender, TextChangedEventArgs e)
    {
        SuggestOutputPath();
    }

    private void QualitySelection_Changed(object sender, SelectionChangedEventArgs e)
    {
        if (SrQualityBox is null || FiQualityBox is null)
        {
            return;
        }
        string sr = SelectedTag(SrEngineBox, "none");
        string fi = SelectedTag(FiEngineBox, "none");
        SrQualityBox.IsEnabled = sr is "nvvfx" or "span" or "flashvsr" or "seedvr2" or "dloral" or "sparkvsr" or "realcugan" or "realesrgan" or "esrgan";
        if (sr is "dloral" or "osdenhancer" or "sparkvsr" && ScaleBox is not null)
        {
            if (ScaleBox.IsEnabled)
            {
                _previousScale = ScaleBox.Value;
            }
            ScaleBox.Value = 4;
            ScaleBox.IsEnabled = false;
        }
        else if (ScaleBox is not null)
        {
            ScaleBox.IsEnabled = true;
            if (!double.IsNaN(_previousScale))
            {
                ScaleBox.Value = _previousScale;
                _previousScale = double.NaN;
            }
        }
        if (SparkReferenceCard is not null)
            SparkReferenceCard.Visibility = sr == "sparkvsr" ? Visibility.Visible : Visibility.Collapsed;
        if (fi == "rife_ncnn")
        {
            // The RIFE ncnn engine selects its model here instead of a
            // quality tier.
            ShowRifeModelChoices();
            FiQualityBox.IsEnabled = true;
        }
        else
        {
            ShowQualityTierChoices();
            FiQualityBox.IsEnabled = fi is "ema_vfi" or "vfimamba" or "dis" or "optical_flow" or "torch_flow";
        }
        SuggestOutputPath();
    }

    private void ShowRifeModelChoices()
    {
        if (!_fiQualityShowsModels)
        {
            _fiQualityTierIndex = Math.Max(FiQualityBox.SelectedIndex, 0);
            _fiQualityShowsModels = true;
            FiQualityBox.Items.Clear();
            foreach ((string token, string display) in RifeNcnnModels)
            {
                FiQualityBox.Items.Add(new ComboBoxItem { Content = display, Tag = token });
            }
            FiQualityBox.Header = "Model";
            ToolTipService.SetToolTip(FiQualityBox,
                "Selects the RIFE ncnn-vulkan model. The optional 4.20-4.26 models install from Models & Downloads.");
        }
        UpdateRifeModelItemStates();
    }

    private void ShowQualityTierChoices()
    {
        if (!_fiQualityShowsModels)
        {
            return;
        }
        _rifeModelSelection = SelectedTag(FiQualityBox, DefaultRifeNcnnModel);
        _fiQualityShowsModels = false;
        FiQualityBox.Items.Clear();
        FiQualityBox.Items.Add(new ComboBoxItem { Content = "Fast", Tag = "fast" });
        FiQualityBox.Items.Add(new ComboBoxItem { Content = "Balanced", Tag = "balanced" });
        FiQualityBox.Items.Add(new ComboBoxItem { Content = "Quality", Tag = "quality" });
        FiQualityBox.Items.Add(new ComboBoxItem { Content = "Ultra", Tag = "ultra" });
        FiQualityBox.Header = "Quality";
        ToolTipService.SetToolTip(FiQualityBox,
            "Optical flow engines support quality tiers; RIFE models use their own fixed parameters.");
        FiQualityBox.SelectedIndex = Math.Clamp(_fiQualityTierIndex, 0, 3);
    }

    private void UpdateRifeModelItemStates()
    {
        if (!_fiQualityShowsModels)
        {
            return;
        }
        if (FiQualityBox.SelectedItem is ComboBoxItem current &&
            current.Tag?.ToString() is string currentToken)
        {
            _rifeModelSelection = currentToken;
        }
        ComboBoxItem? target = null;
        foreach (object? entry in FiQualityBox.Items)
        {
            if (entry is ComboBoxItem item && item.Tag?.ToString() is string token)
            {
                item.IsEnabled = _rifeNcnnModels.Contains(token);
                if (target is null &&
                    string.Equals(token, _rifeModelSelection, StringComparison.Ordinal) &&
                    item.IsEnabled)
                {
                    target = item;
                }
            }
        }
        if (target is not null)
        {
            FiQualityBox.SelectedItem = target;
            return;
        }
        // The remembered model vanished (pack removed): fall back to the
        // first available model; the bundled 4.27 is always among them.
        foreach (object? entry in FiQualityBox.Items)
        {
            if (entry is ComboBoxItem { IsEnabled: true } fallback)
            {
                FiQualityBox.SelectedItem = fallback;
                return;
            }
        }
    }

    private void CodecBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (PresetBox is null || ContainerBox is null || CrfBox is null)
        {
            return;
        }
        string codec = SelectedTag(CodecBox, "auto");
        PresetBox.Text = codec.Contains("nvenc", StringComparison.Ordinal) ? "p5" :
            codec == "auto" ? "balanced" : "medium";

        bool isFFV1 = codec == "ffv1";
        if (isFFV1)
        {
            foreach (var item in ContainerBox.Items)
            {
                if (item is ComboBoxItem cbi && cbi.Tag?.ToString() == "mkv")
                {
                    ContainerBox.SelectedItem = cbi;
                    break;
                }
            }
            EnsureMkvOutputPath();
            ContainerBox.IsEnabled = false;
            PresetBox.IsEnabled = false;
            CrfBox.IsEnabled = false;
        }
        else
        {
            ContainerBox.IsEnabled = true;
            PresetBox.IsEnabled = true;
            CrfBox.IsEnabled = true;
        }
    }

    private void ContainerBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        // Keep the suggested output extension in sync with the selected container,
        // so FFV1 (which must be muxed to MKV) gets a .mkv output path.
        SuggestOutputPath();
    }

    private void EnsureMkvOutputPath()
    {
        // FFV1 can only be muxed to MKV (backend rule), so force the output
        // extension to .mkv even when the user typed the path manually.
        // Only the extension is rewritten - directory and filename are kept.
        if (OutputPathBox is null)
        {
            return;
        }
        string current = OutputPathBox.Text.Trim();
        if (string.IsNullOrEmpty(current))
        {
            SuggestOutputPath(); // container is already MKV; auto-fill the suggestion
            return;
        }
        if (string.Equals(Path.GetExtension(current), ".mkv", StringComparison.OrdinalIgnoreCase))
        {
            return;
        }
        string? directory = Path.GetDirectoryName(current);
        string stem = Path.GetFileNameWithoutExtension(current);
        string next = string.IsNullOrEmpty(directory)
            ? stem + ".mkv"
            : Path.Combine(directory, stem) + ".mkv";
        OutputPathBox.Text = next;
        // Keep the suggestion tracker in sync ONLY when the rewritten path was
        // the app's own suggestion: that is what makes leaving FFV1 later
        // re-suggest the extension with the container. A user-authored path
        // must stay user-authored, or the next suggestion trigger would
        // regenerate its name and directory.
        if (string.Equals(current, _lastSuggestedOutput, StringComparison.OrdinalIgnoreCase))
        {
            _lastSuggestedOutput = next;
        }
    }

    private async void Start_Click(object sender, RoutedEventArgs e)
    {
        if (_backend.IsRunning)
        {
            return;
        }

        // FFV1 can only be muxed to MKV: normalize the output extension one last
        // time so an output edited (e.g. to .mp4) after FFV1 was chosen never
        // trips the backend's container check.
        if (SelectedTag(CodecBox, "auto") == "ffv1")
        {
            EnsureMkvOutputPath();
        }

        IReadOnlyList<string> arguments;
        try
        {
            arguments = BuildArguments();
        }
        catch (Exception exception) when (exception is ArgumentException or IOException)
        {
            ShowInfo("Cannot start processing", exception.Message, InfoBarSeverity.Error);
            return;
        }

        SetProcessingState(true);
        _logText.Clear();
        LogBox.Text = string.Empty;
        TaskProgress.IsIndeterminate = true;
        StatusText.Text = "Initializing processing pipeline…";
        BackendInfoBar.IsOpen = false;

        try
        {
            BackendCommandResult result = await _backend.RunAsync(arguments);
            int exitCode = result.ExitCode;
            if (exitCode == 0)
            {
                TaskProgress.IsIndeterminate = false;
                TaskProgress.Maximum = 100;
                TaskProgress.Value = 100;
                StatusText.Text = "Processing complete";
                OpenOutputButton.IsEnabled = true;
                ShowInfo("Processing complete", OutputPathBox.Text, InfoBarSeverity.Success);
            }
            else if (exitCode == 130)
            {
                TaskProgress.IsIndeterminate = false;
                StatusText.Text = "Cancelled";
                ShowInfo("Task cancelled", "The backend released its resources and removed incomplete output.", InfoBarSeverity.Warning);
            }
            else
            {
                TaskProgress.IsIndeterminate = false;
                StatusText.Text = $"Processing failed (exit code {exitCode})";
                ShowInfo("Processing did not complete", "See the final error in the log below.", InfoBarSeverity.Error);
            }
        }
        catch (Exception exception)
        {
            TaskProgress.IsIndeterminate = false;
            StatusText.Text = "Cannot start or connect to the processing backend";
            AppendLog("[ERROR] " + exception.Message);
            ShowInfo("Backend error", exception.Message, InfoBarSeverity.Error);
        }
        finally
        {
            SetProcessingState(false);
        }
    }

    // Tiny custom steppers for NumberBoxes (built-in compact spin buttons are too large).
    private void NumberSpin_Click(object sender, RoutedEventArgs e)
    {
        if (sender is FrameworkElement fe && fe.Tag is string tag)
        {
            string[] bits = tag.Split(';');
            if (bits.Length < 2 || FindName(bits[0]) is not NumberBox box)
            {
                return;
            }
            double delta = bits[1] == "d" ? -box.SmallChange : box.SmallChange;
            double v = double.IsNaN(box.Value) ? 0 : box.Value + delta;
            if (box.Minimum > double.NegativeInfinity && v < box.Minimum) v = box.Minimum;
            if (box.Maximum < double.PositiveInfinity && v > box.Maximum) v = box.Maximum;
            box.Value = Math.Round(v, 6);
        }
    }

    private async void Cancel_Click(object sender, RoutedEventArgs e)
    {
        CancelButton.IsEnabled = false;
        StatusText.Text = "Stopping safely and finalizing encoded data…";
        await _backend.CancelAsync();
    }

    private void OpenOutput_Click(object sender, RoutedEventArgs e)
    {
        string output = OutputPathBox.Text.Trim();
        if (string.IsNullOrEmpty(output))
        {
            return;
        }
        string directory = Path.GetDirectoryName(output) ?? Environment.CurrentDirectory;
        ProcessStartInfo startInfo = new("explorer.exe") { UseShellExecute = true };
        if (File.Exists(output))
        {
            startInfo.ArgumentList.Add("/select,");
            startInfo.ArgumentList.Add(output);
        }
        else
        {
            startInfo.ArgumentList.Add(directory);
        }
        Process.Start(startInfo);
    }

    private void ModelSourceBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (CustomSourceBox is not null)
        {
            CustomSourceBox.IsEnabled = SelectedTag(ModelSourceBox, "github") == "custom";
        }
    }

    private async void RefreshModels_Click(object sender, RoutedEventArgs e)
    {
        await RefreshModelsAsync();
    }

    private async Task RefreshModelsAsync()
    {
        if (_backend.IsRunning)
        {
            return;
        }
        try
        {
            BackendCommandResult result = await _backend.QueryAsync("--models-json");
            if (result.ExitCode != 0)
            {
                throw new InvalidOperationException(result.StandardError.Trim());
            }
            RenderModels(result.StandardOutput);
        }
        catch (Exception exception)
        {
            ModelStatusText.Text = "Cannot read model status: " + exception.Message;
            ShowModelInfo("Model backend error", exception.Message, InfoBarSeverity.Error);
        }
    }

    private async void DownloadModel_Click(object sender, RoutedEventArgs e)
    {
        if (sender is not Button { Tag: string packId })
        {
            return;
        }
        List<string> arguments =
        [
            "--download-model", packId,
            "--model-source", SelectedTag(ModelSourceBox, "github"),
        ];
        if (SelectedTag(ModelSourceBox, "github") == "custom")
        {
            if (string.IsNullOrWhiteSpace(CustomSourceBox.Text))
            {
                ShowModelInfo("Custom source missing", "Enter a custom base URL or {file} template first.", InfoBarSeverity.Warning);
                return;
            }
            arguments.Add("--source-base");
            arguments.Add(CustomSourceBox.Text.Trim());
        }
        await RunModelCommandAsync(arguments, "Downloading and verifying model…");
    }

    private async void ImportModel_Click(object sender, RoutedEventArgs e)
    {
        if (sender is not Button { Tag: string packId })
        {
            return;
        }
        FileOpenPicker picker = CreateOpenPicker("Choose model ZIP", ".zip");
        StorageFile? file = await picker.PickSingleFileAsync();
        if (file is not null)
        {
            await RunModelCommandAsync(
                ["--install-model-pack", packId, file.Path],
                "Verifying and installing local model pack…");
        }
    }

    private async void RemoveModel_Click(object sender, RoutedEventArgs e)
    {
        if (sender is Button { Tag: string packId })
        {
            ContentDialog confirm = new()
            {
                Title = "Remove downloaded model?",
                Content = $"This deletes the {packId} weight files ({FormatBytes(_modelPacks.FirstOrDefault(p => p.Id == packId)?.InstalledBytes ?? 0)}). You can download them again later.",
                PrimaryButtonText = "Remove",
                CloseButtonText = "Cancel",
                XamlRoot = this.XamlRoot,
            };
            if (await confirm.ShowAsync() != ContentDialogResult.Primary)
            {
                return;
            }
            await RunModelCommandAsync(["--remove-model", packId], "Removing downloaded model…",
                "Model removed", "The model pack was removed. Its entry now shows as not installed.");
        }
    }

    private async void RepairModel_Click(object sender, RoutedEventArgs e)
    {
        if (sender is not Button { Tag: string packId })
        {
            return;
        }
        List<string> arguments =
        [
            "--repair-model", packId,
            "--model-source", SelectedTag(ModelSourceBox, "github"),
        ];
        if (SelectedTag(ModelSourceBox, "github") == "custom")
        {
            if (string.IsNullOrWhiteSpace(CustomSourceBox.Text))
            {
                ShowModelInfo("Custom source missing", "Enter a custom base URL or {file} template first.", InfoBarSeverity.Warning);
                return;
            }
            arguments.Add("--source-base");
            arguments.Add(CustomSourceBox.Text.Trim());
        }
        await RunModelCommandAsync(arguments, "Verifying and repairing model…",
            "Model repaired",
            "Installed files were verified against their pinned SHA-256 and damaged files were re-downloaded. The processing engine can use the pack without restarting.");
    }

    private async Task RunModelCommandAsync(IReadOnlyList<string> arguments, string status,
        string successTitle = "Model ready",
        string successMessage = "Verification completed. The processing engine can use it without restarting.")
    {
        if (_backend.IsRunning)
        {
            ShowModelInfo("Backend busy", "Wait for the current processing or detection task to finish.", InfoBarSeverity.Warning);
            return;
        }
        _modelOperation = true;
        ModelPacksList.IsEnabled = false;
        ModelProgress.IsIndeterminate = true;
        ModelProgress.Value = 0;
        ModelStatusText.Text = status;
        ModelInfoBar.IsOpen = false;
        try
        {
            BackendCommandResult result = await _backend.RunAsync(arguments);
            if (result.ExitCode != 0)
            {
                string detail = string.IsNullOrWhiteSpace(result.StandardError)
                    ? string.Empty
                    : Environment.NewLine + result.StandardError.Trim();
                throw new InvalidOperationException($"Model command failed (exit code {result.ExitCode}).{detail}");
            }
            ShowModelInfo(successTitle, successMessage, InfoBarSeverity.Success);
        }
        catch (Exception exception)
        {
            ShowModelInfo("Model operation failed", exception.Message, InfoBarSeverity.Error);
        }
        finally
        {
            _modelOperation = false;
            ModelProgress.IsIndeterminate = false;
            ModelPacksList.IsEnabled = true;
            await RefreshModelsAsync();
            await RefreshCapabilitiesAsync();
        }
    }

    private void RenderModels(string json)
    {
        using JsonDocument document = JsonDocument.Parse(json);
        JsonElement root = document.RootElement;
        if (!root.TryGetProperty("protocol_version", out JsonElement modelProtocol) ||
            modelProtocol.GetInt32() != 1)
        {
            throw new InvalidOperationException("The model protocol version is incompatible.");
        }
        _modelPacks.Clear();
        if (root.TryGetProperty("model_root", out JsonElement modelRoot))
        {
            ModelRootText.Text = "Model directory: " + modelRoot.GetString();
        }
        int installedCount = 0;
        foreach (JsonElement pack in root.GetProperty("packs").EnumerateArray())
        {
            string status = StringProperty(pack, "status", "missing");
            long installedSize = Int64Property(pack, "installed_size");
            long downloadSize = Int64Property(pack, "download_size");
            JsonElement names = pack.GetProperty("name");
            JsonElement descriptions = pack.GetProperty("description");
            string statusText = status switch
            {
                "bundled" => "Included" + " · " + FormatBytes(installedSize),
                "downloaded" => "Downloaded" + " · " + FormatBytes(installedSize),
                "partial" => "Incomplete; download again",
                _ => "Not installed" + " · " + FormatBytes(downloadSize),
            };
            bool installed = status is "bundled" or "downloaded";
            if (installed)
            {
                installedCount++;
            }
            _modelPacks.Add(new ModelPackViewModel
            {
                Id = StringProperty(pack, "id", ""),
                DisplayName = PackText(names, "?"),
                Description = PackText(descriptions, ""),
                StatusText = statusText,
                ImportText = "Import ZIP",
                RemoveText = "Remove",
                // Installed packs keep a disabled button, but it reads as
                // state ("Installed") instead of a dead action ("Download").
                DownloadText = installed ? "Installed" : "Download",
                // Repair = verify the per-user files against their pinned
                // SHA-256 and re-fetch only the damaged ones. Download skips
                // existing files on presence alone, so it cannot fix a
                // byte-corrupted weight. Bundled (in-package) bytes cannot
                // be repaired per-file; Import ZIP covers that case.
                RepairText = "Repair",
                CanDownload = !installed,
                CanRemove = status is "downloaded" or "partial",
                CanRepair = status is "downloaded" or "partial",
                InstalledBytes = installedSize,
                DownloadBytes = downloadSize,
            });
        }
        ModelStatusText.Text = $"{installedCount} of {_modelPacks.Count} model packs installed";
        // Re-seat the items source so every row container regenerates from
        // the new view models. Clear()+Add() alone can leave recycled
        // containers showing a previous pass's row text in the same session
        // (observed: header/buttons said downloaded while the status text
        // still read "Not installed").
        ModelPacksList.ItemsSource = null;
        ModelPacksList.ItemsSource = _modelPacks;
    }

    private static string FormatBytes(long value)
    {
        if (value <= 0)
        {
            return "—";
        }
        return value >= 1073741824
            ? $"{value / 1073741824.0:F1} GiB"
            : $"{value / 1048576.0:F1} MiB";
    }

    private void ShowModelInfo(string title, string message, InfoBarSeverity severity)
    {
        title = title.Trim();
        message = message.Trim();
        if (title.Length == 0 && message.Length == 0)
        {
            HideModelInfo();
            return;
        }
        ModelInfoBar.Title = title;
        ModelInfoBar.Message = message;
        ModelInfoBar.Severity = severity;
        ModelInfoBar.Visibility = Visibility.Visible;
        ModelInfoBar.IsOpen = true;
    }

    private void HideModelInfo()
    {
        ModelInfoBar.IsOpen = false;
        ModelInfoBar.Visibility = Visibility.Collapsed;
        ModelInfoBar.Title = string.Empty;
        ModelInfoBar.Message = string.Empty;
    }

    private void ModelInfoBar_Closed(InfoBar sender, InfoBarClosedEventArgs args)
    {
        ModelInfoBar.Visibility = Visibility.Collapsed;
    }

    private async void RefreshCapabilities_Click(object sender, RoutedEventArgs e)
    {
        await RefreshCapabilitiesAsync();
    }

    private async Task RefreshCapabilitiesAsync()
    {
        if (_backend.IsRunning)
        {
            ShowInfo("Backend busy", "Wait for the current task before refreshing capabilities.", InfoBarSeverity.Informational);
            return;
        }

        BackendBadgeText.Text = "Detecting";
        try
        {
            BackendCommandResult result = await _backend.QueryAsync("--capabilities-json");
            if (result.ExitCode != 0)
            {
                throw new InvalidOperationException(result.StandardError.Trim());
            }
            _capabilitiesJson = result.StandardOutput;
            RenderCapabilities(_capabilitiesJson);
            BackendBadgeText.Text = "Backend ready";
            HideInfo();
        }
        catch (Exception exception)
        {
            BackendBadgeText.Text = "Backend unavailable";
            CapabilitiesBox.Text = exception.Message;
            ShowInfo("Cannot connect to processing backend", exception.Message, InfoBarSeverity.Error);
        }
    }

    private async void ScanEnvironments_Click(object sender, RoutedEventArgs e)
    {
        if (_backend.IsRunning)
        {
            ShowInfo("Backend busy", "Wait for the current task before scanning environments.", InfoBarSeverity.Informational);
            return;
        }
        ScanEnvironmentsButton.IsEnabled = false;
        try
        {
            EnvironmentResultsBox.Text = "Scanning Python, Conda, uv, pyenv, and virtual environments in parallel…";
            await ScanEnvironmentsAsync(force: true);
        }
        finally
        {
            ScanEnvironmentsButton.IsEnabled = true;
        }
    }

    private async Task ScanEnvironmentsAsync(bool force)
    {
        if (_backend.IsRunning)
        {
            return;
        }
        // Remember the chosen engines: the availability refresh below resets
        // disabled selections to None, and a rescan must not silently discard
        // an engine the new results still support.
        string keptSr = SelectedTag(SrEngineBox, "none");
        string keptFi = SelectedTag(FiEngineBox, "none");
        _environmentsJson = null;
        UpdateExternalEngineAvailability();
        if (!string.IsNullOrWhiteSpace(_capabilitiesJson))
        {
            RenderCapabilities(_capabilitiesJson);
        }
        try
        {
            // The backend persists scan results in %LOCALAPPDATA%\LightVideoEnhancerForked\
            // environment-cache.json (24 h TTL, entries re-validated against the real
            // executables). force=false loads that cache, so a fresh GUI launch shows
            // the environment results without re-probing every interpreter; the Scan
            // button stays as the explicit force-rescan escape hatch.
            BackendCommandResult result = force
                ? await _backend.QueryAsync("--environments-json", "--force")
                : await _backend.QueryAsync("--environments-json");
            if (result.ExitCode != 0)
            {
                throw new InvalidOperationException(result.StandardError.Trim());
            }
            _environmentsJson = result.StandardOutput;
            RenderEnvironments(_environmentsJson);
            if (!string.IsNullOrWhiteSpace(_capabilitiesJson))
            {
                RenderCapabilities(_capabilitiesJson);
            }
            SelectTagItem(SrEngineBox, keptSr);
            SelectTagItem(FiEngineBox, keptFi);
        }
        catch (Exception exception)
        {
            EnvironmentResultsBox.Text = "Scan failed: " + exception.Message;
        }
    }

    private static void SelectTagItem(ComboBox owner, string tag)
    {
        // Re-select a previously chosen engine only when it is still enabled;
        // otherwise leave the Auto fallback that the availability refresh set.
        foreach (var item in owner.Items)
        {
            if (item is ComboBoxItem cbi &&
                string.Equals(cbi.Tag?.ToString(), tag, StringComparison.Ordinal) &&
                cbi.IsEnabled)
            {
                owner.SelectedItem = cbi;
                return;
            }
        }
    }

    private void ThemeBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (ThemeBox?.SelectedItem is not ComboBoxItem item)
        {
            return;
        }
        ElementTheme theme = item.Tag?.ToString() switch
        {
            "light" => ElementTheme.Light,
            "dark" => ElementTheme.Dark,
            _ => ElementTheme.Default,
        };
        if (Application.Current is App app && app.MainWindow is MainWindow window)
        {
            window.ApplyTheme(theme);
        }
        else
        {
            RequestedTheme = theme;
        }
    }

    private IReadOnlyList<string> BuildArguments()
    {
        string input = InputPathBox.Text.Trim();
        if (!File.Exists(input))
        {
            throw new ArgumentException("Choose a valid input video.");
        }

        string output = OutputPathBox.Text.Trim();
        if (string.IsNullOrEmpty(output))
        {
            throw new ArgumentException("Choose an output file (use Save As... or enter a path manually).");
        }
        if (string.Equals(
                Path.GetFullPath(input),
                Path.GetFullPath(output),
                StringComparison.OrdinalIgnoreCase))
        {
            throw new ArgumentException("The output file must be different from the input video.");
        }
        if (double.IsNaN(ScaleBox.Value) || double.IsInfinity(ScaleBox.Value))
        {
            throw new ArgumentException("Super-resolution scale must be numeric.");
        }
        if (double.IsNaN(CrfBox.Value) || double.IsInfinity(CrfBox.Value))
        {
            throw new ArgumentException("CQ / CRF must be numeric.");
        }
        if (double.IsNaN(SsimIdenticalBox.Value) || double.IsInfinity(SsimIdenticalBox.Value) ||
            double.IsNaN(SsimSceneCutBox.Value) || double.IsInfinity(SsimSceneCutBox.Value))
        {
            throw new ArgumentException("SSIM thresholds must be numeric.");
        }

        string srEngine = SelectedTag(SrEngineBox, "none");
        string fiEngine = SelectedTag(FiEngineBox, "none");
        ValidateExternalEngineSelection(
            srEngine, fiEngine,
            fiEngine == "rife_ncnn"
                ? SelectedTag(FiQualityBox, DefaultRifeNcnnModel) : null);
        if (srEngine == "osdenhancer" && fiEngine is not "none")
        {
            throw new ArgumentException("OSDEnhancer already includes 2x interpolation; set the separate interpolation engine to None.");
        }
        if ((srEngine == "span" || fiEngine == "ifrnet_ncnn") && SelectedTag(NcnnGpuBox, "auto") == "cpu")
        {
            throw new ArgumentException("SPAN and IFRNet require a Vulkan GPU; set NCNN Device to Auto or a GPU index.");
        }

        List<string> values =
        [
            "--progress-json", "--control-stdin", input,
            "-o", output,
            "--scale", Numeric(ScaleBox.Value),
            "--sr-engine", srEngine,
            "--fi-engine", fiEngine,
            "--sr-quality", SelectedTag(SrQualityBox, "quality"),
            "--codec", SelectedTag(CodecBox, "auto"),
            "--preset", string.IsNullOrWhiteSpace(PresetBox.Text) ? "balanced" : PresetBox.Text.Trim(),
            "--crf", Math.Round(CrfBox.Value).ToString(CultureInfo.InvariantCulture),
            "--container", SelectedTag(ContainerBox, "mp4"),
            "--ncnn-gpu", SelectedTag(NcnnGpuBox, "auto"),
            "--ssim-identical", SsimIdenticalBox.Value.ToString("0.0000", CultureInfo.InvariantCulture),
            "--ssim-scene-cut", SsimSceneCutBox.Value.ToString("0.0000", CultureInfo.InvariantCulture),
        ];

        // The rate selector carries either a multiplier of the source rate
        // or an exact target frame rate.
        string rateChoice = SelectedTag(FiRateBox, "mult:2");
        if (rateChoice.StartsWith("mult:", StringComparison.Ordinal))
        {
            values.AddRange(new[]
            {
                "--fi-multiplier", rateChoice["mult:".Length..],
            });
        }
        else
        {
            values.AddRange(new[]
            {
                "--fps", rateChoice,
            });
        }

        // The RIFE ncnn engine picks a model instead of a quality tier.
        if (fiEngine == "rife_ncnn")
        {
            values.AddRange(new[]
            {
                "--fi-model", SelectedTag(FiQualityBox, DefaultRifeNcnnModel),
            });
        }
        else
        {
            values.AddRange(new[]
            {
                "--fi-quality", SelectedTag(FiQualityBox, "quality"),
            });
        }

        // FFV1 is encoded by the bundled FFmpeg runtime, which requires the
        // MKV container; the GUI forces that above.

        AddOptionalNumber(values, "--start", StartTimeBox.Text, "Start time");
        AddOptionalNumber(values, "--duration", DurationBox.Text, "Duration");
        string requestedPython = srEngine switch
        {
            "flashvsr" when !string.IsNullOrWhiteSpace(_flashVsrPython) => _flashVsrPython!,
            "seedvr2" when !string.IsNullOrWhiteSpace(_seedVr2Python) => _seedVr2Python!,
            "dloral" when !string.IsNullOrWhiteSpace(_dloralPython) => _dloralPython!,
            "osdenhancer" when !string.IsNullOrWhiteSpace(_osdEnhancerPython) => _osdEnhancerPython!,
            "sparkvsr" when !string.IsNullOrWhiteSpace(_sparkVsrPython) => _sparkVsrPython!,
            _ => TorchPythonBox.Text.Trim(),
        };
        if (fiEngine == "vfimamba" && !string.IsNullOrWhiteSpace(_vfiMambaPython))
            requestedPython = _vfiMambaPython!;
        if (srEngine == "sparkvsr")
        {
            string referencePath = SparkReferencePathBox.Text.Trim();
            string referenceIndices = SparkReferenceIndicesBox.Text.Trim();
            if (string.IsNullOrWhiteSpace(referencePath) != string.IsNullOrWhiteSpace(referenceIndices))
                throw new ArgumentException("Reference path and source-frame indices must both be set or both be blank.");
            if (!string.IsNullOrWhiteSpace(referencePath))
                values.AddRange(["--spark-reference", referencePath, "--spark-reference-indices", referenceIndices]);
            values.AddRange(["--spark-reference-guidance", Numeric(SparkReferenceGuidanceBox.Value)]);
        }
        if (!string.IsNullOrWhiteSpace(requestedPython))
        {
            string python = requestedPython;
            if (!File.Exists(python))
            {
                throw new ArgumentException("The selected PyTorch Python does not exist.");
            }
            values.Add("--torch-python");
            values.Add(python);
        }
        if (SrFirstCheck.IsChecked == true)
        {
            values.Add("--sr-first");
        }
        if (CopyAudioCheck.IsChecked != true)
        {
            values.Add("--no-audio");
        }
        if (OverwriteCheck.IsChecked == true)
        {
            values.Add("--overwrite");
        }
        return values;
    }

    private void AddOptionalNumber(List<string> values, string option, string text, string label)
    {
        if (string.IsNullOrWhiteSpace(text))
        {
            return;
        }
        if (!double.TryParse(text, NumberStyles.Float, CultureInfo.CurrentCulture, out double parsed) &&
            !double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out parsed))
        {
            throw new ArgumentException(label + " must be numeric.");
        }
        values.Add(option);
        values.Add(parsed.ToString(CultureInfo.InvariantCulture));
    }

    private void RenderCapabilities(string json)
    {
        using JsonDocument document = JsonDocument.Parse(json);
        JsonElement root = document.RootElement;
        if (!root.TryGetProperty("protocol_version", out JsonElement protocol) ||
            protocol.GetInt32() != 1)
        {
            throw new InvalidOperationException("The backend protocol version is incompatible.");
        }
        StringBuilder text = new();
        text.AppendLine("GPU");
        string selectedNcnnGpu = SelectedTag(NcnnGpuBox, "auto");
        NcnnGpuBox.Items.Clear();
        NcnnGpuBox.Items.Add(new ComboBoxItem { Content = "Auto", Tag = "auto" });
        NcnnGpuBox.Items.Add(new ComboBoxItem { Content = "CPU", Tag = "cpu" });
        if (root.TryGetProperty("gpus", out JsonElement gpus) && gpus.GetArrayLength() > 0)
        {
            int index = 0;
            foreach (JsonElement gpu in gpus.EnumerateArray())
            {
                string name = StringProperty(gpu, "name", "Unknown GPU");
                string vendor = StringProperty(gpu, "vendor", "unknown").ToUpperInvariant();
                text.AppendLine($"  GPU {index}: {name} [{vendor}]");
                NcnnGpuBox.Items.Add(new ComboBoxItem { Content = $"GPU {index} · {name}", Tag = index.ToString() });
                index++;
            }
        }
        else
        {
            text.AppendLine("  No active display device detected");
        }
        NcnnGpuBox.SelectedIndex = 0;
        for (int index = 0; index < NcnnGpuBox.Items.Count; index++)
        {
            if (NcnnGpuBox.Items[index] is ComboBoxItem item &&
                string.Equals(item.Tag?.ToString(), selectedNcnnGpu, StringComparison.Ordinal))
            {
                NcnnGpuBox.SelectedIndex = index;
                break;
            }
        }

        text.AppendLine();
        text.AppendLine("Processing components");
        AppendCapability(text, root, "worker", "FFmpeg Worker");
        AppendCapability(text, root, "vsr_dll", "D3D11 VSR Bridge");
        AppendCapability(text, root, "rife_model", "RIFE PyTorch model");
        AppendCapability(text, root, "ncnn_rife", "RIFE ncnn-vulkan");
        if (root.TryGetProperty("ncnn_rife_models", out JsonElement rifeModels) &&
            rifeModels.ValueKind == JsonValueKind.Array)
        {
            string models = string.Join(", ", rifeModels.EnumerateArray()
                .Where(element => element.ValueKind == JsonValueKind.String)
                .Select(element => element.GetString() ?? string.Empty)
                .Where(token => token.Length > 0));
            if (models.Length > 0)
            {
                text.AppendLine($"  RIFE ncnn-vulkan models: {models}");
            }
        }
        AppendCapability(text, root, "ema_vfi_model", "EMA-VFI Small model");
        AppendCapability(text, root, "flashvsr_model", "FlashVSR v1.1 model");
        AppendCapability(text, root, "seedvr2_model", "SeedVR2 3B FP8 model");
        AppendCapability(text, root, "dloral_model", "DLoRAL core model");
        AppendCapability(text, root, "osdenhancer_model", "OSDEnhancer v1.0 model");
        AppendCapability(text, root, "sparkvsr_model", "SparkVSR Stage-2 model");
        AppendCapability(text, root, "vfimamba_model", "VFIMamba S / Full models");
        AppendCapability(text, root, "ncnn_ifrnet", "IFRNet ncnn-vulkan");
        AppendCapability(text, root, "ncnn_span", "SPAN ncnn-vulkan");
        AppendCapability(text, root, "ncnn_cugan", "Real-CUGAN ncnn");
        AppendCapability(text, root, "ncnn_esrgan", "Real-ESRGAN ncnn");
        AppendCapability(text, root, "ncnn_classic_esrgan", "Classic ESRGAN model");

        AppendExternalEnvironmentCapabilities(text);

        text.AppendLine();
        text.AppendLine("Available encoders");
        if (root.TryGetProperty("encoders", out JsonElement encoders))
        {
            foreach (JsonElement encoder in encoders.EnumerateArray())
            {
                text.AppendLine("  " + encoder.GetString());
            }
        }
        CapabilitiesBox.Text = text.ToString().TrimEnd();
        UpdateBuiltInEngineAvailability(root);
        UpdateExternalEngineAvailability();
        // Show the WinUI (frontend) version and the backend's reported version, each on its own line.
        string frontendVersion = typeof(MainPage).Assembly.GetName().Version?.ToString(3) ?? "0.0.0";
        VersionText.Text = root.TryGetProperty("version", out JsonElement version)
            ? "WinUI 3: " + frontendVersion + "\nBackend: " + version.GetString()
            : "WinUI 3: " + frontendVersion;
    }

    private void RenderEnvironments(string json)
    {
        using JsonDocument document = JsonDocument.Parse(json);
        StringBuilder text = new();
        int index = 0;
        string? recommended = null;
        _flashVsrPython = null;
        _seedVr2Python = null;
        _dloralPython = null;
        _osdEnhancerPython = null;
        _sparkVsrPython = null;
        _vfiMambaPython = null;
        foreach (JsonElement environment in document.RootElement.EnumerateArray())
        {
            index++;
            string exe = StringProperty(environment, "exe", "?");
            string python = StringProperty(environment, "version", "?");
            bool torch = BoolProperty(environment, "torch");
            bool cuda = BoolProperty(environment, "cuda");
            bool nvvfx = BoolProperty(environment, "nvvfx");
            bool flashvsr = BoolProperty(environment, "flashvsr");
            bool seedvr2 = BoolProperty(environment, "seedvr2");
            bool dloral = BoolProperty(environment, "dloral");
            bool osdenhancer = BoolProperty(environment, "osdenhancer");
            bool sparkvsr = BoolProperty(environment, "sparkvsr");
            bool vfimamba = BoolProperty(environment, "vfimamba");
            string torchVersion = StringProperty(environment, "torch_version", "-");
            string gpu = StringProperty(environment, "gpu_name", "-");
            text.AppendLine($"[{index}] {exe}");
            text.AppendLine($"    Python {python} | PyTorch {(torch ? torchVersion : "--")} | CUDA {(cuda ? "OK" : "--")} | NV-VFX {(nvvfx ? "OK" : "--")} | FlashVSR {(flashvsr ? "OK" : "--")} | SeedVR2 {(seedvr2 ? "OK" : "--")} | DLoRAL {(dloral ? "OK" : "--")} | VFIMamba {(vfimamba ? "OK" : "--")}");
            if (flashvsr)
            {
                _flashVsrPython ??= exe;
            }
            if (seedvr2)
            {
                _seedVr2Python ??= exe;
            }
            if (dloral)
            {
                _dloralPython ??= exe;
            }
            if (osdenhancer)
            {
                _osdEnhancerPython ??= exe;
            }
            if (sparkvsr)
            {
                _sparkVsrPython ??= exe;
            }
            if (vfimamba)
            {
                _vfiMambaPython ??= exe;
            }
            if (cuda)
            {
                text.AppendLine($"    GPU: {gpu}");
                recommended ??= exe;
            }
            else if (torch)
            {
                recommended ??= exe;
            }
            if (environment.TryGetProperty("error", out JsonElement error) && !string.IsNullOrWhiteSpace(error.GetString()))
            {
                text.AppendLine("    Error: " + error.GetString());
            }
            text.AppendLine();
        }
        EnvironmentResultsBox.Text = index == 0 ? "No usable Python environment found." : text.ToString().TrimEnd();
        if (recommended is not null && string.IsNullOrWhiteSpace(TorchPythonBox.Text))
        {
            TorchPythonBox.Text = recommended;
        }
        UpdateExternalEngineAvailability();
    }

    private void AppendExternalEnvironmentCapabilities(StringBuilder text)
    {
        text.AppendLine();
        text.AppendLine("External Python capabilities");
        if (string.IsNullOrWhiteSpace(_environmentsJson))
        {
            text.AppendLine("  — Not scanned; use the button above to detect PyTorch, CUDA, and NV-VFX.");
            return;
        }

        using JsonDocument document = JsonDocument.Parse(_environmentsJson);
        int environments = 0;
        int torch = 0;
        int cuda = 0;
        int nvvfx = 0;
        int flashvsr = 0;
        int seedvr2 = 0;
        int dloral = 0;
        int osdenhancer = 0;
        int sparkvsr = 0;
        int vfimamba = 0;
        foreach (JsonElement environment in document.RootElement.EnumerateArray())
        {
            environments++;
            torch += BoolProperty(environment, "torch") ? 1 : 0;
            cuda += BoolProperty(environment, "cuda") ? 1 : 0;
            nvvfx += BoolProperty(environment, "nvvfx") ? 1 : 0;
            flashvsr += BoolProperty(environment, "flashvsr") ? 1 : 0;
            seedvr2 += BoolProperty(environment, "seedvr2") ? 1 : 0;
            dloral += BoolProperty(environment, "dloral") ? 1 : 0;
            osdenhancer += BoolProperty(environment, "osdenhancer") ? 1 : 0;
            sparkvsr += BoolProperty(environment, "sparkvsr") ? 1 : 0;
            vfimamba += BoolProperty(environment, "vfimamba") ? 1 : 0;
        }
        text.AppendLine($"  {(torch > 0 ? "✓" : "—")} PyTorch ({torch}/{environments})");
        text.AppendLine($"  {(cuda > 0 ? "✓" : "—")} CUDA ({cuda}/{environments})");
        text.AppendLine($"  {(nvvfx > 0 ? "✓" : "—")} NVIDIA VFX ({nvvfx}/{environments})");
        text.AppendLine($"  {(flashvsr > 0 ? "✓" : "—")} FlashVSR ({flashvsr}/{environments})");
        text.AppendLine($"  {(seedvr2 > 0 ? "✓" : "—")} SeedVR2 ({seedvr2}/{environments})");
        text.AppendLine($"  {(dloral > 0 ? "✓" : "—")} DLoRAL ({dloral}/{environments})");
        text.AppendLine($"  {(osdenhancer > 0 ? "✓" : "—")} OSDEnhancer ({osdenhancer}/{environments})");
        text.AppendLine($"  {(sparkvsr > 0 ? "✓" : "—")} SparkVSR ({sparkvsr}/{environments})");
        text.AppendLine($"  {(vfimamba > 0 ? "✓" : "—")} VFIMamba ({vfimamba}/{environments})");
    }

    private static void AppendCapability(StringBuilder text, JsonElement root, string property, string label)
    {
        text.AppendLine($"  {(BoolProperty(root, property) ? "✓" : "—")} {label}");
    }

    private void Backend_OutputReceived(string line)
    {
        DispatcherQueue.TryEnqueue(() => AppendLog(line));
    }

    private void Backend_ProgressReceived(BackendProgress progress)
    {
        DispatcherQueue.TryEnqueue(() =>
        {
            if (_modelOperation)
            {
                ModelProgress.IsIndeterminate = progress.Total <= 0;
                if (progress.Total > 0)
                {
                    ModelProgress.Maximum = progress.Total;
                    ModelProgress.Value = Math.Clamp(progress.Current, 0, progress.Total);
                    double modelPercent = 100.0 * progress.Current / progress.Total;
                    ModelStatusText.Text = $"{progress.Stage}: {modelPercent:F1}%";
                }
                else
                {
                    ModelStatusText.Text = progress.Stage;
                }
                return;
            }
            TaskProgress.IsIndeterminate = progress.Total <= 0;
            if (progress.Total > 0)
            {
                TaskProgress.Maximum = progress.Total;
                TaskProgress.Value = Math.Clamp(progress.Current, 0, progress.Total);
                double percent = 100.0 * progress.Current / progress.Total;
                StatusText.Text = $"{progress.Stage}: {progress.Current} / {progress.Total} ({percent:F1}%)";
            }
            else
            {
                StatusText.Text = progress.Stage;
            }
        });
    }

    private static ScrollViewer? FindScrollViewer(DependencyObject root)
    {
        int count = VisualTreeHelper.GetChildrenCount(root);
        for (int index = 0; index < count; index++)
        {
            DependencyObject child = VisualTreeHelper.GetChild(root, index);
            if (child is ScrollViewer scroller)
            {
                return scroller;
            }
            ScrollViewer? descendant = FindScrollViewer(child);
            if (descendant is not null)
            {
                return descendant;
            }
        }
        return null;
    }

    private void AppendLog(string line)
    {
        // Capture the log's scroll position BEFORE the text grows. New lines
        // must not yank a reader who scrolled up back to the bottom, and no
        // caret/bring-into-view side effect may ever scroll the page. Explicit
        // ChangeView calls on the log's inner scroller have no such side
        // effects (the old SelectionStart=Length moved the caret every line,
        // and its bring-into-view request dragged the whole Process tab back
        // to the Task section, observed live within 1.5 s of scrolling up).
        ScrollViewer? scroller = _logScroller ??= FindScrollViewer(LogBox);
        bool atBottom = scroller is null ||
                        scroller.VerticalOffset >= scroller.ScrollableHeight - 2;
        double previousOffset = scroller?.VerticalOffset ?? 0;

        _logText.AppendLine(line);
        if (_logText.Length > 160_000)
        {
            int boundary = _logText.ToString().IndexOf('\n', 20_000);
            _logText.Remove(0, boundary > 0 ? boundary + 1 : 20_000);
        }
        LogBox.Text = _logText.ToString();
        if (scroller is not null)
        {
            if (atBottom)
            {
                scroller.ChangeView(null, scroller.ScrollableHeight, null, disableAnimation: true);
            }
            else
            {
                scroller.ChangeView(null, previousOffset, null, disableAnimation: true);
            }
        }
    }

    private void SetProcessingState(bool running)
    {
        StartButton.IsEnabled = !running;
        CancelButton.IsEnabled = running;
        ScanEnvironmentsButton.IsEnabled = !running;
        if (running)
        {
            // A new run invalidates the previous result; re-arm on success only.
            OpenOutputButton.IsEnabled = false;
        }
    }

    private void SuggestOutputPath()
    {
        if (InputPathBox is null || OutputPathBox is null || ContainerBox is null)
        {
            return;
        }
        string input = InputPathBox.Text.Trim();
        if (string.IsNullOrEmpty(input))
        {
            return;
        }
        if (!string.IsNullOrWhiteSpace(OutputPathBox.Text) &&
            !string.Equals(OutputPathBox.Text, _lastSuggestedOutput, StringComparison.OrdinalIgnoreCase))
        {
            return;
        }
        string directory = Path.GetDirectoryName(input) ?? Environment.CurrentDirectory;
        string suggested = Path.Combine(directory, SuggestedStem() + "." + SelectedTag(ContainerBox, "mp4"));
        _lastSuggestedOutput = suggested;
        OutputPathBox.Text = suggested;
    }

    private string SuggestedStem()
    {
        string? stem = Path.GetFileNameWithoutExtension(InputPathBox?.Text.Trim());
        if (string.IsNullOrWhiteSpace(stem))
        {
            stem = "enhanced";
        }
        List<string> tags = [];
        if (SrEngineBox is not null && SelectedTag(SrEngineBox, "none") != "none" && ScaleBox is not null && !double.IsNaN(ScaleBox.Value) && ScaleBox.Value != 1)
        {
            tags.Add("x" + Numeric(ScaleBox.Value));
        }
        if (FiEngineBox is not null && SelectedTag(FiEngineBox, "none") != "none" && FiRateBox is not null)
        {
            string rateChoice = SelectedTag(FiRateBox, "mult:2");
            if (rateChoice.StartsWith("mult:", StringComparison.Ordinal))
            {
                tags.Add("f" + rateChoice["mult:".Length..]);
            }
            else
            {
                tags.Add("fps" + RateTagLabel(rateChoice));
            }
        }
        return stem + (tags.Count > 0 ? "_" + string.Join("_", tags) : "_enhanced");
    }

    private static string RateTagLabel(string tag)
    {
        // Exact ratios such as 24000/1001 cannot appear in a file name.
        if (tag.Contains('/'))
        {
            string[] parts = tag.Split('/');
            if (parts.Length == 2 &&
                double.TryParse(parts[0], NumberStyles.Float, CultureInfo.InvariantCulture, out double numerator) &&
                double.TryParse(parts[1], NumberStyles.Float, CultureInfo.InvariantCulture, out double denominator) &&
                denominator != 0)
            {
                return (numerator / denominator).ToString("0.###", CultureInfo.InvariantCulture);
            }
        }
        return tag;
    }

    private FileOpenPicker CreateOpenPicker(string title, params string[] extensions)
    {
        FileOpenPicker picker = new()
        {
            ViewMode = PickerViewMode.Thumbnail,
            SuggestedStartLocation = PickerLocationId.VideosLibrary,
            CommitButtonText = title,
        };
        foreach (string extension in extensions)
        {
            picker.FileTypeFilter.Add(extension);
        }
        InitializeWithWindow.Initialize(picker, MainWindowHandle());
        return picker;
    }

    private nint MainWindowHandle()
    {
        if (Application.Current is not App app || app.MainWindow is null)
        {
            throw new InvalidOperationException("The main window is not initialized.");
        }
        return WindowNative.GetWindowHandle(app.MainWindow);
    }

    private void ShowInfo(string title, string message, InfoBarSeverity severity)
    {
        title = title.Trim();
        message = message.Trim();
        if (title.Length == 0 && message.Length == 0)
        {
            HideInfo();
            return;
        }
        BackendInfoBar.Title = title;
        BackendInfoBar.Message = message;
        BackendInfoBar.Severity = severity;
        BackendInfoBar.Visibility = Visibility.Visible;
        BackendInfoBar.IsOpen = true;
    }

    private void HideInfo()
    {
        BackendInfoBar.IsOpen = false;
        BackendInfoBar.Visibility = Visibility.Collapsed;
        BackendInfoBar.Title = string.Empty;
        BackendInfoBar.Message = string.Empty;
    }

    private void BackendInfoBar_Closed(InfoBar sender, InfoBarClosedEventArgs args)
    {
        BackendInfoBar.Visibility = Visibility.Collapsed;
    }

    private void RenderBackendPath()
    {
        BackendPathText.Text = $"{_backend.Location.DisplayName}\n{_backend.Location.FileName}\n" +
            "Working directory: " + _backend.Location.WorkingDirectory;
    }

    private static string SelectedTag(ComboBox box, string fallback)
    {
        return (box.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? fallback;
    }

    private string Numeric(double value)
    {
        if (double.IsNaN(value) || double.IsInfinity(value))
        {
            throw new ArgumentException("Scale or quality value is invalid.");
        }
        return value.ToString("0.##", CultureInfo.InvariantCulture);
    }

    private static bool BoolProperty(JsonElement element, string name)
    {
        return element.TryGetProperty(name, out JsonElement value) && value.ValueKind == JsonValueKind.True;
    }

    private static long Int64Property(JsonElement element, string name)
    {
        return element.TryGetProperty(name, out JsonElement value) && value.TryGetInt64(out long result)
            ? result
            : 0;
    }

    private static string StringProperty(JsonElement element, string name, string fallback)
    {
        return element.TryGetProperty(name, out JsonElement value) && value.ValueKind == JsonValueKind.String
            ? value.GetString() ?? fallback
            : fallback;
    }

    private static string PackText(JsonElement element, string fallback)
    {
        // Pack names/descriptions are plain English strings since 0.8.12;
        // older backends sent {"en-US": ..., "zh-CN": ...} objects, which
        // are still accepted here so mixed versions keep working.
        if (element.ValueKind == JsonValueKind.String)
        {
            return element.GetString() ?? fallback;
        }
        if (element.ValueKind == JsonValueKind.Object)
        {
            if (element.TryGetProperty("en-US", out JsonElement english) &&
                english.ValueKind == JsonValueKind.String)
            {
                return english.GetString() ?? fallback;
            }
            foreach (JsonProperty property in element.EnumerateObject())
            {
                if (property.Value.ValueKind == JsonValueKind.String)
                {
                    return property.Value.GetString() ?? fallback;
                }
            }
        }
        return fallback;
    }
}
