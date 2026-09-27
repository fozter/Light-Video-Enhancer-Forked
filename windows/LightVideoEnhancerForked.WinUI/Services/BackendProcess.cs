using System.ComponentModel;
using System.Diagnostics;
using System.Text;
using System.Text.Json;

namespace LightVideoEnhancerForked_WinUI.Services;

public sealed record BackendProgress(string Stage, long Current, long Total);

public sealed record BackendCommandResult(int ExitCode, string StandardOutput, string StandardError);

public sealed record BackendLocation(
    string FileName,
    string WorkingDirectory,
    IReadOnlyList<string> PrefixArguments,
    string DisplayName);

/// <summary>
/// Runs the existing Python processing core out of process.  The protocol is
/// deliberately line based so the WinUI frontend never imports Python or CUDA
/// into its own process.
/// </summary>
public sealed class BackendProcess : IDisposable
{
    private const string ProgressPrefix = "__LVE_PROGRESS__";
    private readonly object _sync = new();
    private Process? _process;
    private int _busy;

    public BackendProcess()
    {
        Location = ResolveBackend();
    }

    public BackendLocation Location { get; }

    public bool IsRunning => Volatile.Read(ref _busy) != 0;

    public event Action<string>? OutputReceived;

    public event Action<BackendProgress>? ProgressReceived;

    public async Task<BackendCommandResult> RunAsync(IEnumerable<string> arguments)
    {
        EnterBusy();
        try
        {
            using Process process = CreateProcess(arguments);
            SetCurrent(process);
            if (!process.Start())
            {
                throw new InvalidOperationException("Unable to start the video processing backend.");
            }

            StringBuilder stdoutBuffer = new();
            StringBuilder stderrBuffer = new();
            Task stdout = PumpAsync(process.StandardOutput, false, stdoutBuffer);
            Task stderr = PumpAsync(process.StandardError, true, stderrBuffer);
            await process.WaitForExitAsync();
            try
            {
                await Task.WhenAll(stdout, stderr);
            }
            catch (Exception ex) when (ex is ObjectDisposedException ||
                ex is InvalidOperationException ||
                ex is IOException ||
                ex is System.Runtime.InteropServices.COMException)
            {
                // The backend now ends itself with os._exit past interpreter
                // teardown, which can tear the redirect pipes mid-drain and
                // fail a trailing read with a WinRT/COM or disposal error
                // ("One of the identified items was in an invalid format").
                // The work is already done and the exit code below stays
                // authoritative; only the unread tail is lost.
            }
            return new BackendCommandResult(
                process.ExitCode, stdoutBuffer.ToString(), stderrBuffer.ToString());
        }
        finally
        {
            SetCurrent(null);
            Volatile.Write(ref _busy, 0);
        }
    }

    public async Task<BackendCommandResult> QueryAsync(params string[] arguments)
    {
        EnterBusy();
        try
        {
            using Process process = CreateProcess(arguments);
            SetCurrent(process);
            if (!process.Start())
            {
                throw new InvalidOperationException("Unable to start the capability detection backend.");
            }

            Task<string> stdout = process.StandardOutput.ReadToEndAsync();
            Task<string> stderr = process.StandardError.ReadToEndAsync();
            await process.WaitForExitAsync();
            return new BackendCommandResult(
                process.ExitCode, await stdout, await stderr);
        }
        finally
        {
            SetCurrent(null);
            Volatile.Write(ref _busy, 0);
        }
    }

    public async Task CancelAsync(TimeSpan? gracefulTimeout = null)
    {
        Process? process;
        lock (_sync)
        {
            process = _process;
        }

        if (process is null || process.HasExited)
        {
            return;
        }

        try
        {
            await process.StandardInput.WriteLineAsync("cancel");
            await process.StandardInput.FlushAsync();
        }
        catch (ObjectDisposedException)
        {
            // The run already finished and disposed its process handle
            // between the HasExited check above and this write. (Must come
            // before InvalidOperationException: it derives from it.)
            return;
        }
        catch (InvalidOperationException)
        {
            return;
        }
        catch (IOException)
        {
            return;
        }

        TimeSpan timeout = gracefulTimeout ?? TimeSpan.FromSeconds(12);
        using CancellationTokenSource timeoutSource = new(timeout);
        try
        {
            await process.WaitForExitAsync(timeoutSource.Token);
        }
        catch (OperationCanceledException)
        {
            try
            {
                if (!process.HasExited)
                {
                    process.Kill(entireProcessTree: true);
                }
            }
            catch (InvalidOperationException)
            {
                // Exited concurrently with the kill; nothing to do.
            }
            catch (Win32Exception)
            {
                // Access or state changed under us; the run is over either way.
            }
        }
    }

    private void EnterBusy()
    {
        if (Interlocked.CompareExchange(ref _busy, 1, 0) != 0)
        {
            throw new InvalidOperationException("The backend is already running another task.");
        }
    }

    private void SetCurrent(Process? process)
    {
        lock (_sync)
        {
            _process = process;
        }
    }

    private Process CreateProcess(IEnumerable<string> arguments)
    {
        ProcessStartInfo startInfo = new()
        {
            FileName = Location.FileName,
            WorkingDirectory = Location.WorkingDirectory,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };
        startInfo.Environment["PYTHONUTF8"] = "1";
        startInfo.Environment["PYTHONIOENCODING"] = "utf-8";
        startInfo.Environment["PYTHONUNBUFFERED"] = "1";
        foreach (string argument in Location.PrefixArguments.Concat(arguments))
        {
            startInfo.ArgumentList.Add(argument);
        }
        return new Process { StartInfo = startInfo, EnableRaisingEvents = true };
    }

    private async Task PumpAsync(StreamReader reader, bool errorStream, StringBuilder? collector)
    {
        while (await reader.ReadLineAsync() is { } line)
        {
            if (TryParseProgress(line, out BackendProgress? progress) && progress is not null)
            {
                try
                {
                    ProgressReceived?.Invoke(progress);
                }
                catch
                {
                    // UI event handlers must not interrupt video processing.
                }
                continue;
            }

            collector?.AppendLine(line);
            try
            {
                OutputReceived?.Invoke(errorStream ? "[STDERR] " + line : line);
            }
            catch
            {
                // UI event handlers must not interrupt video processing.
            }
        }
    }

    private static bool TryParseProgress(string line, out BackendProgress? progress)
    {
        progress = null;
        if (!line.StartsWith(ProgressPrefix, StringComparison.Ordinal))
        {
            return false;
        }

        try
        {
            using JsonDocument document = JsonDocument.Parse(line[ProgressPrefix.Length..]);
            JsonElement root = document.RootElement;
            // Byte totals exceed Int32 for multi-GiB packs (SeedVR2 3B is
            // 3.9 GB); GetInt32 would throw FormatException and fault the
            // drain pump, so counters are 64-bit end to end.
            progress = new BackendProgress(
                root.GetProperty("stage").GetString() ?? "Processing",
                GetCounter(root, "current"),
                GetCounter(root, "total"));
        }
        catch (Exception ex) when (ex is JsonException || ex is FormatException ||
            ex is InvalidOperationException || ex is OverflowException)
        {
            progress = new BackendProgress("Processing", 0, 0);
        }
        return true;
    }

    private static long GetCounter(JsonElement root, string property)
    {
        if (root.TryGetProperty(property, out JsonElement value) &&
            value.ValueKind == JsonValueKind.Number &&
            value.TryGetInt64(out long wide) && wide >= 0)
        {
            return wide;
        }
        return 0;
    }

    private static BackendLocation ResolveBackend()
    {
        string? overridden = Environment.GetEnvironmentVariable("LVE_BACKEND");
        if (!string.IsNullOrWhiteSpace(overridden) && File.Exists(overridden))
        {
            return new BackendLocation(
                Path.GetFullPath(overridden),
                Path.GetDirectoryName(Path.GetFullPath(overridden))!,
                Array.Empty<string>(),
                "External backend · " + Path.GetFileName(overridden));
        }

        List<string> baseDirectories = [AppContext.BaseDirectory];
        string? processDirectory = Path.GetDirectoryName(Environment.ProcessPath);
        if (!string.IsNullOrWhiteSpace(processDirectory))
        {
            baseDirectories.Insert(0, processDirectory);
        }
        string[] executableNames =
        [
            "LightVideoEnhancerForked-Backend.exe",
            "LightVideoEnhancerForked-Backend-Win10-11-x64.exe",
        ];
        foreach (string baseDirectory in baseDirectories.Distinct(StringComparer.OrdinalIgnoreCase))
        {
            foreach (string name in executableNames)
            {
                string candidate = Path.Combine(baseDirectory, name);
                if (File.Exists(candidate))
                {
                    return new BackendLocation(
                        candidate, baseDirectory, Array.Empty<string>(),
                        "Portable backend · " + name);
                }
            }
        }

        string? projectRoot = baseDirectories.Select(FindProjectRoot).FirstOrDefault(root => root is not null);
        string python = Environment.GetEnvironmentVariable("LVE_PYTHON") ?? "python.exe";
        if (projectRoot is not null)
        {
            string virtualPython = Path.Combine(projectRoot, ".venv", "Scripts", "python.exe");
            if (File.Exists(virtualPython))
            {
                python = virtualPython;
            }
        }
        return new BackendLocation(
            python,
            projectRoot ?? Environment.CurrentDirectory,
            ["-m", "light_video_enhancer_forked"],
            "Development backend · " + python);
    }

    private static string? FindProjectRoot(string start)
    {
        DirectoryInfo? directory = new(start);
        for (int depth = 0; directory is not null && depth < 14; depth++, directory = directory.Parent)
        {
            if (File.Exists(Path.Combine(directory.FullName, "pyproject.toml")) &&
                Directory.Exists(Path.Combine(directory.FullName, "light_video_enhancer_forked")))
            {
                return directory.FullName;
            }
        }
        return null;
    }

    public void Dispose()
    {
        Process? process;
        lock (_sync)
        {
            process = _process;
            _process = null;
        }
        if (process is not null)
        {
            try
            {
                if (!process.HasExited)
                {
                    process.Kill(entireProcessTree: true);
                }
            }
            catch (InvalidOperationException)
            {
            }
            finally
            {
                process.Dispose();
            }
        }
    }
}
